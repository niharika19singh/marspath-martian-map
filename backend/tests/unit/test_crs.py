import pytest
from backend.app.core.exceptions import UnsupportedCRSError
from backend.app.geospatial.crs import (
    MARS_VOLUMETRIC_RADIUS_METERS,
    geo_to_pixel,
    get_mars_crs_info,
    haversine_distance_mars,
    meters_per_degree_lon,
    pixel_to_geo,
    project_to_mars_metric,
    unproject_from_mars_metric,
    validate_crs,
)
from backend.app.schemas.coordinates import MarsCoordinate


def test_mars_coordinate_normalization():
    # Longitude wrapping
    c1 = MarsCoordinate(lon=370.0, lat=18.0)
    assert c1.lon == 10.0

    c2 = MarsCoordinate(lon=-20.0, lat=18.0)
    assert c2.lon == 340.0
    assert c2.lon_signed == -20.0

    # Latitude bounds
    with pytest.raises(ValueError):
        MarsCoordinate(lon=77.0, lat=95.0)

    with pytest.raises(ValueError):
        MarsCoordinate(lon=77.0, lat=-95.0)


def test_mars_crs_metadata():
    crs = get_mars_crs_info()
    assert crs.identifier == "IAU2000:49900"
    assert crs.ellipsoid_radius_meters == MARS_VOLUMETRIC_RADIUS_METERS
    assert crs.latitude_type == "planetocentric"
    assert crs.longitude_direction == "positive_east"


def test_validate_crs():
    validate_crs("IAU2000:49900")
    validate_crs("Mars2000_Sphere")
    with pytest.raises(UnsupportedCRSError):
        validate_crs("EPSG:4326")  # Earth WGS84 must be rejected
    with pytest.raises(UnsupportedCRSError):
        validate_crs("EPSG:3857")  # Earth Web Mercator must be rejected


def test_haversine_distance_mars():
    # 1 degree latitude difference on Mars
    c1 = MarsCoordinate(lon=77.0, lat=18.0)
    c2 = MarsCoordinate(lon=77.0, lat=19.0)
    dist = haversine_distance_mars(c1, c2)
    expected = (2.0 * 3.141592653589793 * MARS_VOLUMETRIC_RADIUS_METERS) / 360.0
    assert abs(dist - expected) < 1.0


def test_metric_projection_roundtrip():
    ref_lon = 77.58
    ref_lat = 18.38

    test_lon = 77.45
    test_lat = 18.42

    x, y = project_to_mars_metric(test_lon, test_lat, ref_lon, ref_lat)
    lon_back, lat_back = unproject_from_mars_metric(x, y, ref_lon, ref_lat)

    assert abs(lon_back - test_lon) < 1e-6
    assert abs(lat_back - test_lat) < 1e-6


def test_pixel_to_geo_roundtrip():
    min_lon = 77.20
    max_lat = 18.65
    d_lon = 0.002
    d_lat = 0.002

    col = 45
    row = 30
    lon, lat = pixel_to_geo(col, row, min_lon, max_lat, d_lon, d_lat)
    c_back, r_back = geo_to_pixel(lon, lat, min_lon, max_lat, d_lon, d_lat)

    assert c_back == col
    assert r_back == row
