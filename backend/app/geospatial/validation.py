from backend.app.core.exceptions import (
    CoordinatesOutOfBoundsError,
    InvalidConstraintError,
    UnreachableDestinationError,
)
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import RouteConstraints


def validate_coordinates_in_bounds(coord: MarsCoordinate, meta: RasterMetadata, label: str = "Coordinate") -> None:
    """Verifies that a geographic coordinate falls inside the loaded raster coverage."""
    if not (meta.min_lon <= coord.lon <= meta.max_lon and meta.min_lat <= coord.lat <= meta.max_lat):
        bounds_dict = {
            "min_lon": round(meta.min_lon, 4),
            "max_lon": round(meta.max_lon, 4),
            "min_lat": round(meta.min_lat, 4),
            "max_lat": round(meta.max_lat, 4),
        }
        raise CoordinatesOutOfBoundsError(coord.lon, coord.lat, bounds_dict)


def validate_constraints(constraints: RouteConstraints) -> None:
    """Validates user-configured routing constraints."""
    if constraints.max_slope_deg < 5.0 or constraints.max_slope_deg > 45.0:
        raise InvalidConstraintError(
            f"max_slope_deg must be between 5.0 and 45.0 degrees. Got {constraints.max_slope_deg}"
        )
    if constraints.max_roughness < 0.1 or constraints.max_roughness > 1.0:
        raise InvalidConstraintError(
            f"max_roughness must be between 0.1 and 1.0. Got {constraints.max_roughness}"
        )


def check_cell_traversability(
    col: int,
    row: int,
    traversable_mask,
    coord: MarsCoordinate,
    point_name: str = "Waypoint",
) -> None:
    """Checks whether a designated start or destination cell is itself traversable and not in an obstacle."""
    if not traversable_mask[row, col]:
        raise UnreachableDestinationError(
            f"{point_name} at ({coord.lon:.4f}°E, {coord.lat:.4f}°N) is located in untraversable terrain (cliff, severe roughness, or nodata).",
            start=(coord.lon, coord.lat),
            dest=(coord.lon, coord.lat),
        )
