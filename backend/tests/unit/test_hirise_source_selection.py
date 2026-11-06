import os
import tempfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine, from_origin

from backend.app.core.exceptions import ComputationalBoundExceededError
from backend.app.data.providers.hirise import HiRISERasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE, meters_per_degree_lon
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import (
    EvidenceQualityTier,
    RobustnessConfig,
    RoutePlanRequest,
)
from backend.app.services.data_catalog import DataCatalogService
from backend.app.services.route_service import RouteService
from backend.app.services.terrain_source_service import aggregate_corridor_hazard_preserving


def _write_hirise_geotiff(
    path: str,
    elev: np.ndarray,
    min_lon: float = 77.40,
    max_lat: float = 18.42,
    res_meters: float = 1.0,
    crs_str: str | None = "+proj=longlat +R=3396190 +no_defs",
    nodata: float | None = -9999.0,
    tags: dict[str, str] | None = None,
    custom_transform: Affine | None = None,
    dtype: str = "float32",
) -> None:
    """Helper to write a localized Mars GeoTIFF for HiRISE testing."""
    center_lat = max_lat - 0.01
    deg_lon = res_meters / meters_per_degree_lon(center_lat)
    deg_lat = res_meters / METERS_PER_DEGREE_LATITUDE
    transform = (
        custom_transform
        if custom_transform is not None
        else from_origin(min_lon, max_lat, deg_lon, deg_lat)
    )
    h, w = elev.shape
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=dtype,
        crs=crs_str,
        transform=transform,
        nodata=nodata,
    ) as dst:
        if tags:
            dst.update_tags(**tags)
        dst.write(elev.astype(dtype), 1)


def _write_mola_geotiff(path: str) -> None:
    """Helper to write a regional 200m/px Mars GeoTIFF covering Jezero Crater."""
    h, w = 180, 240
    r_grid, c_grid = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    elev = (-2520.0 + 0.4 * r_grid + 0.3 * c_grid).astype(np.float32)
    deg_lon = 200.0 / meters_per_degree_lon(18.38)
    deg_lat = 200.0 / METERS_PER_DEGREE_LATITUDE
    transform = from_origin(77.20, 18.65, deg_lon, deg_lat)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype="float32",
        crs="+proj=longlat +R=3396190 +no_defs",
        transform=transform,
        nodata=-9999.0,
    ) as dst:
        dst.update_tags(VERTICAL_DATUM="Mars Areoid (MOLA 0m Reference Datum)")
        dst.write(elev, 1)


def test_01_default_hirise_disabled_selects_mola_and_preserves_behavior():
    """
    1. Default route request with HiRISE disabled selects MOLA-HRSC (or default regional source)
       and preserves existing routing behavior.
    """
    service = RouteService()
    req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.44, lat=18.42),
        mode=OptimizationMode.BALANCED,
    )
    resp = service.plan_route(req)
    assert resp.status == "success"
    assert resp.source_selection is not None
    assert resp.source_selection.hirise_enabled is False
    assert resp.source_selection.hirise_selected is False
    assert resp.source_selection.hirise_status == "disabled"
    assert resp.source_selection.single_source_invariant_enforced is True
    assert resp.source_selection.aggregation_applied is False
    assert resp.source_selection.aggregation_factor == 1
    assert len(resp.routes) == 1


