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


class MOLAHRSCRasterProvider(BaseRasterProvider):
    """
    Data provider for real NASA/ESA MOLA-HRSC blended numerical elevation models
    covering the Jezero Crater pilot region.
    """

    def __init__(self, dem_path: str | None = None):
        settings = get_settings()
        self.dem_path = dem_path or settings.DEM_PATH
        self.allow_fallback = settings.ALLOW_SYNTHETIC_FALLBACK
        self._raster_data: RasterData | None = None
        self._fallback_provider: SyntheticTerrainProvider | None = None

    def _get_fallback(self) -> SyntheticTerrainProvider:
        if self._fallback_provider is None:
            self._fallback_provider = SyntheticTerrainProvider()
        return self._fallback_provider

    def get_dem_raster(self) -> RasterData:
        if self._raster_data is not None:
            return self._raster_data

        if os.path.exists(self.dem_path):
            try:
                self._raster_data = load_raster_file(self.dem_path)
                return self._raster_data
            except Exception as e:
                if not self.allow_fallback:
                    raise TerrainDataUnavailableError(f"Failed to load DEM from {self.dem_path}: {e}")

        # Fallback to deterministic synthetic fixture if real data file is not on disk
        if self.allow_fallback:
            return self._get_fallback().get_dem_raster()

        raise TerrainDataUnavailableError(
            f"No numerical DEM found at '{self.dem_path}'. Download MOLA/HRSC raster or set MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true."
        )

    def get_bounds(self) -> BoundingBox:
        if os.path.exists(self.dem_path):
            raster = self.get_dem_raster()
            return BoundingBox(
                min_lon=raster.metadata.min_lon,
                min_lat=raster.metadata.min_lat,
                max_lon=raster.metadata.max_lon,
                max_lat=raster.metadata.max_lat,
            )
        return self._get_fallback().get_bounds()

    def get_crs_info(self) -> CRSInfo:
        return get_mars_crs_info()

    def get_provenance(self) -> Dict[str, Any]:
        if os.path.exists(self.dem_path):
            return {
                "dataset_name": "HRSC and MOLA Blended Digital Elevation Model (Jezero Pilot)",
                "mission_instruments": ["ESA Mars Express HRSC", "NASA Mars Global Surveyor MOLA"],
                "data_publisher": "USGS Astrogeology Science Center / PDS Geosciences Node",
                "landing_url": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                "spatial_coverage": "Jezero Crater (MC-11E, ~18.38°N, 77.58°E)",
                "pixel_resolution_meters": 50.0,
                "vertical_datum": "Mars MOLA Areoid",
                "horizontal_crs": "IAU2000 Mars Sphere (R=3,396,190m)",
                "is_synthetic": False,
                "file_path": self.dem_path,
            }
        return self._get_fallback().get_provenance()

    def is_synthetic(self) -> bool:
        return not os.path.exists(self.dem_path)

    def get_science_targets(self) -> List[ScienceTarget]:
        return self._get_fallback().get_science_targets()
