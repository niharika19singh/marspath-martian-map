import logging
import os
import zlib
from dataclasses import dataclass, field
from typing import Any

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
    vertical_units: str = "Unknown / Unspecified"
    metadata_tags: dict[str, str] = field(default_factory=dict)
    is_synthetic: bool = False


VERTICAL_UNIT_TAG_KEYS: tuple[str, ...] = (
    "VERTICAL_UNIT",
    "VERTICAL_UNITS",
    "ELEVATION_UNIT",
    "ELEVATION_UNITS",
    "Z_UNIT",
    "Z_UNITS",
    "UNIT_TYPE",
    "UNITTYPE",
    "UNIT",
    "UNITS",
)

_EXPLICIT_METRE_TOKENS: frozenset[str] = frozenset(
    {
        "m",
        "meter",
        "meters",
        "metre",
        "metres",
        "meter (m)",
        "meters (m)",
        "metre (m)",
        "metres (m)",
        "si_meter",
        "si_meters",
        "meters above areoid",
        "metres above areoid",
        "m above areoid",
    }
)

_CONVERTIBLE_METRIC_VERTICAL_UNITS: dict[str, float] = {
    "cm": 0.01,
    "centimeter": 0.01,
    "centimeters": 0.01,
    "centimetre": 0.01,
    "centimetres": 0.01,
    "mm": 0.001,
    "millimeter": 0.001,
    "millimeters": 0.001,
    "millimetre": 0.001,
    "millimetres": 0.001,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "kilometre": 1000.0,
    "kilometres": 1000.0,
}

_NON_ELEVATION_VALUE_UNITS: frozenset[str] = frozenset(
    {
        "dn",
        "digital_number",
        "digital number",
        "reflectance",
        "radiance",
        "albedo",
        "kelvin",
        "celsius",
        "degc",
        "db",
        "decibel",
        "index",
        "ratio",
        "unitless",
        "dimensionless",
        "count",
        "counts",
        "byte",
        "bytes",
        "pixel",
        "pixels",
        "uint8",
        "rgb",
    }
)

_UNSUPPORTED_VERTICAL_UNITS: frozenset[str] = frozenset(
    {
        "ft",
        "foot",
        "feet",
        "us_survey_foot",
        "survey_foot",
        "in",
        "inch",
        "inches",
        "yd",
        "yard",
        "yards",
        "mi",
        "mile",
        "miles",
        "deg",
        "degree",
        "degrees",
        "arcsec",
        "arcmin",
        "rad",
        "radian",
        "radians",
    }
)

_UNKNOWN_UNIT_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "",
        "none",
        "null",
        "unknown",
        "unspecified",
        "n/a",
        "na",
        "?",
        "undefined",
    }
)


def normalize_vertical_unit_token(
    raw_value: str | None,
) -> tuple[str | None, float | None, str]:
    """
    Normalizes an explicit vertical elevation unit string.
    Returns (canonical_unit, scale_to_meters, status_code).
    Never infers units from filenames, product IDs, or numeric magnitudes.
    """
    if raw_value is None:
        return None, None, "rejected_unknown_vertical_units"
    norm = " ".join(str(raw_value).strip().lower().split())
    if norm in _UNKNOWN_UNIT_PLACEHOLDERS:
        return None, None, "rejected_unknown_vertical_units"
    if norm in _EXPLICIT_METRE_TOKENS:
        return "meters", 1.0, "valid"
    if norm in _CONVERTIBLE_METRIC_VERTICAL_UNITS:
        return "meters", _CONVERTIBLE_METRIC_VERTICAL_UNITS[norm], "converted"
    if norm in _NON_ELEVATION_VALUE_UNITS or any(
        tok in norm for tok in ("reflectance", "radiance", "albedo", "digital number")
    ):
        return None, None, "rejected_non_elevation_raster"
    if norm in _UNSUPPORTED_VERTICAL_UNITS or any(
        tok in norm for tok in ("feet", "foot", "survey_foot", "degree", "radian")
    ):
        return None, None, "rejected_unsupported_vertical_units"
    return None, None, "rejected_unknown_vertical_units"


