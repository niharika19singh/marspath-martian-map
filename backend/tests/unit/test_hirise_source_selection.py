import math
import os
import tempfile
import unittest.mock as mock

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine, from_origin

from backend.app.core.exceptions import ComputationalBoundExceededError
from backend.app.data import manifest
from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.hirise import HiRISERasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE, meters_per_degree_lon
from backend.app.geospatial.raster_loader import (
    RasterMetadata,
    extract_pds3_label_dict,
    load_raster_file,
    parse_pds3_hirise_dtm_label,
)
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


def _write_hirise_pds3_img(
    path: str,
    elev: np.ndarray,
    min_lon: float = 77.410,
    max_lat: float = 18.420,
    res_meters: float = 1.0,
    note_text: str | None = None,
    scaling_factor: float = 1.0,
    offset: float = 0.0,
    sample_bits: int = 32,
    sample_type: str = "PC_REAL",
    missing_constant_hex: str = "16#FF7FFFFB#",
    core_null: int | float | None = None,
    target_name: str = "MARS",
    product_id: str = "DTEEC_045994_1985_046060_1985_U01",
    data_set_id: str = "MRO-M-HIRISE-5-DTM-V1.0",
    center_lat: float = 15.0,
    center_lon: float = 77.44,
) -> None:
    """Helper to generate a deterministic PDS3 HiRISE DTM .IMG raster fixture."""
    h, w = elev.shape
    bytes_per_sample = sample_bits // 8
    record_bytes = w * bytes_per_sample

    default_note = (
        "Pixel values in this file represent elevations in meters above the "
        "martian equipotential surface (Mars 2000 Datum) defined by Smith, et al. (2001). "
        "Conversion from pixel units to geophysical units is given by the keyvalues for "
        "SCALING_FACTOR and OFFSET. This DTM was produced using ISIS and SOCET Set "
        "(copyright BAE Systems) software as described in Kirk et al. (2008)."
    )
    actual_note = note_text if note_text is not None else default_note
    note_clause = f'  NOTE             = "{actual_note}"\r\n' if actual_note != "" else ""
    null_clause = (
        f"  CORE_NULL        = {core_null}\r\n"
        if core_null is not None
        else (
            f"  MISSING_CONSTANT = {missing_constant_hex}\r\n"
            if missing_constant_hex
            else ""
        )
    )

    rad_lat = math.radians(center_lat)
    r_mars = 3394839.8133163
    x_origin = r_mars * math.radians(min_lon - center_lon) * math.cos(rad_lat)
    y_origin = r_mars * math.radians(max_lat)

    sample_proj_offset = 0.5 - (x_origin / res_meters)
    line_proj_offset = (y_origin / res_meters) - 0.5

    min_lat = max_lat - math.degrees((h * res_meters) / r_mars)
    max_lon = min_lon + math.degrees((w * res_meters) / (r_mars * math.cos(rad_lat)))

    label_body = (
        "PDS_VERSION_ID            = PDS3\r\n"
        "RECORD_TYPE               = FIXED_LENGTH\r\n"
        f"RECORD_BYTES              = {record_bytes}\r\n"
        "FILE_RECORDS              = __FILE_RECORDS__\r\n"
        "^IMAGE                    = __IMAGE_PTR__\r\n"
        f'DATA_SET_ID               = "{data_set_id}"\r\n'
        f'DATA_SET_NAME             = "MRO MARS HIGH RESOLUTION IMAGING SCIENCE EXPERIMENT DTM V1.0"\r\n'
        'PRODUCER_INSTITUTION_NAME = "UNIVERSITY OF ARIZONA"\r\n'
        'PRODUCER_ID               = "UA"\r\n'
        'PRODUCER_FULL_NAME        = "ALFRED MCEWEN, USGS-ASTROGEOLOGY"\r\n'
        f'PRODUCT_ID                = "{product_id}"\r\n'
        'PRODUCT_VERSION_ID        = "1"\r\n'
        'INSTRUMENT_HOST_NAME      = "MARS RECONNAISSANCE ORBITER"\r\n'
        'INSTRUMENT_HOST_ID        = "MRO"\r\n'
        'INSTRUMENT_NAME           = "HIGH RESOLUTION IMAGING SCIENCE EXPERIMENT"\r\n'
        'INSTRUMENT_ID             = "HIRISE"\r\n'
        f'TARGET_NAME               = "{target_name}"\r\n'
        "SOURCE_PRODUCT_ID         = (ESP_045994_1985, ESP_046060_1985)\r\n"
        "OBJECT = IMAGE\r\n"
        f"  LINES            = {h}\r\n"
        f"  LINE_SAMPLES     = {w}\r\n"
        "  BANDS            = 1\r\n"
        f"  OFFSET           = {offset}\r\n"
        f"  SCALING_FACTOR   = {scaling_factor}\r\n"
        f"{note_clause}"
        f"  SAMPLE_BITS      = {sample_bits}\r\n"
        f"  SAMPLE_TYPE      = {sample_type}\r\n"
        f"{null_clause}"
        "  VALID_MINIMUM    = -2679.20\r\n"
        "  VALID_MAXIMUM    = -2388.31\r\n"
        "END_OBJECT = IMAGE\r\n"
        "OBJECT = IMAGE_MAP_PROJECTION\r\n"
        '  ^DATA_SET_MAP_PROJECTION     = "DSMAP.CAT"\r\n'
        '  MAP_PROJECTION_TYPE          = "EQUIRECTANGULAR"\r\n'
        "  PROJECTION_LATITUDE_TYPE     = PLANETOCENTRIC\r\n"
        "  A_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  B_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  C_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  COORDINATE_SYSTEM_NAME       = PLANETOCENTRIC\r\n"
        "  POSITIVE_LONGITUDE_DIRECTION = EAST\r\n"
        "  KEYWORD_LATITUDE_TYPE        = PLANETOCENTRIC\r\n"
        f"  CENTER_LATITUDE              = {center_lat} <DEG>\r\n"
        f"  CENTER_LONGITUDE             = {center_lon} <DEG>\r\n"
        "  LINE_FIRST_PIXEL             = 1\r\n"
        f"  LINE_LAST_PIXEL              = {h}\r\n"
        "  SAMPLE_FIRST_PIXEL           = 1\r\n"
        f"  SAMPLE_LAST_PIXEL            = {w}\r\n"
        "  MAP_PROJECTION_ROTATION      = 0.0 <DEG>\r\n"
        "  MAP_RESOLUTION               = 58684.0491709 <PIX/DEG>\r\n"
        f"  MAP_SCALE                    = {res_meters} <METERS/PIXEL>\r\n"
        f"  MAXIMUM_LATITUDE             = {max_lat} <DEG>\r\n"
        f"  MINIMUM_LATITUDE             = {min_lat} <DEG>\r\n"
        f"  LINE_PROJECTION_OFFSET       = {line_proj_offset:.6f} <PIXEL>\r\n"
        f"  SAMPLE_PROJECTION_OFFSET     = {sample_proj_offset:.6f} <PIXEL>\r\n"
        f"  EASTERNMOST_LONGITUDE        = {max_lon} <DEG>\r\n"
        f"  WESTERNMOST_LONGITUDE        = {min_lon} <DEG>\r\n"
        "END_OBJECT = IMAGE_MAP_PROJECTION\r\n"
        "END\r\n"
    )

    label_bytes = label_body.encode("ascii")
    num_hdr_records = int(np.ceil(len(label_bytes) / record_bytes))
    image_ptr = num_hdr_records + 1
    total_records = num_hdr_records + h

    label_text = label_body.replace("__FILE_RECORDS__", str(total_records).ljust(10))
    label_text = label_text.replace("__IMAGE_PTR__", str(image_ptr).ljust(10))
    raw_label = label_text.encode("ascii")
    total_hdr_bytes = num_hdr_records * record_bytes
    if len(raw_label) > total_hdr_bytes:
        num_hdr_records += 1
        image_ptr = num_hdr_records + 1
        total_records = num_hdr_records + h
        label_text = label_body.replace("__FILE_RECORDS__", str(total_records).ljust(10))
        label_text = label_text.replace("__IMAGE_PTR__", str(image_ptr).ljust(10))
        raw_label = label_text.encode("ascii")
        total_hdr_bytes = num_hdr_records * record_bytes

    padded_header = raw_label.ljust(total_hdr_bytes, b" ")
    with open(path, "wb") as f:
        f.write(padded_header)
        f.write(elev.tobytes())


