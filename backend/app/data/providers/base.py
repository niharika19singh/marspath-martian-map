from abc import ABC, abstractmethod
from typing import Any

from backend.app.geospatial.raster_loader import RasterData
from backend.app.schemas.coordinates import BoundingBox, CRSInfo
from backend.app.schemas.mission import ScienceTarget


class BaseRasterProvider(ABC):
    """Abstract interface for planetary raster providers (real or synthetic)."""

    @abstractmethod
    def get_dem_raster(self) -> RasterData:
        """Returns loaded numerical elevation raster."""
        pass

    @abstractmethod
    def get_bounds(self) -> BoundingBox:
        """Returns geographic bounding box coverage."""
        pass

    @abstractmethod
    def get_crs_info(self) -> CRSInfo:
        """Returns coordinate system metadata."""
        pass

    @abstractmethod
    def get_provenance(self) -> dict[str, Any]:
        """Returns dataset provenance, citation, and sensor details."""
        pass

    @abstractmethod
    def is_synthetic(self) -> bool:
        """Returns True if the provider is a synthetic test fixture."""
        pass

    @abstractmethod
    def get_science_targets(self) -> list[ScienceTarget]:
        """Returns scientific points of interest within the region."""
        pass
