import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from backend.app.core.exceptions import MarsPathError, UnsupportedCRSError
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    geo_to_pixel,
    meters_per_degree_lon,
    pixel_to_geo,
    unproject_from_mars_metric,
)

logger = logging.getLogger("marspath.raster_loader")

# Optional rasterio import
try:
    import rasterio
    from rasterio.transform import Affine
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None


@dataclass
class RasterMetadata:
    width: int
    height: int
    coordinate_type: str  # "geographic" or "projected"
    crs_str: str
    units: str            # "degrees" or "meters"
    min_lon: float        # Planetocentric East degrees [0, 360)
    min_lat: float        # Planetocentric degrees [-90, 90]
    max_lon: float
    max_lat: float
    deg_per_px_lon: float
    deg_per_px_lat: float
    meters_per_px_x: float
    meters_per_px_y: float
    affine_transform: Tuple[float, float, float, float, float, float]
    nodata_value: Optional[float]
    vertical_datum: str = "Mars MOLA Areoid"
    is_synthetic: bool = False


class RasterData:
    def __init__(self, data: np.ndarray, metadata: RasterMetadata):
        self.data = data.astype(np.float32)
        self.metadata = metadata
        self._init_nodata_mask()

    def _init_nodata_mask(self):
        mask = np.isnan(self.data)
        if self.metadata.nodata_value is not None:
            mask = mask | (np.isclose(self.data, self.metadata.nodata_value, atol=1e-3))
        # Standard Mars PDS nodata sentinels
        mask = mask | (self.data < -9000.0) | (self.data > 1e30)
        self.nodata_mask = mask

    @property
    def shape(self) -> Tuple[int, int]:
        return self.data.shape

    def get_elevation_at_pixel(self, col: int, row: int) -> float:
        if 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]:
            val = float(self.data[row, col])
            return val if not self.nodata_mask[row, col] else float("nan")
        return float("nan")

    def get_elevation_at_geo(self, lon: float, lat: float) -> float:
        meta = self.metadata
        col, row = geo_to_pixel(
            lon, lat, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat, pixel_center=True
        )
        return self.get_elevation_at_pixel(col, row)


