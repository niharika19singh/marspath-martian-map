import os
from functools import lru_cache

from pydantic import BaseModel

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    HAS_SETTINGS = True
except ImportError:
    HAS_SETTINGS = False


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
        PORT: int = 8000
        LOG_LEVEL: str = "INFO"

        CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,https://marspath.vercel.app"

        DATA_DIR: str = "backend/app/data"
        USE_REAL_DEM: bool = False
        DEM_PATH: str = "backend/app/data/rasters/jezero_mola_hrsc_blended.tif"
        ALLOW_SYNTHETIC_FALLBACK: bool = True

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
        ROUTING_TIMEOUT_SECONDS: float = 10.0
        DEFAULT_MAX_SLOPE_DEG: float = 20.0
        STRICT_MAX_SLOPE_DEG: float = 14.0

        @property
        def cors_origin_list(self) -> list[str]:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

else:

    class Settings(BaseModel):
        """Fallback configuration class when pydantic-settings is not present."""

        ENV: str = os.getenv("MARSPATH_ENV", "development")
        APP_NAME: str = "MARSPath — Mars Exploration Route Intelligence and Science Planner"
        APP_VERSION: str = "0.1.0"
        HOST: str = os.getenv("MARSPATH_HOST", "0.0.0.0")
        PORT: int = int(os.getenv("MARSPATH_PORT", "8000"))
        LOG_LEVEL: str = os.getenv("MARSPATH_LOG_LEVEL", "INFO")

        CORS_ORIGINS: str = os.getenv(
            "MARSPATH_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,https://marspath.vercel.app",
        )

        DATA_DIR: str = os.getenv("MARSPATH_DATA_DIR", "backend/app/data")
        USE_REAL_DEM: bool = os.getenv("MARSPATH_USE_REAL_DEM", "false").lower() in ("true", "1")
        DEM_PATH: str = os.getenv(
            "MARSPATH_DEM_PATH", "backend/app/data/rasters/jezero_mola_hrsc_blended.tif"
        )
        ALLOW_SYNTHETIC_FALLBACK: bool = os.getenv(
            "MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true"
        ).lower() in ("true", "1")

        MARS_RADIUS_METERS: float = 3396190.0
        MARS_EQUATORIAL_RADIUS: float = 3396190.0
        MARS_POLAR_RADIUS: float = 3376200.0

        JEZERO_CENTER_LON: float = 77.58
        JEZERO_CENTER_LAT: float = 18.38
        JEZERO_MIN_LON: float = 77.20
        JEZERO_MAX_LON: float = 77.95
        JEZERO_MIN_LAT: float = 18.15
        JEZERO_MAX_LAT: float = 18.65

        MAX_GRID_CELLS: int = int(os.getenv("MARSPATH_MAX_GRID_CELLS", "250000"))
        MAX_SEARCH_RADIUS_METERS: float = float(
            os.getenv("MARSPATH_MAX_SEARCH_RADIUS_METERS", "50000.0")
        )
        ROUTING_TIMEOUT_SECONDS: float = float(
            os.getenv("MARSPATH_ROUTING_TIMEOUT_SECONDS", "10.0")
        )
        DEFAULT_MAX_SLOPE_DEG: float = 20.0
        STRICT_MAX_SLOPE_DEG: float = 14.0

        @property
        def cors_origin_list(self) -> list[str]:
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
