"""Unit tests for Planetary Protection Special-Region Geofencing and Scout Reconnaissance.

Verifies:
- Accurate categorization: Official restricted zone (red), Candidate sensitive region (amber),
  Demonstration scenario (purple dashed).
- Route intersection checking: Official restricted zones set human_route_approved=False and issue
  mandatory reroute violations.
- Candidate sensitive regions issue advisory warnings and recommend sterile robotic scout reconnaissance.
- Scout Rover reconnaissance dispatch API generates validated simulation payloads with explicit disclaimers.
- Provenance and dataset IDs (CRISM, HiRISE) are preserved without fabrication.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.data.planetary_protection import (
    get_all_special_regions,
)
from backend.app.main import app
from backend.app.routing.geofence import evaluate_route_geofence
from backend.app.schemas.planetary_protection import (
    HumanAccessStatus,
    SpecialRegionClassification,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_01_catalog_categories_and_provenance():
    zones = get_all_special_regions()
    assert len(zones) >= 3

    # Check that each category is represented
    classifications = {z.classification for z in zones}
    assert SpecialRegionClassification.OFFICIAL_RESTRICTED_ZONE in classifications
    assert SpecialRegionClassification.CANDIDATE_SENSITIVE_REGION in classifications
    assert SpecialRegionClassification.DEMONSTRATION_SCENARIO in classifications

    # Check official restricted zone
    official = next(z for z in zones if z.classification == SpecialRegionClassification.OFFICIAL_RESTRICTED_ZONE)
    assert official.human_access_status == HumanAccessStatus.STRICTLY_PROHIBITED
    assert official.boundary_color == "#ef4444"
    assert "CRISM" in official.dataset
    assert official.scout_rover_eligible is True

    # Check candidate region
    candidate = next(z for z in zones if z.classification == SpecialRegionClassification.CANDIDATE_SENSITIVE_REGION)
    assert candidate.human_access_status == HumanAccessStatus.ASSESSMENT_REQUIRED
    assert candidate.boundary_color == "#f59e0b"

    # Check demo zone
    demo = next(z for z in zones if z.classification == SpecialRegionClassification.DEMONSTRATION_SCENARIO)
    assert demo.human_access_status == HumanAccessStatus.SIMULATED_EXERCISE
    assert demo.stroke_style == "dashed"


def test_02_route_outside_all_zones():
    # Traverses well outside all designated zones
    safe_coords = [
        [77.3000, 18.3000],
        [77.3100, 18.3100],
        [77.3200, 18.3200],
    ]
    assessment = evaluate_route_geofence(safe_coords)
    assert assessment.human_route_approved is True
    assert assessment.total_intersections == 0
    assert len(assessment.intersected_regions) == 0
    assert assessment.highest_restriction_level == "NONE"
    assert len(assessment.policy_violations) == 0


def test_03_route_intersecting_official_restricted_zone():
    # Pierces the Western Delta Scarp zone: [77.4280, 18.4500] to [77.4450, 18.4600]
    piercing_coords = [
        [77.4200, 18.4550],  # outside west
        [77.4360, 18.4550],  # inside Western Delta Scarp zone
        [77.4500, 18.4550],  # outside east
    ]
    assessment = evaluate_route_geofence(piercing_coords)

    # Must fail human route approval
    assert assessment.human_route_approved is False
    assert assessment.total_intersections >= 1
    assert assessment.highest_restriction_level == "OFFICIAL_RESTRICTED"
    assert len(assessment.policy_violations) >= 1
    assert "CRITICAL PLANETARY PROTECTION VIOLATION" in assessment.policy_violations[0]
    assert assessment.alternative_routes_suggested is True

    # Region breakdown
    hit = next((r for r in assessment.intersected_regions if r.region_id == "ppz_jezero_delta_aquifer"), None)
    assert hit is not None
    assert hit.action_required == "REROUTE_MANDATORY"
    assert hit.intersecting_length_meters > 0.0


def test_04_route_intersecting_candidate_sensitive_region():
    # Pierces Séítah candidate zone: [77.4380, 18.4280] to [77.4550, 18.4380]
    candidate_coords = [
        [77.4300, 18.4330],
        [77.4460, 18.4330],  # inside Séítah
        [77.4600, 18.4330],
    ]
    assessment = evaluate_route_geofence(candidate_coords)

    # Candidate alone does NOT block route approval, but issues advisory
    assert assessment.human_route_approved is True
    assert assessment.highest_restriction_level == "CANDIDATE_SENSITIVE"
    assert len(assessment.warnings) >= 1
    assert "PLANETARY PROTECTION ADVISORY" in assessment.warnings[0]
    assert len(assessment.policy_violations) == 0

    hit = next((r for r in assessment.intersected_regions if r.region_id == "ppz_seitah_carbonate_rsl"), None)
    assert hit is not None
    assert hit.action_required == "SCOUT_SURVEY_RECOMMENDED"
    assert hit.scout_dispatch_recommended is True


def test_05_api_list_special_regions(client):
    res = client.get("/api/v1/planetary-protection/zones")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["count"] >= 3
    assert len(data["zones"]) >= 3


def test_06_api_evaluate_traverse(client):
    payload = {
        "coordinates": [
            [77.4200, 18.4550],
            [77.4360, 18.4550],
            [77.4500, 18.4550],
        ]
    }
    res = client.post("/api/v1/planetary-protection/evaluate-route", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["human_route_approved"] is False
    assert data["highest_restriction_level"] == "OFFICIAL_RESTRICTED"


def test_07_api_dispatch_scout_rover_simulation(client):
    payload = {
        "target_region_id": "ppz_seitah_carbonate_rsl",
        "scout_platform": "Ingenuity-Class Aerial Scout",
        "instrument_payload": ["APXS", "SHERLOC Raman"],
    }
    res = client.post("/api/v1/planetary-protection/scout-rover-request", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST"
    assert "MOCK MISSION SIMULATION ONLY" in data["simulation_disclaimer"]
    assert data["target_region_id"] == "ppz_seitah_carbonate_rsl"
    assert "APXS" in data["instrument_payload"]
    assert "SCOUT-SORTIE" in data["recon_mission_id"]
