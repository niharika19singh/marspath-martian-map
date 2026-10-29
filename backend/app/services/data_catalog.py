from typing import List
from backend.app.core.config import get_settings
from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.schemas.coordinates import BoundingBox
from backend.app.schemas.layers import LayerCategory, LayerInfo, LayerListResponse
from backend.app.schemas.routes import DataStatusResponse


class DataCatalogService:
    def __init__(self, provider: BaseRasterProvider | None = None):
        self.settings = get_settings()
        self.provider = provider or MOLAHRSCRasterProvider()

    def get_layer_list(self) -> LayerListResponse:
        crs_info = get_mars_crs_info()
        bounds = self.provider.get_bounds()
        is_syn = self.provider.is_synthetic()

        layers: List[LayerInfo] = [
            LayerInfo(
                id="mars_elevation_jezero",
                name="Martian Digital Elevation Model (Topography)",
                category=LayerCategory.ELEVATION,
                description="Numerical surface elevation relative to the Mars areoid datum.",
                units="meters",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MOLA-HRSC Blended DTM" if not is_syn else "Synthetic Jezero Pilot Model",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_slope_degrees",
                name="Terrain Slope Gradient",
                category=LayerCategory.SLOPE,
                description="Physical ground inclination derived from numerical elevation gradients.",
                units="degrees",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Geospatial Processing Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_roughness_tri",
                name="Terrain Ruggedness Index (TRI)",
                category=LayerCategory.ROUGHNESS,
                description="Localized standard deviation of detrended elevation differences.",
                units="dimensionless [0.0 - 1.0]",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Geospatial Processing Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_traversability_mask",
                name="Traversability & Hazard Ceiling Mask",
                category=LayerCategory.HAZARD,
                description="Binary traversability envelope enforcing slope limits and nodata masking.",
                units="boolean",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Risk Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=False,
                is_available=True,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_trek_imagery_basemap",
                name="NASA Mars Trek Visible Basemap",
                category=LayerCategory.IMAGERY,
                description="Global orthorectified multi-mission visible mosaic for frontend display.",
                units="reflectance RGB",
                resolution_meters=6.0,
                bounds=BoundingBox(min_lon=0.0, min_lat=-90.0, max_lon=360.0, max_lat=90.0),
                crs=crs_info,
                source_name="NASA Solar System Treks (JPL)",
                source_url="https://trek.nasa.gov/mars/",
                is_numerical=False,
                is_available=True,
                is_synthetic=False,
            ),
        ]

        return LayerListResponse(
            count=len(layers),
            pilot_region="Jezero Crater, Mars",
            layers=layers,
        )

    def get_data_status(self) -> DataStatusResponse:
        raster = self.provider.get_dem_raster()
        is_syn = self.provider.is_synthetic()
        bounds = self.provider.get_bounds()
        crs_info = self.provider.get_crs_info()

        # Compute valid data fraction
        total_pixels = raster.data.size
        nodata_count = int(raster.nodata_mask.sum())
        valid_frac = float((total_pixels - nodata_count) / max(total_pixels, 1))

        res_meters = round(raster.metadata.deg_per_px_lat * 59274.0, 1)

        limitations = [
            "Regional DEM does not detect sub-meter boulders or fine wheel-entrapment sand ripples.",
            "Visual imagery layers must not be used for physical slope or energy calculations.",
        ]
        if is_syn:
            limitations.append(
                "Currently running on deterministic synthetic test fixture for Jezero Crater. Real NASA DEM is not yet placed in rasters directory."
            )

        return DataStatusResponse(
            status="healthy",
            data_mode="synthetic_test_fixture" if is_syn else "real",
            is_synthetic=is_syn,
            active_pilot_region="Jezero Crater, Mars",
            pilot_bounds=bounds,
            crs=crs_info,
            loaded_dem=self.provider.dem_path if not is_syn else "SyntheticProceduralJezeroModel",
            dem_resolution_meters=res_meters,
            grid_shape=[raster.metadata.height, raster.metadata.width],
            valid_data_fraction=round(valid_frac, 4),
            configured_products=DATA_CATALOG_MANIFEST,
            limitations=limitations,
            blocking_errors=[],
        )
