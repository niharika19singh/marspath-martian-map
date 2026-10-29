import logging
import os
from typing import Any

from backend.app.core.config import get_settings
from backend.app.core.exceptions import TerrainDataUnavailableError
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
            return {
                "dataset_name": "HRSC and MOLA Blended Digital Elevation Model (Jezero Pilot)",
                "mission_instruments": ["ESA Mars Express HRSC", "NASA Mars Global Surveyor MOLA"],
                "data_publisher": "USGS Astrogeology Science Center / PDS Geosciences Node",
                "landing_url": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                "spatial_coverage": f"Jezero Crater ({raster.metadata.min_lat:.2f}°N - {raster.metadata.max_lat:.2f}°N, {raster.metadata.min_lon:.2f}°E - {raster.metadata.max_lon:.2f}°E)",
                "pixel_resolution_meters": round(raster.metadata.meters_per_px_y, 1),
                "vertical_datum": raster.metadata.vertical_datum,
                "horizontal_crs": raster.metadata.crs_str,
                "data_mode": "real",
                "real_data_validation_status": "verified",
                "is_synthetic": False,
                "file_path": self.dem_path,
            }

        # Operating on synthetic
        provenance = self._get_fallback().get_provenance()
        if self._fallback_occurred:
            provenance["data_mode"] = "synthetic_fallback"
            provenance["fallback_reason"] = self._fallback_reason
            provenance["real_dem_requested"] = True
            provenance["real_dem_loaded"] = False
            provenance["real_data_validation_status"] = "incomplete_missing_genuine_dem"
        else:
            provenance["data_mode"] = "synthetic_test_fixture"
            provenance["real_dem_requested"] = False
            provenance["real_dem_loaded"] = False
            provenance["real_data_validation_status"] = "not_requested_synthetic_mode"
        return provenance

    def is_synthetic(self) -> bool:
        raster = self.get_dem_raster()
        return raster.metadata.is_synthetic

    def get_science_targets(self) -> list[ScienceTarget]:
        return self._get_fallback().get_science_targets()