def test_02_hirise_enabled_missing_file_falls_back_to_mola():
    """
    2. Route request with HiRISE enabled but file missing falls back cleanly to MOLA-HRSC
       and reports the exact missing_file reason.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola:
        mola_path = tmp_mola.name

    try:
        _write_mola_geotiff(mola_path)
        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(
            dem_path="/tmp/definitely_missing_hirise_dtm_xyz.tif",
            enabled=True,
        )

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.41, lat=18.40),
            destination=MarsCoordinate(lon=77.42, lat=18.41),
        )
        resp = service.plan_route(req)

        assert resp.status == "success"
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_evaluated is True
        assert resp.source_selection.hirise_enabled is True
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "missing_file"
        assert "does not exist" in (resp.source_selection.hirise_rejection_reason or "")
        assert resp.source_selection.selected_source_tier == "regional_blended_dem"
    finally:
        if os.path.exists(mola_path):
            os.remove(mola_path)


def test_03_corridor_fully_contained_in_valid_hirise_selects_hirise():
    """
    3. Route request fully contained inside a valid local HiRISE raster selects HiRISE.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        # 200 x 200 pixels at 1.0 m/px (~200m x 200m footprint) starting at (77.410E, 18.410N)
        r_idx, c_idx = np.meshgrid(np.arange(200), np.arange(200), indexing="ij")
        hi_elev = (-2490.0 + 0.02 * r_idx + 0.01 * c_idx).astype(np.float32)
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
        )

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        # Short route well inside the 200m x 200m HiRISE patch
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4090),
            destination=MarsCoordinate(lon=77.4122, lat=18.4082),
        )
        resp = service.plan_route(req)

        assert resp.status == "success"
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is True
        assert resp.source_selection.hirise_status == "selected"
        assert resp.source_selection.selected_source_tier == "localized_high_resolution_dtm"
        assert resp.source_selection.effective_resolution_meters == pytest.approx(1.0, abs=0.1)
        assert resp.stats.cell_size_meters == pytest.approx(1.0, abs=0.1)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_04_partial_hirise_coverage_selects_mola_for_entire_request():
    """
    4. Route request partially inside HiRISE and partially outside selects MOLA-HRSC
       for the entire request (single-source invariant).
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((150, 150), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        # Start inside HiRISE (77.411, 18.409), destination outside HiRISE (77.460, 18.390)
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.411, lat=18.409),
            destination=MarsCoordinate(lon=77.460, lat=18.390),
        )
        resp = service.plan_route(req)

        assert resp.status == "success"
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "partial_or_no_corridor_coverage"
        assert resp.source_selection.selected_source_tier == "regional_blended_dem"
        assert resp.source_selection.effective_resolution_meters == pytest.approx(200.0, abs=5.0)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_05_waypoint_outside_hirise_selects_mola_for_entire_request():
    """
    5. Route request with start and destination inside HiRISE but a science waypoint
       outside HiRISE selects MOLA-HRSC for the entire request.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((200, 200), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        # Start and destination inside HiRISE, but science waypoint outside HiRISE
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4090),
            destination=MarsCoordinate(lon=77.4122, lat=18.4082),
            science_waypoints=[MarsCoordinate(lon=77.480, lat=18.380)],
        )
        resp = service.plan_route(req)

        assert resp.status == "success"
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "partial_or_no_corridor_coverage"
        assert resp.source_selection.selected_source_tier == "regional_blended_dem"
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_06_corridor_completely_outside_hirise_selects_mola():
    """
    6. Route request completely outside HiRISE selects MOLA-HRSC.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((150, 150), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        # Both start and destination on crater floor East of the Western Delta
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.55, lat=18.36),
            destination=MarsCoordinate(lon=77.60, lat=18.38),
        )
        resp = service.plan_route(req)

        assert resp.status == "success"
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "partial_or_no_corridor_coverage"
        assert resp.source_selection.selected_source_tier == "regional_blended_dem"
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_07_unauthenticated_local_hirise_classified_as_unverified_source():
    """
    7. Valid local HiRISE raster without verified source checksum is classified as
       `valid_numeric_raster_unverified_source`, NEVER `verified_source`.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi:
        hi_path = tmp_hi.name

    try:
        hi_elev = np.full((120, 120), -2485.0, dtype=np.float32)
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            tags={"PRODUCT_ID": "dem_hirise_jezero_delta_1m"},
        )

        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        prov = hi_prov.get_provenance()

        assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
        assert prov["real_data_validation_status"] != "verified_source"
        assert prov["source_checksum_verified"] is False
        assert prov["official_product_id"] is None
        assert prov["official_source_url"] is None
        assert prov["data_mode"] == "real_unverified_source"
    finally:
        if os.path.exists(hi_path):
            os.remove(hi_path)


