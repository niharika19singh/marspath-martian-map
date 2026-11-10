import numpy as np
from scipy import ndimage

from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE, meters_per_degree_lon


def compute_physical_pixel_sizes(
    center_lat_deg: float,
    deg_per_px_lon: float,
    deg_per_px_lat: float,
) -> tuple[float, float]:
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

    Rigorous nodata handling:
    - Nodata cells are isolated before differentiation so placeholder values
      (e.g. -9999 or -32768) never contaminate valid neighbouring cells.
    - Cells adjacent to nodata boundaries are conservatively masked with NaN.
    """
    # Create clean float array with NaNs at nodata cells
    elev_clean = elevation_grid.astype(np.float64).copy()
    if nodata_mask is not None:
        elev_clean[nodata_mask] = np.nan

    # Compute 2D gradient with physical step sizes in meters
    # np.gradient naturally propagates NaN to immediate neighbor differences
    dz_dy, dz_dx = np.gradient(elev_clean, dy_meters, dx_meters)

    grad_mag = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_rad = np.arctan(grad_mag)
    slope_deg = np.degrees(slope_rad)

    # Explicitly ensure nodata cells are NaN
    if nodata_mask is not None:
        # Dilate nodata mask by 1 cell to catch cells contaminated by central difference
        dilated_mask = ndimage.binary_dilation(nodata_mask, structure=np.ones((3, 3)))
        slope_deg[dilated_mask] = np.nan

    return slope_deg.astype(np.float32)


def compute_roughness_index(
    elevation_grid: np.ndarray,
    kernel_size: int = 3,
    nodata_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Computes localized Terrain Ruggedness Index (TRI) representing micro-topographic roughness.
    Defined as the standard deviation of elevation differences within a localized moving window,
    normalized to a bounded index [0.0, 1.0].

    Nodata handling:
    - Uses masked window convolution so nodata cells cannot corrupt the local mean or variance.
    - Cells with insufficient valid neighbours or in nodata are masked with NaN.
    """
    elev = elevation_grid.astype(np.float64).copy()
    valid_mask = np.ones_like(elev, dtype=bool)

    if nodata_mask is not None:
        valid_mask = ~nodata_mask
        elev[~valid_mask] = 0.0

    # Number of valid cells in local window
    window_cells = float(kernel_size * kernel_size)
    valid_count = (
        ndimage.uniform_filter(
            valid_mask.astype(np.float64), size=kernel_size, mode="constant", cval=0.0
        )
        * window_cells
    )

    # Sum of elevation and sum of squared elevation in window
    elev_sum = (
        ndimage.uniform_filter(elev, size=kernel_size, mode="constant", cval=0.0) * window_cells
    )
    elev_sq_sum = (
        ndimage.uniform_filter(elev**2, size=kernel_size, mode="constant", cval=0.0) * window_cells
    )

    # Safe division avoiding division by zero
    safe_valid = valid_count >= 3.0  # Require at least 3 valid samples in window
    mean = np.zeros_like(elev)
    mean[safe_valid] = elev_sum[safe_valid] / valid_count[safe_valid]

    mean_sq = np.zeros_like(elev)
    mean_sq[safe_valid] = elev_sq_sum[safe_valid] / valid_count[safe_valid]

    variance = np.maximum(mean_sq - mean**2, 0.0)
    std_dev = np.sqrt(variance)

    # Normalize std_dev: 0m -> 0.0, >= 25m -> 1.0
    roughness = np.clip(std_dev / 25.0, 0.0, 1.0).astype(np.float32)

    # Invalidate cells that were nodata or had insufficient valid neighbors
    invalid = (~safe_valid) | (~valid_mask)
    if nodata_mask is not None:
        dilated_mask = ndimage.binary_dilation(nodata_mask, structure=np.ones((3, 3)))
        invalid = invalid | dilated_mask

    roughness[invalid] = np.nan
    return roughness


def build_traversability_mask(
    slope_deg: np.ndarray,
    roughness: np.ndarray,
    max_slope_deg: float = 20.0,
    max_roughness: float = 0.85,
    nodata_mask: np.ndarray | None = None,
    avoid_unobserved_terrain: bool = True,
) -> np.ndarray:
    """
    Creates a binary boolean traversability mask:
    True = Traversable cell
    False = Impassable hazard or untraversable terrain

    If avoid_unobserved_terrain is True:
    Cells with missing elevation data, NaN slopes, or adjacent to nodata holes
    are strictly untraversable (False).
    """
    valid_slope = ~np.isnan(slope_deg)
    valid_rough = ~np.isnan(roughness)

    traversable = (
        (slope_deg <= max_slope_deg) & (roughness <= max_roughness) & valid_slope & valid_rough
    )

    if nodata_mask is not None:
        # Nodata cells are always impassable
        traversable[nodata_mask] = False
        if avoid_unobserved_terrain:
            # Conservative barrier around unobserved terrain
            dilated = ndimage.binary_dilation(nodata_mask, structure=np.ones((3, 3)))
            traversable[dilated] = False

    return traversable
