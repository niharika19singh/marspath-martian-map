import hashlib
import logging
import os
from typing import Any

import numpy as np

from backend.app.core.config import get_settings
from backend.app.core.exceptions import TerrainDataUnavailableError
from backend.app.data.manifest import verify_manifest_provenance
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.geospatial.raster_loader import RasterData, load_raster_file
from backend.app.schemas.coordinates import BoundingBox, CRSInfo
from backend.app.schemas.mission import ScienceTarget

logger = logging.getLogger("marspath.mola_hrsc_provider")


class MOLAHRSCRasterProvider(BaseRasterProvider):
    """
    Data provider for NASA/ESA MOLA-HRSC blended numerical elevation models.
    Strictly obeys MARSPATH_USE_REAL_DEM, MARSPATH_DEM_PATH, and synthetic fallback policy.
    Never silently describes synthetic rasters as real NASA data.
    """

    def __init__(self, dem_path: str | None = None):
        settings = get_settings()
        self.dem_path = dem_path or settings.DEM_PATH
        self.use_real_dem = settings.USE_REAL_DEM
        self.allow_fallback = settings.ALLOW_SYNTHETIC_FALLBACK
        self._raster_data: RasterData | None = None
        self._fallback_provider: SyntheticTerrainProvider | None = None
        self._fallback_occurred: bool = False
        self._fallback_reason: str = ""

    def _get_fallback(self) -> SyntheticTerrainProvider:
        if self._fallback_provider is None:
            self._fallback_provider = SyntheticTerrainProvider()
        return self._fallback_provider

    def get_dem_raster(self) -> RasterData:
        if self._raster_data is not None:
            return self._raster_data

        if not self.use_real_dem:
            # Explicitly operating in synthetic mode
            logger.info("Operating in synthetic test mode (MARSPATH_USE_REAL_DEM=false).")
            self._raster_data = self._get_fallback().get_dem_raster()
            return self._raster_data

        # Real DEM was requested
        logger.info("Real DEM requested. Checking path: %s", self.dem_path)
        if not os.path.exists(self.dem_path):
            msg = f"Real DEM requested (MARSPATH_USE_REAL_DEM=true) but file not found at: {self.dem_path}"
            if not self.allow_fallback:
                raise TerrainDataUnavailableError(msg)
            logger.warning("%s. Falling back to synthetic test model.", msg)
            self._fallback_occurred = True
            self._fallback_reason = msg
            self._raster_data = self._get_fallback().get_dem_raster()
            return self._raster_data

        try:
            loaded_raster = load_raster_file(self.dem_path)
            self._validate_dem_integrity(loaded_raster)
            self._raster_data = loaded_raster
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
            # 1. Compute file SHA-256
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
            )

            if is_verified and matched_prod:
                validation_status = "verified_source"
                data_mode = "real"
                dataset_name = matched_prod["product_name"]
                official_product_id = matched_prod["id"]
                official_source_url = matched_prod["landing_page"]
                pds_doi = matched_prod.get("pds_doi")
                mission_instruments = matched_prod.get("mission_instruments")
                data_publisher = matched_prod.get("publisher")
                limitations = [matched_prod.get("limitations", "Official product limitations.")]
            else:
                validation_status = "valid_numeric_raster_unverified_source"
                data_mode = "real_unverified_source"
                dataset_name = "Local Numerical Elevation Model (Unverified Source)"
                official_product_id = None
                official_source_url = None
                pds_doi = None
                mission_instruments = ["Unverified / Unknown"]
                data_publisher = "Unknown / Local Origin"
                limitations = [
                    "Raster passed 2D numerical and Jezero spatial-integrity checks (valid float array, plausible Mars elevations, valid planetary CRS).",
                    "Authoritative NASA/ESA/USGS source provenance could NOT be verified: file SHA-256 and metadata tags do not match official planetary catalog records.",
                    "Treated as an unverified local numeric terrain raster; cannot be reported as certified flight-grade planetary data.",
                ]

            return {
                "dataset_name": dataset_name,
                "official_product_id": official_product_id,
                "official_source_url": official_source_url,
                "pds_doi": pds_doi,
                "mission_instruments": mission_instruments,
                "data_publisher": data_publisher,
                "file_path": self.dem_path,
                "file_format": file_format,
                "file_sha256": file_sha256,
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

        # Operating on synthetic
        provenance = self._get_fallback().get_provenance()
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
            ]
        return provenance

    def is_synthetic(self) -> bool:
        raster = self.get_dem_raster()
        return raster.metadata.is_synthetic

    def get_science_targets(self) -> list[ScienceTarget]:
        return self._get_fallback().get_science_targets()