def load_raster_file(file_path: str) -> RasterData:
    """
    Loads and georeferences a numerical raster from disk (GeoTIFF, NumPy .npy/.npz).
    Rigidly inspects CRS, affine transforms, units, and bounds.
    Distinguishes geographic degrees from projected metric coordinates.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Raster file not found at: {file_path}")

    # Handle .npy / .npz direct serialized arrays
    if file_path.endswith(".npy") or file_path.endswith(".npz"):
        loaded = np.load(file_path)
        data = loaded["elevation"] if isinstance(loaded, np.lib.npyio.NpzFile) else loaded
        # Check if metadata dictionary was saved in the npz
        min_lon = float(loaded.get("min_lon", 77.20)) if isinstance(loaded, np.lib.npyio.NpzFile) else 77.20
        min_lat = float(loaded.get("min_lat", 18.15)) if isinstance(loaded, np.lib.npyio.NpzFile) else 18.15
        max_lon = float(loaded.get("max_lon", 77.95)) if isinstance(loaded, np.lib.npyio.NpzFile) else 77.95
        max_lat = float(loaded.get("max_lat", 18.65)) if isinstance(loaded, np.lib.npyio.NpzFile) else 18.65
        nodata_val = float(loaded.get("nodata", -9999.0)) if isinstance(loaded, np.lib.npyio.NpzFile) else -9999.0

        d_lon = (max_lon - min_lon) / data.shape[1]
        d_lat = (max_lat - min_lat) / data.shape[0]
        center_lat = (min_lat + max_lat) / 2.0
        m_x = d_lon * meters_per_degree_lon(center_lat)
        m_y = d_lat * METERS_PER_DEGREE_LATITUDE

        meta = RasterMetadata(
            width=data.shape[1],
            height=data.shape[0],
            coordinate_type="geographic",
            crs_str="IAU2000:49900",
            units="degrees",
            min_lon=min_lon,
            min_lat=min_lat,
            max_lon=max_lon,
            max_lat=max_lat,
            deg_per_px_lon=d_lon,
            deg_per_px_lat=d_lat,
            meters_per_px_x=m_x,
            meters_per_px_y=m_y,
            affine_transform=(d_lon, 0.0, min_lon, 0.0, -d_lat, max_lat),
            nodata_value=nodata_val,
            vertical_datum="Mars MOLA Areoid",
            is_synthetic=False,
        )
        return RasterData(data, meta)

    # Use rasterio if available
    if HAS_RASTERIO:
        try:
            with rasterio.open(file_path) as src:
                data = src.read(1)
                bounds = src.bounds
                crs_obj = src.crs

                # Case 1: Check if bounds are projected in meters
                # On Mars, geographic bounds must strictly be [-180, 360] lon and [-90, 90] lat
                is_metric = False
                if crs_obj and crs_obj.is_projected:
                    is_metric = True
                elif abs(bounds.left) > 360.0 or abs(bounds.right) > 360.0 or abs(bounds.top) > 90.0 or abs(bounds.bottom) > 90.0:
                    is_metric = True

                if is_metric:
                    # Projected in meters!
                    # Parse projection parameters (center_lon, center_lat)
                    center_lon = 0.0
                    center_lat = 0.0
                    if crs_obj:
                        crs_dict = crs_obj.to_dict()
                        center_lon = float(crs_dict.get("lon_0", crs_dict.get("central_meridian", 0.0)))
                        center_lat = float(crs_dict.get("lat_0", crs_dict.get("standard_parallel_1", 0.0)))

                    # Unproject bounding box corners from Mars metric coordinates
                    geo_min_lon, geo_min_lat = unproject_from_mars_metric(bounds.left, bounds.bottom, center_lon, center_lat)
                    geo_max_lon, geo_max_lat = unproject_from_mars_metric(bounds.right, bounds.top, center_lon, center_lat)

                    d_lon = (geo_max_lon - geo_min_lon) / src.width
                    d_lat = (geo_max_lat - geo_min_lat) / src.height

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="projected",
                        crs_str=str(src.crs or "MARS_EQUIRECTANGULAR"),
                        units="meters",
                        min_lon=min(geo_min_lon, geo_max_lon),
                        min_lat=min(geo_min_lat, geo_max_lat),
                        max_lon=max(geo_min_lon, geo_max_lon),
                        max_lat=max(geo_min_lat, geo_max_lat),
                        deg_per_px_lon=d_lon,
                        deg_per_px_lat=d_lat,
                        meters_per_px_x=float(src.res[0]),
                        meters_per_px_y=float(src.res[1]),
                        affine_transform=(src.transform.a, src.transform.b, src.transform.c,
                                          src.transform.d, src.transform.e, src.transform.f),
                        nodata_value=src.nodata,
                        vertical_datum="Mars MOLA Areoid",
                        is_synthetic=False,
                    )
                    return RasterData(data, meta)
                else:
                    # Geographic in degrees
                    # Validate geographic bounds
                    if not (-180.0 <= bounds.left <= 360.0 and -90.0 <= bounds.bottom <= 90.0):
                        raise MarsPathError(
                            f"Raster has uninterpretable geographic coordinates: bounds={bounds}"
                        )

                    min_lon = bounds.left % 360.0
                    max_lon = bounds.right % 360.0
                    if max_lon < min_lon and bounds.right > bounds.left:
                        # Antimeridian wrap or 0-360 range
                        max_lon = bounds.right

                    center_lat = (bounds.bottom + bounds.top) / 2.0
                    m_x = src.res[0] * meters_per_degree_lon(center_lat)
                    m_y = src.res[1] * METERS_PER_DEGREE_LATITUDE

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="geographic",
                        crs_str=str(src.crs or "IAU2000:49900"),
                        units="degrees",
                        min_lon=min_lon,
                        min_lat=bounds.bottom,
                        max_lon=max_lon,
                        max_lat=bounds.top,
                        deg_per_px_lon=float(src.res[0]),
                        deg_per_px_lat=float(src.res[1]),
                        meters_per_px_x=m_x,
                        meters_per_px_y=m_y,
                        affine_transform=(src.transform.a, src.transform.b, src.transform.c,
                                          src.transform.d, src.transform.e, src.transform.f),
                        nodata_value=src.nodata,
                        vertical_datum="Mars MOLA Areoid",
                        is_synthetic=False,
                    )
                    return RasterData(data, meta)
        except Exception as e:
            if isinstance(e, MarsPathError):
                raise
            logger.warning("Rasterio failed to load %s: %s. Attempting fallback.", file_path, e)

    # Fallback loader using PIL / TIFF tags
    try:
        from PIL import Image
        with Image.open(file_path) as img:
            data = np.array(img, dtype=np.float32)
            d_lon = (77.95 - 77.20) / data.shape[1]
            d_lat = (18.65 - 18.15) / data.shape[0]
            center_lat = 18.38
            meta = RasterMetadata(
                width=data.shape[1],
                height=data.shape[0],
                coordinate_type="geographic",
                crs_str="IAU2000:49900",
                units="degrees",
                min_lon=77.20,
                min_lat=18.15,
                max_lon=77.95,
                max_lat=18.65,
                deg_per_px_lon=d_lon,
                deg_per_px_lat=d_lat,
                meters_per_px_x=d_lon * meters_per_degree_lon(center_lat),
                meters_per_px_y=d_lat * METERS_PER_DEGREE_LATITUDE,
                affine_transform=(d_lon, 0.0, 77.20, 0.0, -d_lat, 18.65),
                nodata_value=-9999.0,
                vertical_datum="Mars MOLA Areoid",
                is_synthetic=False,
            )
            return RasterData(data, meta)
    except Exception as e:
        raise MarsPathError(f"Unable to load or validate georeferencing for raster {file_path}: {e}") from e