def inspect_vertical_unit_declarations(
    band_unit: str | None,
    band_tags: dict[str, Any] | None,
    dataset_tags: dict[str, Any] | None,
) -> tuple[bool, str, str, float, str]:
    """
    Positively validates vertical elevation units across Rasterio band units (`src.units`),
    GeoTIFF band tags (`src.tags(1)`), and dataset tags (`src.tags()`).

    Returns:
        (is_valid, status_code, reason, scale_to_meters, resolved_unit_label)
    """
    declarations: list[tuple[str, str]] = []
    if band_unit is not None and str(band_unit).strip() != "":
        declarations.append(("band_1.unit", str(band_unit).strip()))

    if band_tags:
        b_upper = {str(k).upper(): str(v).strip() for k, v in band_tags.items()}
        for key in VERTICAL_UNIT_TAG_KEYS:
            if key in b_upper and b_upper[key] != "":
                declarations.append((f"band_1.tag[{key}]", b_upper[key]))

    if dataset_tags:
        d_upper = {str(k).upper(): str(v).strip() for k, v in dataset_tags.items()}
        for key in VERTICAL_UNIT_TAG_KEYS:
            if key in d_upper and d_upper[key] != "":
                declarations.append((f"dataset.tag[{key}]", d_upper[key]))

    if not declarations:
        return (
            False,
            "rejected_unknown_vertical_units",
            (
                "Raster lacks explicit vertical elevation unit metadata in band units or GeoTIFF tags "
                "(expected explicit metre units; missing or unknown units are rejected)."
            ),
            1.0,
            "Unknown / Unspecified",
        )

    resolved_scales: list[tuple[str, str, float, str]] = []
    for src_label, raw_val in declarations:
        canonical, scale, code = normalize_vertical_unit_token(raw_val)
        if canonical is None or scale is None:
            return (
                False,
                code,
                (
                    f"Raster declares invalid, unknown, or unsupported vertical unit '{raw_val}' "
                    f"in {src_label} ({code}; expected explicit metre units)."
                ),
                1.0,
                raw_val,
            )
        resolved_scales.append((src_label, raw_val, float(scale), code))

    first_scale = resolved_scales[0][2]
    for src_label, raw_val, scale, _ in resolved_scales[1:]:
        if abs(scale - first_scale) > 1e-12:
            return (
                False,
                "rejected_unknown_vertical_units",
                (
                    f"Raster contains conflicting vertical unit declarations across metadata fields: "
                    f"{resolved_scales[0][0]}='{resolved_scales[0][1]}' vs {src_label}='{raw_val}'."
                ),
                1.0,
                "Ambiguous / Conflicting",
            )

    primary_src, primary_raw, final_scale, final_code = resolved_scales[0]
    if final_code == "converted":
        reason = (
            f"Verified explicit vertical unit '{primary_raw}' in {primary_src}; "
            f"converted to meters with scale factor {final_scale:g}."
        )
    else:
        reason = f"Verified explicit metre vertical unit '{primary_raw}' in {primary_src}."
    return True, final_code, reason, final_scale, "meters"


