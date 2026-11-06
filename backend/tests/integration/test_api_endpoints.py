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
