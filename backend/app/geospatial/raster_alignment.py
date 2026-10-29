import numpy as np

from backend.app.core.exceptions import ComputationalBoundExceededError
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    geo_to_pixel,
    meters_per_degree_lon,
    pixel_to_geo,
)
from backend.app.geospatial.raster_loader import RasterData, RasterMetadata
from backend.app.schemas.coordinates import MarsCoordinate


def crop_mission_corridor(
    raster: RasterData,
    start: MarsCoordinate,
    dest: MarsCoordinate,
    padding_meters: float = 3000.0,
    max_cells: int = 250000,
) -> tuple[np.ndarray, RasterMetadata, tuple[int, int], tuple[int, int]]:
    """
    Crops a subgrid from the master raster surrounding the start and destination points
    with a buffer/padding margin in physical meters.

    Returns:
        (cropped_elevation, cropped_metadata, (start_col, start_row), (dest_col, dest_row))
        where start and dest indices are local to the cropped subgrid.
    """
    meta = raster.metadata
    center_lat = (start.lat + dest.lat) / 2.0

    # Convert padding from meters to degrees
    pad_lat_deg = padding_meters / METERS_PER_DEGREE_LATITUDE
    pad_lon_deg = padding_meters / meters_per_degree_lon(center_lat)

    # Determine bounding box in geographic coordinates
    min_lon = max(min(start.lon, dest.lon) - pad_lon_deg, meta.min_lon)
    max_lon = min(max(start.lon, dest.lon) + pad_lon_deg, meta.max_lon)
    min_lat = max(min(start.lat, dest.lat) - pad_lat_deg, meta.min_lat)
    max_lat = min(max(start.lat, dest.lat) + pad_lat_deg, meta.max_lat)

    # Convert to master raster pixel indices
    c_min, r_min = geo_to_pixel(
        min_lon, max_lat, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )
    c_max, r_max = geo_to_pixel(
        max_lon, min_lat, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )

    # Clamp indices to valid raster bounds
    c_min = max(0, min(c_min, meta.width - 1))
    c_max = max(c_min + 1, min(c_max, meta.width))
    r_min = max(0, min(r_min, meta.height - 1))
    r_max = max(r_min + 1, min(r_max, meta.height))

    crop_h = r_max - r_min
    crop_w = c_max - c_min
    total_cells = crop_h * crop_w

    if total_cells > max_cells:
        raise ComputationalBoundExceededError(
            f"Mission corridor window requires {total_cells} cells ({crop_w}x{crop_h}), exceeding safety limit of {max_cells}.",
            dimensions=(crop_w, crop_h),
            max_allowed=max_cells,
        )

    # Crop array
    cropped_elev = raster.data[r_min:r_max, c_min:c_max].copy()

    # Compute updated subgrid geographic bounding box
    sub_min_lon, sub_max_lat = pixel_to_geo(
        c_min, r_min, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )
    sub_max_lon, sub_min_lat = pixel_to_geo(
        c_max, r_max, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )

    cropped_meta = RasterMetadata(
        width=crop_w,
        height=crop_h,
        coordinate_type=meta.coordinate_type,
        crs_str=meta.crs_str,
        units=meta.units,
        min_lon=sub_min_lon,
        min_lat=sub_min_lat,
        max_lon=sub_max_lon,
        max_lat=sub_max_lat,
        deg_per_px_lon=meta.deg_per_px_lon,
        deg_per_px_lat=meta.deg_per_px_lat,
        meters_per_px_x=meta.meters_per_px_x,
        meters_per_px_y=meta.meters_per_px_y,
        affine_transform=(
            meta.deg_per_px_lon,
            0.0,
            sub_min_lon,
            0.0,
            -meta.deg_per_px_lat,
            sub_max_lat,
        ),
        nodata_value=meta.nodata_value,
        vertical_datum=meta.vertical_datum,
        is_synthetic=meta.is_synthetic,
    )

    # Start and Dest local pixel indices
    s_col, s_row = geo_to_pixel(
        start.lon, start.lat, sub_min_lon, sub_max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )
    d_col, d_row = geo_to_pixel(
        dest.lon, dest.lat, sub_min_lon, sub_max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat
    )

    # Clamp within subgrid
    s_col = max(0, min(s_col, crop_w - 1))
    s_row = max(0, min(s_row, crop_h - 1))
    d_col = max(0, min(d_col, crop_w - 1))
    d_row = max(0, min(d_row, crop_h - 1))

    return cropped_elev, cropped_meta, (s_col, s_row), (d_col, d_row)
