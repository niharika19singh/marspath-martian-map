import math
from typing import Tuple
import numpy as np
from scipy import ndimage
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE, meters_per_degree_lon


def compute_physical_pixel_sizes(
    center_lat_deg: float,
    deg_per_px_lon: float,
    deg_per_px_lat: float,
) -> Tuple[float, float]:
    """
    Calculates physical metric pixel widths and heights (dx, dy) on Mars surface in meters.
    Crucial: Longitude degrees compress with cos(latitude).
    """
    dy_meters = deg_per_px_lat * METERS_PER_DEGREE_LATITUDE
    dx_meters = deg_per_px_lon * meters_per_degree_lon(center_lat_deg)
    return max(dx_meters, 0.1), max(dy_meters, 0.1)


def compute_slope_degrees(
    elevation_grid: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    nodata_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Computes terrain slope in degrees using 2D finite difference gradients in physical meters.
    Slope = arctan( sqrt( (dz/dx)^2 + (dz/dy)^2 ) ) * (180 / pi).
    Cells adjacent to or containing nodata values are masked with NaN.
    """
    # 2D gradient: axis 0 is rows (Y, North to South), axis 1 is cols (X, West to East)
    # np.gradient uses second-order central differences in the interior and first-order at boundaries
    dz_dy, dz_dx = np.gradient(elevation_grid, dy_meters, dx_meters)

    grad_mag = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_rad = np.arctan(grad_mag)
    slope_deg = np.degrees(slope_rad)

    if nodata_mask is not None:
        slope_deg[nodata_mask] = np.nan

    return slope_deg


def compute_roughness_index(
    elevation_grid: np.ndarray,
    kernel_size: int = 3,
    nodata_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Computes localized Terrain Ruggedness Index (TRI) representing micro-topographic roughness.
    Defined as the standard deviation of elevation differences within a localized moving window,
    normalized to a bounded index [0.0, 1.0].
    """
    # Moving mean using uniform filter
    mean_filter = ndimage.uniform_filter(elevation_grid, size=kernel_size, mode="reflect")
    # Moving square mean
    sqr_filter = ndimage.uniform_filter(elevation_grid**2, size=kernel_size, mode="reflect")

    # Local variance = E[X^2] - (E[X])^2
    variance = np.maximum(sqr_filter - mean_filter**2, 0.0)
    std_dev = np.sqrt(variance)

    # Normalize std_dev: 0m std dev -> 0.0, >= 25m std dev -> 1.0 (extreme boulder/rough field)
    roughness = np.clip(std_dev / 25.0, 0.0, 1.0)

    if nodata_mask is not None:
        roughness[nodata_mask] = np.nan

    return roughness


def build_traversability_mask(
    slope_deg: np.ndarray,
    roughness: np.ndarray,
    max_slope_deg: float = 20.0,
    max_roughness: float = 0.85,
    nodata_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Creates a binary boolean traversability mask:
    True = Traversable cell
    False = Impassable hazard or untraversable terrain
    """
    traversable = (
        (slope_deg <= max_slope_deg)
        & (roughness <= max_roughness)
        & (~np.isnan(slope_deg))
        & (~np.isnan(roughness))
    )

    if nodata_mask is not None:
        traversable[nodata_mask] = False

    return traversable
