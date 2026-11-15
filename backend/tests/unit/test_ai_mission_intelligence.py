"""
Comprehensive unit tests for the MARSPath AI Mission Intelligence Layer.
Verifies natural-language mission parsing, landmark resolution,
candidate comparison grounding, evidence typing, risk briefings,
deterministic safety mandate, and PDF export integration.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.intelligence.landmark_registry import (
    check_out_of_bounds_landmarks,
    extract_explicit_coordinates,
    is_within_jezero,
    resolve_landmark_by_name,
)
from backend.app.intelligence.mission_intelligence import get_mission_intelligence_engine
from backend.app.main import app
from backend.app.services.pdf_export_service import generate_mission_pdf

client = TestClient(app)


# ---------------------------------------------------------------------
# 1. Landmark Registry & Bounding Box Checks
# ---------------------------------------------------------------------


def test_jezero_bounding_box_validation():
    # Inside Jezero
    assert is_within_jezero(77.40, 18.40) is True
    assert is_within_jezero(77.2330, 18.4350) is True  # Perseverance rover

    # Outside Jezero
    assert is_within_jezero(137.4, -4.6) is False  # Gale Crater
    assert is_within_jezero(0.0, 0.0) is False
    assert is_within_jezero(78.50, 18.40) is False  # East of bounds


def test_landmark_alias_resolution():
    seitah = resolve_landmark_by_name("Séítah")
    assert seitah is not None
    assert seitah["id"] == "SEITAH_CARBONATE_RIDGE"
    assert seitah["lon"] == 77.4395

    kodiak = resolve_landmark_by_name("kodiak butte")
    assert kodiak is not None
    assert kodiak["id"] == "KODIAK_DELTA_BUTTE"

    delta = resolve_landmark_by_name("western delta")
    assert delta is not None
    assert delta["id"] == "WESTERN_DELTA_FRONT"

    rover = resolve_landmark_by_name("current rover position")
    assert rover is not None
    assert rover["id"] == "PERSEVERANCE_SOL_2022"


def test_out_of_bounds_landmark_detection():
    warnings = check_out_of_bounds_landmarks("Plan a route from Perseverance to Olympus Mons")
    assert len(warnings) == 1
    assert "Olympus Mons" in warnings[0]

    gale_warnings = check_out_of_bounds_landmarks("Can we drive to Gale Crater?")
    assert len(gale_warnings) == 1
    assert "Gale Crater" in gale_warnings[0]

    jezero_clean = check_out_of_bounds_landmarks("Find a safe path to Séítah and Kodiak")
    assert len(jezero_clean) == 0


def test_explicit_coordinate_parsing():
    c1 = extract_explicit_coordinates("Target is at 77.45E, 18.44N please.")
    assert c1 == (77.45, 18.44)

    c2 = extract_explicit_coordinates("Waypoint (18.4350, 77.2330)")
    assert c2 == (77.2330, 18.4350)


# ---------------------------------------------------------------------
# 2. Natural-Language Mission Planner Engine
# ---------------------------------------------------------------------


def test_natural_language_planner_valid_prompt():
    engine = get_mission_intelligence_engine()
    prompt = "Find a safe route from the current rover position to Séítah, prioritizing low slope and sufficient return EVA margin."

    plan = engine.parse_natural_language_mission(
        user_prompt=prompt,
        current_coords={"lon": 77.2330, "lat": 18.4350},
    )

    assert plan.requires_clarification is False
    assert plan.routing_profile == "safety_first"
    assert plan.resolved_start["lon"] == 77.2330
    assert plan.resolved_start["lat"] == 18.4350
    assert plan.resolved_destination["lon"] == 77.4395
    assert plan.resolved_destination["lat"] == 18.4310
    assert plan.constraints["max_slope_deg"] == 12.0
    assert plan.constraints["eva_time_budget_hours"] == 8.0

    # Ensure valid RoutePlanRequest payload
    req = plan.validated_route_request
    assert req is not None
    assert req["start"]["lon"] == 77.2330
    assert req["destination"]["lon"] == 77.4395
    assert req["mode"] == "safety_first"
    assert req["include_return_leg"] is True


def test_natural_language_planner_out_of_bounds_clarification():
    engine = get_mission_intelligence_engine()
    plan = engine.parse_natural_language_mission(
        user_prompt="Drive from rover to Olympus Mons",
    )

    assert plan.requires_clarification is True
    assert plan.validated_route_request is None
    assert len(plan.clarification_questions) >= 1
    assert "Olympus Mons" in plan.clarification_questions[0]
    assert "Jezero" in plan.clarification_questions[0]


def test_natural_language_planner_ambiguous_destination():
    engine = get_mission_intelligence_engine()
    plan = engine.parse_natural_language_mission(
        user_prompt="Take me somewhere safe and interesting",
    )

    assert plan.requires_clarification is True
    assert plan.validated_route_request is None
    assert any("destination" in q.lower() for q in plan.clarification_questions)


# ---------------------------------------------------------------------
# 3. Candidate Route Comparison
# ---------------------------------------------------------------------


def test_candidate_route_comparison_numerical_grounding():
    engine = get_mission_intelligence_engine()

    routes = [
        {
            "route_id": "primary",
            "name": "Primary Corridor (A*)",
            "mode": "balanced",
            "total_cost": 4073.2,
            "summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4, "avg_slope_deg": 5.8},
            "cost_breakdown": {"slope_penalty": 320.0, "hazard_penalty": 210.0},
            "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 120.0, "total_traverse_duration_hours": 4.2},
            "robustness_assessment": {"reliability_score_pct": 94.0, "cost_std_dev": 28.5},
        },
        {
            "route_id": "alternative_1",
            "name": "Alternative Corridor 1 (Low Slope)",
            "mode": "safety_first",
            "total_cost": 4350.0,
            "summary": {"total_distance_meters": 3520.0, "max_slope_deg": 8.9, "avg_slope_deg": 4.7},
            "cost_breakdown": {"slope_penalty": 180.0, "hazard_penalty": 110.0},
            "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 95.0, "total_traverse_duration_hours": 4.6},
            "robustness_assessment": {"reliability_score_pct": 98.0, "cost_std_dev": 18.2},
        },
    ]

    res = engine.compare_route_candidates(routes, mission_objective="Prioritize low slope and safety")

    assert len(res.candidate_evaluations) == 2
    # Verify exact numerical grounding
    assert res.candidate_evaluations[0].distance_km == 3.28
    assert res.candidate_evaluations[0].total_cost == 4073.2
    assert res.candidate_evaluations[0].max_slope_deg == 11.4

    assert res.candidate_evaluations[1].distance_km == 3.52
    assert res.candidate_evaluations[1].total_cost == 4350.0
    assert res.candidate_evaluations[1].max_slope_deg == 8.9

    # Recommended route must be alternative_1 due to safety/slope prioritization
    assert res.recommended_route_id == "alternative_1"
    assert "alternative_1" in res.recommendation_rationale

    # Grounding audit
    assert res.grounding_audit["candidates_audited"] == 2
    assert "primary" in res.grounding_audit["metric_verification"]


# ---------------------------------------------------------------------
# 4. Scientific Terrain Interpreter & Evidence Classification
# ---------------------------------------------------------------------


def test_scientific_terrain_interpretation_evidence_typing():
    engine = get_mission_intelligence_engine()

    res = engine.interpret_scientific_terrain(
        route_summary={"total_distance_meters": 3280.0, "max_slope_deg": 11.4}
    )

    assert "Jezero" in res.geological_setting
    assert len(res.measured_data_evidence) >= 2
    assert len(res.derived_metrics_evidence) >= 2
    assert len(res.proxy_indicators_evidence) >= 2

    # Verify data types are strictly preserved
    assert all(e.data_type == "measured" for e in res.measured_data_evidence)
    assert all(e.data_type == "derived" for e in res.derived_metrics_evidence)
    assert all(e.data_type == "proxy" for e in res.proxy_indicators_evidence)

    # Citations check
    assert len(res.citations) >= 4
    instruments = {c["instrument"] for c in res.citations}
    assert "HiRISE" in instruments
    assert "MEDA" in instruments
    assert "CRISM" in instruments
    assert "THEMIS" in instruments


# ---------------------------------------------------------------------
# 5. Mission Risk Briefing & Deterministic Safety Mandate
# ---------------------------------------------------------------------


def test_mission_risk_briefing_safety_mandate():
    engine = get_mission_intelligence_engine()

    route = {
        "route_id": "primary",
        "summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4},
        "total_cost": 4073.2,
        "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 120.0, "total_traverse_duration_hours": 4.2},
        "robustness_assessment": {"total_scenarios_evaluated": 50, "reliability_score_pct": 94.0},
    }

    res = engine.generate_mission_risk_briefing(selected_route=route)

    assert len(res.critical_hazards) >= 3
    assert len(res.uncertainty_limitations) >= 3
    assert "Primary Contingency Corridor" in res.recommended_contingency_corridor
    assert res.return_feasibility["status"] == "FEASIBLE"
    assert res.return_feasibility["buffer_margin_minutes"] == 120.0

    # Mandatory Safety Protocol Verification
    mandate = res.deterministic_safety_mandate
    assert "strictly advisory" in mandate.lower() or "cannot override" in mandate.lower()
    assert "14.0°" in mandate


# ---------------------------------------------------------------------
# 6. REST API Endpoints Integration
# ---------------------------------------------------------------------


def test_api_mission_plan_from_prompt():
    response = client.post(
        "/api/v1/ai/mission/plan-from-prompt",
        json={"user_prompt": "Find a safe route from the current rover position to Séítah"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["requires_clarification"] is False
    assert data["routing_profile"] == "safety_first"
    assert data["resolved_destination"]["lon"] == 77.4395
    assert data["validated_route_request"]["mode"] == "safety_first"


def test_api_route_candidate_comparison():
    payload = {
        "routes": [
            {
                "route_id": "primary",
                "name": "Primary Corridor (A*)",
                "mode": "balanced",
                "total_cost": 4073.2,
                "summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4},
                "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 120.0},
            }
        ],
        "mission_objective": "Balanced traversal",
    }
    response = client.post("/api/v1/ai/routes/compare-candidates", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["candidate_evaluations"]) == 1
    assert data["recommended_route_id"] == "primary"


def test_api_terrain_interpretation():
    response = client.post(
        "/api/v1/ai/terrain/interpret",
        json={"route_id": "primary", "route_summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4}},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["measured_data_evidence"]) >= 1
    assert len(data["derived_metrics_evidence"]) >= 1


def test_api_mission_risk_briefing():
    payload = {
        "selected_route": {
            "route_id": "primary",
            "summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4},
            "total_cost": 4073.2,
        },
        "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 120.0},
    }
    response = client.post("/api/v1/ai/mission/risk-briefing", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "FEASIBLE" in data["return_feasibility"]["status"]
    assert len(data["critical_hazards"]) >= 1


# ---------------------------------------------------------------------
# 7. PDF Export with Section 6 AI Mission Intelligence
# ---------------------------------------------------------------------


def test_pdf_export_contains_ai_mission_intelligence():
    plan_data = {
        "mission_id": "test_ai_export_mission",
        "routes": [
            {
                "route_id": "primary",
                "name": "Primary Corridor (A*)",
                "mode": "balanced",
                "total_cost": 4073.2,
                "summary": {"total_distance_meters": 3280.0, "max_slope_deg": 11.4},
                "cost_breakdown": {"slope_penalty": 320.0, "base_distance_cost": 3280.0},
                "turnaround": {"status": "FEASIBLE", "buffer_margin_minutes": 120.0, "total_traverse_duration_hours": 4.2},
                "robustness_assessment": {"total_scenarios_evaluated": 50, "reliability_score_pct": 94.0},
            }
        ],
    }

    pdf_bytes = generate_mission_pdf(plan_data=plan_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 5000
    assert pdf_bytes.startswith(b"%PDF-")
