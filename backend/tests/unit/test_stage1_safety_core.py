import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.app.core.exceptions import UnreachableDestinationError
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.geospatial.terrain_metrics import compute_directional_gradients
from backend.app.main import app
from backend.app.routing.astar import astar_search
from backend.app.routing.cost_model import (
    calculate_edge_cost,
    calculate_step_relative_effort,
    compute_minetti_relative_effort_factor,
)
from backend.app.routing.dijkstra import dijkstra_search
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.routing.return_constraint import (
    compute_backward_time_grid,
    serialize_time_grid_overlay,
)
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import RoutePlanRequest
from backend.app.services.route_service import RouteService

client = TestClient(app)


def _linear_ramp_grid(rows: int = 12, cols: int = 12, east_grade: float = 0.25, dx: float = 20.0):
    """Creates a synthetic planar ramp sloping upward toward the east (+col)."""
    col_idx = np.arange(cols, dtype=np.float32)
    elevation = np.tile(col_idx * dx * east_grade, (rows, 1))
    slope_deg_scalar = np.degrees(np.arctan(abs(east_grade)))
    slope = np.full((rows, cols), slope_deg_scalar, dtype=np.float32)
    roughness = np.full((rows, cols), 0.1, dtype=np.float32)
    traversable = np.ones((rows, cols), dtype=bool)
    return elevation, slope, roughness, traversable


def test_directional_slope_asymmetry_and_cross_slope_on_linear_ramp():
    dx = 20.0
    dy = 20.0
    elev, slope, roughness, traversable = _linear_ramp_grid(east_grade=0.25, dx=dx)
    dz_deast, dz_dnorth = compute_directional_gradients(elev, dx, dy)

    # Along +East, dz/deast is positive ~0.25; dz/dnorth is 0 on planar east ramp
    assert np.allclose(dz_deast[2:-2, 2:-2], 0.25, atol=1e-4)
    assert np.allclose(dz_dnorth[2:-2, 2:-2], 0.0, atol=1e-4)

    graph_dir = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=roughness,
        traversable_mask=traversable,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
        dz_deast=dz_deast,
        dz_dnorth=dz_dnorth,
        cost_mode="directional",
        cross_slope_weight=0.35,
    )

    # Moving East (uphill) vs moving West (downhill)
    cost_up, _, _, _, _, bd_up = graph_dir.edge_cost(5, 4, 5, 5)
    cost_down, _, _, _, _, bd_down = graph_dir.edge_cost(5, 5, 5, 4)
    assert cost_up > cost_down
    assert abs(sum(bd_down.values()) - cost_down) < 0.05

    # Moving North (perpendicular to eastward ramp) encounters full cross-slope hazard
    _, _, _, along_deg_cross, cross_deg_cross = graph_dir.compute_edge_geometry(5, 5, 4, 5)
    assert abs(along_deg_cross) < 0.05
    assert cross_deg_cross > 10.0

    # Directional cross-slope cost exceeds zero-cross_slope_weight baseline
    graph_no_cross = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=roughness,
        traversable_mask=traversable,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
        dz_deast=dz_deast,
        dz_dnorth=dz_dnorth,
        cost_mode="directional",
        cross_slope_weight=0.0,
    )
    cost_north_weighted, _, _, _, _, _ = graph_dir.edge_cost(5, 5, 4, 5)
    cost_north_unweighted, _, _, _, _, _ = graph_no_cross.edge_cost(5, 5, 4, 5)
    assert cost_north_weighted > cost_north_unweighted

    # Legacy magnitude mode vs directional canonical 5-key breakdown
    assert set(bd_up.keys()) == {
        "base_distance_cost",
        "slope_penalty",
        "roughness_penalty",
        "hazard_penalty",
        "extra_penalty",
    }
    assert abs(sum(bd_up.values()) - cost_up) < 0.05


