import numpy as np
import pytest
from backend.app.core.exceptions import ComputationalBoundExceededError, UnreachableDestinationError
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
