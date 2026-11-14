from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.app.integrations.ai.orchestration.response_validator import ResponseValidator
from backend.app.integrations.ai.providers.azure_foundry import AzureFoundryProvider
from backend.app.integrations.ai.providers.gemini import GeminiProvider
from backend.app.integrations.ai.schemas.models import (
    ModelComparisonRequest,
    RouteExplanationRequest,
)
from backend.app.integrations.ai.services.mars_science_assistant import get_science_assistant
from backend.app.integrations.google_cloud.cost_controls import CloudCostManager
from backend.app.integrations.google_cloud.jobs.job_registry import get_job_registry
from backend.app.integrations.google_cloud.scheduler.scheduler_service import get_scheduler_service
from backend.app.integrations.google_cloud.storage.gcs_storage import GCSStorageAdapter
from backend.app.integrations.google_cloud.storage.local_storage import LocalStorageAdapter
from backend.app.integrations.google_cloud.storage.storage_factory import get_storage_adapter
from backend.app.main import app

client = TestClient(app)


class TestLocalStorageAdapter:
    """Verifies the LocalStorageAdapter adheres to BaseStorageAdapter contract."""

    def test_bucket_initialization_and_layout(self, tmp_path):
        adapter = LocalStorageAdapter(root_dir=tmp_path / "gcs_local", bucket_name="marspath-data")
        status = asyncio.run(adapter.get_status())
        assert status.provider == "local_filesystem"
        assert (tmp_path / "gcs_local" / "marspath-data" / "raw" / "nasa").is_dir()
        assert (tmp_path / "gcs_local" / "marspath-data" / "processed").is_dir()
        assert (tmp_path / "gcs_local" / "marspath-data" / "tiles").is_dir()

    def test_upload_download_and_metadata(self, tmp_path):
        adapter = LocalStorageAdapter(root_dir=tmp_path / "gcs_local", bucket_name="marspath-data")
        sample_data = b"Mars 2020 Perseverance Rover Science Telemetry"
        obj_name = "raw/nasa/test_telemetry.bin"

        meta = asyncio.run(
            adapter.upload_bytes(
                object_name=obj_name,
                data=sample_data,
                content_type="application/octet-stream",
                source_id="pds_geosciences",
                metadata={"sol": "1000", "instrument": "MEDA"},
            )
        )
        assert meta.object_name == obj_name
        assert meta.size_bytes == len(sample_data)
        assert meta.sha256_hash is not None
        assert meta.source_id == "pds_geosciences"
        assert meta.custom_metadata["sol"] == "1000"

        # Check existence
        assert asyncio.run(adapter.exists(obj_name)) is True
        assert asyncio.run(adapter.exists("nonexistent/key.txt")) is False

        # Download and verify
        downloaded = asyncio.run(adapter.download_bytes(obj_name))
        assert downloaded == sample_data

        # Verify retrieved metadata
        retrieved_meta = asyncio.run(adapter.get_metadata(obj_name))
        assert retrieved_meta is not None
        assert retrieved_meta.sha256_hash == meta.sha256_hash

        # List objects
        listed = asyncio.run(adapter.list_objects(prefix="raw/nasa"))
        assert any(obj.object_name == obj_name for obj in listed)

        # Signed URL simulation
        signed_url = asyncio.run(adapter.generate_signed_url(obj_name, expiration_seconds=900))
        assert obj_name in signed_url

        # Delete
        assert asyncio.run(adapter.delete_object(obj_name)) is True
        assert asyncio.run(adapter.exists(obj_name)) is False

    def test_gcs_fallback_when_credentials_missing(self, tmp_path, monkeypatch):
        # Ensure credentials aren't set
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        monkeypatch.setenv("GCS_BUCKET", "")
        monkeypatch.setenv("MARSPATH_GCS_ENABLED", "false")

        adapter = GCSStorageAdapter(bucket_name="test-bucket", local_fallback_root=tmp_path / "fallback", is_enabled=False)
        assert adapter.is_fallback_mode is True
        status = asyncio.run(adapter.get_status())
        assert status.provider == "local_filesystem"

        # Verify factory returns valid adapter
        factory_adapter = get_storage_adapter()
        assert factory_adapter is not None