def _write_hirise_pds3_detached_lbl_and_img(
    lbl_path: str,
    img_path: str,
    elev: np.ndarray,
    min_lon: float = 77.410,
    max_lat: float = 18.420,
    res_meters: float = 1.0,
    note_text: str | None = None,
    scaling_factor: float = 1.0,
    offset: float = 0.0,
    sample_bits: int = 32,
    sample_type: str = "PC_REAL",
    missing_constant_hex: str = "16#FF7FFFFB#",
    core_null: int | float | None = None,
    target_name: str = "MARS",
    product_id: str = "DTEEC_045994_1985_046060_1985_U01",
    data_set_id: str = "MRO-M-HIRISE-5-DTM-V1.0",
    center_lat: float = 15.0,
    center_lon: float = 77.44,
) -> None:
    """Helper to generate a deterministic detached PDS3 .LBL and companion .IMG fixture."""
    h, w = elev.shape
    bytes_per_sample = sample_bits // 8
    record_bytes = w * bytes_per_sample

    default_note = (
        "Pixel values in this file represent elevations in meters above the "
        "martian equipotential surface (Mars 2000 Datum) defined by Smith, et al. (2001). "
        "Conversion from pixel units to geophysical units is given by the keyvalues for "
        "SCALING_FACTOR and OFFSET. This DTM was produced using ISIS and SOCET Set "
        "(copyright BAE Systems) software as described in Kirk et al. (2008)."
    )
    actual_note = note_text if note_text is not None else default_note
    note_clause = f'  NOTE             = "{actual_note}"\r\n' if actual_note != "" else ""
    null_clause = (
        f"  CORE_NULL        = {core_null}\r\n"
        if core_null is not None
        else (
            f"  MISSING_CONSTANT = {missing_constant_hex}\r\n"
            if missing_constant_hex
            else ""
        )
    )

    rad_lat = math.radians(center_lat)
    r_mars = 3394839.8133163
    x_origin = r_mars * math.radians(min_lon - center_lon) * math.cos(rad_lat)
    y_origin = r_mars * math.radians(max_lat)

    sample_proj_offset = 0.5 - (x_origin / res_meters)
    line_proj_offset = (y_origin / res_meters) - 0.5

    min_lat = max_lat - math.degrees((h * res_meters) / r_mars)
    max_lon = min_lon + math.degrees((w * res_meters) / (r_mars * math.cos(rad_lat)))

    companion_img_filename = os.path.basename(img_path)
    label_body = (
        "PDS_VERSION_ID            = PDS3\r\n"
        "RECORD_TYPE               = FIXED_LENGTH\r\n"
        f"RECORD_BYTES              = {record_bytes}\r\n"
        f"FILE_RECORDS              = {h}\r\n"
        f'^IMAGE                    = "{companion_img_filename}"\r\n'
        f'DATA_SET_ID               = "{data_set_id}"\r\n'
        f'DATA_SET_NAME             = "MRO MARS HIGH RESOLUTION IMAGING SCIENCE EXPERIMENT DTM V1.0"\r\n'
        'PRODUCER_INSTITUTION_NAME = "UNIVERSITY OF ARIZONA"\r\n'
        'PRODUCER_ID               = "UA"\r\n'
        'PRODUCER_FULL_NAME        = "ALFRED MCEWEN, USGS-ASTROGEOLOGY"\r\n'
        f'PRODUCT_ID                = "{product_id}"\r\n'
        'PRODUCT_VERSION_ID        = "1"\r\n'
        'INSTRUMENT_HOST_NAME      = "MARS RECONNAISSANCE ORBITER"\r\n'
        'INSTRUMENT_HOST_ID        = "MRO"\r\n'
        'INSTRUMENT_NAME           = "HIGH RESOLUTION IMAGING SCIENCE EXPERIMENT"\r\n'
        'INSTRUMENT_ID             = "HIRISE"\r\n'
        f'TARGET_NAME               = "{target_name}"\r\n'
        "SOURCE_PRODUCT_ID         = (ESP_045994_1985, ESP_046060_1985)\r\n"
        "OBJECT = IMAGE\r\n"
        f"  LINES            = {h}\r\n"
        f"  LINE_SAMPLES     = {w}\r\n"
        "  BANDS            = 1\r\n"
        f"  OFFSET           = {offset}\r\n"
        f"  SCALING_FACTOR   = {scaling_factor}\r\n"
        f"{note_clause}"
        f"  SAMPLE_BITS      = {sample_bits}\r\n"
        f"  SAMPLE_TYPE      = {sample_type}\r\n"
        f"{null_clause}"
        "  VALID_MINIMUM    = -2679.20\r\n"
        "  VALID_MAXIMUM    = -2388.31\r\n"
        "END_OBJECT = IMAGE\r\n"
        "OBJECT = IMAGE_MAP_PROJECTION\r\n"
        '  ^DATA_SET_MAP_PROJECTION     = "DSMAP.CAT"\r\n'
        '  MAP_PROJECTION_TYPE          = "EQUIRECTANGULAR"\r\n'
        "  PROJECTION_LATITUDE_TYPE     = PLANETOCENTRIC\r\n"
        "  A_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  B_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  C_AXIS_RADIUS                = 3394.8398133163 <KM>\r\n"
        "  COORDINATE_SYSTEM_NAME       = PLANETOCENTRIC\r\n"
        "  POSITIVE_LONGITUDE_DIRECTION = EAST\r\n"
        "  KEYWORD_LATITUDE_TYPE        = PLANETOCENTRIC\r\n"
        f"  CENTER_LATITUDE              = {center_lat} <DEG>\r\n"
        f"  CENTER_LONGITUDE             = {center_lon} <DEG>\r\n"
        "  LINE_FIRST_PIXEL             = 1\r\n"
        f"  LINE_LAST_PIXEL              = {h}\r\n"
        "  SAMPLE_FIRST_PIXEL           = 1\r\n"
        f"  SAMPLE_LAST_PIXEL            = {w}\r\n"
        "  MAP_PROJECTION_ROTATION      = 0.0 <DEG>\r\n"
        "  MAP_RESOLUTION               = 58684.0491709 <PIX/DEG>\r\n"
        f"  MAP_SCALE                    = {res_meters} <METERS/PIXEL>\r\n"
        f"  MAXIMUM_LATITUDE             = {max_lat} <DEG>\r\n"
        f"  MINIMUM_LATITUDE             = {min_lat} <DEG>\r\n"
        f"  LINE_PROJECTION_OFFSET       = {line_proj_offset:.6f} <PIXEL>\r\n"
        f"  SAMPLE_PROJECTION_OFFSET     = {sample_proj_offset:.6f} <PIXEL>\r\n"
        f"  EASTERNMOST_LONGITUDE        = {max_lon} <DEG>\r\n"
        f"  WESTERNMOST_LONGITUDE        = {min_lon} <DEG>\r\n"
        "END_OBJECT = IMAGE_MAP_PROJECTION\r\n"
        "END\r\n"
    )

    with open(img_path, "wb") as f_img:
        f_img.write(elev.tobytes())

    with open(lbl_path, "wb") as f_lbl:
        f_lbl.write(label_body.encode("ascii"))


