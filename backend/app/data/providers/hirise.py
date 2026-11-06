import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    MarsPathError,
    TerrainDataUnavailableError,
    UnsupportedCRSError,
)
from backend.app.data.manifest import DATA_CATALOG_MANIFEST, verify_manifest_provenance
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.geospatial.raster_loader import (
    HAS_PYPROJ,
    HAS_RASTERIO,
    RasterData,
    load_raster_file,
    pyproj,
    rasterio,
)
from backend.app.schemas.coordinates import BoundingBox, CRSInfo
from backend.app.schemas.mission import ScienceTarget
from backend.app.services.evidence_service import EvidenceService

logger = logging.getLogger("marspath.provider.hirise")


def _compute_file_sha256(file_path: str) -> str:
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception:
        return "unavailable_read_error"


def _compute_raster_statistics(raster: RasterData) -> dict[str, Any]:
    total_cells = int(raster.data.size)
    nodata_cells = int(raster.nodata_mask.sum())
    valid_cells = total_cells - nodata_cells
    valid_vals = raster.data[~raster.nodata_mask]
    min_elev = float(np.min(valid_vals)) if valid_cells > 0 else float("nan")
    max_elev = float(np.max(valid_vals)) if valid_cells > 0 else float("nan")
    mean_elev = float(np.mean(valid_vals)) if valid_cells > 0 else float("nan")
    return {
        "total_cells": total_cells,
        "valid_cells": valid_cells,
        "nodata_cells": nodata_cells,
        "valid_data_fraction": round(valid_cells / max(total_cells, 1), 4),
        "min_elevation_meters": round(min_elev, 2) if np.isfinite(min_elev) else None,
        "max_elevation_meters": round(max_elev, 2) if np.isfinite(max_elev) else None,
        "mean_elevation_meters": round(mean_elev, 2) if np.isfinite(mean_elev) else None,
    }


@dataclass
class HiRISEValidationResult:
    """Result of validating an optional local HiRISE DTM raster."""

    is_valid: bool
    status_code: str
    reason: str
    raster: RasterData | None = None