class TestCloudRunJobs:
    """Verifies all 8 Cloud Run Jobs execute and record execution history."""

    def test_all_eight_jobs_registered(self):
        registry = get_job_registry()
        job_names = {j.name for j in registry.list_jobs()}
        expected_jobs = {
            "nasa_catalog_sync",
            "planetary_imagery_processor",
            "dem_processor",
            "meda_processor",
            "themis_processor",
            "crism_processor",
            "provenance_validator",
            "imagery_tile_generator",
        }
        assert expected_jobs.issubset(job_names), f"Missing jobs: {expected_jobs - job_names}"

    def test_job_execution_dry_run(self):
        registry = get_job_registry()

        # Job 1: Catalog sync
        res1 = asyncio.run(registry.run_job("nasa_catalog_sync", {"max_items": 5}))
        assert res1.status == "SUCCESS"
        assert res1.items_processed >= 0

        # Job 2: Planetary imagery processor
        res2 = asyncio.run(registry.run_job("planetary_imagery_processor", {"generate_overviews": True}))
        assert res2.status == "SUCCESS"
        assert len(res2.output_artifacts) > 0

        # Job 3: DEM processor
        res3 = asyncio.run(registry.run_job("dem_processor", {"compute_slope": True, "compute_roughness": True}))
        assert res3.status == "SUCCESS"

        # Job 4: MEDA processor
        res4 = asyncio.run(registry.run_job("meda_processor", {"sols": [1000, 1001]}))
        assert res4.status == "SUCCESS"

        # Job 5: THEMIS processor
        res5 = asyncio.run(registry.run_job("themis_processor", {"region": "Jezero"}))
        assert res5.status == "SUCCESS"

        # Job 6: CRISM processor
        res6 = asyncio.run(registry.run_job("crism_processor", {"minerals": ["Fe/Mg-smectite", "carbonate"]}))
        assert res6.status == "SUCCESS"

        # Job 7: Provenance validator
        res7 = asyncio.run(registry.run_job("provenance_validator", {"strict": True}))
        assert res7.status == "SUCCESS"

        # Job 8: Imagery tile generator
        res8 = asyncio.run(registry.run_job("imagery_tile_generator", {"zoom_levels": [0, 1, 2]}))
        assert res8.status == "SUCCESS"

        # Verify history recorded
        history = registry.get_history()
        assert len(history) >= 8


class TestCloudSchedulerAndCost:
    """Verifies scheduler definitions and budget enforcement."""

    def test_cloud_scheduler_service(self):
        scheduler = get_scheduler_service()
        schedules = scheduler.list_schedules()
        assert len(schedules) >= 4
        sched_names = [s.name for s in schedules]
        assert any("daily-catalog-sync" in name for name in sched_names)

        spec = scheduler.get_schedule("marspath-daily-catalog-sync")
        assert spec is not None
        assert spec.cron_expression == "0 4 * * *"

    def test_cost_controls(self):
        manager = CloudCostManager()
        report = manager.get_cost_report()
        assert report.cloud_cost_tracking_enabled is True
        assert report.storage_quota_mb > 0
        assert "ZERO_COST_LOCAL_SANDBOX" in report.billing_protection_mode
        assert len(report.budget_alerts) >= 3


