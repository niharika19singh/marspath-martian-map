import os
import tempfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.app.core.exceptions import MarsPathError, UnsupportedCRSError
from backend.app.geospatial.crs import (
    geo_to_pixel,
    meters_per_degree_lon,
    pixel_to_geo,
    project_to_mars_metric,
    unproject_from_mars_metric,
    validate_crs,
)
from backend.app.geospatial.raster_loader import load_raster_file


def test_real_geotiff_geographic_ingestion():
    """Validates ingestion of a genuine geographic Mars GeoTIFF with nodata and affine transform."""
    data = np.full((50, 50), -2500.0, dtype=np.float32)
    # Set a nodata spot
    data[10, 10] = -9999.0
    # Top-left at lon=77.0, lat=18.5, 0.01 deg/px
    transform = from_origin(77.0, 18.5, 0.01, 0.01)
    crs_str = "+proj=longlat +R=3396190 +no_defs"

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=50,
            width=50,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
            nodata=-9999.0,
        ) as dst:
            dst.write(data, 1)

        raster = load_raster_file(tmp_path)
        meta = raster.metadata

        assert meta.coordinate_type == "geographic"
        assert meta.units == "degrees"
        assert abs(meta.min_lon - 77.0) < 1e-5
        assert abs(meta.max_lat - 18.5) < 1e-5
        assert abs(meta.max_lon - 77.5) < 1e-5
        assert abs(meta.min_lat - 18.0) < 1e-5
        assert meta.nodata_value == -9999.0
        assert raster.nodata_mask[10, 10] is np.True_ or raster.nodata_mask[10, 10] == 1
        assert not raster.nodata_mask[0, 0]

        # In absence of metadata datum tag, vertical datum must not be invented
        assert "Unknown / Unspecified" in meta.vertical_datum

        # Physical resolution in meters
        expected_mx = 0.01 * meters_per_degree_lon(18.25)
        assert abs(meta.meters_per_px_x - expected_mx) < 5.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_real_geotiff_projected_metric_ingestion():
    """
    Validates that a projected Mars GeoTIFF with metre coordinates is correctly
    unprojected to geographic degrees and that metre coordinates are NEVER stored as degrees.
    """
    data = np.full((100, 100), -2450.0, dtype=np.float32)
    # Centered at Jezero (lat_0=18.38, lon_0=77.58), span 5000m x 5000m (50m/px)
    transform = from_origin(-2500.0, 2500.0, 50.0, 50.0)
    crs_proj = "+proj=eqc +lat_ts=18.38 +lat_0=18.38 +lon_0=77.58 +x_0=0 +y_0=0 +R=3396190 +units=m +no_defs"

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with rasterio.open(
            tmp_path,
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
            dst.write(data, 1)

        raster = load_raster_file(tmp_path)
        meta = raster.metadata

        assert meta.coordinate_type == "projected"
        assert meta.units == "meters"
        assert meta.meters_per_px_x == 50.0
        assert meta.meters_per_px_y == 50.0

        # Prove projected coordinates were unprojected to Mars geographic degrees
        assert 77.4 <= meta.min_lon <= 77.6
        assert 77.5 <= meta.max_lon <= 77.7
        assert 18.2 <= meta.min_lat <= 18.4
        assert 18.3 <= meta.max_lat <= 18.5

        # Crucial check: Projected metre values (-2500, +2500) must NEVER be stored as degrees
        assert meta.min_lon > 0.0 and meta.max_lon < 360.0
        assert meta.min_lat > -90.0 and meta.max_lat < 90.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_real_geotiff_with_vertical_datum_tag():
    """Validates that declared vertical datum tag in real GeoTIFF is honestly preserved."""
    data = np.full((10, 10), -2500.0, dtype=np.float32)
    transform = from_origin(77.0, 18.5, 0.01, 0.01)
    crs_str = "+proj=longlat +R=3396190 +no_defs"

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.update_tags(VERTICAL_DATUM="Mars Areoid (MOLA MEGDR IAU2000)")
            dst.write(data, 1)

        raster = load_raster_file(tmp_path)
        assert raster.metadata.vertical_datum == "Mars Areoid (MOLA MEGDR IAU2000)"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_unsupported_earth_crs_geotiff_rejected():
    """Validates that an Earth WGS84 GeoTIFF is strictly rejected with UnsupportedCRSError."""
    data = np.full((10, 10), 100.0, dtype=np.float32)
    transform = from_origin(0.0, 10.0, 1.0, 1.0)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with pytest.raises(UnsupportedCRSError) as excinfo:
            load_raster_file(tmp_path)

        assert "EPSG:4326" in str(excinfo.value) or "Earth" in str(excinfo.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_metric_bounds_without_crs_rejected():
    """Validates that a raster with metre-scale bounds but missing CRS definition is rejected."""
    data = np.full((10, 10), 100.0, dtype=np.float32)
    # Metre bounds > 360 degrees
    transform = from_origin(50000.0, 50000.0, 50.0, 50.0)

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=10,
            width=10,
            count=1,
            dtype="float32",
            crs=None,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        with pytest.raises(MarsPathError) as excinfo:
            load_raster_file(tmp_path)

        assert "lacks a CRS definition" in str(excinfo.value)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_pixel_edge_vs_pixel_center_conventions():
    min_lon = 77.0
    max_lat = 18.5
    d_lon = 0.01
    d_lat = 0.01

    # In PixelIsArea convention:
    # Pixel (0, 0) top-left corner is (77.0, 18.5)
    # Pixel (0, 0) center is (77.005, 18.495)
    edge_lon, edge_lat = pixel_to_geo(0, 0, min_lon, max_lat, d_lon, d_lat, pixel_center=False)
    assert abs(edge_lon - 77.0) < 1e-6
    assert abs(edge_lat - 18.5) < 1e-6

    center_lon, center_lat = pixel_to_geo(0, 0, min_lon, max_lat, d_lon, d_lat, pixel_center=True)
    assert abs(center_lon - 77.005) < 1e-6
    assert abs(center_lat - 18.495) < 1e-6

    # Coordinate to pixel: point inside pixel (0, 0) maps to col 0, row 0
    c, r = geo_to_pixel(77.004, 18.496, min_lon, max_lat, d_lon, d_lat, pixel_center=True)
    assert c == 0
    assert r == 0

    # Point in pixel (1, 2)
    c2, r2 = geo_to_pixel(77.015, 18.475, min_lon, max_lat, d_lon, d_lat, pixel_center=True)
    assert c2 == 1
    assert r2 == 2


def test_crs_separation_and_validation():
    # Geographic Mars CRS must pass
    validate_crs("IAU2000:49900")
    validate_crs("Mars2000_Sphere")
    validate_crs("MARS_EQUIRECTANGULAR")

    # Earth CRS must be explicitly rejected
    with pytest.raises(UnsupportedCRSError):
        validate_crs("EPSG:4326")
    with pytest.raises(UnsupportedCRSError):
        validate_crs("EPSG:3857")
    with pytest.raises(UnsupportedCRSError):
        validate_crs("WGS84")


def test_projected_metric_roundtrip():
    ref_lon, ref_lat = 77.58, 18.38
    target_lon, target_lat = 77.45, 18.42

    x_m, y_m = project_to_mars_metric(target_lon, target_lat, ref_lon, ref_lat)
    assert -15000.0 < x_m < 0.0  # West of reference
    assert 0.0 < y_m < 5000.0  # North of reference

    unproj_lon, unproj_lat = unproject_from_mars_metric(x_m, y_m, ref_lon, ref_lat)
    assert abs(unproj_lon - target_lon) < 1e-6
    assert abs(unproj_lat - target_lat) < 1e-6
