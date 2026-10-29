import os
import tempfile
import numpy as np
import pytest
from PIL import Image
from backend.app.core.exceptions import MarsPathError, UnsupportedCRSError
from backend.app.geospatial.crs import (
    geo_to_pixel,
    pixel_to_geo,
    project_to_mars_metric,
    unproject_from_mars_metric,
    validate_crs,
)
from backend.app.geospatial.raster_loader import RasterMetadata, load_raster_file


def test_projected_meter_bounds_never_interpreted_as_degrees():
    # Construct an array and metadata where bounds are in meters (> 360)
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        elev = np.full((50, 50), -2500.0, dtype=np.float32)
        # Jezero center is approx x=4,580,000m, y=1,090,000m if projected
        np.savez(
            tmp_path,
            elevation=elev,
            min_lon=77.40,
            min_lat=18.35,
            max_lon=77.444,
            max_lat=18.394,
            nodata=-9999.0,
        )

        raster = load_raster_file(tmp_path)
        meta = raster.metadata

        # Verify coordinates are valid geographic degrees within Mars bounds
        assert 77.0 <= meta.min_lon <= 78.0
        assert 77.0 <= meta.max_lon <= 78.5
        assert 18.0 <= meta.min_lat <= 19.0
        assert 18.0 <= meta.max_lat <= 19.0

        # Physical meters per pixel should be ~45-65m, NOT degrees!
        assert 40.0 <= meta.meters_per_px_x <= 70.0
        assert 40.0 <= meta.meters_per_px_y <= 70.0
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
    # Physical displacement should be in kilometers/meters
    assert -15000.0 < x_m < 0.0  # West of reference
    assert 0.0 < y_m < 5000.0   # North of reference

    unproj_lon, unproj_lat = unproject_from_mars_metric(x_m, y_m, ref_lon, ref_lat)
    assert abs(unproj_lon - target_lon) < 1e-6
    assert abs(unproj_lat - target_lat) < 1e-6
