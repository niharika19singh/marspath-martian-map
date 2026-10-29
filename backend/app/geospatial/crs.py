import math
from typing import Tuple
from backend.app.core.exceptions import CoordinatesOutOfBoundsError, UnsupportedCRSError
from backend.app.schemas.coordinates import BoundingBox, CRSInfo, MarsCoordinate

# Mars Geodetic Constants (IAU 2000 Working Group on Cartographic Coordinates and Rotational Elements)
MARS_VOLUMETRIC_RADIUS_METERS = 3396190.0  # R_Mars in meters
MARS_EQUATORIAL_RADIUS_METERS = 3396190.0
MARS_POLAR_RADIUS_METERS = 3376200.0
MARS_CIRCUMFERENCE_METERS = 2.0 * math.pi * MARS_VOLUMETRIC_RADIUS_METERS
METERS_PER_DEGREE_LATITUDE = MARS_CIRCUMFERENCE_METERS / 360.0  # ~59,274.69 meters/degree

SUPPORTED_CRS_IDENTIFIERS = {
    "IAU2000:49900",
    "IAU_2000:49900",
    "MARS2000_SPHERE",
    "MARS2000",
    "URN:OGC:DEF:CRS:IAU:2000:49900",
}


def get_mars_crs_info() -> CRSInfo:
    """Returns official Mars IAU2000 CRS metadata."""
    return CRSInfo(
        identifier="IAU2000:49900",
        name="Mars 2000 Sphere (IAU/IAG Working Group)",
        ellipsoid_radius_meters=MARS_VOLUMETRIC_RADIUS_METERS,
        latitude_type="planetocentric",
        longitude_direction="positive_east",
        projection="Equirectangular Metric (Plate Carree centered at reference)",
    )


def validate_crs(crs_identifier: str) -> None:
    """Validates that the requested CRS is a recognized Mars planetary CRS."""
    norm = crs_identifier.strip().upper()
    if norm not in SUPPORTED_CRS_IDENTIFIERS:
        raise UnsupportedCRSError(crs_identifier, list(SUPPORTED_CRS_IDENTIFIERS))


def meters_per_degree_lon(lat_deg: float) -> float:
    """Computes physical ground distance in meters for 1 degree of East longitude at a given latitude."""
    lat_rad = math.radians(lat_deg)
    return METERS_PER_DEGREE_LATITUDE * math.cos(lat_rad)


def haversine_distance_mars(coord1: MarsCoordinate, coord2: MarsCoordinate) -> float:
    """
    Computes great-circle ground distance between two points on the Mars sphere in meters.
    Uses Mars mean volumetric radius R = 3,396,190 meters.
    """
    lat1, lon1 = math.radians(coord1.lat), math.radians(coord1.lon)
    lat2, lon2 = math.radians(coord2.lat), math.radians(coord2.lon)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return MARS_VOLUMETRIC_RADIUS_METERS * c


def project_to_mars_metric(
    lon_deg: float,
    lat_deg: float,
    ref_lon_deg: float,
    ref_lat_deg: float,
) -> Tuple[float, float]:
    """
    Forward projection: Projects (lon_deg, lat_deg) into local Martian metric space (x_meters, y_meters)
    relative to a reference origin (ref_lon_deg, ref_lat_deg) using Mars Equirectangular projection.
    """
    dlon_deg = lon_deg - ref_lon_deg
    # Normalize delta lon to [-180, 180] for shortest arc across wrapping boundaries
    dlon_deg = (dlon_deg + 180.0) % 360.0 - 180.0
    dlat_deg = lat_deg - ref_lat_deg

    ref_lat_rad = math.radians(ref_lat_deg)
    x = MARS_VOLUMETRIC_RADIUS_METERS * math.radians(dlon_deg) * math.cos(ref_lat_rad)
    y = MARS_VOLUMETRIC_RADIUS_METERS * math.radians(dlat_deg)
    return x, y


def unproject_from_mars_metric(
    x_meters: float,
    y_meters: float,
    ref_lon_deg: float,
    ref_lat_deg: float,
) -> Tuple[float, float]:
    """
    Inverse projection: Converts local Martian metric coordinates (x, y) back into (lon_deg, lat_deg).
    """
    ref_lat_rad = math.radians(ref_lat_deg)
    dlat_rad = y_meters / MARS_VOLUMETRIC_RADIUS_METERS
    cos_ref = math.cos(ref_lat_rad)
    if abs(cos_ref) < 1e-7:
        dlon_rad = 0.0
    else:
        dlon_rad = x_meters / (MARS_VOLUMETRIC_RADIUS_METERS * cos_ref)

    lat_deg = ref_lat_deg + math.degrees(dlat_rad)
    lon_deg = (ref_lon_deg + math.degrees(dlon_rad)) % 360.0
    return lon_deg, lat_deg


def geo_to_pixel(
    lon: float,
    lat: float,
    min_lon: float,
    max_lat: float,
    deg_per_px_lon: float,
    deg_per_px_lat: float,
) -> Tuple[int, int]:
    """
    Maps geographic coordinates (lon, lat) to raster grid indices (col, row).
    Standard North-up raster where row 0 is max_lat and col 0 is min_lon.
    """
    col = int(round((lon - min_lon) / deg_per_px_lon))
    row = int(round((max_lat - lat) / deg_per_px_lat))
    return col, row


def pixel_to_geo(
    col: int,
    row: int,
    min_lon: float,
    max_lat: float,
    deg_per_px_lon: float,
    deg_per_px_lat: float,
) -> Tuple[float, float]:
    """
    Maps raster grid indices (col, row) to geographic coordinates (lon, lat).
    """
    lon = min_lon + (col * deg_per_px_lon)
    lat = max_lat - (row * deg_per_px_lat)
    return lon % 360.0, lat