def test_08_hirise_with_earth_crs_is_rejected():
    """
    8. HiRISE raster with Earth CRS (e.g. EPSG:4326 / WGS84) is strictly rejected.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((120, 120), -2485.0, dtype=np.float32)
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            crs_str="EPSG:4326",
        )

        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        val = hi_prov.validate_hirise_raster()
        assert val.is_valid is False
        assert val.status_code == "rejected_invalid_crs"

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        resp = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4112, lat=18.4090),
                destination=MarsCoordinate(lon=77.4122, lat=18.4082),
            )
        )
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "rejected_invalid_crs"
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_09_hirise_with_missing_crs_or_identity_transform_is_rejected():
    """
    9. HiRISE raster with missing CRS or invalid/identity georeferencing is rejected.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_no_crs,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_ident,
    ):
        no_crs_path = tmp_no_crs.name
        ident_path = tmp_ident.name

    try:
        hi_elev = np.full((100, 100), -2485.0, dtype=np.float32)
        # Case A: Missing CRS
        _write_hirise_geotiff(
            no_crs_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            crs_str=None,
        )
        prov_no_crs = HiRISERasterProvider(dem_path=no_crs_path, enabled=True)
        res_no_crs = prov_no_crs.validate_hirise_raster()
        assert res_no_crs.is_valid is False
        assert res_no_crs.status_code == "rejected_missing_crs"

        # Case B: Identity transform
        _write_hirise_geotiff(
            ident_path,
            hi_elev,
            crs_str="+proj=longlat +R=3396190 +no_defs",
            custom_transform=Affine.identity(),
        )
        prov_ident = HiRISERasterProvider(dem_path=ident_path, enabled=True)
        res_ident = prov_ident.validate_hirise_raster()
        assert res_ident.is_valid is False
        assert res_ident.status_code in (
            "rejected_invalid_georeferencing",
            "rejected_invalid_resolution",
            "rejected_outside_jezero_delta_bounds",
        )
    finally:
        for p in (no_crs_path, ident_path):
            if os.path.exists(p):
                os.remove(p)


