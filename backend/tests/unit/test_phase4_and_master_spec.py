"""Comprehensive regression & integration tests for Phase 2, 3, and 4 Master Deliverables."""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

from backend.app.conditions.climate import (
    evaluate_modelled_climatology,
    find_comparable_meda_observation,
)
from backend.app.conditions.mars24 import compute_mars24
from backend.app.conditions.mission_clock import evaluate_route_mission_clock
from backend.app.conditions.rover_replay import get_rover_replay_service
from backend.app.conditions.terrain_shadows import get_dem_shadow_analyzer
from backend.app.main import app
from backend.app.services.planning_intelligence import (
    classify_route_uncertainty,
    evaluate_mission_stress_suite,
    evaluate_pareto_frontier,
    evaluate_science_eva_plan,
    plan_next_best_reconnaissance,
)

client = TestClient(app)


def test_mars24_canonical_regression_cases():
    """Verify the 3 canonical NASA GISS Mars24 regression cases and historical leap-second TT offset."""
    # Case 1: 2000-01-06T00:00:00+00:00, lon 0°E -> Ls ≈ 277.18758°, LTST ≈ 23.64840 h
    r1 = compute_mars24(0.0, 0.0, "2000-01-06T00:00:00+00:00")
    assert math.isclose(r1.tt_minus_utc_s, 64.184, abs_tol=1e-3)
    assert math.isclose(r1.ls_deg, 277.18758, abs_tol=5e-4)
    assert math.isclose(r1.ltst_hours, 23.64840, abs_tol=5e-4)

    # Case 2: 2004-01-03T13:46:31+00:00, lon 175.298°E (Spirit landing) -> Ls ≈ 327.32416°, LTST ≈ 0.00025 h
    r2 = compute_mars24(-14.5684, 175.298, "2004-01-03T13:46:31+00:00")
    assert math.isclose(r2.tt_minus_utc_s, 64.184, abs_tol=1e-3)
    assert math.isclose(r2.ls_deg, 327.32416, abs_tol=5e-4)
    assert math.isclose(r2.ltst_hours, 0.00025, abs_tol=5e-4)

    # Case 3: 2000-01-06T00:00:00+00:00, lon 15°E -> Ls ≈ 277.18758°, LTST ≈ 0.64840 h
    r3 = compute_mars24(0.0, 15.0, "2000-01-06T00:00:00+00:00")
    assert math.isclose(r3.ls_deg, 277.18758, abs_tol=5e-4)
    assert math.isclose(r3.ltst_hours, 0.64840, abs_tol=5e-4)

    # Verify post-2017 leap-second table gives 69.184 s
    r_modern = compute_mars24(18.4447, 77.4508, "2026-06-15T08:00:00Z")
    assert math.isclose(r_modern.tt_minus_utc_s, 69.184, abs_tol=1e-3)


def test_mars24_polar_continuous_day_and_night():
    """Verify polar continuous day and polar continuous night detection."""
    # At 2000-01-06, Ls ≈ 277.19° (Southern Summer / Northern Winter solstice)
    north_pole_winter = compute_mars24(85.0, 0.0, "2000-01-06T00:00:00Z")
    assert north_pole_winter.polar_day_state == "POLAR_CONTINUOUS_NIGHT"
    assert north_pole_winter.sunrise_ltst_hours is None
    assert north_pole_winter.sunset_ltst_hours is None
    assert north_pole_winter.daylight_mars_hours == 0.0

    south_pole_summer = compute_mars24(-85.0, 0.0, "2000-01-06T00:00:00Z")
    assert south_pole_summer.polar_day_state == "POLAR_CONTINUOUS_DAY"
    assert south_pole_summer.sunrise_ltst_hours is None
    assert south_pole_summer.sunset_ltst_hours is None
    assert south_pole_summer.daylight_mars_hours == 24.0


