from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.coordinates import BoundingBox, CRSInfo


class LayerCategory(str, Enum):
    ELEVATION = "elevation"
    SLOPE = "slope"
    ROUGHNESS = "roughness"
    HAZARD = "hazard"
    IMAGERY = "imagery"
    SCIENCE = "science"


class LayerInfo(BaseModel):
    """Metadata describing an available geospatial layer with explicit rendering semantics."""

    id: str = Field(..., description="Unique layer identifier")
    name: str = Field(..., description="Human-readable title")
    category: LayerCategory = Field(..., description="Geospatial domain category")
    layer_type: str = Field(
        default="analysis_derived",
        description="'tile_service' for direct web map display or 'analysis_derived' for internal routing matrices",
    )
    description: str = Field(..., description="Detailed layer scientific description")
    units: str = Field(..., description="Physical measurement unit (e.g., meters, degrees, dimensionless)")
    resolution_meters: float = Field(..., description="Spatial resolution per pixel in physical meters")
    bounds: BoundingBox = Field(..., description="Spatial coverage extent")
    crs: CRSInfo = Field(..., description="Coordinate system definition")
    source_name: str = Field(..., description="NASA/ESA/USGS instrument or mission name")
    source_url: str = Field(..., description="Official landing page or PDS service endpoint")
    is_numerical: bool = Field(..., description="Whether layer contains floating-point physical values")
    is_available: bool = Field(..., description="Whether layer is currently loaded and ready for queries")
    is_renderable: bool = Field(
        default=False,
        description="True if layer can be directly rendered in OpenLayers/Leaflet via tile/raster URL",
    )
    render_url: Optional[str] = Field(
        default=None,
        description="WMTS or XYZ tile URL template if renderable",
    )
    is_synthetic: bool = Field(..., description="True if operating on test fixture rather than verified NASA raster")


class LayerListResponse(BaseModel):
    """API response model for listing all configured geospatial layers."""

    count: int
    pilot_region: str
    layers: List[LayerInfo]