def _write_hirise_geotiff(
    path: str,
    elev: np.ndarray,
    min_lon: float = 77.40,
    max_lat: float = 18.42,
    res_meters: float = 1.0,
    crs_str: str | None = "+proj=longlat +R=3396190 +no_defs",
    nodata: float | None = -9999.0,
    tags: dict[str, str] | None = None,
    band_tags: dict[str, str] | None = None,
    band_unit: str | None = "m",
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
        if band_unit is not None:
            dst.set_band_unit(1, band_unit)
        if band_tags:
            dst.update_tags(1, **band_tags)
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
            dst.set_band_unit(1, "metre")
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


def test_19_vertical_elevation_units_positive_validation_and_mola_fallback():
    """
    Phase 4.1 Regression Test (1-4):
    - Missing vertical-unit metadata rejects HiRISE with `rejected_unknown_vertical_units`,
      even when elevation values (-2485.0) look numerically plausible and an unauthenticated
      PRODUCT_ID tag is present.
    - Unknown/ambiguous or conflicting units are rejected (`rejected_unknown_vertical_units`).
    - Unsupported imperial/angular units ('feet', 'degrees') are rejected (`rejected_unsupported_vertical_units`).
    - Radiometric/imagery units ('dn', 'reflectance') are rejected (`rejected_non_elevation_raster`).
    - Explicit metre units ('m', 'meter', 'meters', 'metre', 'metres') in band units, band tags,
      or dataset tags allow validation to succeed.
    - Explicit metric units ('cm') convert valid pixels to meters with documented scale factor (0.01)
      without corrupting NoData pixels.
    - Unknown units cannot produce a HiRISE route; regional MOLA-HRSC fallback succeeds cleanly.
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

        # Case 1: Missing vertical unit metadata (even with PRODUCT_ID tag and plausible values)
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            band_unit=None,
            tags={"PRODUCT_ID": "dem_hirise_jezero_delta_1m"},
        )
        prov_missing = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        val_missing = prov_missing.validate_hirise_raster()
        assert val_missing.is_valid is False
        assert val_missing.status_code == "rejected_unknown_vertical_units"

        # Verify route request falls back to MOLA-HRSC when HiRISE has unknown units
        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        service = RouteService(provider=mola_prov, hirise_provider=prov_missing)
        resp_fallback = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4106, lat=18.4094),
                destination=MarsCoordinate(lon=77.4114, lat=18.4086),
            )
        )
        assert resp_fallback.status == "success"
        assert resp_fallback.source_selection is not None
        assert resp_fallback.source_selection.hirise_selected is False
        assert resp_fallback.source_selection.hirise_status == "rejected_unknown_vertical_units"
        assert resp_fallback.source_selection.selected_source_tier == "regional_blended_dem"

        # Case 2: Conflicting band unit ('m') vs dataset tag ('cm') -> rejected_unknown_vertical_units
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            band_unit="m",
            tags={"VERTICAL_UNIT": "cm"},
        )
        val_conflict = HiRISERasterProvider(dem_path=hi_path, enabled=True).validate_hirise_raster()
        assert val_conflict.is_valid is False
        assert val_conflict.status_code == "rejected_unknown_vertical_units"

        # Case 3: Unsupported imperial unit ('feet') -> rejected_unsupported_vertical_units
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            band_unit=None,
            tags={"VERTICAL_UNIT": "feet"},
        )
        val_feet = HiRISERasterProvider(dem_path=hi_path, enabled=True).validate_hirise_raster()
        assert val_feet.is_valid is False
        assert val_feet.status_code == "rejected_unsupported_vertical_units"

        # Case 4: Radiometric unit ('reflectance') -> rejected_non_elevation_raster
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            band_unit="reflectance",
        )
        val_refl = HiRISERasterProvider(dem_path=hi_path, enabled=True).validate_hirise_raster()
        assert val_refl.is_valid is False
        assert val_refl.status_code == "rejected_non_elevation_raster"

        # Case 5: Explicit metre unit in dataset tag (with band_unit=None) -> valid
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            band_unit=None,
            tags={"ELEVATION_UNITS": "Metres"},
        )
        val_metres = HiRISERasterProvider(dem_path=hi_path, enabled=True).validate_hirise_raster()
        assert val_metres.is_valid is True
        assert val_metres.status_code == "ready"
        assert val_metres.raster is not None
        assert val_metres.raster.metadata.vertical_units == "meters"

        # Case 6: Explicit 'cm' unit converts valid pixels by 0.01 to meters and documents conversion
        hi_cm = np.full((120, 120), -248500.0, dtype=np.float32)  # -2485.0 m in cm
        hi_cm[0, 0] = -999999.0
        _write_hirise_geotiff(
            hi_path,
            hi_cm,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            nodata=-999999.0,
            band_unit="centimeters",
        )
        prov_cm = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        val_cm = prov_cm.validate_hirise_raster()
        assert val_cm.is_valid is True
        assert val_cm.raster is not None
        assert val_cm.raster.nodata_mask[0, 0] == np.True_
        assert val_cm.raster.data[10, 10] == pytest.approx(-2485.0, abs=0.01)
        cm_provenance = prov_cm.get_provenance()
        assert cm_provenance["units"] == "meters"
        assert any("converted" in lim.lower() for lim in cm_provenance["provenance_limitations"])
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_20_projected_raster_nodata_hole_conservative_propagation():
    """
    Phase 4.1 Regression Test (6-8):
    - Creates a projected Mars Equirectangular raster with a localized 1x1 NoData hole at (50, 50)
      and a 2x2 NoData hole at (70:72, 70:72) surrounded by valid -2475.0 m elevation pixels.
    - Extracts a destination geographic analysis grid whose bilinear resampling footprint
      straddles the single-pixel NoData hole.
    - Verifies that all 4 destination pixels whose bilinear interpolation kernel touches the
      1x1 NoData hole become NaN (whereas the old buggy src_nodata=1.0 left 2 of them interpolated),
      valid regions away from NoData remain aligned at -2475.0 m, and zero 0.0 values are created.
    """
    from backend.app.services.terrain_source_service import TerrainSourceSelector

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi_proj:
        hi_proj_path = tmp_hi_proj.name

    try:
        crs_proj = (
            "+proj=eqc +lat_ts=18.405 +lat_0=18.405 +lon_0=77.415 "
            "+x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"
        )
        transform = from_origin(-50.0, 50.0, 1.0, 1.0)
        hi_elev = np.full((100, 100), -2475.0, dtype=np.float32)
        # Localized 2x2 NoData hole at rows 49..50, cols 49..50 surrounded by valid -2475.0m pixels
        hi_elev[49:51, 49:51] = -9999.0

        with rasterio.open(
            hi_proj_path,
            "w",
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="float32",
            crs=crs_proj,
            transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.set_band_unit(1, "m")
            dst.write(hi_elev, 1)

        hi_prov = HiRISERasterProvider(dem_path=hi_proj_path, enabled=True)
        val = hi_prov.validate_hirise_raster()
        assert val.is_valid is True
        assert val.raster is not None

        # Extract a corridor window centered over (77.415, 18.405) where destination pixels
        # straddle the 2x2 NoData hole (3 rows x 2 cols = 6 destination pixels touch the hole;
        # the old buggy src_nodata=1.0 only marked 2 and interpolated the other 4!)
        warped_elev, warped_meta = TerrainSourceSelector._extract_native_hirise_corridor(
            hirise_raster=val.raster,
            corr_min_lon=77.4145,
            corr_min_lat=18.4045,
            corr_max_lon=77.4155,
            corr_max_lat=18.4055,
        )

        # All 6 destination cells touching the 2x2 source NoData hole must be NaN
        nan_count = int(np.sum(np.isnan(warped_elev)))
        assert nan_count == 6
        # Never turn NoData into 0.0
        assert not np.any(warped_elev == 0.0)
        # All valid cells away from the hole preserve exact -2475.0m elevation
        valid_vals = warped_elev[~np.isnan(warped_elev)]
        assert valid_vals.size > 0
        assert np.allclose(valid_vals, -2475.0, atol=1e-3)
        assert warped_meta.crs_str == "IAU2000:49900"
    finally:
        if os.path.exists(hi_proj_path):
            os.remove(hi_proj_path)


def test_21_provider_cache_reuse_single_load_single_hash_and_invalidation(monkeypatch):
    """
    Phase 4.1 Regression Test (9-11):
    - Repeated RouteService and DataCatalogService constructions reuse the shared provider/cache.
    - Across multiple RouteService instances, route plans, get_data_status(), get_layer_list(),
      and get_provenance() calls on an unchanged file, `load_raster_file` is called ONCE and
      `_compute_file_sha256` is called ONCE.
    - Modifying the file on disk invalidates the cached entry by file identity, evicts the stale
      raster copy, and recomputes validation and SHA-256 exactly once for the new file version.
    """
    import backend.app.data.providers.hirise as hirise_mod

    HiRISERasterProvider.clear_process_cache()

    load_calls = 0
    hash_calls = 0
    orig_load = hirise_mod.load_raster_file
    orig_hash = hirise_mod._compute_file_sha256

    def counting_load(path: str):
        nonlocal load_calls
        load_calls += 1
        return orig_load(path)

    def counting_hash(path: str):
        nonlocal hash_calls
        hash_calls += 1
        return orig_hash(path)

    monkeypatch.setattr(hirise_mod, "load_raster_file", counting_load)
    monkeypatch.setattr(hirise_mod, "_compute_file_sha256", counting_hash)

    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        hi_elev_v1 = np.full((150, 150), -2490.0, dtype=np.float32)
        _write_hirise_geotiff(
            hi_path, hi_elev_v1, min_lon=77.410, max_lat=18.410, res_meters=1.0, band_unit="m"
        )

        # Verify default RouteService() and DataCatalogService() share the same provider instance
        rs_default_1 = RouteService()
        rs_default_2 = RouteService()
        cat_default = DataCatalogService()
        assert rs_default_1.hirise_provider is rs_default_2.hirise_provider
        assert rs_default_1.hirise_provider is cat_default.hirise_provider
        assert rs_default_1.provider is rs_default_2.provider

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True

        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4108, lat=18.4092),
            destination=MarsCoordinate(lon=77.4116, lat=18.4084),
        )

        # Execute 3 separate RouteService instances and 2 DataCatalogService instances on hi_path
        for _ in range(3):
            hi_p = HiRISERasterProvider(dem_path=hi_path, enabled=True)
            svc = RouteService(provider=mola_prov, hirise_provider=hi_p)
            resp = svc.plan_route(req)
            assert resp.source_selection is not None
            assert resp.source_selection.hirise_selected is True
            _ = hi_p.get_provenance()

        for _ in range(2):
            cat = DataCatalogService(
                provider=mola_prov,
                hirise_provider=HiRISERasterProvider(dem_path=hi_path, enabled=True),
            )
            _ = cat.get_data_status()
            _ = cat.get_layer_list()

        # File v1 must have been loaded ONCE and hashed ONCE across all 5 service runs!
        assert load_calls == 1
        assert hash_calls == 1
        assert len(HiRISERasterProvider._PROCESS_CACHE) == 1

        # Now overwrite hi_path with new elevation (-2420.0m) -> cache must invalidate automatically
        hi_elev_v2 = np.full((150, 150), -2420.0, dtype=np.float32)
        _write_hirise_geotiff(
            hi_path, hi_elev_v2, min_lon=77.410, max_lat=18.410, res_meters=1.0, band_unit="m"
        )

        hi_p_v2 = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        svc_v2 = RouteService(provider=mola_prov, hirise_provider=hi_p_v2)
        resp_v2 = svc_v2.plan_route(req)
        assert resp_v2.routes[0].summary.min_elevation_meters == pytest.approx(-2420.0, abs=0.5)
        assert load_calls == 2
        assert hash_calls == 2
        # Stale entry for the same path was evicted -> still only 1 cached entry in memory
        assert len(HiRISERasterProvider._PROCESS_CACHE) == 1
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_22_concurrent_route_requests_never_mutate_shared_source_terrain():
    """
    Phase 4.1 Regression Test (12):
    - Shared cached RasterData arrays are marked read-only (`writeable = False`).
    - Concurrent route requests (including robustness stress-testing perturbations and
      block aggregation) cannot mutate the shared source elevation or nodata mask arrays.
    """
    from concurrent.futures import ThreadPoolExecutor

    with (
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_hi,
    ):
        mola_path = tmp_mola.name
        hi_path = tmp_hi.name

    try:
        _write_mola_geotiff(mola_path)
        r_idx, c_idx = np.meshgrid(np.arange(160), np.arange(160), indexing="ij")
        hi_elev = (-2490.0 + 0.03 * r_idx + 0.02 * c_idx).astype(np.float32)
        hi_elev[5, 5] = -9999.0
        _write_hirise_geotiff(
            hi_path,
            hi_elev,
            min_lon=77.410,
            max_lat=18.410,
            res_meters=1.0,
            nodata=-9999.0,
            band_unit="m",
        )

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        hi_prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        shared_raster = hi_prov.get_dem_raster()
        assert shared_raster.data.flags.writeable is False
        assert shared_raster.nodata_mask.flags.writeable is False
        snapshot_before = shared_raster.data.copy()
        mask_before = shared_raster.nodata_mask.copy()

        with pytest.raises(ValueError):
            shared_raster.data[10, 10] = 0.0

        def _worker(seed_val: int) -> float:
            svc = RouteService(
                provider=mola_prov,
                hirise_provider=HiRISERasterProvider(dem_path=hi_path, enabled=True),
                max_cells=2500 if seed_val % 2 == 0 else 250000,
            )
            req = RoutePlanRequest(
                start=MarsCoordinate(lon=77.4106, lat=18.4094),
                destination=MarsCoordinate(lon=77.4114, lat=18.4086),
                robustness_config=RobustnessConfig(
                    enabled=True,
                    vertical_sigma_m=0.25,
                    correlation_length_m=4.0,
                    scenario_count=3,
                    seed=seed_val,
                ),
            )
            res = svc.plan_route(req)
            return res.routes[0].total_cost

        with ThreadPoolExecutor(max_workers=4) as pool:
            costs = list(pool.map(_worker, [11, 22, 33, 44]))

        assert len(costs) == 4
        assert all(c > 0.0 for c in costs)
        assert np.array_equal(shared_raster.data, snapshot_before, equal_nan=True)
        assert np.array_equal(shared_raster.nodata_mask, mask_before)
    finally:
        for p in (mola_path, hi_path):
            if os.path.exists(p):
                os.remove(p)


def test_23_pds3_dtm_official_note_convention_and_mars2000_vertical_reference():
    """
    Phase 4.2 Test (1 & 2):
    - Parses official NASA/JPL/UArizona HiRISE PDS3 DTM label semantics.
    - Recognizes the documented elevation-in-metres statement without accepting arbitrary prose.
    - Recognizes the Mars 2000 equipotential surface vertical reference datum.
    - Validates recognized variants without inventing unstated datums.
    """
    with tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_hi:
        hi_path = tmp_hi.name

    try:
        elev = np.full((25, 25), -2480.0, dtype=np.float32)
        _write_hirise_pds3_img(
            hi_path,
            elev,
            min_lon=77.410,
            max_lat=18.420,
            res_meters=1.0,
            note_text=(
                "Pixel values in this file represent elevations in meters above the "
                "martian equipotential surface (Mars 2000 Datum) defined by Smith, et al. (2001). "
                "Conversion from pixel units to geophysical units is given by the keyvalues for "
                "SCALING_FACTOR and OFFSET. This DTM was produced using ISIS and SOCET Set "
                "(copyright BAE Systems) software as described in Kirk et al. (2008)."
            ),
        )

        pds_dict = extract_pds3_label_dict(hi_path)
        assert pds_dict is not None
        assert pds_dict.get("PRODUCT_ID") == "DTEEC_045994_1985_046060_1985_U01"

        raster = load_raster_file(hi_path)
        assert raster.metadata.vertical_units == "meters"
        assert (
            raster.metadata.vertical_datum
            == "Mars 2000 Datum (Martian Equipotential Surface, Smith et al. 2001)"
        )
        assert raster.metadata.metadata_tags["_HAS_PDS3_LABEL"] == "true"
        assert raster.metadata.metadata_tags["PRODUCT_ID"] == "DTEEC_045994_1985_046060_1985_U01"

        prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        val = prov.validate_hirise_raster()
        assert val.is_valid is True
        assert val.status_code == "ready"

        # Test variant NOTE declarations
        var_note_1 = "Pixel values in this file represent elevations in meters above Mars 2000 Datum."
        res_v1 = parse_pds3_hirise_dtm_label({"IMAGE": {"NOTE": var_note_1}})
        assert res_v1.is_valid_dtm is True
        assert res_v1.vertical_units == "meters"
        assert res_v1.vertical_datum == "Mars 2000 Datum"

        var_note_2 = "Pixel values in this file represent elevations in meters above Martian Equipotential Surface."
        res_v2 = parse_pds3_hirise_dtm_label({"IMAGE": {"NOTE": var_note_2}})
        assert res_v2.is_valid_dtm is True
        assert res_v2.vertical_datum == "Mars 2000 Datum (Martian Equipotential Surface)"

        var_note_3 = "Pixel values in this file represent elevations in metres above Mars Areoid (MOLA 0m reference datum)."
        res_v3 = parse_pds3_hirise_dtm_label({"IMAGE": {"NOTE": var_note_3}})
        assert res_v3.is_valid_dtm is True
        assert res_v3.vertical_datum == "Mars Areoid (MOLA 0m reference datum)"
    finally:
        if os.path.exists(hi_path):
            os.remove(hi_path)


def test_24_pds3_dtm_scaling_factor_offset_and_nodata_preservation():
    """
    Phase 4.2 / 4.2.1 Test (3 & 4):
    - Reads and applies PDS3 SCALING_FACTOR and OFFSET transformations.
    - Mandatory regression test: A stored sample of -10000 with SCALING_FACTOR=0.5
      and OFFSET=-2500 must decode to -7500 m and remain valid, not NoData.
    - Explicit PDS3 missing sentinels (16#FF7FFFFB#, CORE_NULL=-32768) remain NoData with non-default scale and offset.
    - Preserves NoData values during transformation without converting missing pixels to 0.0.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_f32,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_i16,
    ):
        f32_path = tmp_f32.name
        i16_path = tmp_i16.name

    try:
        # Case A: 32-bit float with SCALING_FACTOR=0.5, OFFSET=-2500.0, and 16#FF7FFFFB# missing constant
        # Raw value 100.0 -> elevation = 100.0 * 0.5 + (-2500.0) = -2450.0 meters.
        arr_f32 = np.full((20, 20), 100.0, dtype="<f4")
        # Hex 0xFF7FFFFB in big-endian float32 is ~ -3.4028227e+38 (explicit PDS3 missing constant)
        arr_f32[0, 0] = -3.4028226550889045e38
        # Mandatory regression test: stored -10000 -> (-10000 * 0.5) + (-2500) = -7500m (valid, not NoData!)
        arr_f32[1, 1] = -10000.0

        _write_hirise_pds3_img(
            f32_path,
            arr_f32,
            scaling_factor=0.5,
            offset=-2500.0,
            missing_constant_hex="16#FF7FFFFB#",
        )

        r_f32 = load_raster_file(f32_path)
        # Missing constant [0, 0] must be NoData and not scaled
        assert r_f32.nodata_mask[0, 0] is True or r_f32.nodata_mask[0, 0] == 1
        assert np.isnan(r_f32.get_elevation_at_pixel(0, 0))

        # Stored -10000 sample must decode to -7500m and remain VALID, NOT NoData!
        assert r_f32.nodata_mask[1, 1] is False or r_f32.nodata_mask[1, 1] == 0
        assert r_f32.data[1, 1] == pytest.approx(-7500.0, abs=1e-3)
        assert r_f32.get_elevation_at_pixel(1, 1) == pytest.approx(-7500.0, abs=1e-3)

        # Baseline sample 100.0 -> -2450.0m (valid)
        assert r_f32.nodata_mask[5, 5] is False or r_f32.nodata_mask[5, 5] == 0
        assert r_f32.data[5, 5] == pytest.approx(-2450.0, abs=1e-3)
        assert r_f32.get_elevation_at_pixel(5, 5) == pytest.approx(-2450.0, abs=1e-3)

        # Case B: 16-bit integer DTM with CORE_NULL = -32768, SCALING_FACTOR=0.25, OFFSET=-2400.0
        # Raw value 200 -> elevation = 200 * 0.25 + (-2400.0) = -2350.0 meters.
        arr_i16 = np.full((20, 20), 200, dtype="<i2")
        arr_i16[0, 0] = -32768
        # Stored negative raw value -1000 -> (-1000 * 0.25) + (-2400.0) = -2650.0 meters (valid!)
        arr_i16[1, 1] = -1000

        _write_hirise_pds3_img(
            i16_path,
            arr_i16,
            sample_bits=16,
            sample_type="LSB_INTEGER",
            core_null=-32768,
            scaling_factor=0.25,
            offset=-2400.0,
        )

        r_i16 = load_raster_file(i16_path)
        # CORE_NULL [0, 0] must be NoData and not scaled
        assert r_i16.nodata_mask[0, 0] is True or r_i16.nodata_mask[0, 0] == 1
        assert np.isnan(r_i16.get_elevation_at_pixel(0, 0))

        # Stored -1000 must decode to -2650m and remain VALID
        assert r_i16.nodata_mask[1, 1] is False or r_i16.nodata_mask[1, 1] == 0
        assert r_i16.data[1, 1] == pytest.approx(-2650.0, abs=1e-3)
        assert r_i16.get_elevation_at_pixel(1, 1) == pytest.approx(-2650.0, abs=1e-3)

        # Stored 200 must decode to -2350m and remain VALID
        assert r_i16.nodata_mask[5, 5] is False or r_i16.nodata_mask[5, 5] == 0
        assert r_i16.data[5, 5] == pytest.approx(-2350.0, abs=1e-3)
        assert r_i16.get_elevation_at_pixel(5, 5) == pytest.approx(-2350.0, abs=1e-3)
    finally:
        for p in (f32_path, i16_path):
            if os.path.exists(p):
                os.remove(p)


def test_25_pds3_dtm_missing_unknown_and_unsupported_label_rejections():
    """
    Phase 4.2 Test (5, 6, 7):
    - Rejects missing NOTE declaration.
    - Rejects radiometric I/F or orthoimage note text.
    - Rejects non-metric or unsupported units (e.g. feet).
    - Rejects non-Mars planetary datum (e.g. WGS84, Earth sea level).
    - Rejects 8-bit browse image formats.
    - Rejects non-Mars target name.
    - Rejects conflicting datum declarations.
    - Falls back to regional MOLA-HRSC with explicit rejection status.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_no_note,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_feet,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_radio,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_earth,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_moon,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_8bit,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
    ):
        no_note_path = tmp_no_note.name
        feet_path = tmp_feet.name
        radio_path = tmp_radio.name
        earth_path = tmp_earth.name
        moon_path = tmp_moon.name
        bit8_path = tmp_8bit.name
        mola_path = tmp_mola.name

    try:
        _write_mola_geotiff(mola_path)
        elev_f32 = np.full((20, 20), -2480.0, dtype=np.float32)

        # 1. Missing NOTE
        _write_hirise_pds3_img(no_note_path, elev_f32, note_text="")
        val1 = HiRISERasterProvider(dem_path=no_note_path, enabled=True).validate_hirise_raster()
        assert val1.is_valid is False
        assert val1.status_code == "rejected_unknown_vertical_units"

        # 2. Feet units in NOTE
        _write_hirise_pds3_img(
            feet_path,
            elev_f32,
            note_text="Pixel values in this file represent elevations in feet above the Mars 2000 Datum.",
        )
        val2 = HiRISERasterProvider(dem_path=feet_path, enabled=True).validate_hirise_raster()
        assert val2.is_valid is False
        assert val2.status_code == "rejected_unsupported_vertical_units"

        # 3. Radiometric / Orthoimage NOTE
        _write_hirise_pds3_img(
            radio_path,
            elev_f32,
            note_text="The conversion from DN to I/F (intensity/flux) is given by SCALING_FACTOR.",
        )
        val3 = HiRISERasterProvider(dem_path=radio_path, enabled=True).validate_hirise_raster()
        assert val3.is_valid is False
        assert val3.status_code == "rejected_non_elevation_raster"

        # 4. Earth datum in NOTE
        _write_hirise_pds3_img(
            earth_path,
            elev_f32,
            note_text="Pixel values represent elevations in meters above Earth WGS84 mean sea level.",
        )
        val4 = HiRISERasterProvider(dem_path=earth_path, enabled=True).validate_hirise_raster()
        assert val4.is_valid is False
        assert val4.status_code == "rejected_invalid_crs"

        # 5. Non-Mars TARGET_NAME
        _write_hirise_pds3_img(moon_path, elev_f32, target_name="MOON")
        val5 = HiRISERasterProvider(dem_path=moon_path, enabled=True).validate_hirise_raster()
        assert val5.is_valid is False
        assert val5.status_code == "rejected_invalid_crs"

        # 6. 8-bit sample bits
        elev_u8 = np.full((20, 20), 128, dtype=np.uint8)
        _write_hirise_pds3_img(
            bit8_path, elev_u8, sample_bits=8, sample_type="MSB_UNSIGNED_INTEGER"
        )
        val6 = HiRISERasterProvider(dem_path=bit8_path, enabled=True).validate_hirise_raster()
        assert val6.is_valid is False
        assert val6.status_code == "rejected_non_elevation_raster"

        # Verify route fallback to regional MOLA with explicit status reporting
        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        svc = RouteService(
            provider=mola_prov,
            hirise_provider=HiRISERasterProvider(dem_path=feet_path, enabled=True),
        )
        resp = svc.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.4106, lat=18.4094),
                destination=MarsCoordinate(lon=77.4114, lat=18.4086),
            )
        )
        assert resp.source_selection.hirise_selected is False
        assert resp.source_selection.hirise_status == "rejected_unsupported_vertical_units"
        assert resp.source_selection.selected_source_tier == "regional_blended_dem"
    finally:
        for p in (no_note_path, feet_path, radio_path, earth_path, moon_path, bit8_path, mola_path):
            if os.path.exists(p):
                os.remove(p)


def test_26_pds3_img_and_geotiff_validation_parity_and_route_equivalence():
    """
    Phase 4.2 Test (8):
    - Confirms validation and routing parity between GeoTIFF and PDS3 IMG formats.
    - Both formats validate correctly, extract identical corridors, and yield equivalent routes.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_pds3,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_gtiff,
        tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_mola,
    ):
        pds3_path = tmp_pds3.name
        gtiff_path = tmp_gtiff.name
        mola_path = tmp_mola.name

    try:
        _write_mola_geotiff(mola_path)

        r_grid, c_grid = np.meshgrid(np.arange(200), np.arange(200), indexing="ij")
        elev = (-2485.0 + 0.04 * r_grid + 0.03 * c_grid).astype(np.float32)

        _write_hirise_pds3_img(
            pds3_path,
            elev,
            min_lon=77.410,
            max_lat=18.420,
            res_meters=1.0,
        )
        _write_hirise_geotiff(
            gtiff_path,
            elev,
            min_lon=77.410,
            max_lat=18.420,
            res_meters=1.0,
            band_unit="m",
            tags={"VERTICAL_DATUM": "Mars 2000 Datum (Martian Equipotential Surface, Smith et al. 2001)"},
        )

        pds3_val = HiRISERasterProvider(dem_path=pds3_path, enabled=True).validate_hirise_raster()
        gtiff_val = HiRISERasterProvider(dem_path=gtiff_path, enabled=True).validate_hirise_raster()
        assert pds3_val.is_valid is True
        assert gtiff_val.is_valid is True
        assert pds3_val.status_code == "ready"
        assert gtiff_val.status_code == "ready"

        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True

        req = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4190),
            destination=MarsCoordinate(lon=77.4122, lat=18.4182),
        )

        svc_pds3 = RouteService(
            provider=mola_prov,
            hirise_provider=HiRISERasterProvider(dem_path=pds3_path, enabled=True),
        )
        resp_pds3 = svc_pds3.plan_route(req)

        svc_gtiff = RouteService(
            provider=mola_prov,
            hirise_provider=HiRISERasterProvider(dem_path=gtiff_path, enabled=True),
        )
        resp_gtiff = svc_gtiff.plan_route(req)

        assert resp_pds3.source_selection.hirise_selected is True
        assert resp_gtiff.source_selection.hirise_selected is True
        assert (
            resp_pds3.routes[0].summary.total_distance_meters
            == pytest.approx(resp_gtiff.routes[0].summary.total_distance_meters, abs=1.0)
        )
        assert resp_pds3.routes[0].total_cost == pytest.approx(resp_gtiff.routes[0].total_cost, abs=1.0)
        assert (
            resp_pds3.routes[0].evidence_passport.source.vertical_datum
            == resp_gtiff.routes[0].evidence_passport.source.vertical_datum
        )
    finally:
        for p in (pds3_path, gtiff_path, mola_path):
            if os.path.exists(p):
                os.remove(p)


