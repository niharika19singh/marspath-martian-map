import os
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import AliasChoices, BaseModel, Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    HAS_SETTINGS = True
except ImportError:
    HAS_SETTINGS = False


def validate_cors_origins(raw_origins: str | list[str]) -> list[str]:
    """
    Validates and normalizes configured CORS origins in a fail-closed manner.

    - Requires at least one explicit origin (empty configuration raises ValueError).
    - Rejects any wildcard ('*') origin or pattern.
    - Requires exact http:// or https:// scheme and host without path, query, fragment, or credentials.
    """
    if isinstance(raw_origins, str):
        candidates = [item.strip() for item in raw_origins.split(",") if item.strip()]
    elif isinstance(raw_origins, list):
        candidates = [str(item).strip() for item in raw_origins if str(item).strip()]
    else:
        raise ValueError("CORS_ORIGINS must be a comma-separated string or list of origin strings.")

    if not candidates:
        raise ValueError(
            "CORS_ORIGINS must specify at least one explicit origin; empty origin configuration fails closed."
        )

    validated: list[str] = []
    for origin in candidates:
        if "*" in origin:
            raise ValueError(
                f"Wildcard CORS origin '{origin}' is not permitted; explicit origins are required."
            )
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(
                f"Invalid CORS origin '{origin}': must specify an explicit http:// or https:// scheme and host."
            )
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError(
                f"Invalid CORS origin '{origin}': must be an exact origin without path, query, fragment, or credentials."
            )
        validated.append(origin)

    return validated


if HAS_SETTINGS:

    class Settings(BaseSettings):
        """MARSPath application configuration using pydantic-settings."""

        model_config = SettingsConfigDict(
            env_prefix="MARSPATH_",
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )

        ENV: str = "development"
        APP_NAME: str = "MARSPath — Mars Exploration Route Intelligence and Science Planner"
        APP_VERSION: str = "0.1.0"
        HOST: str = "0.0.0.0"
        PORT: int = Field(default=8000, validation_alias=AliasChoices("PORT", "MARSPATH_PORT"))
        LOG_LEVEL: str = "INFO"

        CORS_ORIGINS: str = (
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:5173,http://127.0.0.1:5173,"
            "http://localhost:4173,http://127.0.0.1:4173,"
            "http://localhost:8080,http://127.0.0.1:8080,"
            "https://marspath.vercel.app"
        )

        DATA_DIR: str = "backend/app/data"
        USE_REAL_DEM: bool = False
        DEM_PATH: str = "backend/app/data/rasters/jezero_mola_hrsc_blended.tif"
        ALLOW_SYNTHETIC_FALLBACK: bool = True
        USE_HIRISE_DEM: bool = False
        HIRISE_DEM_PATH: str = "backend/app/data/rasters/hirise_jezero_delta_dtm.tif"

        MARS_RADIUS_METERS: float = 3396190.0
        MARS_EQUATORIAL_RADIUS: float = 3396190.0
        MARS_POLAR_RADIUS: float = 3376200.0

        JEZERO_CENTER_LON: float = 77.58
        JEZERO_CENTER_LAT: float = 18.38
        JEZERO_MIN_LON: float = 77.20
        JEZERO_MAX_LON: float = 77.95
        JEZERO_MIN_LAT: float = 18.15
        JEZERO_MAX_LAT: float = 18.65

        MAX_GRID_CELLS: int = 250000
        MAX_SEARCH_RADIUS_METERS: float = 50000.0
        ROUTING_TIMEOUT_SECONDS: float = Field(
            default=10.0,
            description=(
                "Maximum wall-clock seconds allocated specifically for route graph traversal "
                "(A* search across primary path, multi-point waypoint legs, and alternative corridors). "
                "Evaluated periodically during node expansion and across search iterations. "
                "Does not encompass upstream terrain source selection or corridor cropping, which are "
                "bounded by pilot region bounds and MAX_SEARCH_RADIUS_METERS."
            ),
        )
        DEFAULT_MAX_SLOPE_DEG: float = 20.0
        STRICT_MAX_SLOPE_DEG: float = 14.0

        @property
        def cors_origin_list(self) -> list[str]:
            return validate_cors_origins(self.CORS_ORIGINS)