def test_minetti_relative_effort_curve_properties():
    # Unitless effort factor == 1.0 on flat terrain and >= 0.45 everywhere (downhill floor)
    assert compute_minetti_relative_effort_factor(0.0) == pytest.approx(1.0, abs=1e-6)
    for grade in (-0.4, -0.2, -0.1, 0.0, 0.1, 0.25, 0.45):
        factor = compute_minetti_relative_effort_factor(grade)
        assert factor >= 0.45

    # Uphill relative effort exceeds equal-magnitude downhill effort
    eff_up = calculate_step_relative_effort(distance_3d=25.0, along_grade=0.25, suit_load_factor=1.2)
    eff_down = calculate_step_relative_effort(distance_3d=25.0, along_grade=-0.25, suit_load_factor=1.2)
    assert eff_up > eff_down > 0.0

    # In calculate_edge_cost with minetti_effort, cost >= distance_3d strictly holds (A* admissibility)
    for along_deg, dz in ((-12.0, -5.3), (0.0, 0.0), (14.0, 6.0)):
        c_minetti, bd_minetti = calculate_edge_cost(
            distance_3d=25.0,
            slope_deg=abs(along_deg),
            roughness=0.1,
            delta_z=dz,
            mode=OptimizationMode.BALANCED,
            along_slope_deg=along_deg,
            cross_slope_deg=3.0,
            cost_mode="directional",
            effort_model="minetti_effort",
            suit_load_factor=1.2,
        )
        assert c_minetti >= 25.0
        assert abs(sum(bd_minetti.values()) - c_minetti) < 0.05


@pytest.mark.parametrize(
    "cost_mode,effort_model",
    [
        ("directional", "slope_penalty"),
        ("directional", "minetti_effort"),
        ("legacy_magnitude", "slope_penalty"),
    ],
)
def test_astar_dijkstra_cost_equivalence_stage1_modes(cost_mode, effort_model):
    elev, slope, roughness, traversable = _linear_ramp_grid(rows=14, cols=14, east_grade=0.18, dx=20.0)
    traversable[0:9, 7] = False
    slope[0:9, 7] = 35.0
    dz_deast, dz_dnorth = compute_directional_gradients(elev, 20.0, 20.0)

    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=roughness,
        traversable_mask=traversable,
        dx_meters=20.0,
        dy_meters=20.0,
        mode=OptimizationMode.BALANCED,
        dz_deast=dz_deast,
        dz_dnorth=dz_dnorth,
        cost_mode=cost_mode,
        effort_model=effort_model,
    )

    start = (2, 2)
    dest = (2, 11)
    _, cost_astar, nodes_astar, _ = astar_search(graph, start, dest)
    _, cost_dijkstra, nodes_dijkstra, _ = dijkstra_search(graph, start, dest)

    assert abs(cost_astar - cost_dijkstra) < 1e-3
    assert nodes_astar <= nodes_dijkstra


def test_backward_dijkstra_return_and_rescue_grids_and_nodata():
    rows, cols = 10, 10
    elev = np.zeros((rows, cols), dtype=np.float32)
    slope = np.zeros((rows, cols), dtype=np.float32)
    # Build a 16-degree ridge across column 5 except gap at row 8
    slope[0:8, 5] = 16.0
    elev[:, 5] = 5.0
    traversable = np.ones((rows, cols), dtype=bool)
    # Place NoData cell at (1, 1) -> cannot be reachable and must serialize as None
    traversable[1, 1] = False
    elev[1, 1] = np.nan

    habitat = (5, 2)
    ret_res = compute_backward_time_grid(
        elevation=elev,
        slope_deg=slope,
        traversable_mask=traversable,
        dx_meters=30.0,
        dy_meters=30.0,
        habitat_node=habitat,
        base_speed_m_s=1.0,
        budget_seconds=120.0,
    )
    assert ret_res.time_seconds_grid[habitat] == 0.0
    assert np.isinf(ret_res.time_seconds_grid[1, 1])  # NoData cell is never safe / finite

    # Serialize grid with max_dim=10 (no decimation): non-finite cells MUST become None, never 0
    meta = RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic_latlon",
        crs_str="IAU2000:49900",
        units="deg",
        min_lon=77.40,
        min_lat=18.39,
        max_lon=77.41,
        max_lat=18.40,
        deg_per_px_lon=0.01 / cols,
        deg_per_px_lat=0.01 / rows,
        meters_per_px_x=30.0,
        meters_per_px_y=30.0,
        affine_transform=(0.01 / cols, 0.0, 77.40, 0.0, -0.01 / rows, 18.40),
        nodata_value=-32768.0,
    )
    overlay = serialize_time_grid_overlay(
        ret_res.time_seconds_grid,
        meta=meta,
        budget_minutes=2.0,
        max_dim=10,
    )
    assert overlay["minutes_grid"][1][1] is None
    assert overlay["minutes_grid"][habitat[0]][habitat[1]] == 0.0

    # Rescue map with drivable slope limit 12° must detour around the 16° ridge in col 5
    rescue_res = compute_backward_time_grid(
        elevation=elev,
        slope_deg=slope,
        traversable_mask=traversable,
        dx_meters=30.0,
        dy_meters=30.0,
        habitat_node=habitat,
        base_speed_m_s=2.0,
        budget_seconds=3600.0,
        max_drivable_slope_deg=12.0,
    )
    assert np.isinf(rescue_res.time_seconds_grid[2, 5])  # 16° wall cannot be entered by 12° rescue vehicle
    assert np.isfinite(rescue_res.time_seconds_grid[2, 7])
    # Detour through row 8 must make (2, 7) time strictly longer than straight-line time
    straight_sec = (5 * 30.0) / 2.0
    assert rescue_res.time_seconds_grid[2, 7] > straight_sec


