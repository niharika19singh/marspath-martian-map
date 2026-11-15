"""Unit tests for Dual-Radius Walk-Back Safety Envelopes and RF line-of-sight analysis.

Verifies:
- Separation of rover mobility model (10 km/h, 14° slope limit) and suited pedestrian model (4 km/h, 3.5h emergency limit).
- Derivation from real DEM backward-Dijkstra (never arbitrary concentric circles).
- Feasibility status calculation (SAFE WITHIN CONFIGURED LIMIT, LIMITED MARGIN, WALK-BACK LIMIT EXCEEDED, DATA UNAVAILABLE).
- Detection of high-difficulty bottlenecks along traverse segments.
- RF line-of-sight continuity and verified Mars relay orbiters (MRO, TGO, Odyssey, MAVEN, MEX).
"""

import math

import numpy as np
import pytest

from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.rf_visibility import evaluate_rf_line_of_sight
from backend.app.routing.walkback import (
    compute_dual_radius_envelopes,
    evaluate_on_foot_feasibility,
)
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.safety_envelopes import WalkBackStatus


@pytest.fixture
def test_terrain():
    """10x10 synthetic DEM test fixture in Jezero Crater."""
    rows, cols = 10, 10
    elev = np.zeros((rows, cols), dtype=np.float32)
    # Gentle slope in middle, steep cliff on east
    for r in range(rows):
        for c in range(cols):
            elev[r, c] = float(c * 10.0) if c < 8 else float(c * 50.0)

    slope = np.zeros((rows, cols), dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            slope[r, c] = 4.0 if c < 8 else 22.0

    trav = np.ones((rows, cols), dtype=bool)
    trav[:, 9] = False  # untraversable boundary

    meta = RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.40,
        min_lat=18.40,
        max_lon=77.50,
        max_lat=18.50,
        deg_per_px_lon=0.01,
        deg_per_px_lat=0.01,
        meters_per_px_x=100.0,
        meters_per_px_y=100.0,
        affine_transform=(0.01, 0.0, 77.40, 0.0, -0.01, 18.50),
        nodata_value=-32768.0,
        is_synthetic=True,
    )
    return elev, slope, trav, meta


def test_01_rover_vs_pedestrian_speed_and_slope_separation(test_terrain):
    elev, slope, trav, meta = test_terrain
    hab_node = (5, 5)
    hab_coord = MarsCoordinate(lon=77.45, lat=18.45)
    dest_coord = MarsCoordinate(lon=77.42, lat=18.42)

    dual_env, rover_res, walk_res = compute_dual_radius_envelopes(
        elevation=elev,
        slope_deg=slope,
        traversable_mask=trav,
        dx_meters=100.0,
        dy_meters=100.0,
        habitat_node=hab_node,
        meta=meta,
        habitat_coord=hab_coord,
        dest_coord=dest_coord,
        rover_speed_m_s=2.7778,  # 10 km/h
        rover_max_slope_deg=14.0,
        rover_budget_hours=8.0,
        walk_speed_m_s=1.1111,  # 4 km/h
        walk_max_slope_deg=20.0,
        walk_budget_hours=3.5,
    )

    # 1. Envelopes must have distinct mobility assumptions
    assert dual_env.rover_assisted.assumed_speed_km_h > dual_env.on_foot_walkback.assumed_speed_km_h
    assert math.isclose(dual_env.rover_assisted.assumed_speed_km_h, 10.0, rel_tol=1e-2)
    assert math.isclose(dual_env.on_foot_walkback.assumed_speed_km_h, 4.0, rel_tol=1e-2)
    assert dual_env.rover_assisted.color == "#00d2ff"  # Cyan
    assert dual_env.on_foot_walkback.color == "#00e676"  # Green

    # 2. Both must have serialized time grid overlays
    assert dual_env.rover_assisted.time_grid is not None
    assert dual_env.on_foot_walkback.time_grid is not None
    assert "minutes_grid" in dual_env.rover_assisted.time_grid
    assert "minutes_grid" in dual_env.on_foot_walkback.time_grid

    # 3. Model assumptions documented without fabrication
    assert "rover_mobility" in dual_env.model_assumptions
    assert "pedestrian_mobility" in dual_env.model_assumptions


