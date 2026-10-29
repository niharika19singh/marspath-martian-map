import logging
import os
from dataclasses import dataclass

import numpy as np

from backend.app.core.exceptions import MarsPathError, UnsupportedCRSError
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    geo_to_pixel,
    meters_per_degree_lon,
)

logger = logging.getLogger("marspath.raster_loader")

# Optional rasterio and pyproj imports
try:
    import rasterio
    import rasterio.crs

    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None

try:
    import pyproj

    HAS_PYPROJ = True
except ImportError:
    HAS_PYPROJ = False
    pyproj = None


@dataclass
class RasterMetadata:
    width: int
    height: int
    coordinate_type: str  # "geographic" or "projected"
    crs_str: str
    units: str  # "degrees" or "meters"
    min_lon: float  # Planetocentric East degrees [0, 360)
    min_lat: float  # Planetocentric degrees [-90, 90]
    max_lon: float
    max_lat: float
    deg_per_px_lon: float
    deg_per_px_lat: float
    meters_per_px_x: float
    meters_per_px_y: float
    affine_transform: tuple[float, float, float, float, float, float]
    nodata_value: float | None
    vertical_datum: str = "Unknown / Unspecified"
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
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    def get_elevation_at_pixel(self, col: int, row: int) -> float:
        if 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]:
            val = float(self.data[row, col])
            return val if not self.nodata_mask[row, col] else float("nan")
        return float("nan")

    def get_elevation_at_geo(self, lon: float, lat: float) -> float:
        meta = self.metadata
        col, row = geo_to_pixel(
            lon,
            lat,
            meta.min_lon,
            meta.max_lat,
            meta.deg_per_px_lon,
            meta.deg_per_px_lat,
            pixel_center=True,
        )
        return self.get_elevation_at_pixel(col, row)


def _validate_not_earth_crs(crs_obj, file_path: str) -> None:
    """Rejects terrestrial Earth datums (e.g. WGS84 with semi-major radius ~6378km)."""
    if crs_obj is None:
        return
    crs_str = str(crs_obj).upper()
    if "WGS" in crs_str or "EPSG:4326" in crs_str or "EPSG:3857" in crs_str:
        raise UnsupportedCRSError(
            crs_str,
            supported=["IAU2000:49900", "MARS2000_SPHERE", "MARS_EQUIRECTANGULAR"],
        )
    if hasattr(crs_obj, "ellipsoid") and crs_obj.ellipsoid:
        semi_major = crs_obj.ellipsoid.semi_major_metre
        if semi_major and abs(semi_major - 6378137.0) < 10000.0:
            raise UnsupportedCRSError(
                f"Earth WGS84 (radius ~{semi_major:.0f}m) in {file_path}",
                supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
            )


