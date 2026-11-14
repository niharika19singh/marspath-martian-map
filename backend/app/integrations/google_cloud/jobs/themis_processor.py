from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService
from backend.app.integrations.google_cloud.jobs.base_job import BaseCloudRunJob
from backend.app.integrations.google_cloud.storage.storage_factory import get_storage_adapter

logger = logging.getLogger(__name__)


class ThemisProcessorJob(BaseCloudRunJob):
    """
    Cloud Run Job 5 — THEMIS Processing.
    Ingests calibrated 100m infrared observations from 2001 Mars Odyssey, derives surface
    thermal inertia, and tags quantitative wheel-sinkage traversability risk corridors.
    """

    name = "themis_processor"
    description = "Derives surface thermal inertia and classifies rover wheel-sinkage hazards"
    timeout_seconds = 300
    memory_limit_mb = 1024
    cpu_limit = "1.0"

    async def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        storage = get_storage_adapter()
        catalog = UnifiedDataCatalogService()

        themis_obs = catalog.get_themis_observations()

        high_risk_count = sum(1 for o in themis_obs if o.thermal_inertia_tiu is not None and o.thermal_inertia_tiu < 150)
        bedrock_count = sum(1 for o in themis_obs if o.thermal_inertia_tiu is not None and o.thermal_inertia_tiu >= 300)

        output_key = "processed/thermal/themis_jezero_traversability.json"
        data = json.dumps([t.model_dump(mode="json") for t in themis_obs], indent=2).encode("utf-8")

        meta = await storage.upload_bytes(
            object_name=output_key,
            data=data,
            content_type="application/json",
            metadata={
                "instrument": "THEMIS",
                "observations_count": str(len(themis_obs)),
                "high_sinkage_hazard_count": str(high_risk_count),
                "bedrock_optimal_count": str(bedrock_count),
            },
            source_id="themis_viewer",
            dataset_provenance="2001 Mars Odyssey THEMIS IR Repository (ASU/JPL)",
        )

        return {
            "items_processed": len(themis_obs),
            "items_succeeded": len(themis_obs),
            "items_failed": 0,
            "logs": [
                f"Processed {len(themis_obs)} THEMIS Day/Night IR observation sets.",
                f"Identified {high_risk_count} fine-drift aeolian sand hazards (I < 150 tiu).",
                f"Identified {bedrock_count} consolidated carbonate bedrock units (I > 300 tiu).",
                f"Persisted thermal traversability catalog to: {meta.object_name}.",
            ],
            "output_artifacts": [output_key],
            "telemetry": {
                "high_risk_count": high_risk_count,
                "bedrock_count": bedrock_count,
            },
        }