else:

    class Settings(BaseModel):
        """Fallback configuration class when pydantic-settings is not present."""

        ENV: str = Field(default_factory=lambda: os.getenv("MARSPATH_ENV", "development"))
        APP_NAME: str = "MARSPath — Mars Exploration Route Intelligence and Science Planner"
        APP_VERSION: str = "0.1.0"
        HOST: str = Field(default_factory=lambda: os.getenv("MARSPATH_HOST", "0.0.0.0"))
        PORT: int = Field(
            default_factory=lambda: int(os.getenv("PORT", os.getenv("MARSPATH_PORT", "8000")))
        )
        LOG_LEVEL: str = Field(default_factory=lambda: os.getenv("MARSPATH_LOG_LEVEL", "INFO"))

        CORS_ORIGINS: str = Field(
            default_factory=lambda: os.getenv(
                "MARSPATH_CORS_ORIGINS",
                (
                    "http://localhost:3000,http://127.0.0.1:3000,"
                    "http://localhost:5173,http://127.0.0.1:5173,"
                    "http://localhost:4173,http://127.0.0.1:4173,"
                    "http://localhost:8080,http://127.0.0.1:8080,"
                    "https://marspath.vercel.app"
                ),
            )
        )

        DATA_DIR: str = Field(
            default_factory=lambda: os.getenv("MARSPATH_DATA_DIR", "backend/app/data")
        )
        USE_REAL_DEM: bool = Field(
            default_factory=lambda: os.getenv("MARSPATH_USE_REAL_DEM", "false").lower()
            in ("true", "1")
        )
        DEM_PATH: str = Field(
            default_factory=lambda: os.getenv(
                "MARSPATH_DEM_PATH", "backend/app/data/rasters/jezero_mola_hrsc_blended.tif"
            )
        )
        ALLOW_SYNTHETIC_FALLBACK: bool = Field(
            default_factory=lambda: os.getenv(
                "MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true"
            ).lower()
            in ("true", "1")
        )
        USE_HIRISE_DEM: bool = Field(
            default_factory=lambda: os.getenv("MARSPATH_USE_HIRISE_DEM", "false").lower()
            in ("true", "1")
        )
        HIRISE_DEM_PATH: str = Field(
            default_factory=lambda: os.getenv(
                "MARSPATH_HIRISE_DEM_PATH",
                "backend/app/data/rasters/hirise_jezero_delta_dtm.tif",
            )
        )

        MARS_RADIUS_METERS: float = 3396190.0
        MARS_EQUATORIAL_RADIUS: float = 3396190.0
        MARS_POLAR_RADIUS: float = 3376200.0

        JEZERO_CENTER_LON: float = 77.58
        JEZERO_CENTER_LAT: float = 18.38
        JEZERO_MIN_LON: float = 77.20
        JEZERO_MAX_LON: float = 77.95
        JEZERO_MIN_LAT: float = 18.15
        JEZERO_MAX_LAT: float = 18.65

        MAX_GRID_CELLS: int = Field(
            default_factory=lambda: int(os.getenv("MARSPATH_MAX_GRID_CELLS", "250000"))
        )
        MAX_SEARCH_RADIUS_METERS: float = Field(
            default_factory=lambda: float(
                os.getenv("MARSPATH_MAX_SEARCH_RADIUS_METERS", "50000.0")
            )
        )
        ROUTING_TIMEOUT_SECONDS: float = Field(
            default_factory=lambda: float(
                os.getenv("MARSPATH_ROUTING_TIMEOUT_SECONDS", "10.0")
            ),
            description=(
                "Maximum wall-clock seconds allocated specifically for route graph traversal "
                "(A* search across primary path, multi-point waypoint legs, and alternative corridors). "
                "Evaluated periodically during node expansion and across search iterations. "
                "Does not encompass upstream terrain source selection or corridor cropping, which are "
                "bounded by pilot region bounds and MAX_SEARCH_RADIUS_METERS."
            ),
        )
        DEFAULT_MAX_SLOPE_DEG: float = 20.0
        STRICT_MAX_SLOPE_DEG: float = 14.0

        @property
        def cors_origin_list(self) -> list[str]:
            return validate_cors_origins(self.CORS_ORIGINS)


@lru_cache
def get_settings() -> Settings:
    return Settings()
