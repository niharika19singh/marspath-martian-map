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

    primary = data["routes"][0]
    assert primary["summary"]["total_distance_meters"] > 0
    assert primary["summary"]["max_slope_deg"] <= 20.0
    assert primary["geometry"]["type"] == "LineString"
    assert len(primary["geometry"]["coordinates"]) > 2
    # Check that GeoJSON coordinate is [lon, lat, elevation]
    coord0 = primary["geometry"]["coordinates"][0]
    assert len(coord0) == 3
    assert 77.0 <= coord0[0] <= 78.0  # East longitude
    assert 18.0 <= coord0[1] <= 19.0  # Planetocentric latitude


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