def test_dem_terrain_shadows_four_states():
    """Verify numeric DEM ray-marching distinguishes BELOW_HORIZON, TERRAIN_SHADOWED, ILLUMINATED, and INSUFFICIENT_DEM_COVERAGE."""
    analyzer = get_dem_shadow_analyzer()

    # 1. BELOW_HORIZON
    res_night = analyzer.evaluate_shadow(18.4447, 77.4508, solar_elevation_deg=-10.0, solar_azimuth_deg=90.0)
    assert res_night.shadow_state == "BELOW_HORIZON"
    assert res_night.is_below_horizon is True
    assert res_night.is_illuminated is False

    # 2. TERRAIN_SHADOWED (low sun 1.2° toward western delta scarp / rim azimuth 285°)
    res_shadow = analyzer.evaluate_shadow(18.4447, 77.4508, solar_elevation_deg=1.2, solar_azimuth_deg=285.0)
    assert res_shadow.shadow_state == "TERRAIN_SHADOWED"
    assert res_shadow.is_terrain_shadowed is True
    assert res_shadow.max_horizon_angle_deg is not None and res_shadow.max_horizon_angle_deg > 1.2

    # 3. ILLUMINATED (high sun 45°)
    res_illum = analyzer.evaluate_shadow(18.4447, 77.4508, solar_elevation_deg=45.0, solar_azimuth_deg=135.0)
    assert res_illum.shadow_state == "ILLUMINATED"
    assert res_illum.is_illuminated is True

    # 4. INSUFFICIENT_DEM_COVERAGE (Gale Crater 137.44°E, -4.59°S)
    res_out = analyzer.evaluate_shadow(-4.5895, 137.4417, solar_elevation_deg=30.0, solar_azimuth_deg=90.0)
    assert res_out.shadow_state == "INSUFFICIENT_DEM_COVERAGE"
    assert res_out.has_dem_coverage is False


def test_climatology_circular_interpolation_and_meda_comparability():
    """Verify smooth circular interpolation across 360° Ls and 24h LTST and honest MEDA comparison."""
    c_ls_359 = evaluate_modelled_climatology(18.4447, 77.4508, ls_deg=359.8, ltst_hours=14.0)
    c_ls_001 = evaluate_modelled_climatology(18.4447, 77.4508, ls_deg=0.2, ltst_hours=14.0)
    assert c_ls_359["kind"] == "modelled_climatology"
    assert abs(c_ls_359["air_temperature_c"] - c_ls_001["air_temperature_c"]) < 0.25

    c_ltst_239 = evaluate_modelled_climatology(18.4447, 77.4508, ls_deg=90.0, ltst_hours=23.95)
    c_ltst_001 = evaluate_modelled_climatology(18.4447, 77.4508, ls_deg=90.0, ltst_hours=0.05)
    assert abs(c_ltst_239["air_temperature_c"] - c_ltst_001["air_temperature_c"]) < 0.25

    # Comparable MEDA observation at Jezero Sol 15 state (Ls=13.24, LTST=14.20)
    meda_comp = find_comparable_meda_observation(18.4447, 77.4508, ls_deg=13.5, ltst_hours=14.1)
    assert meda_comp["kind"] == "measured_observation"
    assert meda_comp["is_directly_comparable"] is True

    # Non-comparable location (Olympus Mons)
    meda_far = find_comparable_meda_observation(18.65, -133.8, ls_deg=13.5, ltst_hours=14.1)
    assert meda_far["is_directly_comparable"] is False