def get_file_identity(file_path: str) -> tuple[str, int, int, int, int, int] | None:
    """
    Computes a fast, deterministic file identity key combining:
    - Canonical resolved path (`realpath`)
    - File size in bytes (`st_size`)
    - Modification time in nanoseconds (`st_mtime_ns`)
    - Metadata change time in nanoseconds (`st_ctime_ns`)
    - Inode number (`st_ino`)
    - Lightweight 12 KB header/middle/tail CRC32 sample (`zlib.crc32`) so even
      sub-millisecond same-size in-place file rewrites are detected without
      reading or hashing the full raster.
    """
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        resolved = os.path.realpath(os.path.abspath(file_path))
        st = os.stat(resolved)
        size = int(st.st_size)
        crc = 0
        if size > 0:
            with open(resolved, "rb") as f:
                crc = zlib.crc32(f.read(4096), crc)
                if size > 8192:
                    f.seek(size // 2)
                    crc = zlib.crc32(f.read(4096), crc)
                if size > 4096:
                    f.seek(max(0, size - 4096))
                    crc = zlib.crc32(f.read(4096), crc)
        return (
            resolved,
            size,
            int(st.st_mtime_ns),
            int(st.st_ctime_ns),
            int(st.st_ino),
            int(crc),
        )
    except OSError:
        return None


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

    def mark_readonly(self) -> None:
        """Marks internal elevation and nodata arrays as read-only so shared cached rasters cannot be mutated."""
        self.data.flags.writeable = False
        self.nodata_mask.flags.writeable = False

    def get_elevation_at_pixel(self, col: int, row: int) -> float:
        if 0 <= row < self.data.shape[0] and 0 <= col < self.data.shape[1]:
            val = float(self.data[row, col])
            return val if not self.nodata_mask[row, col] else float("nan")
        return float("nan")

    def geo_to_native_pixel_float(self, lon: float, lat: float) -> tuple[float, float]:
        """
        Maps Mars planetocentric (lon, lat) in degrees to continuous pixel coordinates
        (col_float, row_float) using the raster's actual CRS and affine transform.
        In PixelIsArea convention, pixel (c, r) spans [c, c+1) x [r, r+1) with center (c+0.5, r+0.5).
        """
        meta = self.metadata
        a, b, c_off, d, e, f_off = meta.affine_transform
        det = a * e - b * d

        if meta.coordinate_type == "projected" and HAS_PYPROJ and meta.crs_str not in ("", "Unknown / Unspecified"):
            mars_geo_crs = pyproj.CRS("+proj=longlat +R=3396190 +no_defs")
            transformer = pyproj.Transformer.from_crs(
                mars_geo_crs, pyproj.CRS.from_user_input(meta.crs_str), always_xy=True
            )
            x_val, y_val = transformer.transform(lon, lat)
        else:
            x_val, y_val = lon, lat

        if abs(det) > 1e-18:
            dx = x_val - c_off
            dy = y_val - f_off
            col_f = (e * dx - b * dy) / det
            row_f = (-d * dx + a * dy) / det
            return float(col_f), float(row_f)

        col, row = geo_to_pixel(
            lon,
            lat,
            meta.min_lon,
            meta.max_lat,
            meta.deg_per_px_lon,
            meta.deg_per_px_lat,
            pixel_center=True,
        )
        return float(col) + 0.5, float(row) + 0.5

    def get_elevation_at_geo(self, lon: float, lat: float) -> float:
        meta = self.metadata
        if meta.coordinate_type == "projected" and HAS_PYPROJ and meta.crs_str not in ("", "Unknown / Unspecified"):
            col_f, row_f = self.geo_to_native_pixel_float(lon, lat)
            col = int(np.floor(col_f))
            row = int(np.floor(row_f))
            return self.get_elevation_at_pixel(col, row)
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
    """Rejects terrestrial Earth datums or non-Mars planetary radii."""
    if crs_obj is None:
        return
    crs_str = str(crs_obj).upper()
    if (
        "WGS" in crs_str
        or "EPSG:4326" in crs_str
        or "EPSG:3857" in crs_str
        or "EARTH" in crs_str
        or "NAD83" in crs_str
    ):
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
        if semi_major and not (3370000.0 <= semi_major <= 3405000.0):
            raise UnsupportedCRSError(
                f"Non-Mars ellipsoid radius ({semi_major:.1f}m) in {file_path}",
                supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
            )
    if HAS_PYPROJ:
        try:
            proj_crs = pyproj.CRS.from_user_input(crs_obj)
            if proj_crs.ellipsoid and proj_crs.ellipsoid.semi_major_metre:
                sm = float(proj_crs.ellipsoid.semi_major_metre)
                if abs(sm - 6378137.0) < 10000.0 or not (3370000.0 <= sm <= 3405000.0):
                    raise UnsupportedCRSError(
                        f"Unsupported planetary datum radius ({sm:.1f}m) in {file_path}",
                        supported=["Mars IAU2000 Sphere (R=3,396,190m)"],
                    )
        except UnsupportedCRSError:
            raise
        except Exception:
            pass


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
        npz_crs = str(loaded.get("crs", "Unknown / Unspecified")).strip() or "Unknown / Unspecified"
        tags = {str(k): str(v) for k, v in loaded.items() if k not in ("elevation", "data")}

        d_lon = (max_lon - min_lon) / data.shape[1]
        d_lat = (max_lat - min_lat) / data.shape[0]
        center_lat = (min_lat + max_lat) / 2.0
        m_x = d_lon * meters_per_degree_lon(center_lat)
        m_y = d_lat * METERS_PER_DEGREE_LATITUDE

        unit_ok, unit_status, unit_reason, unit_scale, resolved_v_unit = (
            inspect_vertical_unit_declarations(None, None, tags)
        )
        tags["_VERTICAL_UNIT_VALID"] = "true" if unit_ok else "false"
        tags["_VERTICAL_UNIT_STATUS"] = unit_status
        tags["_VERTICAL_UNIT_REASON"] = unit_reason
        tags["_VERTICAL_UNIT_SCALE"] = str(unit_scale)

        data_f32 = data.astype(np.float32).copy()
        if unit_ok and abs(unit_scale - 1.0) > 1e-12:
            raw_nd = np.isnan(data_f32) | (
                np.isclose(data_f32, nodata_val, atol=1e-3)
                if nodata_val is not None
                else np.zeros_like(data_f32, dtype=bool)
            )
            data_f32[~raw_nd] *= float(unit_scale)
            data_f32[raw_nd] = np.nan
            tags["VERTICAL_UNIT_CONVERSION"] = unit_reason

        meta = RasterMetadata(
            width=data_f32.shape[1],
            height=data_f32.shape[0],
            coordinate_type="geographic",
            crs_str=npz_crs,
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
            vertical_units=resolved_v_unit,
            metadata_tags=tags,
            is_synthetic=False,
        )
        return RasterData(data_f32, meta)

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

                # Extract vertical datum and vertical unit declarations from band + dataset tags
                tags = dict(src.tags())
                band_tags = dict(src.tags(1)) if src.count >= 1 else {}
                band_unit = src.units[0] if (src.units and len(src.units) > 0) else None
                unit_ok, unit_status, unit_reason, unit_scale, resolved_v_unit = (
                    inspect_vertical_unit_declarations(band_unit, band_tags, tags)
                )
                merged_tags = dict(tags)
                for bk, bv in band_tags.items():
                    if bk not in merged_tags:
                        merged_tags[bk] = bv
                if band_unit is not None and str(band_unit).strip():
                    merged_tags["_BAND_1_UNIT"] = str(band_unit).strip()
                merged_tags["_VERTICAL_UNIT_VALID"] = "true" if unit_ok else "false"
                merged_tags["_VERTICAL_UNIT_STATUS"] = unit_status
                merged_tags["_VERTICAL_UNIT_REASON"] = unit_reason
                merged_tags["_VERTICAL_UNIT_SCALE"] = str(unit_scale)

                vert_datum = merged_tags.get(
                    "VERTICAL_DATUM",
                    merged_tags.get(
                        "DATUM",
                        "Unknown / Unspecified (datum tag not declared in raster metadata)",
                    ),
                )

                data_f32 = data.astype(np.float32).copy()
                if unit_ok and abs(unit_scale - 1.0) > 1e-12:
                    raw_nd = np.isnan(data_f32) | (
                        np.isclose(data_f32, float(src.nodata), atol=1e-3)
                        if src.nodata is not None
                        else np.zeros_like(data_f32, dtype=bool)
                    )
                    data_f32[~raw_nd] *= float(unit_scale)
                    data_f32[raw_nd] = np.nan
                    merged_tags["VERTICAL_UNIT_CONVERSION"] = unit_reason

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
                            corners_x = [bounds.left, bounds.left, bounds.right, bounds.right]
                            corners_y = [bounds.bottom, bounds.top, bounds.bottom, bounds.top]
                            geo_lons, geo_lats = transformer.transform(corners_x, corners_y)
                            norm_lons = [float(lon) % 360.0 for lon in geo_lons]
                            min_lon = min(norm_lons)
                            max_lon = max(norm_lons)
                            min_lat = min(float(lat) for lat in geo_lats)
                            max_lat = max(float(lat) for lat in geo_lats)
                        except Exception as te:
                            raise UnsupportedCRSError(
                                f"Failed to transform projected CRS '{crs_obj}' to Mars geographic: {te}"
                            ) from te
                    else:
                        raise MarsPathError(
                            "pyproj is required to unproject metric GeoTIFFs to Mars geographic coordinates."
                        )

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
                        vertical_units=resolved_v_unit,
                        metadata_tags=merged_tags,
                        is_synthetic=False,
                    )
                    return RasterData(data_f32, meta)
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
                        crs_str=str(crs_obj).strip() if (crs_obj and str(crs_obj).strip()) else "Unknown / Unspecified",
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
                        vertical_units=resolved_v_unit,
                        metadata_tags=merged_tags,
                        is_synthetic=False,
                    )
                    return RasterData(data_f32, meta)
        except Exception as e:
            if isinstance(e, MarsPathError):
                raise
            raise MarsPathError(f"Rasterio failed to load or validate GeoTIFF '{file_path}': {e}") from e

    raise MarsPathError(
        f"Unable to read GeoTIFF '{file_path}'. Rasterio geospatial library is required to ingest real GeoTIFF files."
    )
