"""End-to-end integration tests for Dual-Radius Walk-Back Safety and Planetary Protection Geofencing.

Verifies that POST /api/v1/routes/plan returns real, integrated:
1. dual_envelopes (Rover-Assisted cyan and On-Foot Walk-Back green overlays).
2. walk_back_assessment (distance, duration, remaining EVA margin, bottlenecks).
3. planetary_protection (geofence intersection, human_route_approved flag, violations).
4. special_regions catalog.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_01_route_plan_returns_walkback_and_geofence_intelligence(client):
    payload = {
        "start": {"lon": 77.40, "lat": 18.40},
        "destination": {"lon": 77.44, "lat": 18.42},
        "habitat": {"lon": 77.40, "lat": 18.40},
        "mode": "safety_first",
        "algorithm": "astar",
        "max_eva_hours": 8.0,
    }
    res = client.post("/api/v1/routes/plan", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["status"] == "success"
    assert "dual_envelopes" in data
    assert data["dual_envelopes"] is not None

    dual = data["dual_envelopes"]
    assert dual["rover_assisted"]["color"] == "#00d2ff"
    assert dual["on_foot_walkback"]["color"] == "#00e676"
    assert dual["rover_assisted"]["assumed_speed_km_h"] > dual["on_foot_walkback"]["assumed_speed_km_h"]

    # Check walk_back_assessment on response and primary route
    assert "walk_back_assessment" in data
    assert data["walk_back_assessment"] is not None
    wb = data["walk_back_assessment"]
    assert "on_foot_feasibility" in wb
    feasibility = wb["on_foot_feasibility"]
    assert feasibility["status"] in (
        "SAFE WITHIN CONFIGURED LIMIT",
        "LIMITED MARGIN",
        "WALK-BACK LIMIT EXCEEDED",
    )
    assert feasibility["walk_back_distance_km"] > 0.0
    assert feasibility["walk_back_duration_hours"] > 0.0

    # Check planetary protection
    assert "planetary_protection" in data
    assert data["planetary_protection"] is not None
    pp = data["planetary_protection"]
    assert "human_route_approved" in pp
    assert "special_regions" in data
    assert len(data["special_regions"]) >= 3

    # Check route-level fields
    assert len(data["routes"]) > 0
    primary = data["routes"][0]
    assert primary["walk_back_assessment"] is not None
    assert primary["planetary_protection_assessment"] is not None