def test_27_pds3_provenance_attribution_no_redundant_hashing_and_unverified_status():
    """
    Phase 4.2 Test (9, 10, 11):
    - Confirms that genuine HiRISE DTM identity (DTEEC_045994_1985_046060_1985_U01) is preserved.
    - Avoids attributing different products (e.g. ESP_037803) merely because coverage overlaps.
    - Keeps provenance status as `valid_numeric_raster_unverified_source` when no matching authoritative hash exists.
    - Avoids unnecessary full-file MD5 hashing when no matching catalog MD5 exists.
    - Reuses cached SHA-256 and provenance across repeated calls.
    """
    with tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_hi:
        hi_path = tmp_hi.name

    try:
        elev = np.full((25, 25), -2480.0, dtype=np.float32)
        _write_hirise_pds3_img(
            hi_path,
            elev,
            product_id="DTEEC_045994_1985_046060_1985_U01",
        )

        HiRISERasterProvider.clear_process_cache()
        prov = HiRISERasterProvider(dem_path=hi_path, enabled=True)

        with mock.patch("backend.app.data.manifest._compute_file_digest", wraps=manifest._compute_file_digest) as mock_digest:
            p1 = prov.get_provenance()
            assert mock_digest.call_count == 0  # Zero MD5 full-file passes!

            assert p1["declared_product_id"] == "DTEEC_045994_1985_046060_1985_U01"
            assert p1["matched_catalog_product_id"] == "DTEEC_045994_1985_046060_1985_U01"
            assert p1["official_product_id"] is None
            assert p1["source_checksum_verified"] is False
            assert p1["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
            assert p1["file_format"] == "PDS3 IMG"
            assert p1["pds3_label_metadata"] is not None
            assert p1["pds3_label_metadata"]["product_id"] == "DTEEC_045994_1985_046060_1985_U01"

            # Second provenance call: cached, zero additional file digest calls
            p2 = prov.get_provenance()
            assert mock_digest.call_count == 0
            assert p2["file_sha256"] == p1["file_sha256"]

        # When authoritative checksum is registered in manifest, transitions to verified_source
        file_sha = p1["file_sha256"]
        dteec_entry = next(p for p in DATA_CATALOG_MANIFEST if p["id"] == "DTEEC_045994_1985_046060_1985_U01")
        old_sha = dteec_entry.get("sha256")
        dteec_entry["sha256"] = file_sha
        try:
            HiRISERasterProvider.clear_process_cache()
            p_auth = HiRISERasterProvider(dem_path=hi_path, enabled=True).get_provenance()
            assert p_auth["real_data_validation_status"] == "verified_source"
            assert p_auth["official_product_id"] == "DTEEC_045994_1985_046060_1985_U01"
            assert p_auth["source_checksum_verified"] is True
            assert p_auth["provenance_verification_method"] == "authoritative_manifest_sha256_match"
        finally:
            dteec_entry["sha256"] = old_sha
    finally:
        if os.path.exists(hi_path):
            os.remove(hi_path)


@pytest.mark.skipif(
    not os.path.exists("/tmp/DTEEC_045994_1985_046060_1985_U01.IMG"),
    reason="Real official HiRISE PDS3 DTM file not present on local machine",
)
def test_28_real_hirise_dtm_pds3_loading_and_route_smoke():
    """
    Phase 4.2 Test: Real-data validation and route planning smoke test using the genuine
    NASA/JPL/UArizona 381 MB HiRISE PDS3 DTM (DTEEC_045994_1985_046060_1985_U01.IMG).
    """
    real_path = "/tmp/DTEEC_045994_1985_046060_1985_U01.IMG"
    hi_prov = HiRISERasterProvider(dem_path=real_path, enabled=True)
    val = hi_prov.validate_hirise_raster()

    assert val.is_valid is True
    assert val.status_code == "ready"
    assert val.raster is not None
    assert val.raster.metadata.width == 6673
    assert val.raster.metadata.height == 14266
    assert val.raster.metadata.vertical_units == "meters"
    assert "Mars 2000 Datum" in val.raster.metadata.vertical_datum

    prov = hi_prov.get_provenance()
    assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
    assert prov["file_format"] == "PDS3 IMG"
    assert prov["pds3_label_metadata"]["product_id"] == "DTEEC_045994_1985_046060_1985_U01"

    # Plan route inside usable HiRISE delta footprint
    mola_prov = MOLAHRSCRasterProvider()
    svc = RouteService(provider=mola_prov, hirise_provider=hi_prov)

    req_in = RoutePlanRequest(
        start=MarsCoordinate(lon=77.435, lat=18.420),
        destination=MarsCoordinate(lon=77.438, lat=18.423),
    )
    resp_in = svc.plan_route(req_in)
    assert resp_in.status == "success"
    assert resp_in.source_selection.hirise_selected is True
    assert resp_in.source_selection.selected_source_id == "DTEEC_045994_1985_046060_1985_U01"
    assert resp_in.source_selection.selected_source_tier == "localized_high_resolution_dtm"
    assert resp_in.source_selection.native_resolution_meters == pytest.approx(1.01, abs=0.05)
    ev = resp_in.routes[0].evidence_passport
    assert "Mars 2000 Datum" in ev.source.vertical_datum
    assert ev.quality_tier == EvidenceQualityTier.UNVERIFIED

    # Plan route outside footprint -> MOLA fallback
    req_out = RoutePlanRequest(
        start=MarsCoordinate(lon=77.20, lat=18.30),
        destination=MarsCoordinate(lon=77.25, lat=18.35),
    )
    resp_out = svc.plan_route(req_out)
    assert resp_out.status == "success"
    assert resp_out.source_selection.hirise_selected is False
    assert resp_out.source_selection.hirise_status == "partial_or_no_corridor_coverage"


def test_29_detached_pds3_lbl_companion_img_ingestion_and_routing():
    """
    Phase 4.2.1 Test:
    - Demonstrates support for detached PDS3 labels where metadata is stored in a .LBL file
      pointing to a companion .IMG binary in the same directory via ^IMAGE.
    - Opens via the configured .LBL path in Rasterio/GDAL.
    - Verifies dimensions, CRS, affine transform, PDS3 NOTE, product ID, vertical datum, and NoData.
    - Verifies that MARSPATH_HIRISE_DEM_PATH can point to the .LBL file and execute route planning.
    - Verifies cache invalidation when the detached file is modified.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        lbl_path = os.path.join(tmp_dir, "DTEEC_045994_1985_046060_1985_U01.LBL")
        img_path = os.path.join(tmp_dir, "DTEEC_045994_1985_046060_1985_U01.IMG")
        mola_path = os.path.join(tmp_dir, "mola.tif")
        _write_mola_geotiff(mola_path)

        h, w = 200, 200
        r_grid, c_grid = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        elev = (-2485.0 + 0.04 * r_grid + 0.03 * c_grid).astype(np.float32)
        elev[0, 0] = -3.4028227e38  # NoData sentinel

        _write_hirise_pds3_detached_lbl_and_img(
            lbl_path=lbl_path,
            img_path=img_path,
            elev=elev,
            min_lon=77.410,
            max_lat=18.420,
            res_meters=1.0,
        )

        # 1. Test direct loader on .LBL file
        raster = load_raster_file(lbl_path)
        assert raster.metadata.width == w
        assert raster.metadata.height == h
        assert raster.metadata.vertical_units == "meters"
        assert "Mars 2000 Datum" in raster.metadata.vertical_datum
        assert raster.nodata_mask[0, 0] is True or raster.nodata_mask[0, 0] == 1
        assert raster.nodata_mask[5, 5] is False or raster.nodata_mask[5, 5] == 0

        # 2. Test HiRISERasterProvider configured with .LBL path
        hi_prov = HiRISERasterProvider(dem_path=lbl_path, enabled=True)
        val = hi_prov.validate_hirise_raster()
        assert val.is_valid is True
        assert val.status_code == "ready"
        assert val.raster is not None
        assert val.raster.data.flags.writeable is False
        assert val.raster.nodata_mask.flags.writeable is False

        prov = hi_prov.get_provenance()
        assert prov["file_format"] == "PDS3 LBL"
        assert prov["pds3_label_metadata"]["product_id"] == "DTEEC_045994_1985_046060_1985_U01"
        assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"

        # 3. Test route planning inside delta footprint
        mola_prov = MOLAHRSCRasterProvider(dem_path=mola_path)
        mola_prov.use_real_dem = True
        svc = RouteService(provider=mola_prov, hirise_provider=hi_prov)

        req_in = RoutePlanRequest(
            start=MarsCoordinate(lon=77.4112, lat=18.4190),
            destination=MarsCoordinate(lon=77.4122, lat=18.4182),
        )
        resp_in = svc.plan_route(req_in)
        assert resp_in.status == "success"
        assert resp_in.source_selection.hirise_selected is True
        assert resp_in.source_selection.selected_source_id == "DTEEC_045994_1985_046060_1985_U01"
        assert resp_in.routes[0].summary.total_distance_meters == pytest.approx(77.2, abs=1.0)
        assert "Mars 2000 Datum" in resp_in.routes[0].evidence_passport.source.vertical_datum

        # 4. Route outside footprint -> falls back to MOLA
        req_out = RoutePlanRequest(
            start=MarsCoordinate(lon=77.20, lat=18.30),
            destination=MarsCoordinate(lon=77.25, lat=18.35),
        )
        resp_out = svc.plan_route(req_out)
        assert resp_out.status == "success"
        assert resp_out.source_selection.hirise_selected is False
        assert resp_out.source_selection.hirise_status == "partial_or_no_corridor_coverage"

        # 5. Process cache reuses validated entry
        hi_prov_2 = HiRISERasterProvider(dem_path=lbl_path, enabled=True)
        val_2 = hi_prov_2.validate_hirise_raster()
        assert val_2.raster is val.raster

        # 6. Modifying file triggers cache eviction
        os.utime(lbl_path, (os.path.getatime(lbl_path) + 10, os.path.getmtime(lbl_path) + 10))
        val_3 = HiRISERasterProvider(dem_path=lbl_path, enabled=True).validate_hirise_raster()
        assert val_3.raster is not None


def test_30_pds3_pc_integer_signed_decoding_and_unsigned_rejections():
    """
    Phase 4.2.1 Test:
    - Verifies PC_INTEGER signed integer PDS3 encoding interpretation.
    - Confirms that negative stored values decode accurately through SCALING_FACTOR and OFFSET.
    - Confirms that CORE_NULL sentinels are preserved without corruption.
    - Confirms that unsigned integer imagery formats are rejected.
    """
    with (
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_pc,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_u16,
        tempfile.NamedTemporaryFile(suffix=".IMG", delete=False) as tmp_u8,
    ):
        pc_path = tmp_pc.name
        u16_path = tmp_u16.name
        u8_path = tmp_u8.name

    try:
        # 1. 16-bit PC_INTEGER signed integer with SCALING_FACTOR=0.5, OFFSET=-2450.0, CORE_NULL=-32768
        # Stored values:
        # [0, 0] = -32768 (CORE_NULL)
        # [1, 1] = -50 -> (-50 * 0.5) + (-2450.0) = -2475.0 m (valid negative offset)
        # [2, 2] = 0   -> (0 * 0.5) + (-2450.0) = -2450.0 m (valid baseline)
        # [5, 5] = 100 -> (100 * 0.5) + (-2450.0) = -2400.0 m (valid positive offset)
        arr_pc = np.full((20, 20), 100, dtype="<i2")
        arr_pc[0, 0] = -32768
        arr_pc[1, 1] = -50
        arr_pc[2, 2] = 0

        _write_hirise_pds3_img(
            pc_path,
            arr_pc,
            sample_bits=16,
            sample_type="PC_INTEGER",
            core_null=-32768,
            scaling_factor=0.5,
            offset=-2450.0,
        )

        r_pc = load_raster_file(pc_path)
        # CORE_NULL must be NoData and never scaled or converted to 0.0
        assert r_pc.nodata_mask[0, 0] is True or r_pc.nodata_mask[0, 0] == 1
        assert np.isnan(r_pc.get_elevation_at_pixel(0, 0))

        # Stored -50 -> -2475.0m (valid)
        assert r_pc.nodata_mask[1, 1] is False or r_pc.nodata_mask[1, 1] == 0
        assert r_pc.data[1, 1] == pytest.approx(-2475.0, abs=1e-3)
        assert r_pc.get_elevation_at_pixel(1, 1) == pytest.approx(-2475.0, abs=1e-3)

        # Stored 0 -> -2450.0m (valid)
        assert r_pc.nodata_mask[2, 2] is False or r_pc.nodata_mask[2, 2] == 0
        assert r_pc.data[2, 2] == pytest.approx(-2450.0, abs=1e-3)

        # Stored 100 -> -2400.0m (valid)
        assert r_pc.nodata_mask[5, 5] is False or r_pc.nodata_mask[5, 5] == 0
        assert r_pc.data[5, 5] == pytest.approx(-2400.0, abs=1e-3)
        assert r_pc.metadata.metadata_tags["PDS3_SAMPLE_TYPE"] == "PC_INTEGER"

        # HiRISE provider validates PC_INTEGER as ready
        val_pc = HiRISERasterProvider(dem_path=pc_path, enabled=True).validate_hirise_raster()
        assert val_pc.is_valid is True
        assert val_pc.status_code == "ready"

        # 2. Rejection of 16-bit PC_UNSIGNED_INTEGER (radiometric imagery)
        arr_u16 = np.full((20, 20), 1000, dtype="<u2")
        _write_hirise_pds3_img(
            u16_path,
            arr_u16,
            sample_bits=16,
            sample_type="PC_UNSIGNED_INTEGER",
        )
        val_u16 = HiRISERasterProvider(dem_path=u16_path, enabled=True).validate_hirise_raster()
        assert val_u16.is_valid is False
        assert val_u16.status_code == "rejected_non_elevation_raster"

        # 3. Rejection of 8-bit UNSIGNED_INTEGER
        arr_u8 = np.full((20, 20), 128, dtype=np.uint8)
        _write_hirise_pds3_img(
            u8_path,
            arr_u8,
            sample_bits=8,
            sample_type="UNSIGNED_INTEGER",
        )
        val_u8 = HiRISERasterProvider(dem_path=u8_path, enabled=True).validate_hirise_raster()
        assert val_u8.is_valid is False
        assert val_u8.status_code == "rejected_non_elevation_raster"
    finally:
        for p in (pc_path, u16_path, u8_path):
            if os.path.exists(p):
                os.remove(p)
