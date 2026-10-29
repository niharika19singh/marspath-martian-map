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

        layers: list[LayerInfo] = [
            LayerInfo(
                id="mars_elevation_jezero",
                name="Martian Digital Elevation Model (Topography)",
                category=LayerCategory.ELEVATION,
                layer_type="analysis_derived",
                description="Numerical surface elevation relative to the Mars areoid datum. Internal analysis layer queried via /api/v1/routes/plan.",
                units="meters",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MOLA-HRSC Blended DTM"
                if not is_syn
                else "Synthetic Jezero Pilot Model",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_slope_degrees",
                name="Terrain Slope Gradient",
                category=LayerCategory.SLOPE,
                layer_type="analysis_derived",
                description="Physical ground inclination derived from numerical elevation gradients. Internal analysis layer queried via /api/v1/routes/plan.",
                units="degrees",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Geospatial Processing Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_roughness_tri",
                name="Terrain Ruggedness Index (TRI)",
                category=LayerCategory.ROUGHNESS,
                layer_type="analysis_derived",
                description="Localized standard deviation of detrended elevation differences. Internal analysis layer queried via /api/v1/routes/plan.",
                units="dimensionless [0.0 - 1.0]",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Geospatial Processing Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_traversability_mask",
                name="Traversability & Hazard Ceiling Mask",
                category=LayerCategory.HAZARD,
                layer_type="analysis_derived",
                description="Binary traversability envelope enforcing slope limits and nodata masking. Internal analysis layer queried via /api/v1/routes/plan.",
                units="boolean",
                resolution_meters=50.0 if not is_syn else 112.5,
                bounds=bounds,
                crs=crs_info,
                source_name="MARSPath Risk Engine",
                source_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
                is_numerical=False,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_trek_imagery_basemap",
                name="NASA Mars Trek Visible Basemap",
                category=LayerCategory.IMAGERY,
                layer_type="tile_service",
                description="Global orthorectified multi-mission visible mosaic for direct frontend display via XYZ/WMTS tile services.",
                units="reflectance RGB",
                resolution_meters=6.0,
                bounds=BoundingBox(min_lon=0.0, min_lat=-90.0, max_lon=360.0, max_lat=90.0),
                crs=crs_info,
                source_name="NASA Solar System Treks (JPL)",
                source_url="https://trek.nasa.gov/mars/",
                is_numerical=False,
                is_available=True,
                is_renderable=True,
                render_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
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

        res_meters = round(raster.metadata.meters_per_px_y, 1)

        provenance = self.provider.get_provenance()
        active_mode = provenance.get("data_mode", "synthetic_test_fixture" if is_syn else "real")
        val_status = provenance.get("real_data_validation_status", "synthetic_test_fixture")

        limitations = [
            "Regional DEM does not detect sub-meter boulders or fine wheel-entrapment sand ripples.",
            "Visual imagery layers must not be used for physical slope or energy calculations.",
        ]
        if is_syn:
            if active_mode == "synthetic_fallback":
                limitations.append(
                    f"Fallback to synthetic test fixture occurred: {provenance.get('fallback_reason', 'Real DEM missing or invalid')}."
                )
            else:
                limitations.append(
                    "Operating in development mode with deterministic synthetic test fixture for Jezero Crater. Real NASA DEM is not loaded."
                )
        elif val_status == "valid_numeric_raster_unverified_source":
            limitations.extend(provenance.get("provenance_limitations", []))

        return DataStatusResponse(
            status="healthy",
            data_mode=active_mode,
            real_data_validation_status=val_status,
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
