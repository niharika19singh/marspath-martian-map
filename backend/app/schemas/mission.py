from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.schemas.coordinates import MarsCoordinate


class OptimizationMode(str, Enum):
    SAFETY_FIRST = "safety_first"
    BALANCED = "balanced"
    SCIENCE_FIRST = "science_first"


class RouteConstraints(BaseModel):
    """Configurable physical constraints for route viability."""

    max_slope_deg: float = Field(
        default=20.0,
        ge=5.0,
        le=45.0,
        description="Absolute maximum traversable terrain slope in degrees. Slopes above this are untraversable.",
    )
    max_roughness: float = Field(
        default=0.85,
        ge=0.1,
        le=1.0,
        description="Normalized terrain roughness threshold (0=mirror smooth, 1=extreme boulder/fractured rock).",
    )
    avoid_unobserved_terrain: bool = Field(
        default=True,
        description="Impose heavy penalty or strictly prohibit crossing cells with missing/no-data coverage.",
    )
    max_search_nodes: int = Field(
        default=100000,
        ge=1000,
        le=500000,
        description="Safety ceiling on search state expansions to prevent unbounded computation.",
    )


class ScienceTarget(BaseModel):
    """Scientific point of interest (POI) identified on Jezero terrain."""

    id: str = Field(..., description="Target identifier")
    name: str = Field(..., description="Scientific feature name")
    target_type: str = Field(..., description="E.g. delta_fan, carbonate_strata, olivine_bedrock, impact_ejecta")
    coordinate: MarsCoordinate = Field(..., description="Location on Mars")
    scientific_priority: float = Field(default=1.0, ge=0.0, le=10.0, description="Priority multiplier for science routing")
    description: str = Field(..., description="Geological rationale and context")
