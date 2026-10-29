import numpy as np
import pytest
from backend.app.routing.cost_model import calculate_edge_cost
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode


def test_edge_cost_non_negative():
    # Test across all modes that cost >= distance_3d > 0
    for mode in [OptimizationMode.SAFETY_FIRST, OptimizationMode.BALANCED, OptimizationMode.SCIENCE_FIRST]:
        cost, breakdown = calculate_edge_cost(
            distance_3d=100.0,
            slope_deg=10.0,
            roughness=0.3,
            delta_z=5.0,
            mode=mode,
        )
        assert cost >= 100.0
        assert breakdown["base_distance_cost"] == 100.0
        assert breakdown["slope_penalty"] >= 0.0
        assert breakdown["roughness_penalty"] >= 0.0


def test_directional_uphill_penalty():
    # Uphill vs Downhill on same distance and slope
    cost_uphill, _ = calculate_edge_cost(
        distance_3d=100.0, slope_deg=12.0, roughness=0.2, delta_z=+15.0, mode=OptimizationMode.BALANCED
    )
    cost_downhill, _ = calculate_edge_cost(
        distance_3d=100.0, slope_deg=12.0, roughness=0.2, delta_z=-15.0, mode=OptimizationMode.BALANCED
    )
    assert cost_uphill > cost_downhill


def test_diagonal_corner_cutting_prevention():
    # 2x2 grid where top-right and bottom-left are untraversable
    # [T, F]
    # [F, T]
    # A diagonal step from (0,0) to (1,1) cuts through the blocked corners and MUST be disallowed.
    elev = np.zeros((2, 2), dtype=np.float32)
    slope = np.zeros((2, 2), dtype=np.float32)
    rough = np.zeros((2, 2), dtype=np.float32)
    traversable = np.array([[True, False], [False, True]])

    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=traversable,
        dx_meters=10.0,
        dy_meters=10.0,
    )

    neighbors = list(graph.get_valid_neighbors(0, 0))
    # (1, 1) must NOT be yielded because (0, 1) and (1, 0) are False
    target_nodes = [n[0] for n in neighbors]
    assert (1, 1) not in target_nodes