class TestMarsScienceCopilotAndAIProviders:
    """Verifies Gemini, Azure Foundry, and Assistant orchestration."""

    def test_gemini_fallback_response(self):
        provider = GeminiProvider()
        resp = asyncio.run(provider.chat("What is the significance of the carbonate deposits in Jezero crater?"))
        assert "Google Gemini" in resp.provider_used
        assert len(resp.scientific_citations) > 0
        assert len(resp.reply) > 0
        assert resp.uncertainty_notice is not None

    def test_azure_foundry_comparative_response(self):
        provider = AzureFoundryProvider()
        resp = asyncio.run(provider.chat("Analyze the traversability risk of Jezero delta front."))
        assert "Azure" in resp.provider_used
        assert len(resp.reply) > 0

    def test_mars_science_assistant_route_explanation(self):
        assistant = get_science_assistant()
        req = RouteExplanationRequest(
            route_id="primary",
            question="Why was this route corridor selected and what terrain risk trade-offs were made?",
        )
        resp = asyncio.run(assistant.explain_route(req))
        assert resp.route_id == "primary"
        assert resp.total_distance_km >= 0.0
        assert len(resp.explanation) > 0

    def test_model_comparison(self):
        assistant = get_science_assistant()
        req = ModelComparisonRequest(
            question="Compare rover navigation through sand ripples versus bedrock on Mars.",
        )
        resp = asyncio.run(assistant.compare_models(req))
        assert resp.gemini_response is not None
        assert "Gemini" in resp.gemini_response.provider_used
        assert len(resp.comparison_summary) > 0

    def test_uncertainty_caveat_enforcement(self):
        caveat = ResponseValidator.get_mandatory_caveat()
        assert "explanatory hypothesis" in caveat
        grounded = ResponseValidator.validate_route_explanation("The rover traverses safely.", "route_01", 1.25)
        assert "1.25" in grounded


class TestCloudAndAIApiEndpoints:
    """Verifies FastAPI endpoints mounted on /api/v1/cloud and /api/v1/ai."""

    def test_cloud_status_endpoint(self):
        res = client.get("/api/v1/cloud/status")
        assert res.status_code == 200
        data = res.json()
        assert "gcs_status" in data
        assert "cloud_run_status" in data
        assert "cost_report" in data
        assert "cloud_features" in data

    def test_cloud_storage_status(self):
        res = client.get("/api/v1/cloud/storage/status")
        assert res.status_code == 200
        data = res.json()
        assert "provider" in data
        assert "total_objects" in data

    def test_cloud_jobs_status(self):
        res = client.get("/api/v1/cloud/jobs/status")
        assert res.status_code == 200
        data = res.json()
        assert "jobs" in data
        assert len(data["jobs"]) >= 8

    def test_run_cloud_job_endpoint(self):
        res = client.post("/api/v1/cloud/jobs/run/nasa_catalog_sync", json={"max_items": 3})
        assert res.status_code == 200
        data = res.json()
        assert data["job_name"] == "nasa_catalog_sync"
        assert data["status"] == "SUCCESS"

    def test_cloud_costs_endpoint(self):
        res = client.get("/api/v1/cloud/costs")
        assert res.status_code == 200
        data = res.json()
        assert "storage_quota_mb" in data
        assert "billing_protection_mode" in data

    def test_ai_status_endpoint(self):
        res = client.get("/api/v1/ai/status")
        assert res.status_code == 200
        data = res.json()
        assert "active_provider" in data
        assert "available_providers" in data

    def test_ai_providers_endpoint(self):
        res = client.get("/api/v1/ai/providers")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        provider_ids = [p["provider_id"] for p in data]
        assert "gemini" in provider_ids
        assert "azure_foundry" in provider_ids

    def test_ai_mars_science_chat_endpoint(self):
        res = client.post(
            "/api/v1/ai/mars-science/chat",
            json={
                "message": "Explain the significance of clay minerals in Jezero delta.",
                "provider": "gemini",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "Google Gemini" in data["provider_used"]
        assert len(data["reply"]) > 0
        assert len(data["scientific_citations"]) > 0

    def test_ai_route_explain_endpoint(self):
        res = client.post(
            "/api/v1/ai/route/explain",
            json={
                "route_id": "primary",
                "question": "Why was this corridor chosen over steep craters?",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["route_id"] == "primary"
        assert "explanation" in data
        assert data["total_distance_km"] >= 0.0

    def test_ai_models_compare_endpoint(self):
        res = client.post(
            "/api/v1/ai/models/compare",
            json={
                "question": "Evaluate the risk of Martian dust accumulation on solar arrays vs RTG systems.",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "gemini_response" in data
        assert "comparison_summary" in data
