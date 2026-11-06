from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["planetary_target"] == "Mars"
    assert "data_readiness" in data
    assert data["data_readiness"]["crs"] == "IAU2000:49900"
    assert "real_data_validation_status" in data["data_readiness"]
    assert data["data_readiness"]["data_mode"] in (
        "synthetic_test_fixture",
        "synthetic_fallback",
        "real",
        "real_official_endpoint_unverified_checksum",
        "real_unverified_source",
    )


def test_layers_endpoint():
    response = client.get("/api/v1/layers")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 4
    layer_ids = [lyr["id"] for lyr in data["layers"]]
    assert "mars_elevation_jezero" in layer_ids
    assert "mars_slope_degrees" in layer_ids
    assert "mars_roughness_tri" in layer_ids
    assert "mars_trek_imagery_basemap" in layer_ids


def test_data_status_endpoint():
    response = client.get("/api/v1/data/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["crs"]["identifier"] == "IAU2000:49900"
    assert data["active_pilot_region"] == "Jezero Crater, Mars"
    assert data["valid_data_fraction"] > 0.95
    assert len(data["configured_products"]) > 0
    assert "hirise_enabled" in data
    assert "hirise_loaded" in data
    assert "hirise_status" in data


def test_route_plan_success():
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
        "mode": "balanced",
        "constraints": {
            "max_slope_deg": 20.0,
            "max_roughness": 0.85,
            "avoid_unobserved_terrain": True,
        },
        "num_alternatives": 2,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["mission_id"].startswith("mission_")
    assert len(data["routes"]) == 2
    assert data["source_selection"] is not None
    assert data["source_selection"]["single_source_invariant_enforced"] is True
    assert data["source_selection"]["hirise_selected"] is False

    primary = data["routes"][0]
    assert primary["summary"]["total_distance_meters"] > 0
    assert primary["summary"]["max_slope_deg"] <= 20.0
    assert "hazard_exposure_meters" in primary["summary"]
    assert "risk_category" in primary["summary"]
    assert primary["summary"]["risk_category"] in ("nominal", "moderate", "high")
    assert primary["geometry"]["type"] == "LineString"
    assert len(primary["geometry"]["coordinates"]) > 2
    # Check that GeoJSON coordinate is [lon, lat, elevation]
    coord0 = primary["geometry"]["coordinates"][0]
    assert len(coord0) == 3
    assert 77.0 <= coord0[0] <= 78.0  # East longitude
    assert 18.0 <= coord0[1] <= 19.0  # Planetocentric latitude

    # Check that every route alternative includes a structured Terrain Evidence & Route Confidence Passport
    for route_item in data["routes"]:
        assert "evidence_passport" in route_item
        passport = route_item["evidence_passport"]
        assert passport is not None
        assert passport["schema_version"] == "1.0.0"
        assert passport["quality_tier"] in ("high", "moderate", "low", "unverified")
        assert isinstance(passport["tier_explanation"], str) and len(passport["tier_explanation"]) > 10
        assert "source" in passport
        assert "coverage" in passport
        assert "resolution_assessment" in passport
        assert "known_limitations" in passport
        assert "segments" in passport
        assert len(passport["segments"]) == len(route_item["geometry"]["coordinates"]) - 1


def test_openapi_exposes_evidence_passport_schemas():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    for model_name in [
        "RouteEvidencePassport",
        "SourceEvidence",
        "CoverageEvidence",
        "ResolutionAssessment",
        "RouteSegment",
        "EvidenceQualityTier",
        "RobustnessConfig",
        "RouteRobustnessAssessment",
        "BaselineRouteRobustness",
        "RobustnessScenarioResult",
        "ScenarioBaselineRouteResult",
        "UncertaintyAssumptions",
        "TerrainSourceSelectionReport",
    ]:
        assert model_name in schemas, f"Missing OpenAPI schema: {model_name}"


def test_route_plan_with_robustness_stress_testing():
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
        "mode": "balanced",
        "num_alternatives": 2,
        "robustness_config": {
            "enabled": True,
            "vertical_sigma_m": 1.5,
            "correlation_length_m": 400.0,
            "scenario_count": 3,
            "seed": 42,
            "cost_regret_threshold_fraction": 0.05,
        },
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["robustness_assessment"] is not None
    rob = data["robustness_assessment"]
    assert rob["enabled"] is True
    assert rob["model_name"] == "spatially_correlated_gaussian_elevation_perturbation"
    assert rob["requested_scenario_count"] == 3
    assert rob["completed_scenario_count"] + rob["failed_scenario_count"] == 3
    assert len(rob["scenario_results"]) == 3
    assert len(rob["baseline_route_assessments"]) == len(data["routes"])
    assert (
        rob["scientific_disclaimer"]
        == "Results describe route stability under the specified hypothetical terrain perturbation model. They do not establish the actual probability of rover failure or mission success."
    )


def test_route_plan_robustness_enabled_without_parameters_rejected():
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "robustness_config": {
            "enabled": True,
        },
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422


def test_route_plan_unsupported_crs():
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "EPSG:4326",  # Earth WGS84 must be rejected
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422


def test_route_plan_out_of_bounds():
    payload = {
        "start": {"lon": 150.0, "lat": 10.0},  # Outside Jezero pilot
        "destination": {"lon": 77.44, "lat": 18.42},
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422


def test_route_plan_invalid_constraints():
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "constraints": {
            "max_slope_deg": 65.0,  # Exceeds 45.0 limit
        },
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422


def test_cors_preflight_production_vercel_origin():
    """Verifies that CORS preflight from production frontend origin returns 200 with required headers."""
    response = client.options(
        "/api/v1/routes/plan",
        headers={
            "Origin": "https://marspath.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://marspath.vercel.app"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


def test_cors_preflight_localhost_origin():
    """Verifies that CORS preflight from local development frontend origin returns 200."""
    response = client.options(
        "/api/v1/routes/plan",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_route_plan_search_radius_exceeded(monkeypatch):
    """Verifies that requests exceeding MAX_SEARCH_RADIUS_METERS raise 413 ComputationalBoundExceededError."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "MAX_SEARCH_RADIUS_METERS", 500.0)

    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 413
    data = response.json()
    assert "exceeds configured maximum search radius" in str(data)


def test_route_plan_routing_timeout_error_returns_504(monkeypatch):
    """Verifies that routing timeout raises RoutingTimeoutError returning HTTP 504 Gateway Timeout."""
    from backend.app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "ROUTING_TIMEOUT_SECONDS", 0.0001)

    def mock_astar(*args, **kwargs):
        from backend.app.core.exceptions import RoutingTimeoutError

        raise RoutingTimeoutError("A* computation timed out.", timeout_seconds=0.0001, elapsed_seconds=0.0002)

    monkeypatch.setattr("backend.app.services.route_service.astar_search", mock_astar)

    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 504
    data = response.json()
    assert "timeout" in str(data).lower()


def test_config_settings_port_and_env_loading(monkeypatch):
    """Verifies that Settings respects PORT fallback, MARSPATH_PORT, and production environment."""
    from backend.app.core.config import Settings

    monkeypatch.setenv("PORT", "10000")
    monkeypatch.delenv("MARSPATH_PORT", raising=False)
    monkeypatch.setenv("MARSPATH_ENV", "production")

    cfg = Settings()
    assert cfg.PORT == 10000
    assert cfg.ENV == "production"

    monkeypatch.setenv("MARSPATH_PORT", "9000")
    cfg2 = Settings()
    # If both PORT and MARSPATH_PORT are set, it parses properly as int
    assert cfg2.PORT in (9000, 10000)


def test_runtime_dem_provisioning_and_tamper_detection(tmp_path, monkeypatch):
    """Verifies idempotent provisioning reuse and tamper detection when a file is modified."""
    import json

    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    from backend.app.data.ingestion import (
        _validate_existing_local_dem,
        compute_file_sha256,
        provision_runtime_dem,
    )

    dem_file = tmp_path / "test_mola.tif"
    sidecar_file = tmp_path / "test_mola.tif.provenance.json"

    # Write a valid test GeoTIFF
    arr = np.full((50, 50), -2500.0, dtype=np.float32)
    transform = from_origin(77.20, 18.65, 0.003, 0.003)
    with rasterio.open(
        dem_file,
        "w",
        driver="GTiff",
        height=50,
        width=50,
        count=1,
        dtype=np.float32,
        crs="+proj=longlat +a=3396190 +b=3396190 +no_defs",
        transform=transform,
        nodata=-32768.0,
    ) as dst:
        dst.write(arr, 1)

    file_sha = compute_file_sha256(dem_file)
    with open(sidecar_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "local_file_path": str(dem_file),
                "local_file_sha256": file_sha,
                "validation_status": "official_endpoint_retrieved_checksum_unverified",
                "source_checksum_verified": False,
            },
            f,
        )

    monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
    monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")

    # 1. Reuse existing valid DEM
    is_valid, reason, sidecar = _validate_existing_local_dem(dem_file)
    assert is_valid is True
    res = provision_runtime_dem(dem_path=str(dem_file), use_real_dem=True, force=False)
    assert res["status"] == "already_provisioned_valid"
    assert res["action"] == "reused_existing_valid_dem"

    # 2. Tamper with file
    with open(dem_file, "r+b") as f:
        f.seek(100)
        f.write(b"\x99\x88\x77\x66")

    is_valid_tampered, reason_tampered, _ = _validate_existing_local_dem(dem_file)
    assert is_valid_tampered is False
    assert "sha256_mismatch" in reason_tampered

