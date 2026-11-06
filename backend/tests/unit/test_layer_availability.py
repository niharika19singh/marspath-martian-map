import hashlib
import json
import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.routes import RoutePlanRequest
from backend.app.services.data_catalog import DEFAULT_USGS_200M_URL, DataCatalogService
from backend.app.services.route_service import RouteService

ANALYSIS_LAYER_IDS = [
    "mars_elevation_jezero",
    "mars_slope_degrees",
    "mars_roughness_tri",
    "mars_traversability_mask",
]


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
    for layer_id in ANALYSIS_LAYER_IDS:
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


def test_synthetic_layers_never_advertise_usgs_url_and_use_synthetic_source_name():
    """
    Requirements 1 & 2 (Case C):
    - Synthetic layer responses never advertise the USGS DEM URL.
    - Synthetic layers use `Synthetic Jezero Crater Terrain Model` as source_name.
    - Do not display an official USGS product ID.
    - Route and data-status responses also never attribute active synthetic terrain to USGS.
    """
    provider = MOLAHRSCRasterProvider(dem_path="nonexistent_synthetic.tif")
    provider.use_real_dem = False

    catalog = DataCatalogService(provider=provider)
    layers_resp = catalog.get_layer_list()
    status_resp = catalog.get_data_status()

    layers_by_id = {lyr.id: lyr for lyr in layers_resp.layers}
    for layer_id in ANALYSIS_LAYER_IDS:
        lyr = layers_by_id[layer_id]
        assert lyr.is_synthetic is True
        assert lyr.source_name == "Synthetic Jezero Crater Terrain Model"
        assert lyr.source_url is None
        assert lyr.product_id is None
        assert lyr.source_checksum_verified is False
        assert lyr.validation_status == "synthetic_test_fixture"
        assert "not derived from nasa or usgs" in (lyr.provenance_note or "").lower()

    assert status_resp.is_synthetic is True
    assert status_resp.dem_loaded is False
    assert status_resp.real_dem_loaded is False
    assert status_resp.active_dem_dataset_name == "Synthetic Jezero Crater Terrain Model"
    assert status_resp.active_dem_product_id is None
    assert status_resp.active_dem_source_url is None
    assert not any("Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2" in lim for lim in status_resp.limitations)

    route_svc = RouteService(provider=provider)
    plan_resp = route_svc.plan_route(
        RoutePlanRequest(
            start=MarsCoordinate(lon=77.40, lat=18.39),
            destination=MarsCoordinate(lon=77.44, lat=18.42),
        )
    )
    assert plan_resp.data_mode == "synthetic_test_fixture"
    assert plan_resp.provenance["dataset_name"] == "Synthetic Jezero Crater Terrain Model"
    assert plan_resp.provenance["official_product_id"] is None
    assert plan_resp.provenance["official_source_url"] is None
    assert not any("USGS warns" in lim for lim in plan_resp.limitations)