def test_route_service_return_block_flag_rescue_and_turnaround_end_to_end():
    service = RouteService()

    # 1. Very tight return budget + block mode -> rejects unreachable return path cleanly
    tight_req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.45, lat=18.43),
        max_eva_hours=0.55,
        walking_speed_m_s=0.1,
        return_constraint_mode="block",
        departure_utc="2026-11-14T15:00:00Z",
    )
    with pytest.raises(UnreachableDestinationError):
        service.plan_route(tight_req)

    # 2. Same tight budget in flag mode -> succeeds cleanly with exceeds_return_budget flagged
    flag_req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.425, lat=18.405),
        max_eva_hours=0.6,
        walking_speed_m_s=0.15,
        return_constraint_mode="flag",
        cost_mode="directional",
        effort_model="minetti_effort",
        suit_load_factor=1.15,
        daylight_buffer_minutes=45.0,
        rescue_enabled=True,
        rescue_speed_m_s=2.0,
        rescue_max_slope_deg=12.0,
        rescue_threshold_minutes=15.0,
        departure_utc="2026-11-14T15:00:00Z",
    )
    flag_resp = service.plan_route(flag_req)
    assert flag_resp.return_zone is not None
    assert flag_resp.rescue_zone is not None

    primary = flag_resp.routes[0]
    assert primary.summary.cost_mode == "directional"
    assert primary.summary.effort_model == "minetti_effort"
    assert primary.summary.estimated_relative_effort is not None
    assert primary.summary.estimated_relative_effort > 0
    assert primary.summary.exceeds_return_budget is True
    assert primary.summary.provenance is not None
    assert primary.summary.provenance["kind"] in ("computed", "derived", "modeled")
    assert primary.summary.provenance["resolution"]
    assert primary.turnaround is not None
    assert "turnaround_ltst_hms" in primary.turnaround
    assert "sunset_ltst_hms" in primary.turnaround


def test_turnaround_responds_to_departure_time_and_buffer_and_sunset_api():
    base_payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.42, "lat": 18.40},
        "crs_identifier": "IAU2000:49900",
        "mode": "balanced",
        "cost_mode": "directional",
        "effort_model": "minetti_effort",
        "return_constraint_mode": "flag",
        "max_eva_hours": 6.0,
        "daylight_buffer_minutes": 30.0,
        # ~08:35 LTST in Jezero Crater (daytime)
        "departure_utc": "2026-11-14T15:00:00Z",
    }
    resp_morning = client.post("/api/v1/routes/plan", json=base_payload)
    assert resp_morning.status_code == 200
    d_morning = resp_morning.json()

    # ~21:20 LTST in Jezero Crater (after sunset)
    resp_night = client.post(
        "/api/v1/routes/plan",
        json={**base_payload, "departure_utc": "2026-11-15T04:00:00Z", "daylight_buffer_minutes": 60.0},
    )
    assert resp_night.status_code == 200
    d_night = resp_night.json()

    t1 = d_morning["routes"][0]["turnaround"]
    t2 = d_night["routes"][0]["turnaround"]
    assert t1 is not None and t2 is not None
    assert t1["turnaround_utc"] != t2["turnaround_utc"]
    assert t1["feasible_before_sunset"] is True
    assert t2["feasible_before_sunset"] is False
