from typing import Tuple
import numpy as np
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import geo_to_pixel
from backend.app.geospatial.terrain_metrics import compute_physical_pixel_sizes
from backend.app.geospatial.raster_loader import RasterData
from backend.app.schemas.coordinates import MarsCoordinate


class TerrainService:
    def __init__(self, provider: BaseRasterProvider | None = None):
        self.provider = provider or MOLAHRSCRasterProvider()

    def get_master_raster(self) -> RasterData:
        return self.provider.get_dem_raster()

    def sample_elevation(self, coord: MarsCoordinate) -> float:
        raster = self.get_master_raster()
        meta = raster.metadata
        col, row = geo_to_pixel(coord.lon, coord.lat, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat)
        return raster.get_elevation_at_pixel(col, row)

    def get_pixel_sizes(self, center_lat: float) -> Tuple[float, float]:
        raster = self.get_master_raster()
        meta = raster.metadata
        return compute_physical_pixel_sizes(center_lat, meta.deg_per_px_lon, meta.deg_per_px_lat)