def test_unverified_local_dem_never_receives_official_product_id_or_usgs_attribution():
    """
    Requirement 3 (Case D):
    Unverified local DEMs never receive an official product ID or official NASA/USGS
    source attribution across elevation, slope, roughness, and traversability layers.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
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
            # Even with self-asserted tags, unverified local file must not get USGS attribution
            dst.update_tags(PRODUCT_ID="Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2")
            dst.write(data, 1)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        catalog = DataCatalogService(provider=provider)
        layers_resp = catalog.get_layer_list()
        status_resp = catalog.get_data_status()

        layers_by_id = {lyr.id: lyr for lyr in layers_resp.layers}
        for layer_id in ANALYSIS_LAYER_IDS:
            lyr = layers_by_id[layer_id]
            assert lyr.is_synthetic is False
            assert lyr.source_name == "Local Numerical Elevation Model (Unverified Source)"
            assert lyr.source_url is None
            assert lyr.product_id is None
            assert lyr.validation_status == "valid_numeric_raster_unverified_source"
            assert lyr.source_checksum_verified is False
            assert "unverified local numerical raster" in (lyr.provenance_note or "").lower()

        assert status_resp.real_data_validation_status == "valid_numeric_raster_unverified_source"
        assert status_resp.active_dem_product_id is None
        assert status_resp.active_dem_source_url is None
        assert "unverified" in (status_resp.active_dem_dataset_name or "").lower()
        assert "Mars MGS MOLA" not in (status_resp.active_dem_dataset_name or "")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_official_endpoint_extraction_exposes_official_source_and_unverified_checksum_disclosure():
    """
    Requirement 4 (Case A):
    An official-endpoint extraction exposes the official dataset name, authoritative source URL,
    and product ID while clearly identifying that the full upstream checksum remains unverified.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    sidecar_path = f"{tmp_path}.provenance.json"

    try:
        deg_per_px = 200.0 / METERS_PER_DEGREE_LATITUDE
        data = np.full((50, 60), -2480.0, dtype=np.float32)
        transform = from_origin(77.2, 18.6, deg_per_px, deg_per_px)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=50,
            width=60,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with open(tmp_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()
        arr_sha = hashlib.sha256(np.ascontiguousarray(data, dtype=np.float32).tobytes()).hexdigest()

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_arr_sha = usgs_entry.get("jezero_window_array_sha256")
        usgs_entry["jezero_window_array_sha256"] = arr_sha

        try:
            sidecar_data = {
                "source_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
                "ingestion_method": "official_endpoint_vsicurl_range_extract",
                "published_upstream_md5": "e98092a06bea74d5ec9a704dcd1fe318",
                "source_checksum_verified": False,
                "local_file_sha256": actual_sha,
                "extracted_array_sha256": arr_sha,
            }
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(sidecar_data, f)

            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            catalog = DataCatalogService(provider=provider)
            layers_resp = catalog.get_layer_list()
            status_resp = catalog.get_data_status()

            layers_by_id = {lyr.id: lyr for lyr in layers_resp.layers}
            for layer_id in ANALYSIS_LAYER_IDS:
                lyr = layers_by_id[layer_id]
                assert lyr.is_synthetic is False
                assert lyr.source_name == "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
                assert lyr.source_url == DEFAULT_USGS_200M_URL
                assert lyr.product_id == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
                assert lyr.validation_status == "official_endpoint_retrieved_checksum_unverified"
                assert lyr.source_checksum_verified is False
                assert "unverified" in (lyr.provenance_note or "").lower()

            assert status_resp.dem_loaded is True
            assert status_resp.real_dem_requested is True
            assert status_resp.real_dem_loaded is True
            assert status_resp.is_synthetic is False
            assert status_resp.data_mode == "real_official_endpoint_unverified_checksum"
            assert status_resp.source_checksum_verified is False
            assert status_resp.local_integrity_verified is True
        finally:
            usgs_entry["jezero_window_array_sha256"] = orig_arr_sha
    finally:
        for p in (tmp_path, sidecar_path):
            if os.path.exists(p):
                os.remove(p)


def test_verified_full_source_dem_exposes_verified_provenance():
    """
    Requirement 5 (Case B):
    When independent full-source checksum verification succeeds, layers and data status
    expose the verified product identity, official source URL, and verified provenance.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        deg_per_px = 200.0 / METERS_PER_DEGREE_LATITUDE
        data = np.full((50, 60), -2490.0, dtype=np.float32)
        transform = from_origin(77.2, 18.6, deg_per_px, deg_per_px)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=50,
            width=60,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with open(tmp_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_sha = usgs_entry.get("sha256")
        usgs_entry["sha256"] = actual_sha

        try:
            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            catalog = DataCatalogService(provider=provider)
            layers_resp = catalog.get_layer_list()
            status_resp = catalog.get_data_status()

            layers_by_id = {lyr.id: lyr for lyr in layers_resp.layers}
            for layer_id in ANALYSIS_LAYER_IDS:
                lyr = layers_by_id[layer_id]
                assert lyr.is_synthetic is False
                assert lyr.source_name == "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
                assert lyr.source_url == DEFAULT_USGS_200M_URL
                assert lyr.product_id == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
                assert lyr.validation_status == "verified_source"
                assert lyr.source_checksum_verified is True
                assert "verified" in (lyr.provenance_note or "").lower()

            assert status_resp.dem_loaded is True
            assert status_resp.real_dem_loaded is True
            assert status_resp.data_mode == "real"
            assert status_resp.real_data_validation_status == "verified_source"
            assert status_resp.source_checksum_verified is True
            assert status_resp.local_integrity_verified is True
        finally:
            usgs_entry["sha256"] = orig_sha
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

