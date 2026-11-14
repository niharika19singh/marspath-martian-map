import numpy as np

from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.routing.astar import astar_search
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode


def test_nodata_hole_does_not_corrupt_valid_slopes_and_roughness():
    # 20x20 flat terrain at -2500m
    rows, cols = 20, 20
    elevation = np.full((rows, cols), -2500.0, dtype=np.float32)

    # Nodata hole in the middle: cells (8:12, 8:12) are -9999.0
    nodata_mask = np.zeros((rows, cols), dtype=bool)
    nodata_mask[8:12, 8:12] = True
    elevation[nodata_mask] = -9999.0

    dx, dy = 10.0, 10.0
    slopes = compute_slope_degrees(elevation, dx, dy, nodata_mask=nodata_mask)
    roughness = compute_roughness_index(elevation, kernel_size=3, nodata_mask=nodata_mask)

    # Cells far from the hole (e.g. 0 to 5) must remain perfectly 0.0 slope and 0.0 roughness!
    assert np.all(slopes[0:5, 0:5] == 0.0)
    assert np.all(roughness[0:5, 0:5] == 0.0)

    # Nodata cells and their immediate boundary must be NaN
    assert np.all(np.isnan(slopes[8:12, 8:12]))
    assert np.all(np.isnan(roughness[8:12, 8:12]))


def test_routing_navigates_around_nodata_hole():
    rows, cols = 25, 25
    elevation = np.full((rows, cols), -2500.0, dtype=np.float32)

    # Create a 5x5 nodata hole blocking the direct path between start (12, 2) and dest (12, 22)
    nodata_mask = np.zeros((rows, cols), dtype=bool)
    nodata_mask[10:15, 10:15] = True
    elevation[nodata_mask] = -9999.0

    dx, dy = 10.0, 10.0
    slopes = compute_slope_degrees(elevation, dx, dy, nodata_mask=nodata_mask)
    roughness = compute_roughness_index(elevation, kernel_size=3, nodata_mask=nodata_mask)

    traversable = build_traversability_mask(
        slope_deg=slopes,
        roughness=roughness,
        max_slope_deg=20.0,
        max_roughness=0.85,
        nodata_mask=nodata_mask,
        avoid_unobserved_terrain=True,
    )

    # The hole and its perimeter must be strictly impassable
    assert not np.any(traversable[10:15, 10:15])

    graph = TerrainGridGraph(
        elevation=elevation,
        slope_deg=slopes,
        roughness=roughness,
        traversable_mask=traversable,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )

    start = (12, 2)
    dest = (12, 22)

    path, cost, nodes_expanded, _ = astar_search(graph, start, dest)

    # Path must be found and reach destination
    assert path[0] == start
    assert path[-1] == dest
    assert cost > 0.0
    assert not np.isnan(cost)

    # Path must NOT step into the nodata hole
    for r, c in path:
        assert not (10 <= r < 15 and 10 <= c < 15), f"Path stepped into nodata hole at ({r}, {c})!"
