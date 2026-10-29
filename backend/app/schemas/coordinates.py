from pydantic import BaseModel, Field, field_validator


class MarsCoordinate(BaseModel):
    """
    Planetary coordinate representation on Mars.
    Conforms to IAU2000 planetary geodesy:
    - Longitude: Positive East, range [0, 360) or [-180, 180]. Auto-normalized to [0, 360).
    - Latitude: Planetocentric latitude, range [-90, 90].
    """

    lon: float = Field(..., description="East Longitude in decimal degrees [0, 360) or [-180, 180)")
    lat: float = Field(..., description="Planetocentric Latitude in decimal degrees [-90, 90]")

    @field_validator("lat")
    @classmethod
    def validate_latitude(cls, v: float) -> float:
        if not (-90.0 <= v <= 90.0):
            raise ValueError(f"Planetocentric latitude must be between -90 and +90 degrees. Got {v}")
        return float(v)

    @field_validator("lon")
    @classmethod
    def normalize_longitude(cls, v: float) -> float:
        # Wrap longitude into [0, 360)
        norm = float(v) % 360.0
        return norm

    @property
    def lon_signed(self) -> float:
        """Returns longitude in [-180, +180) range for standard GIS tooling if required."""
        return self.lon if self.lon <= 180.0 else self.lon - 360.0


class BoundingBox(BaseModel):
    """Spatial bounding box in Mars planetary degrees."""

    min_lon: float = Field(..., description="Westernmost East Longitude")
    min_lat: float = Field(..., description="Southernmost Planetocentric Latitude")
    max_lon: float = Field(..., description="Easternmost East Longitude")
    max_lat: float = Field(..., description="Northernmost Planetocentric Latitude")


class CRSInfo(BaseModel):
    """Metadata describing the active Mars Coordinate Reference System."""

    identifier: str = Field(..., description="CRS identifier, e.g. IAU2000:49900")
    name: str = Field(..., description="Descriptive name of the datum/ellipsoid")
    ellipsoid_radius_meters: float = Field(..., description="Mean radius of Mars used in calculations")
    latitude_type: str = Field("planetocentric", description="Planetocentric or planetographic")
    longitude_direction: str = Field("positive_east", description="Positive East or Positive West")
    projection: str = Field("Equirectangular / Plate Carree (Mars Sphere)", description="Projected coordinate system")