def test_conditions_api_endpoints_and_rover_replay():
    """Verify GET /api/conditions and /api/v1/conditions and Rover Replay archive boundaries."""
    r = client.get("/api/conditions?lat=18.4447&lon=77.4508&utc=2026-06-15T08:00:00Z")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    for key in [
        "mars_sol_date",
        "local_true_solar_time",
        "solar_longitude_ls",
        "solar_elevation",
        "terrain_shadow_state",
        "modelled_air_temperature",
        "measured_meda_pressure",
    ]:
        metric = body["metrics"][key]
        assert set(metric.keys()) == {"value", "unit", "kind", "source", "status"}

    # Rover replay pre-landing
    rep_pre = get_rover_replay_service().get_replay_state(utc_time="2020-12-01T00:00:00Z")
    assert rep_pre["archive_status"] == "PRE_LANDING"
    assert rep_pre["position_available"] is False
    assert rep_pre["active_waypoint"] is None

    # Rover replay exact sol (Sol 0)
    rep_s0 = get_rover_replay_service().get_replay_state(sol=0)
    assert rep_s0["archive_status"] == "EXACT_SOL_RECORD"
    assert rep_s0["position_available"] is True
    assert rep_s0["position_interpolated"] is False

    # Rover replay post-archive cutoff (Sol 5000)
    rep_post = get_rover_replay_service().get_replay_state(sol=5000)
    assert rep_post["archive_status"] == "POST_ARCHIVE_CUTOFF"
    assert rep_post["sols_beyond_archive_cutoff"] > 0


def test_mission_clock_and_phase2_planning_intelligence():
    """Verify Route Mission Clock, Pareto filtering, Recon planner, Science/EVA-hr, and 7-Scenario Stress Suite."""
    coords = [
        [77.4508, 18.4447, -2573.0],
        [77.4395, 18.4310, -2580.0],
        [77.4110, 18.4515, -2545.0],
    ]
    clock = evaluate_route_mission_clock(
        coordinates=coords,
        departure_utc="2026-06-15T07:30:00Z",
        base_speed_m_s=1.11,
        include_return_leg=True,
    )
    assert clock["cost_function_modified"] is False
    assert clock["outbound_leg"]["distance_m"] > 1000.0
    assert clock["return_leg"] is not None
    assert len(clock["segments"]) >= 4

    unc = classify_route_uncertainty(segments=[], coordinates=coords, dem_resolution_m=200.0)
    assert unc["overall_support_tier"] in ("STRONG", "MODERATE", "WEAK", "UNKNOWN")

    sci = evaluate_science_eva_plan(coordinates=coords, duration_hours=1.5)
    assert sci["visited_targets_count"] >= 2
    assert sci["science_return_per_eva_hour"] > 0.0

    recon = plan_next_best_reconnaissance(unc, coords)
    assert recon["search_policy"] == "EXISTING_NASA_ARCHIVES_FIRST"
    assert recon["recommendations_count"] >= 1

    pareto = evaluate_pareto_frontier(
        [
            {
                "route_id": "route_fast",
                "duration_hours": 1.2,
                "distance_m": 4200.0,
                "terrain_hazard_score": 45.0,
                "uncertainty_exposure_score": 25.0,
                "science_return_score": 150.0,
            },
            {
                "route_id": "route_safe",
                "duration_hours": 1.5,
                "distance_m": 4800.0,
                "terrain_hazard_score": 18.0,
                "uncertainty_exposure_score": 15.0,
                "science_return_score": 150.0,
            },
            {
                "route_id": "route_dominated",
                "duration_hours": 1.8,
                "distance_m": 5200.0,
                "terrain_hazard_score": 55.0,
                "uncertainty_exposure_score": 35.0,
                "science_return_score": 120.0,
            },
        ]
    )
    assert pareto["pareto_optimal_count"] == 2
    assert pareto["dominated_count"] == 1

    stress = evaluate_mission_stress_suite(
        coordinates=coords,
        baseline_duration_hours=1.5,
        baseline_cost=4500.0,
        max_slope_deg=18.0,
        uncertainty_summary=unc,
        science_plan=sci,
    )
    assert stress["scenarios_evaluated_count"] == 7
    assert len(stress["scenarios"]) == 7

    # Check presets and nasa imagery endpoints
    r_presets = client.get("/api/v1/routes/presets")
    assert r_presets.status_code == 200
    assert r_presets.json()["count"] >= 6

    r_img = client.get("/api/nasa/imagery")
    assert r_img.status_code == 200
    assert len(r_img.json()["wmts_layers"]) >= 4