def load_raster_file(file_path: str) -> RasterData:
    """
    Loads and georeferences a numerical raster from disk (GeoTIFF, NumPy .npy/.npz).
    Rigidly inspects CRS, affine transforms, units, and bounds.
    Distinguishes geographic degrees from projected metric coordinates.
    Never assigns arbitrary invented bounds when metadata is missing.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Raster file not found at: {file_path}")

    # Handle .npy / .npz direct serialized arrays with explicit headers
    if file_path.endswith(".npy") or file_path.endswith(".npz"):
        loaded = np.load(file_path)
        data = loaded["elevation"] if isinstance(loaded, np.lib.npyio.NpzFile) else loaded

        if not isinstance(loaded, np.lib.npyio.NpzFile) or "min_lon" not in loaded:
            raise MarsPathError(
                f"NumPy raster '{file_path}' lacks required georeferencing header fields (min_lon, min_lat, max_lon, max_lat)."
            )

        min_lon = float(loaded["min_lon"])
        min_lat = float(loaded["min_lat"])
        max_lon = float(loaded["max_lon"])
        max_lat = float(loaded["max_lat"])
        nodata_val = float(loaded.get("nodata", -9999.0))
        vert_datum = str(loaded.get("vertical_datum", "Unknown / Unspecified"))

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
            vertical_datum=vert_datum,
            is_synthetic=False,
        )
        return RasterData(data, meta)

    # GeoTIFF loading via Rasterio
    if HAS_RASTERIO:
        try:
            with rasterio.open(file_path) as src:
                data = src.read(1)
                bounds = src.bounds
                crs_obj = src.crs
                transform = src.transform

                # 1. Reject Earth CRS
                _validate_not_earth_crs(crs_obj, file_path)

                # 2. Check if bounds are projected in meters
                is_metric = False
                if crs_obj and crs_obj.is_projected:
                    is_metric = True
                elif (
                    abs(bounds.left) > 360.0
                    or abs(bounds.right) > 360.0
                    or abs(bounds.top) > 90.0
                    or abs(bounds.bottom) > 90.0
                ):
                    is_metric = True

                # Extract vertical datum from tags if present
                tags = src.tags()
                vert_datum = tags.get(
                    "VERTICAL_DATUM",
                    tags.get("DATUM", "Unknown / Unspecified (datum tag not declared in raster metadata)"),
                )

                if is_metric:
                    # Projected coordinates in meters!
                    if crs_obj is None:
                        raise MarsPathError(
                            f"GeoTIFF '{file_path}' has metric bounds ({bounds.left:.1f}, {bounds.bottom:.1f}) but lacks a CRS definition. Cannot interpret projection."
                        )

                    # Transform metric bounds into Mars geographic degrees
                    if HAS_PYPROJ:
                        mars_geo_crs = pyproj.CRS("+proj=longlat +R=3396190 +no_defs")
                        try:
                            transformer = pyproj.Transformer.from_crs(
                                pyproj.CRS.from_user_input(crs_obj), mars_geo_crs, always_xy=True
                            )
                            geo_left, geo_bottom = transformer.transform(bounds.left, bounds.bottom)
                            geo_right, geo_top = transformer.transform(bounds.right, bounds.top)
                        except Exception as te:
                            raise UnsupportedCRSError(
                                f"Failed to transform projected CRS '{crs_obj}' to Mars geographic: {te}"
                            ) from te
                    else:
                        raise MarsPathError(
                            "pyproj is required to unproject metric GeoTIFFs to Mars geographic coordinates."
                        )

                    # Normalize lon into [0, 360)
                    min_lon = min(geo_left, geo_right) % 360.0
                    max_lon = max(geo_left, geo_right) % 360.0
                    if max_lon < min_lon:
                        max_lon = max(geo_left, geo_right)

                    min_lat = min(geo_bottom, geo_top)
                    max_lat = max(geo_bottom, geo_top)

                    d_lon = (max_lon - min_lon) / src.width
                    d_lat = (max_lat - min_lat) / src.height

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="projected",
                        crs_str=str(crs_obj),
                        units="meters",
                        min_lon=min_lon,
                        min_lat=min_lat,
                        max_lon=max_lon,
                        max_lat=max_lat,
                        deg_per_px_lon=d_lon,
                        deg_per_px_lat=d_lat,
                        meters_per_px_x=float(src.res[0]),
                        meters_per_px_y=float(src.res[1]),
                        affine_transform=(
                            transform.a,
                            transform.b,
                            transform.c,
                            transform.d,
                            transform.e,
                            transform.f,
                        ),
                        nodata_value=src.nodata,
                        vertical_datum=vert_datum,
                        is_synthetic=False,
                    )
                    return RasterData(data, meta)
                else:
                    # Geographic in degrees
                    if not (-180.0 <= bounds.left <= 360.0 and -90.0 <= bounds.bottom <= 90.0):
                        raise MarsPathError(
                            f"GeoTIFF '{file_path}' has invalid geographic bounds: {bounds}"
                        )

                    min_lon = bounds.left % 360.0
                    max_lon = bounds.right % 360.0
                    if max_lon < min_lon and bounds.right > bounds.left:
                        max_lon = bounds.right

                    center_lat = (bounds.bottom + bounds.top) / 2.0
                    m_x = src.res[0] * meters_per_degree_lon(center_lat)
                    m_y = src.res[1] * METERS_PER_DEGREE_LATITUDE

                    meta = RasterMetadata(
                        width=src.width,
                        height=src.height,
                        coordinate_type="geographic",
                        crs_str=str(crs_obj or "IAU2000:49900"),
                        units="degrees",
                        min_lon=min_lon,
                        min_lat=bounds.bottom,
                        max_lon=max_lon,
                        max_lat=bounds.top,
                        deg_per_px_lon=float(src.res[0]),
                        deg_per_px_lat=float(src.res[1]),
                        meters_per_px_x=m_x,
                        meters_per_px_y=m_y,
                        affine_transform=(
                            transform.a,
                            transform.b,
                            transform.c,
                            transform.d,
                            transform.e,
                            transform.f,
                        ),
                        nodata_value=src.nodata,
                        vertical_datum=vert_datum,
                        is_synthetic=False,
                    )
                    return RasterData(data, meta)
        except Exception as e:
            if isinstance(e, MarsPathError):
                raise
            raise MarsPathError(f"Rasterio failed to load or validate GeoTIFF '{file_path}': {e}") from e

    raise MarsPathError(
        f"Unable to read GeoTIFF '{file_path}'. Rasterio geospatial library is required to ingest real GeoTIFF files."
    )
