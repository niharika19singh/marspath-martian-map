import logging
import os
from typing import Any, Dict, List
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
            self._raster_data = load_raster_file(self.dem_path)
            logger.info("Successfully loaded real DEM from %s", self.dem_path)
            return self._raster_data
        except Exception as e:
            msg = f"Failed to load or validate real DEM at '{self.dem_path}': {e}"
            if not self.allow_fallback:
                raise TerrainDataUnavailableError(msg)
            logger.warning("%s. Falling back to synthetic test model.", msg)
            self._fallback_occurred = True
            self._fallback_reason = msg
            self._raster_data = self._get_fallback().get_dem_raster()
            return self._raster_data

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

    def get_provenance(self) -> Dict[str, Any]:
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
        else:
            provenance["data_mode"] = "synthetic_test_fixture"
            provenance["real_dem_requested"] = False
            provenance["real_dem_loaded"] = False
        return provenance

    def is_synthetic(self) -> bool:
        raster = self.get_dem_raster()
        return raster.metadata.is_synthetic

    def get_science_targets(self) -> List[ScienceTarget]:
        return self._get_fallback().get_science_targets()