class HiRISERasterProvider(BaseRasterProvider):
    """
    Localized high-resolution terrain provider for the HiRISE Jezero Western Delta DTM (~1 m/px).

    Principles:
    - Strictly local and optional: never performs network calls or startup downloads.
    - Enforces rigorous planetary CRS, affine transform, metric resolution, spatial footprint,
      elevation unit, and valid-observation checks before allowing routing selection.
    - Maintains strict provenance honesty: local rasters without an independently verified
      manifest SHA-256 or cryptographic sidecar are reported as `valid_numeric_raster_unverified_source`.
    """

    DELTA_REGION_MIN_LON = 77.30
    DELTA_REGION_MAX_LON = 77.55
    DELTA_REGION_MIN_LAT = 18.30
    DELTA_REGION_MAX_LAT = 18.52

    MIN_RESOLUTION_METERS = 0.15
    MAX_RESOLUTION_METERS = 25.0
    MIN_VALID_OBSERVATION_FRACTION = 0.10
    MIN_VALID_CELL_COUNT = 25

    def __init__(self, dem_path: str | None = None, enabled: bool | None = None):
        settings = get_settings()
        self.dem_path = dem_path if dem_path is not None else settings.HIRISE_DEM_PATH
        self.enabled = enabled if enabled is not None else settings.USE_HIRISE_DEM
        self._cached_validation: HiRISEValidationResult | None = None
        self._manifest_entry = next(
            (p for p in DATA_CATALOG_MANIFEST if p["id"] == "dem_hirise_jezero_delta_1m"),
            {},
        )

    def validate_hirise_raster(self) -> HiRISEValidationResult:
        """
        Validates whether the optional local HiRISE DTM is enabled, present, geospatially valid,
        in a supported Mars CRS, and contains sufficient valid elevation observations.
        """
        if self._cached_validation is not None:
            return self._cached_validation

        if not self.enabled:
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="disabled",
                reason="HiRISE high-resolution DTM is disabled in configuration (MARSPATH_USE_HIRISE_DEM=false).",
                raster=None,
            )
            return self._cached_validation

        if not self.dem_path or not os.path.exists(self.dem_path):
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="missing_file",
                reason=f"Configured HiRISE DTM file does not exist at '{self.dem_path}'.",
                raster=None,
            )
            return self._cached_validation

        # Pre-check GeoTIFF header for CRS, affine transform, dtype, and elevation unit tags
        if self.dem_path.lower().endswith((".tif", ".tiff")) and HAS_RASTERIO:
            try:
                with rasterio.open(self.dem_path) as src:
                    if src.crs is None or not str(src.crs).strip():
                        self._cached_validation = HiRISEValidationResult(
                            is_valid=False,
                            status_code="rejected_missing_crs",
                            reason=f"HiRISE GeoTIFF '{self.dem_path}' lacks an explicit Coordinate Reference System (CRS).",
                            raster=None,
                        )
                        return self._cached_validation

                    crs_check = self._validate_mars_crs_object(src.crs)
                    if crs_check is not None:
                        self._cached_validation = HiRISEValidationResult(
                            is_valid=False,
                            status_code="rejected_invalid_crs",
                            reason=crs_check,
                            raster=None,
                        )
                        return self._cached_validation

                    tr = src.transform
                    det = tr.a * tr.e - tr.b * tr.d
                    if (
                        tr == rasterio.Affine.identity()
                        or abs(det) < 1e-18
                        or src.res[0] <= 0.0
                        or src.res[1] <= 0.0
                    ):
                        self._cached_validation = HiRISEValidationResult(
                            is_valid=False,
                            status_code="rejected_invalid_georeferencing",
                            reason=f"HiRISE GeoTIFF '{self.dem_path}' has a degenerate or uncalibrated identity affine transform.",
                            raster=None,
                        )
                        return self._cached_validation

                    dtype_str = str(src.dtypes[0]).lower()
                    if "uint8" in dtype_str or "bool" in dtype_str or "complex" in dtype_str:
                        self._cached_validation = HiRISEValidationResult(
                            is_valid=False,
                            status_code="rejected_non_elevation_raster",
                            reason=f"HiRISE raster dtype '{dtype_str}' indicates imagery/mask data rather than numerical elevation.",
                            raster=None,
                        )
                        return self._cached_validation

                    tags = {k.upper(): str(v).lower() for k, v in src.tags().items()}
                    unit_tag = tags.get(
                        "VERTICAL_UNIT", tags.get("ELEVATION_UNITS", tags.get("UNITS", "meters"))
                    )
                    if any(
                        bad in unit_tag
                        for bad in ("dn", "reflectance", "radiance", "albedo", "feet", "foot")
                    ):
                        self._cached_validation = HiRISEValidationResult(
                            is_valid=False,
                            status_code="rejected_non_elevation_raster",
                            reason=f"HiRISE raster declares unsupported vertical/value unit '{unit_tag}' (expected meters).",
                            raster=None,
                        )
                        return self._cached_validation
            except Exception as exc:
                self._cached_validation = HiRISEValidationResult(
                    is_valid=False,
                    status_code="rejected_corrupt_raster",
                    reason=f"Failed to inspect HiRISE GeoTIFF '{self.dem_path}': {exc}",
                    raster=None,
                )
                return self._cached_validation

        try:
            raster = load_raster_file(self.dem_path)
        except UnsupportedCRSError as exc:
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_invalid_crs",
                reason=f"HiRISE raster CRS rejected: {exc}",
                raster=None,
            )
            return self._cached_validation
        except MarsPathError as exc:
            code = (
                "rejected_missing_crs"
                if "lacks a crs" in str(exc).lower()
                else "rejected_invalid_georeferencing"
            )
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code=code,
                reason=f"HiRISE raster georeferencing rejected: {exc}",
                raster=None,
            )
            return self._cached_validation
        except Exception as exc:
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_corrupt_raster",
                reason=f"HiRISE raster load failed: {exc}",
                raster=None,
            )
            return self._cached_validation

        meta = raster.metadata

        if not meta.crs_str or meta.crs_str == "Unknown / Unspecified":
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_missing_crs",
                reason="HiRISE raster lacks an explicit Mars CRS declaration.",
                raster=None,
            )
            return self._cached_validation

        if not EvidenceService._is_established_mars_crs(meta.crs_str):
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_invalid_crs",
                reason=f"HiRISE raster CRS '{meta.crs_str}' is not an established Mars planetary CRS.",
                raster=None,
            )
            return self._cached_validation

        if raster.data.ndim != 2 or meta.height < 10 or meta.width < 10:
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_invalid_dimensions",
                reason=f"HiRISE raster dimensions ({meta.height}x{meta.width}) are below minimum viable 10x10 DTM grid.",
                raster=None,
            )
            return self._cached_validation

        res_x = float(meta.meters_per_px_x)
        res_y = float(meta.meters_per_px_y)
        if not (
            self.MIN_RESOLUTION_METERS <= res_x <= self.MAX_RESOLUTION_METERS
            and self.MIN_RESOLUTION_METERS <= res_y <= self.MAX_RESOLUTION_METERS
        ):
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_invalid_resolution",
                reason=(
                    f"HiRISE physical resolution ({res_x:.2f}m x {res_y:.2f}m) is outside the valid "
                    f"high-resolution DTM range [{self.MIN_RESOLUTION_METERS}, {self.MAX_RESOLUTION_METERS}] m/px."
                ),
                raster=None,
            )
            return self._cached_validation

        lon_span = meta.max_lon - meta.min_lon
        lat_span = meta.max_lat - meta.min_lat
        overlaps_delta = (
            meta.min_lon < self.DELTA_REGION_MAX_LON
            and meta.max_lon > self.DELTA_REGION_MIN_LON
            and meta.min_lat < self.DELTA_REGION_MAX_LAT
            and meta.max_lat > self.DELTA_REGION_MIN_LAT
        )
        if (
            not overlaps_delta
            or lon_span <= 0.0
            or lat_span <= 0.0
            or lon_span > 0.40
            or lat_span > 0.40
        ):
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_outside_jezero_delta_bounds",
                reason=(
                    f"HiRISE raster bounds [{meta.min_lon:.4f}, {meta.min_lat:.4f}, "
                    f"{meta.max_lon:.4f}, {meta.max_lat:.4f}] do not match the localized "
                    f"Jezero Western Delta coverage region."
                ),
                raster=None,
            )
            return self._cached_validation

        valid_mask = (
            ~raster.nodata_mask
            & np.isfinite(raster.data)
            & (raster.data >= -9000.0)
            & (raster.data <= 25000.0)
        )
        valid_count = int(np.sum(valid_mask))
        total_count = int(raster.data.size)
        valid_fraction = valid_count / total_count if total_count > 0 else 0.0

        if (
            valid_count < self.MIN_VALID_CELL_COUNT
            or valid_fraction < self.MIN_VALID_OBSERVATION_FRACTION
        ):
            self._cached_validation = HiRISEValidationResult(
                is_valid=False,
                status_code="rejected_insufficient_valid_observations",
                reason=(
                    f"HiRISE raster contains insufficient valid elevation observations "
                    f"({valid_count}/{total_count} cells, {valid_fraction * 100:.1f}% < "
                    f"{self.MIN_VALID_OBSERVATION_FRACTION * 100:.0f}% threshold)."
                ),
                raster=None,
            )
            return self._cached_validation

        self._cached_validation = HiRISEValidationResult(
            is_valid=True,
            status_code="ready",
            reason="HiRISE DTM validated and ready for localized high-resolution corridor selection.",
            raster=raster,
        )
        return self._cached_validation

    def _validate_mars_crs_object(self, crs_obj: Any) -> str | None:
        crs_str = str(crs_obj).strip()
        crs_upper = crs_str.upper()
        if any(
            tok in crs_upper
            for tok in ("WGS", "EPSG:4326", "EPSG:3857", "EARTH", "NAD83", "NAD27")
        ):
            return f"Earth CRS '{crs_str}' is forbidden for Mars HiRISE terrain analysis."

        if not EvidenceService._is_established_mars_crs(crs_str):
            return f"Coordinate Reference System '{crs_str}' is not a supported Mars planetary CRS."

        if HAS_PYPROJ:
            try:
                proj_crs = pyproj.CRS.from_user_input(crs_obj)
                if proj_crs.ellipsoid and proj_crs.ellipsoid.semi_major_metre:
                    radius = float(proj_crs.ellipsoid.semi_major_metre)
                    if not (3370000.0 <= radius <= 3405000.0):
                        return (
                            f"CRS semi-major radius ({radius:.1f} m) does not match Mars IAU2000 "
                            f"reference sphere (3,396,190 m)."
                        )
            except Exception as exc:
                return f"Unparseable CRS definition '{crs_str}': {exc}"

        return None

    def get_dem_raster(self) -> RasterData:
        res = self.validate_hirise_raster()
        if not res.is_valid or res.raster is None:
            raise TerrainDataUnavailableError(
                f"HiRISE DTM unavailable ({res.status_code}): {res.reason}"
            )
        return res.raster

    def get_bounds(self) -> BoundingBox:
        raster = self.get_dem_raster()
        return BoundingBox(
            min_lon=raster.metadata.min_lon,
            min_lat=raster.metadata.min_lat,
            max_lon=raster.metadata.max_lon,
            max_lat=raster.metadata.max_lat,
        )

    def get_crs_info(self) -> CRSInfo:
        return get_mars_crs_info()

    def is_synthetic(self) -> bool:
        return False

    def get_science_targets(self) -> list[ScienceTarget]:
        return SyntheticTerrainProvider().get_science_targets()

    def get_provenance(self) -> dict[str, Any]:
        """
        Returns strict, honest provenance metadata for the HiRISE DTM provider.
        Never claims verified NASA/USGS/UArizona source authenticity unless cryptographic
        manifest or sidecar verification succeeds.
        """
        res = self.validate_hirise_raster()
        if not res.is_valid or res.raster is None:
            return {
                "dataset_name": "HiRISE Jezero Crater Western Delta Digital Terrain Model (Not Loaded)",
                "official_product_id": None,
                "pds_doi": None,
                "official_source_url": None,
                "data_mode": "unavailable",
                "source_tier": "localized_high_resolution_dtm",
                "hirise_enabled": self.enabled,
                "real_dem_requested": self.enabled,
                "real_dem_loaded": False,
                "local_integrity_verified": False,
                "source_checksum_verified": False,
                "real_data_validation_status": res.status_code,
                "provenance_verification_method": "none_file_missing_or_invalid",
                "fallback_reason": res.reason,
                "dem_file_path": self.dem_path,
                "file_format": "None",
                "file_sha256": None,
                "crs": "None",
                "coordinate_type": "None",
                "units": "None",
                "vertical_datum": "None",
                "resolution_meters": 1.0,
                "native_resolution_meters": 1.0,
                "effective_resolution_meters": 1.0,
                "aggregation_applied": False,
                "aggregation_factor": 1,
                "aggregation_method": "none",
                "bounds": None,
                "nodata_value": None,
                "raster_statistics": None,
                "provenance_limitations": [res.reason],
            }

        meta = res.raster.metadata
        file_sha = _compute_file_sha256(self.dem_path)
        stats = _compute_raster_statistics(res.raster)
        is_verified, ver_method, matched_manifest = verify_manifest_provenance(
            file_sha256=file_sha,
            metadata_tags=meta.metadata_tags,
            file_path=self.dem_path,
        )

        is_geotiff = self.dem_path.lower().endswith((".tif", ".tiff"))
        file_format = "GeoTIFF" if is_geotiff else "NumPy (.npz/.npy)"
        native_res_m = round((meta.meters_per_px_x + meta.meters_per_px_y) / 2.0, 3)

        limitations: list[str] = []
        v_datum_lower = (meta.vertical_datum or "").lower()
        if "unknown" in v_datum_lower or "unspecified" in v_datum_lower:
            limitations.append(
                "Vertical datum is not declared in the local HiRISE raster header ('Unknown / Unspecified'); "
                "absolute elevations cannot be assumed tied to the MOLA areoid without external tie-point metadata."
            )
        limitations.append(
            "Localized coverage only (~1 m/px stereo DTM over Jezero Western Delta); cannot be combined "
            "with regional MOLA-HRSC grids in a single route."
        )
        limitations.append(
            "Even at ~1 m/px post spacing, orbital stereo DTMs have ~2-4 m horizontal feature scale and "
            "cannot resolve wheel-scale (<0.5 m) rocks, sharp outcrops, or regolith cohesion hazards."
        )

        if is_verified and matched_manifest:
            return {
                "dataset_name": matched_manifest.get("product_name")
                or matched_manifest.get("title")
                or "HiRISE Jezero Crater Western Delta Digital Terrain Model (DTM)",
                "official_product_id": matched_manifest["id"],
                "mission_instruments": matched_manifest.get(
                    "mission_instruments", ["MRO HiRISE Stereo Processing"]
                ),
                "data_publisher": matched_manifest.get(
                    "publisher", "USGS Astrogeology / University of Arizona"
                ),
                "pds_doi": matched_manifest.get("pds_doi") or matched_manifest.get("doi"),
                "official_source_url": matched_manifest.get("landing_page")
                or matched_manifest.get("official_url"),
                "data_mode": "real",
                "source_tier": "localized_high_resolution_dtm",
                "hirise_enabled": self.enabled,
                "real_dem_requested": True,
                "real_dem_loaded": True,
                "local_integrity_verified": True,
                "source_checksum_verified": True,
                "real_data_validation_status": "verified_source",
                "provenance_verification_method": ver_method,
                "fallback_reason": None,
                "dem_file_path": self.dem_path,
                "file_format": file_format,
                "file_sha256": file_sha,
                "crs": meta.crs_str,
                "coordinate_type": meta.coordinate_type,
                "units": meta.units,
                "vertical_datum": meta.vertical_datum,
                "resolution_meters": native_res_m,
                "native_resolution_meters": native_res_m,
                "effective_resolution_meters": native_res_m,
                "aggregation_applied": False,
                "aggregation_factor": 1,
                "aggregation_method": "none",
                "bounds": {
                    "min_lon": round(meta.min_lon, 6),
                    "min_lat": round(meta.min_lat, 6),
                    "max_lon": round(meta.max_lon, 6),
                    "max_lat": round(meta.max_lat, 6),
                },
                "nodata_value": meta.nodata_value,
                "raster_statistics": stats,
                "provenance_limitations": limitations,
            }

        local_ok: bool | None = None
        if ver_method == "unverified_sidecar_source_not_authenticated":
            local_ok = True
        elif ver_method in (
            "failed_local_sha256_integrity_mismatch",
            "failed_local_sidecar_corrupted_json",
        ):
            local_ok = False

        limitations.insert(
            0,
            "Raster is numerically valid and georeferenced to the Mars Jezero Western Delta region, "
            "but its upstream NASA PDS / UArizona HiRISE product authenticity has NOT been cryptographically verified.",
        )
        return {
            "dataset_name": f"Local Unverified Mars High-Resolution DTM ({os.path.basename(self.dem_path)})",
            "official_product_id": None,
            "mission_instruments": ["Unverified Local High-Resolution Stereo DTM"],
            "data_publisher": "Unknown / Local Origin",
            "pds_doi": None,
            "official_source_url": None,
            "data_mode": "real_unverified_source",
            "source_tier": "localized_high_resolution_dtm",
            "hirise_enabled": self.enabled,
            "real_dem_requested": True,
            "real_dem_loaded": True,
            "local_integrity_verified": local_ok,
            "source_checksum_verified": False,
            "real_data_validation_status": "valid_numeric_raster_unverified_source",
            "provenance_verification_method": ver_method,
            "fallback_reason": None,
            "dem_file_path": self.dem_path,
            "file_format": file_format,
            "file_sha256": file_sha,
            "crs": meta.crs_str,
            "coordinate_type": meta.coordinate_type,
            "units": meta.units,
            "vertical_datum": meta.vertical_datum,
            "resolution_meters": native_res_m,
            "native_resolution_meters": native_res_m,
            "effective_resolution_meters": native_res_m,
            "aggregation_applied": False,
            "aggregation_factor": 1,
            "aggregation_method": "none",
            "bounds": {
                "min_lon": round(meta.min_lon, 6),
                "min_lat": round(meta.min_lat, 6),
                "max_lon": round(meta.max_lon, 6),
                "max_lat": round(meta.max_lat, 6),
            },
            "nodata_value": meta.nodata_value,
            "raster_statistics": stats,
            "provenance_limitations": limitations,
        }
