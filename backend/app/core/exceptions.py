class MarsPathError(Exception):
    """Base exception for all MARSPath errors."""

    def __init__(self, message: str, status_code: int = 400, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class UnsupportedCRSError(MarsPathError):
    """Raised when an unsupported CRS or coordinate format is passed."""

    def __init__(self, crs_identifier: str, supported: list[str] | None = None):
        msg = f"Coordinate Reference System '{crs_identifier}' is not supported. Mars requires planetary CRS."
        super().__init__(
            msg,
            status_code=422,
            details={
                "requested_crs": crs_identifier,
                "supported_crs": supported or ["IAU2000:49900", "Mars2000_Sphere"],
            },
        )


class CoordinatesOutOfBoundsError(MarsPathError):
    """Raised when coordinates fall outside supported mission pilot bounds."""

    def __init__(self, lon: float, lat: float, bounds: dict):
        msg = f"Coordinates ({lon:.4f}°E, {lat:.4f}°N) are outside supported pilot bounds: {bounds}"
        super().__init__(
            msg,
            status_code=422,
            details={"lon": lon, "lat": lat, "bounds": bounds},
        )


class TerrainDataUnavailableError(MarsPathError):
    """Raised when numerical elevation data is missing and fallback is disabled."""

    def __init__(self, reason: str):
        super().__init__(
            f"Numerical Martian terrain data unavailable: {reason}",
            status_code=503,
            details={"reason": reason},
        )


class UnreachableDestinationError(MarsPathError):
    """Raised when no traversable route can be found between start and destination."""

    def __init__(self, reason: str, start: tuple, dest: tuple):
        super().__init__(
            f"Unreachable destination: {reason}",
            status_code=404,
            details={"start": start, "destination": dest, "reason": reason},
        )


class ComputationalBoundExceededError(MarsPathError):
    """Raised when mission corridor exceeds safe computational limits."""

    def __init__(self, message: str, dimensions: tuple, max_allowed: int):
        super().__init__(
            f"Computational bounds exceeded: {message}",
            status_code=413,
            details={"grid_dimensions": dimensions, "max_allowed_cells": max_allowed},
        )


class InvalidConstraintError(MarsPathError):
    """Raised when user-specified constraints are invalid or contradictory."""

    def __init__(self, message: str):
        super().__init__(message, status_code=422)
