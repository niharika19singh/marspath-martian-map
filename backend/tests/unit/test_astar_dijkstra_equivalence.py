import numpy as np
import pytest

from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    RoutingTimeoutError,
    UnreachableDestinationError,
)
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.alternatives import generate_route_alternatives
from backend.app.routing.astar import astar_search
from backend.app.routing.dijkstra import dijkstra_search
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode


@pytest.fixture
def test_terrain_grid():
    """Constructs a deterministic 20x20 terrain grid with variable elevations and an obstacle."""
    rows, cols = 20, 20
    elevation = np.zeros((rows, cols), dtype=np.float32)
    # Gentle slope from left to right
    for c in range(cols):
        elevation[:, c] = c * 2.0

    slope_deg = np.full((rows, cols), 5.0, dtype=np.float32)
    roughness = np.full((rows, cols), 0.1, dtype=np.float32)
    traversable = np.ones((rows, cols), dtype=bool)

    # Place an impassable wall down column 10, with a gap at row 15
    traversable[0:15, 10] = False
    slope_deg[0:15, 10] = 35.0  # Steep cliff

    return elevation, slope_deg, roughness, traversable


def test_astar_dijkstra_cost_equivalence(test_terrain_grid):
    elev, slope, rough, trav = test_terrain_grid
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
        mode=OptimizationMode.BALANCED,
    )

    start = (2, 2)
    dest = (2, 18)

    path_astar, cost_astar, nodes_astar, _ = astar_search(graph, start, dest)
    path_dijkstra, cost_dijkstra, nodes_dijkstra, _ = dijkstra_search(graph, start, dest)

    # 1. Both must find an identical optimal path cost!
    assert abs(cost_astar - cost_dijkstra) < 1e-4

    # 2. Both paths must reach destination
    assert path_astar[0] == start
    assert path_astar[-1] == dest
    assert path_dijkstra[0] == start
    assert path_dijkstra[-1] == dest

    # 3. A* must expand fewer or equal nodes compared to uninformed Dijkstra
    assert nodes_astar <= nodes_dijkstra


def test_unreachable_destination_blocked(test_terrain_grid):
    elev, slope, rough, trav = test_terrain_grid
    # Fully wall off the entire column 10
    trav[:, 10] = False

    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
    )

    start = (5, 2)
    dest = (5, 18)

    with pytest.raises(UnreachableDestinationError):
        astar_search(graph, start, dest)

    with pytest.raises(UnreachableDestinationError):
        dijkstra_search(graph, start, dest)


def test_computational_bound_exceeded(test_terrain_grid):
    elev, slope, rough, trav = test_terrain_grid
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
    )

    start = (0, 0)
    dest = (19, 19)

    # Set unrealistically low expansion bound
    with pytest.raises(ComputationalBoundExceededError):
        astar_search(graph, start, dest, max_expansions=10)


def test_astar_timeout_expiration_deterministic(test_terrain_grid, monkeypatch):
    """Verifies that an expired deadline during A* node expansion raises RoutingTimeoutError."""
    import backend.app.routing.astar as astar_mod

    elev, slope, rough, trav = test_terrain_grid
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
    )

    # Set check interval to 2 so timeout check fires early
    monkeypatch.setattr(astar_mod, "ASTAR_TIMEOUT_CHECK_INTERVAL_NODES", 2)

    clock = {"t": 100.0}

    def controlled_perf_counter():
        clock["t"] += 2.0  # Advance by 2s on every call
        return clock["t"]

    monkeypatch.setattr(astar_mod.time, "perf_counter", controlled_perf_counter)

    with pytest.raises(RoutingTimeoutError) as exc_info:
        astar_search(graph, (0, 0), (19, 19), timeout_seconds=3.0)

    err = exc_info.value
    assert err.status_code == 504
    assert err.details["timeout_seconds"] == 3.0
    assert err.details["elapsed_seconds"] >= 3.0
    assert "timeout" in err.message.lower()


def test_astar_timeout_immediate_expired_deadline(test_terrain_grid):
    """Verifies that a deadline that has already expired before search starts raises immediately."""
    elev, slope, rough, trav = test_terrain_grid
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
    )

    past_deadline = 10.0
    with pytest.raises(RoutingTimeoutError) as exc_info:
        astar_search(
            graph,
            (0, 0),
            (19, 19),
            timeout_seconds=5.0,
            deadline=past_deadline,
            overall_start_time=5.0,
        )

    err = exc_info.value
    assert err.status_code == 504
    assert err.details["timeout_seconds"] == 5.0
    assert err.details["elapsed_seconds"] > 0.0


def test_shared_deadline_across_route_alternatives_not_swallowed(test_terrain_grid, monkeypatch):
    """
    Verifies that when a shared deadline expires during alternative corridor search:
    1. RoutingTimeoutError is raised and not swallowed by alternative-search fallback handling.
    2. overall_start_time is respected and elapsed_seconds measures total time from request start.
    """
    import backend.app.routing.astar as astar_mod

    elev, slope, rough, trav = test_terrain_grid
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=25.0,
        dy_meters=25.0,
    )
    meta = RasterMetadata(
        width=20,
        height=20,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.0,
        min_lat=18.0,
        max_lon=77.1,
        max_lat=18.1,
        deg_per_px_lon=0.005,
        deg_per_px_lat=0.005,
        meters_per_px_x=25.0,
        meters_per_px_y=25.0,
        affine_transform=(0.005, 0.0, 77.0, 0.0, -0.005, 18.1),
        nodata_value=-32768.0,
        vertical_datum="Synthetic Reference Datum (Mars Sphere R=3,396,190m)",
        is_synthetic=True,
    )

    # Let primary route complete with mock time < deadline (100.0 .. 105.0 < 110.0),
    # then jump past deadline (115.0 > 110.0) when alternative corridor search starts.
    call_count = {"astar_calls": 0}
    clock_state = {"t": 100.0, "stage": "primary"}
    orig_astar = astar_mod.astar_search

    def controlled_perf_counter():
        if clock_state["stage"] == "alternative":
            return 115.0
        clock_state["t"] += 0.001
        return clock_state["t"]

    monkeypatch.setattr(astar_mod.time, "perf_counter", controlled_perf_counter)

    def monitored_astar(*args, **kwargs):
        call_count["astar_calls"] += 1
        if call_count["astar_calls"] >= 2:
            clock_state["stage"] = "alternative"
        return orig_astar(*args, **kwargs)

    monkeypatch.setattr("backend.app.routing.alternatives.astar_search", monitored_astar)

    with pytest.raises(RoutingTimeoutError) as exc_info:
        generate_route_alternatives(
            graph=graph,
            meta=meta,
            start_px=(0, 0),
            dest_px=(19, 19),
            requested_mode=OptimizationMode.BALANCED,
            num_alternatives=2,
            timeout_seconds=10.0,
            deadline=110.0,
            overall_start_time=100.0,
        )

    err = exc_info.value
    assert err.status_code == 504
    assert err.details["timeout_seconds"] == 10.0
    assert err.details["elapsed_seconds"] == 15.0
    assert call_count["astar_calls"] >= 2