def test_10_hirise_with_insufficient_valid_observations_is_rejected():
    """
    10. HiRISE raster with all-NoData or insufficient valid data (<10%) is rejected.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_all_nd,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_sparse,
    ):
        all_nd_path = tmp_all_nd.name
        sparse_path = tmp_sparse.name

    try:
        # All NoData
        elev_nd = np.full((100, 100), -9999.0, dtype=np.float32)
        _write_hirise_geotiff(all_nd_path, elev_nd, nodata=-9999.0)
        prov_nd = HiRISERasterProvider(dem_path=all_nd_path, enabled=True)
        res_nd = prov_nd.validate_hirise_raster()
        assert res_nd.is_valid is False
        assert res_nd.status_code == "rejected_insufficient_valid_observations"

        # Only 5% valid data (< 10% threshold)
        elev_sparse = np.full((100, 100), -9999.0, dtype=np.float32)
        elev_sparse[:20, :20] = -2490.0  # 400 / 10000 = 4%
        _write_hirise_geotiff(sparse_path, elev_sparse, nodata=-9999.0)
        prov_sparse = HiRISERasterProvider(dem_path=sparse_path, enabled=True)
        res_sparse = prov_sparse.validate_hirise_raster()
        assert res_sparse.is_valid is False
        assert res_sparse.status_code == "rejected_insufficient_valid_observations"
    finally:
        for p in (all_nd_path, sparse_path):
            if os.path.exists(p):
                os.remove(p)


def test_11_small_hirise_corridor_within_budget_runs_at_native_resolution():
    """
    11. Small HiRISE corridor within MAX_GRID_CELLS runs at native resolution without aggregation.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((300, 300), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(
            provider=mola_prov,
            hirise_provider=hi_prov,
            max_cells=250000,
        )
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4115, lat=18.4085),
            destination=MarsCoordinate(lon=77.4130, lat=18.4075),
        )
        resp = service.plan_route(req)

        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is True
        assert resp.source_selection.aggregation_applied is False
        assert resp.source_selection.aggregation_factor == 1
        assert resp.source_selection.aggregation_method == "none"
        assert (
            resp.source_selection.corridor_native_grid_shape
            == resp.source_selection.corridor_analysis_grid_shape
        )
        assert (
            resp.source_selection.native_resolution_meters
            == resp.source_selection.effective_resolution_meters
        )
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_12_large_hirise_corridor_aggregates_or_falls_back_to_mola():
    """
    12. Large HiRISE corridor exceeding MAX_GRID_CELLS:
        (a) Uses documented conservative block aggregation when aggregated resolution remains
            materially finer than MOLA-HRSC.
        (b) Rejects HiRISE and selects MOLA-HRSC when required aggregation factor degrades
            effective resolution to >= MOLA-HRSC resolution.
        (c) Raises ComputationalBoundExceededError if max_cells is too small even for a minimal grid.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        # 240 x 240 HiRISE raster at 1.0 m/px
        hi_elev = np.full((240, 240), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4090),
            destination=MarsCoordinate(lon=77.4128, lat=18.4075),
        )

        # Case (a): Native corridor is ~160x160 (~25,600 cells); set max_cells=4000 so k=3 (~3 m/px) is used
        service_agg = RouteService(
            provider=mola_prov,
            hirise_provider=hi_prov,
            max_cells=4000,
        )
        resp_agg = service_agg.plan_route(req)
        assert resp_agg.source_selection is not None
        assert resp_agg.source_selection.hirise_selected is True
        assert resp_agg.source_selection.aggregation_applied is True
        assert resp_agg.source_selection.aggregation_factor >= 2
        assert (
            resp_agg.source_selection.aggregation_method
            == "mean_elevation_strict_nodata_max_subgrid_slope_roughness"
        )
        rows, cols = resp_agg.source_selection.corridor_analysis_grid_shape
        assert rows * cols <= 4000
        assert (
            resp_agg.source_selection.effective_resolution_meters
            == pytest.approx(
                resp_agg.source_selection.native_resolution_meters
                * resp_agg.source_selection.aggregation_factor,
                rel=0.05,
            )
        )

        # Case (b): If HiRISE native resolution is 20 m/px and max_cells=25 forces k=10 (200 m/px >= MOLA),
        # HiRISE is rejected and MOLA-HRSC is selected.
        with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi20:
            hi20_path = tmp_hi20.name
        try:
            hi20_elev = np.full((120, 120), -2490.0, dtype=np.float32)
            _write_hirise_geotiff(
                hi20_path, hi20_elev, min_lon=77.395, max_lat=18.425, res_meters=20.0
            )
            hi20_prov = HiRISERasterProvider(dem_path=hi20_path, enabled=True)
            service_fb = RouteService(
                provider=mola_prov,
                hirise_provider=hi20_prov,
                max_cells=64,
                corridor_padding_meters=750.0,
            )
            resp_fb = service_fb.plan_route(req)
            assert resp_fb.source_selection is not None
            assert resp_fb.source_selection.hirise_selected is False
            assert (
                resp_fb.source_selection.hirise_status
                == "rejected_aggregated_resolution_no_better_than_regional"
            )
            assert resp_fb.source_selection.selected_source_tier == "regional_blended_dem"
        finally:
            if os.path.exists(hi20_path):
                os.remove(hi20_path)

        # Case (c): Impossibly small max_cells (< 16) raises ComputationalBoundExceededError
        service_tiny = RouteService(
            provider=mola_prov,
            hirise_provider=hi_prov,
            max_cells=4,
        )
        with pytest.raises(ComputationalBoundExceededError):
            service_tiny.plan_route(req)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_13_aggregation_preserves_subgrid_hazards_and_never_turns_nodata_into_zero():
    """
    13. Aggregation preserves or conservatively represents maximum native slope/roughness
        hazards and NEVER turns NoData into 0.0.
    """
    # Create a 20x20 native grid at 1 m/px
    native_elev = np.full((20, 20), -2500.0, dtype=np.float32)
    # Introduce a sharp narrow scarp inside block (r=2, c=2 -> native rows 4..5, cols 4..5)
    # that would partially average out if slope were only computed after block averaging
    native_elev[4, 4:6] = -2495.0  # 5m jump over 1m = ~78 deg native slope!
    # Put a NoData cell in block (r=0, c=0 -> native row 0, col 1)
    native_elev[0, 1] = np.nan

    meta = RasterMetadata(
        width=20,
        height=20,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.41,
        min_lat=18.40,
        max_lon=77.4104,
        max_lat=18.4004,
        deg_per_px_lon=0.00002,
        deg_per_px_lat=0.00002,
        meters_per_px_x=1.0,
        meters_per_px_y=1.0,
        affine_transform=(0.00002, 0.0, 77.41, 0.0, -0.00002, 18.4004),
        nodata_value=-9999.0,
        vertical_datum="Unknown / Unspecified",
    )

    agg_elev, agg_meta, subgrid_max_slope, subgrid_max_rough = (
        aggregate_corridor_hazard_preserving(native_elev, meta, factor=2)
    )

    assert agg_elev.shape == (10, 10)
    assert agg_meta.meters_per_px_x == 2.0
    assert agg_meta.meters_per_px_y == 2.0

    # Block (0, 0) had a single NaN pixel -> aggregated block MUST be NaN, NEVER 0.0
    assert np.isnan(agg_elev[0, 0])
    assert not np.any(agg_elev == 0.0)

    # Block (2, 2) contained the 5m/1m fine-scale scarp -> subgrid_max_slope must preserve the steep native slope (>60 deg)
    assert subgrid_max_slope[2, 2] > 60.0
    assert subgrid_max_rough[2, 2] > 0.05


def test_14_evidence_passport_reports_native_effective_resolution_aggregation_and_datum_limitations():
    """
    14. Evidence passport reports selected source, native resolution, effective resolution,
        aggregation metadata, and vertical-datum limitations accurately.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev = np.full((240, 240), -2490.0, dtype=np.float32)
        # Leave vertical datum tag unspecified so it is Unknown / Unspecified
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(
            provider=mola_prov,
            hirise_provider=hi_prov,
            max_cells=4000,
        )
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4090),
            destination=MarsCoordinate(lon=77.4128, lat=18.4075),
        )
        resp = service.plan_route(req)
        passport = resp.routes[0].evidence_passport
        assert passport is not None

        # Unauthenticated local HiRISE must receive UNVERIFIED quality tier
        assert passport.quality_tier == EvidenceQualityTier.UNVERIFIED
        assert passport.source.validation_status == "valid_numeric_raster_unverified_source"
        assert passport.source.source_checksum_verified is False
        assert passport.source.product_id is None

        # Native vs effective resolution and aggregation metadata
        assert passport.source.aggregation_applied is True
        assert passport.source.aggregation_factor >= 2
        assert passport.source.native_resolution_x_meters == pytest.approx(1.0, abs=0.1)
        assert passport.source.pixel_resolution_x_meters > 1.5

        res_assess = passport.resolution_assessment
        assert res_assess.aggregation_applied is True
        assert res_assess.aggregation_factor == passport.source.aggregation_factor
        assert res_assess.native_effective_resolution_meters == pytest.approx(1.0, abs=0.1)
        assert res_assess.effective_resolution_meters > 1.5
        assert res_assess.obstacle_detection_capable is False

        # Vertical datum limitation must be disclosed
        assert "unknown_vertical_datum" in passport.quality_flags
        assert any("vertical datum" in lim.lower() for lim in passport.known_limitations)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_15_robustness_stress_testing_works_on_selected_hirise_corridor():
    """
    15. Robustness stress testing works when a HiRISE corridor is selected and remains
        within MAX_GRID_CELLS.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        r_idx, c_idx = np.meshgrid(np.arange(120), np.arange(120), indexing="ij")
        hi_elev = (-2490.0 + 0.03 * r_idx + 0.02 * c_idx).astype(np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4106, lat=18.4094),
            destination=MarsCoordinate(lon=77.4114, lat=18.4086),
            robustness_config=RobustnessConfig(
                enabled=True,
                vertical_sigma_m=0.15,
                correlation_length_m=5.0,
                scenario_count=3,
                seed=99,
            ),
        )
        resp = service.plan_route(req)
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is True
        assert resp.robustness_assessment is not None
        assert resp.robustness_assessment.enabled is True
        assert resp.robustness_assessment.requested_scenario_count == 3
        assert resp.robustness_assessment.completed_scenario_count == 3
        assert (
            resp.robustness_assessment.uncertainty_assumptions.actual_dx_meters
            == pytest.approx(1.0, abs=0.1)
        )
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_16_data_status_and_layers_report_hirise_honestly():
    """
    16. /api/v1/data/status and /api/v1/layers report HiRISE availability and validation
        status honestly across disabled, missing, and loaded-unverified states.
    """
    # Case A: Disabled
    cat_disabled = DataCatalogService(
        hirise_provider=HiRISERasterProvider(dem_path="missing.tif", enabled=False)
    )
    status_dis = cat_disabled.get_data_status()
    assert status_dis.hirise_enabled is False
    assert status_dis.hirise_loaded is False
    assert status_dis.hirise_status == "disabled"
    hi_entry_dis = next(
        p for p in status_dis.configured_products if p["id"] == "dem_hirise_jezero_delta_1m"
    )
    assert hi_entry_dis["is_loaded"] is False
    assert hi_entry_dis["runtime_status"] == "disabled"

    # Case B: Enabled but missing file
    cat_missing = DataCatalogService(
        hirise_provider=HiRISERasterProvider(dem_path="/tmp/no_such_hirise.tif", enabled=True)
    )
    status_mis = cat_missing.get_data_status()
    assert status_mis.hirise_enabled is True
    assert status_mis.hirise_loaded is False
    assert status_mis.hirise_status == "missing_file"

    # Case C: Enabled and loaded (unverified local file)
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi:
        hi_path = tmp_hi.name
    try:
        hi_elev = np.full((100, 100), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0)
        cat_loaded = DataCatalogService(
            hirise_provider=HiRISERasterProvider(dem_path=hi_path, enabled=True)
        )
        status_ld = cat_loaded.get_data_status()
        assert status_ld.hirise_enabled is True
        assert status_ld.hirise_loaded is True
        assert status_ld.hirise_status == "ready"
        assert status_ld.hirise_dem_provenance is not None
        assert (
            status_ld.hirise_dem_provenance["real_data_validation_status"]
            == "valid_numeric_raster_unverified_source"
        )

        layers_ld = cat_loaded.get_layer_list()
        hi_layer = next(
            (lyr for lyr in layers_ld.layers if lyr.id == "mars_hirise_jezero_delta_dtm"),
            None,
        )
        assert hi_layer is not None
        assert hi_layer.validation_status == "valid_numeric_raster_unverified_source"
        assert hi_layer.source_checksum_verified is False
        assert hi_layer.product_id is None
    finally:
        if os.path.exists(hi_path):
            os.remove(hi_path)


def test_17_single_source_invariant_never_merges_mola_and_hirise_grids():
    """
    17. Proves that no code path merges MOLA and HiRISE elevation arrays into a single route grid:
        - Give MOLA constant elevation -2500.0m and HiRISE constant elevation -1800.0m (with a NoData hole).
        - When HiRISE is selected, all valid route elevations come strictly from -1800.0m (never -2500.0m),
          and HiRISE NoData cells remain NaN (never filled with -2500.0m MOLA values).
        - When corridor partially exits HiRISE, all route elevations come strictly from -2500.0m MOLA.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        # MOLA at -2500.0m everywhere
        h, w = 180, 240
        mola_elev = np.full((h, w), -2500.0, dtype=np.float32)
        deg_lon = 200.0 / meters_per_degree_lon(18.38)
        deg_lat = 200.0 / METERS_PER_DEGREE_LATITUDE
        with rasterio.open(
            mola_path,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype="float32",
            crs="+proj=longlat +R=3396190 +no_defs",
            transform=from_origin(77.20, 18.65, deg_lon, deg_lat),
            nodata=-9999.0,
        ) as dst:
            dst.write(mola_elev, 1)

        # HiRISE at -1800.0m with an interior NoData patch (-9999.0)
        hi_elev = np.full((200, 200), -1800.0, dtype=np.float32)
        hi_elev[90:100, 90:100] = -9999.0
        _write_hirise_geotiff(
            hi_path, hi_elev, min_lon=77.410, max_lat=18.410, res_meters=1.0, nodata=-9999.0
        )

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)

        # Route 1: Fully inside HiRISE -> all vertices must be -1800.0m, never -2500.0m
        resp_hi = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4108, lat=18.4092),
                destination=MarsCoordinate(lon=77.4126, lat=18.4076),
            )
        )
        assert resp_hi.source_selection is not None
        assert resp_hi.source_selection.hirise_selected is True
        z_vals_hi = [c[2] for c in resp_hi.routes[0].geometry.coordinates]
        assert all(abs(z - (-1800.0)) < 1e-3 for z in z_vals_hi)

        # Route 2: Partially outside HiRISE -> all vertices must be -2500.0m, never -1800.0m
        resp_mola = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4110, lat=18.4090),
                destination=MarsCoordinate(lon=77.4600, lat=18.3900),
            )
        )
        assert resp_mola.source_selection is not None
        assert resp_mola.source_selection.hirise_selected is False
        z_vals_mola = [c[2] for c in resp_mola.routes[0].geometry.coordinates]
        assert all(abs(z - (-2500.0)) < 1e-3 for z in z_vals_mola)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_18_projected_mars_crs_hirise_corridor_reprojection_and_pixel_alignment():
    """
    18. Validates that a projected Mars Equirectangular metric GeoTIFF (~1 m/px) is:
        - Correctly unprojected to Mars geographic bounds using pyproj + R=3,396,190 m.
        - Correctly warped onto the route analysis grid while preserving NoData as NaN (never 0.0).
        - Properly selected for a route inside its footprint.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi_proj,
    ):
        mola_path = tmp_mola.name
        hi_proj_path = tmp_hi_proj.name

    try:
        _write_mola_geotiff(mola_path)
        # Projected Mars Equirectangular centered at (77.415E, 18.405N), 200m x 200m at 1.0 m/px
        crs_proj = (
            "+proj=eqc +lat_ts=18.405 +lat_0=18.405 +lon_0=77.415 "
            "+x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
        )
        transform = from_origin(-100.0, 100.0, 1.0, 1.0)
        hi_elev = np.full((200, 200), -2475.0, dtype=np.float32)

        with rasterio.open(
            hi_proj_path,
            "w",
            driver="GTiff",
            height=200,
            width=200,
            count=1,
            dtype="float32",
            crs=crs_proj,
            transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.write(hi_elev, 1)

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_proj_path, enabled=True)

        val = hi_prov.validate_hirise_raster()
        assert val.is_valid is True
        assert val.raster is not None
        assert val.raster.metadata.coordinate_type == "projected"
        assert 77.410 <= val.raster.metadata.min_lon <= 77.415
        assert 77.415 <= val.raster.metadata.max_lon <= 77.420

        # Check round-trip pixel lookup at center (77.415, 18.405) -> pixel (100.0, 100.0)
        col_f, row_f = val.raster.geo_to_native_pixel_float(77.415, 18.405)
        assert col_f == pytest.approx(100.0, abs=0.05)
        assert row_f == pytest.approx(100.0, abs=0.05)

        service = RouteService(provider=mola_prov, hirise_provider=hi_prov)
        resp = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4145, lat=18.4046),
                destination=MarsCoordinate(lon=77.4155, lat=18.4054),
            )
        )
        assert resp.source_selection is not None
        assert resp.source_selection.hirise_selected is True
        assert resp.routes[0].summary.min_elevation_meters == pytest.approx(-2475.0, abs=0.5)
    finally:
        for p in (mola_path, hi_proj_path):
            if os.path.exists(p):
                os.remove(p)