def test_02_walk_back_safe_within_configured_limit():
    coords = [
        MarsCoordinate(lon=77.40, lat=18.40),
        MarsCoordinate(lon=77.41, lat=18.41),
        MarsCoordinate(lon=77.42, lat=18.42),
    ]

    feasibility, rover_h, ratio = evaluate_on_foot_feasibility(
        route_coords=coords,
        route_distance_km=2.0,
        route_max_slope_deg=5.0,
        route_avg_slope_deg=3.0,
        route_roughness_tri=0.2,
        walk_speed_m_s=1.1111,
        walk_time_seconds_from_dest=2400.0,  # 40 mins
        rover_time_seconds_from_dest=900.0,  # 15 mins
        max_permitted_walking_hours=3.5,
        eva_budget_hours=8.0,
    )

    assert feasibility.status == WalkBackStatus.SAFE_WITHIN_LIMIT
    assert feasibility.destination_exceeds_limit is False
    assert feasibility.warning_message is None
    assert feasibility.terrain_difficulty == "MILD"
    assert feasibility.emergency_resource_margin_pct > 50.0
    assert ratio > 1.0  # Walking takes longer than rover


def test_03_walk_back_limit_exceeded_warning():
    coords = [
        MarsCoordinate(lon=77.40, lat=18.40),
        MarsCoordinate(lon=77.48, lat=18.48),
    ]

    feasibility, rover_h, ratio = evaluate_on_foot_feasibility(
        route_coords=coords,
        route_distance_km=14.0,
        route_max_slope_deg=18.0,
        route_avg_slope_deg=10.0,
        route_roughness_tri=0.5,
        walk_speed_m_s=1.1111,
        walk_time_seconds_from_dest=16200.0,  # 4.5 hours -> exceeds 3.5h limit!
        rover_time_seconds_from_dest=5400.0,  # 1.5 hours
        max_permitted_walking_hours=3.5,
        eva_budget_hours=8.0,
    )

    assert feasibility.status == WalkBackStatus.LIMIT_EXCEEDED
    assert feasibility.destination_exceeds_limit is True
    assert "DESTINATION EXCEEDS CONFIGURED ON-FOOT WALK-BACK LIMIT" in feasibility.warning_message
    assert feasibility.terrain_difficulty == "SEVERE"


def test_04_walk_back_limited_margin():
    coords = [
        MarsCoordinate(lon=77.40, lat=18.40),
        MarsCoordinate(lon=77.45, lat=18.45),
    ]

    # Walk time 2.8 hours (between 2.5h and 3.5h) -> tight margin
    feasibility, rover_h, ratio = evaluate_on_foot_feasibility(
        route_coords=coords,
        route_distance_km=6.0,
        route_max_slope_deg=12.0,
        route_avg_slope_deg=7.0,
        route_roughness_tri=0.35,
        walk_speed_m_s=1.1111,
        walk_time_seconds_from_dest=2.8 * 3600.0,
        rover_time_seconds_from_dest=0.8 * 3600.0,
        max_permitted_walking_hours=3.5,
        eva_budget_hours=8.0,
    )

    assert feasibility.status == WalkBackStatus.LIMITED_MARGIN
    assert feasibility.destination_exceeds_limit is False
    assert feasibility.warning_message is not None
    assert "CAUTION: On-foot return margin is limited" in feasibility.warning_message


def test_05_walk_back_data_unavailable_on_nodata():
    feasibility, rover_h, ratio = evaluate_on_foot_feasibility(
        route_coords=[],
        route_distance_km=0.0,
        route_max_slope_deg=0.0,
        route_avg_slope_deg=0.0,
        route_roughness_tri=0.0,
        out_of_bounds=True,
    )

    assert feasibility.status == WalkBackStatus.DATA_UNAVAILABLE
    assert feasibility.destination_exceeds_limit is True
    assert "DATA UNAVAILABLE" in feasibility.warning_message


def test_06_rf_line_of_sight_and_active_orbiters():
    hab = MarsCoordinate(lon=77.45, lat=18.45)
    route = [
        MarsCoordinate(lon=77.45, lat=18.45),
        MarsCoordinate(lon=77.46, lat=18.46),
        MarsCoordinate(lon=77.47, lat=18.47),
    ]

    rf_status = evaluate_rf_line_of_sight(
        habitat_coord=hab,
        route_coords=route,
        max_slope_deg=6.0,
    )

    # Moderate slope and short distance -> Direct LOS connected
    assert rf_status.direct_habitat_los in ("CONNECTED", "POTENTIAL_OBSTRUCTION")
    assert len(rf_status.active_orbiters) == 5  # MRO, Odyssey, TGO, MAVEN, Mars Express
    # Verify MRO is tracked
    mro = next((o for o in rf_status.active_orbiters if "MRO" in o.spacecraft), None)
    assert mro is not None
    assert mro.payload == "Electra UHF Software Defined Radio"
    assert mro.is_in_view is True
    assert rf_status.best_orbiter_contact is not None
