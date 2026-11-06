import copy
import hashlib
import logging
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.app.core.config import get_settings
from backend.app.core.exceptions import TerrainDataUnavailableError
from backend.app.data.manifest import verify_manifest_provenance
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.geospatial.raster_loader import (
    RasterData,
    get_file_identity,
    load_raster_file,
)
from backend.app.schemas.coordinates import BoundingBox, CRSInfo
from backend.app.schemas.mission import ScienceTarget

logger = logging.getLogger("marspath.mola_hrsc_provider")


@dataclass
class _MOLACachedEntry:
    file_identity: tuple[str, int, int, int, int, int]
    raster: RasterData
    file_sha256: str | None = None
    sidecar_identity: tuple[str, int, int, int, int, int] | None = None
    provenance: dict[str, Any] | None = None


class MOLAHRSCRasterProvider(BaseRasterProvider):
    """
    Data provider for NASA/ESA MOLA-HRSC blended numerical elevation models.
    Strictly obeys MARSPATH_USE_REAL_DEM, MARSPATH_DEM_PATH, and synthetic fallback policy.
    Never silently describes synthetic rasters as real NASA data.
    Uses a thread-safe bounded process cache keyed by file identity.
    """

    MAX_CACHE_ENTRIES = 4
    _CACHE_LOCK = threading.RLock()
    _PROCESS_CACHE: OrderedDict[tuple[str, int, int, int, int, int], _MOLACachedEntry] = (
        OrderedDict()
    )

    def __init__(self, dem_path: str | None = None):
        settings = get_settings()
        self.dem_path = dem_path or settings.DEM_PATH
        self.use_real_dem = settings.USE_REAL_DEM
        self.allow_fallback = settings.ALLOW_SYNTHETIC_FALLBACK
        self._raster_data: RasterData | None = None
        self._cached_file_id: tuple[str, int, int, int, int, int] | None = None
        self._fallback_provider: SyntheticTerrainProvider | None = None
        self._fallback_occurred: bool = False
        self._fallback_reason: str = ""

    def _get_fallback(self) -> SyntheticTerrainProvider:
        if self._fallback_provider is None:
            self._fallback_provider = SyntheticTerrainProvider()
        return self._fallback_provider

    def get_dem_raster(self) -> RasterData:
        if not self.use_real_dem:
            if self._raster_data is not None and self._raster_data.metadata.is_synthetic:
                return self._raster_data
            logger.info("Operating in synthetic test mode (MARSPATH_USE_REAL_DEM=false).")
            self._raster_data = self._get_fallback().get_dem_raster()
            self._raster_data.mark_readonly()
            return self._raster_data

        file_id = get_file_identity(self.dem_path)
        if file_id is not None:
            with self._CACHE_LOCK:
                cached = self._PROCESS_CACHE.get(file_id)
                if cached is not None:
                    self._PROCESS_CACHE.move_to_end(file_id)
                    self._raster_data = cached.raster
                    self._cached_file_id = file_id
                    self._fallback_occurred = False
                    self._fallback_reason = ""
                    return cached.raster

        # Real DEM was requested
        logger.info("Real DEM requested. Checking path: %s", self.dem_path)
        if file_id is None or not os.path.exists(self.dem_path):
            err_detail = ""
            err_file = f"{self.dem_path}.provision_error.json"
            if os.path.exists(err_file):
                try:
                    import json

                    with open(err_file, encoding="utf-8") as ef:
                        err_data = json.load(ef)
                    if err_data.get("error"):
                        err_detail = f" (provisioning error: {err_data['error']})"
                except Exception:
                    pass
            msg = (
                f"Real DEM requested (MARSPATH_USE_REAL_DEM=true) but file not found at: "
                f"{self.dem_path}{err_detail}"
            )
            if not self.allow_fallback:
                raise TerrainDataUnavailableError(msg)
            logger.warning("%s. Falling back to synthetic test model.", msg)
            self._fallback_occurred = True
            self._fallback_reason = msg
            self._raster_data = self._get_fallback().get_dem_raster()
            self._raster_data.mark_readonly()
            return self._raster_data

        try:
            loaded_raster = load_raster_file(self.dem_path)
            self._validate_dem_integrity(loaded_raster)
            loaded_raster.mark_readonly()
            with self._CACHE_LOCK:
                stale = [
                    k for k in self._PROCESS_CACHE if k[0] == file_id[0] and k != file_id
                ]
                for k in stale:
                    self._PROCESS_CACHE.pop(k, None)
                self._PROCESS_CACHE[file_id] = _MOLACachedEntry(
                    file_identity=file_id, raster=loaded_raster
                )
                while len(self._PROCESS_CACHE) > self.MAX_CACHE_ENTRIES:
                    self._PROCESS_CACHE.popitem(last=False)
            self._raster_data = loaded_raster
            self._cached_file_id = file_id
            self._fallback_occurred = False
            self._fallback_reason = ""
            logger.info("Successfully loaded and validated real DEM from %s", self.dem_path)
            return self._raster_data
        except Exception as e:
            msg = f"Failed to load or validate real DEM at '{self.dem_path}': {e}"
            if not self.allow_fallback:
                raise TerrainDataUnavailableError(msg) from e
            logger.warning("%s. Falling back to synthetic test model.", msg)
            self._fallback_occurred = True
            self._fallback_reason = msg
            self._raster_data = self._get_fallback().get_dem_raster()
            self._raster_data.mark_readonly()
            return self._raster_data

    def _validate_dem_integrity(self, raster: RasterData) -> None:
        """
        Validates that loaded file is genuine numerical elevation data, not an arbitrary
        image or malformed array, and is situated over the Jezero target domain.
        """
        import numpy as np

        if raster.data.dtype.kind not in ("f", "i", "u"):
            raise TerrainDataUnavailableError(
                f"Raster '{self.dem_path}' does not contain numerical elevation values (dtype={raster.data.dtype})."
            )

        if raster.data.ndim != 2 or raster.data.shape[0] < 10 or raster.data.shape[1] < 10:
            raise TerrainDataUnavailableError(
                f"Raster '{self.dem_path}' has invalid dimensions {raster.data.shape} for a 2D DEM."
            )

        # Inspect elevation values excluding nodata
        valid = raster.data[~raster.nodata_mask] if hasattr(raster, "nodata_mask") else raster.data
        if valid.size == 0 or np.isnan(valid).all():
            raise TerrainDataUnavailableError(f"Raster '{self.dem_path}' contains only nodata or NaN values.")

        min_val = float(np.min(valid))
        max_val = float(np.max(valid))
        if min_val < -9000.0 or max_val > 25000.0:
            raise TerrainDataUnavailableError(
                f"Raster '{self.dem_path}' contains out-of-range Martian elevations ({min_val:.1f}m to {max_val:.1f}m)."
            )

        # Inspect resolution (50m nominal HRSC/MOLA, HiRISE 1m, MOLA 500m)
        res_x = raster.metadata.meters_per_px_x
        res_y = raster.metadata.meters_per_px_y
        if not (0.2 <= res_x <= 2000.0 and 0.2 <= res_y <= 2000.0):
            raise TerrainDataUnavailableError(
                f"Raster '{self.dem_path}' has non-geospatial resolution ({res_x:.1f}m x {res_y:.1f}m)."
            )

        # Inspect coverage overlap with Jezero region
        meta = raster.metadata
        if meta.max_lon < 75.0 or meta.min_lon > 80.0 or meta.max_lat < 16.0 or meta.min_lat > 21.0:
            raise TerrainDataUnavailableError(
                f"Raster '{self.dem_path}' bounds ({meta.min_lon:.2f}°E to {meta.max_lon:.2f}°E, "
                f"{meta.min_lat:.2f}°N to {meta.max_lat:.2f}°N) do not intersect Jezero Crater."
            )

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

    def get_provenance(self) -> dict[str, Any]:
        raster = self.get_dem_raster()
        if self.use_real_dem and not self._fallback_occurred and not raster.metadata.is_synthetic:
            file_id = self._cached_file_id or get_file_identity(self.dem_path)
            sidecar_id = get_file_identity(f"{self.dem_path}.provenance.json")
            with self._CACHE_LOCK:
                entry = self._PROCESS_CACHE.get(file_id) if file_id is not None else None
                if (
                    entry is not None
                    and entry.provenance is not None
                    and entry.sidecar_identity == sidecar_id
                ):
                    return copy.deepcopy(entry.provenance)

                if entry is not None and entry.file_sha256 is not None:
                    file_sha256 = entry.file_sha256
                else:
                    # 1. Compute file SHA-256 once per file identity
                    sha256_hash = hashlib.sha256()
                    try:
                        with open(self.dem_path, "rb") as f:
                            for chunk in iter(lambda: f.read(65536), b""):
                                sha256_hash.update(chunk)
                        file_sha256 = sha256_hash.hexdigest()
                    except Exception as err:
                        logger.warning("Could not compute SHA-256 for '%s': %s", self.dem_path, err)
                        file_sha256 = "unavailable_read_error"

            # 2. File format
            ext = os.path.splitext(self.dem_path)[1].lower()
            file_format = {
                ".tif": "GeoTIFF",
                ".tiff": "GeoTIFF",
                ".npz": "NumPy Array Archive (.npz)",
                ".npy": "NumPy Array (.npy)",
                ".img": "PDS3 IMG Raster",
                ".cub": "USGS ISIS3 Cube",
            }.get(ext, f"Binary Raster ({ext})")

            # 3. Raster no-data statistics
            total_cells = int(raster.data.size)
            nodata_cells = int(raster.nodata_mask.sum())
            valid_cells = total_cells - nodata_cells
            valid_vals = raster.data[~raster.nodata_mask]
            min_elev = float(np.min(valid_vals)) if valid_cells > 0 else float("nan")
            max_elev = float(np.max(valid_vals)) if valid_cells > 0 else float("nan")
            mean_elev = float(np.mean(valid_vals)) if valid_cells > 0 else float("nan")

            # 4. Authoritative source verification
            is_verified, method, matched_prod = verify_manifest_provenance(
                file_sha256=file_sha256,
                metadata_tags=raster.metadata.metadata_tags,
                file_path=self.dem_path,
            )

            local_integrity_verified: bool | None = None
            source_checksum_verified: bool = False

            if is_verified and matched_prod:
                validation_status = "verified_source"
                data_mode = "real"
                local_integrity_verified = True
                source_checksum_verified = True
                dataset_name = matched_prod["product_name"]
                official_product_id = matched_prod["id"]
                official_source_url = (
                    matched_prod.get("landing_page") or matched_prod.get("upstream_url")
                )
                pds_doi = matched_prod.get("pds_doi")
                mission_instruments = matched_prod.get("mission_instruments")
                data_publisher = matched_prod.get("publisher")
                limitations = [
                    matched_prod.get("limitations", "Official product limitations."),
                    "Route cost weights and categorical risk levels are deterministic multi-criteria decision heuristics, not calibrated probabilities of rover failure.",
                ]
            elif method == "official_endpoint_retrieved_checksum_unverified" and matched_prod:
                validation_status = "official_endpoint_retrieved_checksum_unverified"
                data_mode = "real_official_endpoint_unverified_checksum"
                local_integrity_verified = True
                source_checksum_verified = False
                dataset_name = matched_prod["product_name"]
                official_product_id = matched_prod["id"]
                official_source_url = (
                    matched_prod.get("landing_page") or matched_prod.get("upstream_url")
                )
                pds_doi = matched_prod.get("pds_doi")
                mission_instruments = matched_prod.get("mission_instruments")
                data_publisher = matched_prod.get("publisher")
                limitations = [
                    "Retrieved from official USGS/PDS HTTPS endpoint via GDAL /vsicurl/ HTTP Range extraction; local GeoTIFF SHA-256 integrity is verified.",
                    "Full 11.38 GB upstream file MD5 checksum (e98092a06bea74d5ec9a704dcd1fe318) was NOT independently verified over all source bytes because only the Jezero Crater sub-window was streamed.",
                    matched_prod.get("limitations", "Official product limitations."),
                    "Route cost weights and categorical risk levels are deterministic multi-criteria decision heuristics, not calibrated probabilities of rover failure.",
                ]
            elif method in (
                "failed_local_sha256_integrity_mismatch",
                "failed_local_sidecar_corrupted_json",
            ):
                validation_status = "valid_numeric_raster_unverified_source"
                data_mode = "real_unverified_source"
                local_integrity_verified = False
                source_checksum_verified = False
                dataset_name = "Local Numerical Elevation Model (Integrity Check Failed / Unverified)"
                official_product_id = None
                official_source_url = None
                pds_doi = None
                mission_instruments = ["Unverified / Unknown"]
                data_publisher = "Unknown / Local Origin"
                limitations = [
                    "CRITICAL: Local file SHA-256 digest does NOT match the digest recorded in its provenance sidecar (file may have been tampered with or corrupted).",
                    "Authoritative NASA/ESA/USGS source provenance could NOT be verified.",
                    "Treated as an unverified local numeric terrain raster; cannot be reported as certified planetary data.",
                ]
            elif method == "unverified_sidecar_source_not_authenticated":
                validation_status = "valid_numeric_raster_unverified_source"
                data_mode = "real_unverified_source"
                local_integrity_verified = True
                source_checksum_verified = False
                dataset_name = "Local Numerical Elevation Model (Unverified Source)"
                official_product_id = None
                official_source_url = None
                pds_doi = None
                mission_instruments = ["Unverified / Unknown"]
                data_publisher = "Unknown / Local Origin"
                limitations = [
                    "Local file SHA-256 matches its sidecar, preserving local file integrity since creation.",
                    "Authoritative NASA/ESA/USGS source provenance could NOT be verified: sidecar source checksum claims are not backed by independently verified upstream source bytes.",
                    "Treated as an unverified local numeric terrain raster; cannot be reported as certified planetary data.",
                ]
            elif method == "unverified_source_unauthenticated_tags" and matched_prod:
                validation_status = "valid_numeric_raster_unverified_source"
                data_mode = "real_unverified_source"
                local_integrity_verified = None
                source_checksum_verified = False
                dataset_name = "Local Numerical Elevation Model (Unverified Source / Unauthenticated Tags)"
                official_product_id = None
                official_source_url = None
                pds_doi = None
                mission_instruments = ["Unverified / Unknown"]
                data_publisher = "Unknown / Local Origin"
                limitations = [
                    "Raster passed 2D numerical and Jezero spatial-integrity checks (valid float array, plausible Mars elevations, valid planetary CRS).",
                    f"Raster header contains unauthenticated tags referencing '{matched_prod['id']}', but authoritative source provenance could NOT be cryptographically authenticated (no verified upstream checksum chain or registered manifest hash).",
                    "Treated as an unverified local numeric terrain raster; cannot be attributed to NASA or USGS or reported as certified flight-grade planetary data.",
                ]
            else:
                validation_status = "valid_numeric_raster_unverified_source"
                data_mode = "real_unverified_source"
                local_integrity_verified = None
                source_checksum_verified = False
                dataset_name = "Local Numerical Elevation Model (Unverified Source)"
                official_product_id = None
                official_source_url = None
                pds_doi = None
                mission_instruments = ["Unverified / Unknown"]
                data_publisher = "Unknown / Local Origin"
                limitations = [
                    "Raster passed 2D numerical and Jezero spatial-integrity checks (valid float array, plausible Mars elevations, valid planetary CRS).",
                    "Authoritative NASA/ESA/USGS source provenance could NOT be verified: file SHA-256 does not match official planetary catalog records and no verified upstream source bytes are present.",
                    "Treated as an unverified local numeric terrain raster; cannot be reported as certified flight-grade planetary data.",
                ]

            prov_out = {
                "dataset_name": dataset_name,
                "official_product_id": official_product_id,
                "official_source_url": official_source_url,
                "pds_doi": pds_doi,
                "mission_instruments": mission_instruments,
                "data_publisher": data_publisher,
                "file_path": self.dem_path,
                "file_format": file_format,
                "file_sha256": file_sha256,
                "local_integrity_verified": local_integrity_verified,
                "source_checksum_verified": source_checksum_verified,
                "real_dem_requested": self.use_real_dem,
                "real_dem_loaded": True,
                "data_mode": data_mode,
                "real_data_validation_status": validation_status,
                "provenance_verification_method": method,
                "is_synthetic": False,
                "horizontal_crs": raster.metadata.crs_str,
                "coordinate_type": raster.metadata.coordinate_type,
                "projection_units": raster.metadata.units,
                "pixel_resolution_meters": {
                    "x": round(raster.metadata.meters_per_px_x, 2),
                    "y": round(raster.metadata.meters_per_px_y, 2),
                },
                "spatial_coverage": {
                    "min_lon": round(raster.metadata.min_lon, 4),
                    "max_lon": round(raster.metadata.max_lon, 4),
                    "min_lat": round(raster.metadata.min_lat, 4),
                    "max_lat": round(raster.metadata.max_lat, 4),
                },
                "raster_statistics": {
                    "total_cells": total_cells,
                    "valid_cells": valid_cells,
                    "nodata_cells": nodata_cells,
                    "valid_data_fraction": round(valid_cells / max(total_cells, 1), 4),
                    "min_elevation_meters": round(min_elev, 2),
                    "max_elevation_meters": round(max_elev, 2),
                    "mean_elevation_meters": round(mean_elev, 2),
                },
                "vertical_datum": raster.metadata.vertical_datum,
                "provenance_limitations": limitations,
            }
            with self._CACHE_LOCK:
                if entry is not None:
                    entry.file_sha256 = file_sha256
                    entry.sidecar_identity = sidecar_id
                    entry.provenance = prov_out
            return copy.deepcopy(prov_out)

        # Operating on synthetic
        provenance = self._get_fallback().get_provenance()
        provenance["local_integrity_verified"] = None
        provenance["source_checksum_verified"] = False
        if self._fallback_occurred:
            provenance["data_mode"] = "synthetic_fallback"
            provenance["real_data_validation_status"] = "incomplete_missing_genuine_dem"
            provenance["fallback_reason"] = self._fallback_reason
            provenance["real_dem_requested"] = True
            provenance["real_dem_loaded"] = False
            provenance["file_path"] = self.dem_path
            provenance["provenance_verification_method"] = "none_file_missing_or_invalid"
            provenance["provenance_limitations"] = [
                f"Real DEM was requested at '{self.dem_path}', but file was not found or failed validation: {self._fallback_reason}.",
                "Real-data validation remains incomplete. Fallback synthetic model active.",
                "Route cost weights and categorical risk levels are deterministic multi-criteria decision heuristics, not calibrated probabilities of rover failure.",
            ]
        else:
            provenance["data_mode"] = "synthetic_test_fixture"
            provenance["real_data_validation_status"] = "synthetic_test_fixture"
            provenance["real_dem_requested"] = False
            provenance["real_dem_loaded"] = False
            provenance["provenance_verification_method"] = "deterministic_synthetic_procedural_generator"
            provenance["provenance_limitations"] = [
                "Operating on deterministic synthetic/procedural test fixture for Jezero Crater. Real NASA DEM is not loaded.",
                "Elevation and terrain gradients are mathematically synthesized; not suitable for flight-grade navigation.",
                "Route cost weights and categorical risk levels are deterministic multi-criteria decision heuristics, not calibrated probabilities of rover failure.",
            ]
        return provenance

    def is_synthetic(self) -> bool:
        raster = self.get_dem_raster()
        return raster.metadata.is_synthetic

    def get_science_targets(self) -> list[ScienceTarget]:
        return self._get_fallback().get_science_targets()


_SHARED_MOLA_LOCK = threading.RLock()
_SHARED_MOLA_INSTANCES: dict[tuple[str, bool, bool], MOLAHRSCRasterProvider] = {}


def get_shared_mola_provider(dem_path: str | None = None) -> MOLAHRSCRasterProvider:
    """
    Returns a process-shared `MOLAHRSCRasterProvider` instance for the active
    settings configuration, reusing the bounded file-identity cache across requests.
    """
    settings = get_settings()
    eff_path = dem_path if dem_path is not None else settings.DEM_PATH
    key = (eff_path, bool(settings.USE_REAL_DEM), bool(settings.ALLOW_SYNTHETIC_FALLBACK))
    with _SHARED_MOLA_LOCK:
        inst = _SHARED_MOLA_INSTANCES.get(key)
        if inst is None:
            inst = MOLAHRSCRasterProvider(dem_path=eff_path)
            _SHARED_MOLA_INSTANCES[key] = inst
        return inst
