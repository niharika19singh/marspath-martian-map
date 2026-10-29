from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.coordinates import BoundingBox, CRSInfo, MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, RouteConstraints


class RoutePlanRequest(BaseModel):
    """Payload for requesting an optimized Martian route."""

    start: MarsCoordinate = Field(..., description="Starting waypoint (lon, lat in East degrees)")
    destination: MarsCoordinate = Field(
        ..., description="Target destination waypoint (lon, lat in East degrees)"
    )
    crs_identifier: str = Field(
        default="IAU2000:49900",
        description="Planetary Coordinate Reference System identifier (default IAU2000:49900 Mars Sphere)",
    )
    mode: OptimizationMode = Field(
        default=OptimizationMode.BALANCED,
        description="Routing priority mode: safety_first, balanced, or science_first",
    )
    constraints: RouteConstraints = Field(
        default_factory=RouteConstraints,
        description="Traversability limits and safety bounds",
    )
    science_waypoints: list[MarsCoordinate] = Field(
        default_factory=list,
        description="Optional ordered intermediate science coordinates to visit",
    )
    num_alternatives: int = Field(
        default=1,
        ge=1,
        le=3,
        description="Number of distinct alternative routes to compute (1-3)",
    )


class RouteSegment(BaseModel):
    """Detailed terrain attributes for a single discrete step along the path."""

    from_coord: MarsCoordinate
    to_coord: MarsCoordinate
    step_distance_meters: float
    elevation_start_m: float
    elevation_end_m: float
    delta_elevation_m: float
    slope_deg: float
    roughness: float
    is_valid_data: bool
    segment_cost: float


class RouteSummary(BaseModel):
    """Aggregate quantitative metrics for a planned route corridor."""

    total_distance_meters: float = Field(
        ..., description="Total ground path distance in physical meters"
    )
    elevation_gain_meters: float = Field(..., description="Cumulative ascent along path in meters")
    elevation_loss_meters: float = Field(..., description="Cumulative descent along path in meters")
    min_elevation_meters: float = Field(..., description="Lowest topographic elevation encountered")
    max_elevation_meters: float = Field(
        ..., description="Highest topographic elevation encountered"
    )
    max_slope_deg: float = Field(..., description="Steepest local gradient encountered in degrees")
    average_slope_deg: float = Field(..., description="Mean slope across all traversed cells")
    average_roughness: float = Field(..., description="Mean normalized roughness across route")
    data_coverage_fraction: float = Field(
        ..., description="Proportion of route passing through valid numeric data [0-1]"
    )
    estimated_duration_hours: float = Field(
        ..., description="Estimated traversal time assuming rover motion profile"
    )
    motion_profile: str = Field(
        default="rover_slope_derated_0.15mps",
        description="Physical velocity profile: nominal 0.15 m/s with slope-dependent speed derating",
    )
    energy_index: float = Field(
        ..., description="Relative energy consumption score factoring distance and slopes"
    )
    science_score: float = Field(
        ..., description="Science acquisition score based on visited targets and proximity"
    )


class GeoJSONGeometry(BaseModel):
    """GeoJSON LineString representation annotated with planetary coordinate details."""

    type: str = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        description="List of [lon, lat, elevation] tuples where lon=East degrees, lat=Planetocentric degrees",
    )


class RouteAlternative(BaseModel):
    """An individual viable route solution with performance breakdown."""

    route_id: str
    name: str
    mode: OptimizationMode
    score_rank: int
    total_cost: float
    cost_breakdown: dict[str, float] = Field(
        ...,
        description="Breakdown of cost components: base_distance_cost, slope_penalty, roughness_penalty, hazard_penalty, extra_penalty",
    )
    summary: RouteSummary
    geometry: GeoJSONGeometry
    waypoints_visited: list[MarsCoordinate] = Field(default_factory=list)
    science_targets_visited: list[str] = Field(
        default_factory=list,
        description="IDs of science targets directly visited by the route path",
    )
    science_targets_nearby: list[str] = Field(
        default_factory=list,
        description="IDs of science targets within sensor observation range (<500m)",
    )
    warnings: list[str] = Field(default_factory=list)


class ComputationStats(BaseModel):
    """Performance telemetry from graph-search execution."""

    algorithm_used: str = Field(..., description="A* or Dijkstra")
    search_duration_seconds: float = Field(
        ..., description="Actual wall-clock time spent in route computation"
    )
    nodes_expanded: int = Field(
        ..., description="Real count of grid states popped from priority queue during search"
    )
    grid_rows: int = Field(..., description="Row count of cropped local terrain window")
    grid_cols: int = Field(..., description="Column count of cropped local terrain window")
    cell_size_meters: float = Field(..., description="Physical cell width/height in meters")


class RoutePlanResponse(BaseModel):
    """Complete route intelligence response."""

    mission_id: str
    status: str = Field("success", description="Status string: success or partial")
    crs: CRSInfo
    pilot_region: str
    data_mode: str = Field(
        ..., description="'real' if loaded from NASA DEM, or 'synthetic_test_fixture'"
    )
    provenance: dict[str, Any] = Field(
        ..., description="Data source citations, acquisition IDs, and processing metadata"
    )
    routes: list[RouteAlternative]
    stats: ComputationStats
    limitations: list[str] = Field(
        default_factory=list,
        description="Explicit engineering limitations (e.g. resolution limitations, sub-pixel obstacle disclaimer)",
    )


class DataStatusResponse(BaseModel):
    """System report on data readiness, CRS, and raster availability."""

    status: str
    data_mode: str
    is_synthetic: bool
    active_pilot_region: str
    pilot_bounds: BoundingBox
    crs: CRSInfo
    loaded_dem: str | None
    dem_resolution_meters: float
    grid_shape: list[int]
    valid_data_fraction: float
    configured_products: list[dict[str, Any]]
    limitations: list[str]
    blocking_errors: list[str] = Field(default_factory=list)
