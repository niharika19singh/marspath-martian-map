import math

import numpy as np

from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_physical_pixel_sizes,
    compute_roughness_index,
    compute_slope_degrees,
)


def test_compute_physical_pixel_sizes():
    dx, dy = compute_physical_pixel_sizes(
        center_lat_deg=18.38, deg_per_px_lon=0.001, deg_per_px_lat=0.001
    )
    # 1 deg lat on Mars is ~59274.69m -> 0.001 deg is ~59.27m
    assert abs(dy - 59.27) < 0.5
    # 1 deg lon at 18.38 deg N is ~59274.69 * cos(18.38°) ~ 56251.6m -> 0.001 deg is ~56.25m
    assert abs(dx - 56.25) < 0.5


def test_analytical_slope_computation():
    # Construct a synthetic planar ramp with 10% grade in X direction: dz/dx = 0.1
    # Expected slope: arctan(0.1) = 5.71059 degrees
    rows, cols = 50, 50
    dx, dy = 10.0, 10.0

    x_coords = np.arange(cols) * dx
    elevation = np.tile(0.1 * x_coords, (rows, 1))

    slopes = compute_slope_degrees(elevation, dx_meters=dx, dy_meters=dy)
    expected_slope_deg = math.degrees(math.atan(0.1))

    # Test interior cells (avoiding boundary approximations)
    interior = slopes[5:45, 5:45]
    np.testing.assert_allclose(interior, expected_slope_deg, rtol=1e-3)


def test_roughness_on_flat_vs_boulders():
    # Flat surface should have roughness 0.0
    flat_elevation = np.full((30, 30), -2500.0, dtype=np.float32)
    roughness_flat = compute_roughness_index(flat_elevation, kernel_size=3)
    np.testing.assert_allclose(roughness_flat, 0.0, atol=1e-5)

    # Bouldered surface with severe elevation fluctuations
    rough_elevation = flat_elevation.copy()
    rough_elevation[::2, ::2] += 25.0  # 25m local variance
    roughness_rough = compute_roughness_index(rough_elevation, kernel_size=3)
    assert np.max(roughness_rough) > 0.3


def test_traversability_mask():
    slopes = np.array([[5.0, 10.0, 15.0], [18.0, 22.0, 30.0], [2.0, 8.0, float("nan")]])
    roughness = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.1, 0.95, 0.2],  # (2, 1) exceeds max_roughness 0.85
        ]
    )

    mask = build_traversability_mask(
        slope_deg=slopes,
        roughness=roughness,
        max_slope_deg=20.0,
        max_roughness=0.85,
    )

    # (0, 0): slope 5 <= 20, rough 0.1 <= 0.85 -> True
    assert mask[0, 0] is np.True_
    # (1, 1): slope 22 > 20 -> False
    assert mask[1, 1] is np.False_
    # (1, 2): slope 30 > 20 -> False
    assert mask[1, 2] is np.False_
    # (2, 1): rough 0.95 > 0.85 -> False
    assert mask[2, 1] is np.False_
    # (2, 2): slope NaN -> False
    assert mask[2, 2] is np.False_
