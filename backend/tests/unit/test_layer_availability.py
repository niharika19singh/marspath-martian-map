import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE
from backend.app.services.data_catalog import DataCatalogService


def test_layer_availability_semantics():
    service = DataCatalogService()
    response = service.get_layer_list()
    status = service.get_data_status()

    layers_by_id = {lyr.id: lyr for lyr in response.layers}

    # Visual Basemap must be directly renderable
    basemap = layers_by_id["mars_trek_imagery_basemap"]
    assert basemap.is_renderable is True
    assert basemap.layer_type == "tile_service"
    assert basemap.render_url is not None
    assert "https://trek.nasa.gov" in basemap.render_url

    # Elevation, Slope, Roughness, Hazard are analysis matrices, NOT renderable tile layers
    for layer_id in [
        "mars_elevation_jezero",
        "mars_slope_degrees",
        "mars_roughness_tri",
        "mars_traversability_mask",
    ]:
        layer = layers_by_id[layer_id]
        assert layer.is_renderable is False
        assert layer.layer_type == "analysis_derived"
        assert layer.render_url is None
        assert "Internal analysis layer" in layer.description
        assert layer.resolution_meters == status.dem_resolution_meters


def test_layer_resolution_derived_from_actual_200m_raster_and_matches_data_status():
    """
    Verifies that `/api/v1/layers` derives `resolution_meters` from the actual loaded
    raster metadata (e.g. 200.0 m/px for the 200m global DEM) rather than hardcoding 50.0 m/px,
    and matches `/api/v1/data/status`.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # 200m/px angular step on Mars 2000 Sphere
        deg_per_px = 200.0 / METERS_PER_DEGREE_LATITUDE
        data = np.full((60, 80), -2450.0, dtype=np.float32)
        transform = from_origin(77.2, 18.6, deg_per_px, deg_per_px)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=60,
            width=80,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        service = DataCatalogService(provider=provider)
        layers_resp = service.get_layer_list()
        status_resp = service.get_data_status()

        assert status_resp.dem_resolution_meters == 200.0
        for lyr in layers_resp.layers:
            if lyr.layer_type == "analysis_derived":
                assert lyr.resolution_meters == 200.0
                assert lyr.resolution_meters == status_resp.dem_resolution_meters
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
