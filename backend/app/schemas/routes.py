from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.coordinates import BoundingBox, CRSInfo, MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, RouteConstraints


class EvidenceQualityTier(str, Enum):
    """
    Deterministic classification of terrain evidence quality for regional route assessment.
    NOTE: This is a data-evidence classification, NOT a probability of rover survival or mission safety.
    """

    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    UNVERIFIED = "unverified"


class SourceEvidence(BaseModel):
    """Authoritative source identity, provenance status, and physical grid metadata."""

    dataset_name: str = Field(..., description="Human-readable name of the active terrain source")
    product_id: str | None = Field(
        default=None,
        description="Official planetary catalog product ID when genuinely established; None for synthetic or unverified local sources",
    )
    publisher: str | None = Field(
        default=None,
        description="Data publisher or origin authority",
    )
    official_source_url: str | None = Field(
        default=None,
        description="Authoritative USGS/PDS source URL when genuinely established; None for synthetic or unverified local sources",
    )
    data_mode: str = Field(
        ...,
        description="Active data mode: real, real_official_endpoint_unverified_checksum, real_unverified_source, synthetic_fallback, or synthetic_test_fixture",
    )
    validation_status: str = Field(
        ...,
        description="Provenance validation status: verified_source, official_endpoint_retrieved_checksum_unverified, valid_numeric_raster_unverified_source, synthetic_test_fixture, or incomplete_missing_genuine_dem",
    )
    verification_method: str = Field(
        ...,
        description="Specific cryptographic or procedural provenance verification method executed",
    )
    is_synthetic: bool = Field(
        ..., description="True if terrain is procedurally synthesized rather than observational"
    )
    local_integrity_verified: bool | None = Field(
        default=None,
        description="True if local file SHA-256 matches its recorded provenance sidecar",
    )
    source_checksum_verified: bool = Field(
        default=False,
        description="True ONLY when the full upstream archive checksum has been independently verified against official catalog bytes",
    )
    file_sha256: str | None = Field(
        default=None, description="SHA-256 digest of the local DEM file when loaded from disk"
    )
    pixel_resolution_x_meters: float = Field(
        ..., description="Actual physical zonal pixel width (dx) in meters at route latitude"
    )
    pixel_resolution_y_meters: float = Field(
        ..., description="Actual physical meridional pixel height (dy) in meters"
    )
    nominal_resolution_meters: float | None = Field(
        default=None,
        description="Nominal published dataset resolution in meters per pixel if applicable",
    )
    raster_width: int = Field(..., description="Width of the loaded master DEM raster in pixels")
    raster_height: int = Field(..., description="Height of the loaded master DEM raster in pixels")
    crs_identifier: str = Field(..., description="Horizontal Coordinate Reference System identifier")
    vertical_datum: str = Field(..., description="Vertical elevation reference datum")
    spatial_coverage: BoundingBox = Field(
        ..., description="Actual geographic bounding box of the loaded DEM raster"
    )
    source_limitations: list[str] = Field(
        default_factory=list,
        description="Source-specific provenance and scientific caveats",
    )


class CoverageEvidence(BaseModel):
    """Independent observation completeness measurements along the route and across the cropped corridor."""

    route_sample_count: int = Field(
        ..., description="Total number of discrete raster cell samples along the route"
    )
    valid_route_sample_count: int = Field(
        ..., description="Number of route cell samples with valid numerical terrain observations"
    )
    invalid_route_sample_count: int = Field(
        ..., description="Number of route cell samples falling on nodata or invalid cells"
    )
    route_data_coverage_fraction: float = Field(
        ...,
        description="Valid route samples divided by total route samples [0.0 - 1.0]",
    )
    corridor_total_cells: int = Field(
        ..., description="Total raster cells within the cropped mission analysis corridor"
    )
    corridor_valid_cells: int = Field(
        ..., description="Valid numerical raster cells within the cropped mission corridor"
    )
    corridor_invalid_cells: int = Field(
        ..., description="Nodata or invalid cells within the cropped mission corridor"
    )
    corridor_data_coverage_fraction: float = Field(
        ...,
        description="Valid corridor cells divided by total corridor cells [0.0 - 1.0]",
    )
    near_nodata_segment_count: int = Field(
        default=0,
        description="Number of route segments passing adjacent to a nodata boundary in the corridor",
    )


class ResolutionAssessment(BaseModel):
    """Physical resolution evaluation and scale suitability disclosure."""

    actual_x_meters_per_pixel: float = Field(
        ..., description="Actual zonal cell size (dx) in meters per pixel at the corridor latitude"
    )
    actual_y_meters_per_pixel: float = Field(
        ..., description="Actual meridional cell size (dy) in meters per pixel"
    )
    effective_resolution_meters: float = Field(
        ..., description="Conservative effective grid resolution max(dx, dy) in meters"
    )
    nominal_dataset_resolution_meters: float | None = Field(
        default=None,
        description="Nominal published equatorial resolution in meters per pixel when established",
    )
    suitability_classification: str = Field(
        ...,
        description="Scale suitability classification (e.g. regional_corridor_assessment_only, synthetic_simulation_only)",
    )
    obstacle_detection_capable: bool = Field(
        default=False,
        description="True only if resolution is fine enough (<=1 m/px) to resolve rover-scale boulders/obstacles",
    )
    limitation_statement: str = Field(
        ...,
        description="Explicit disclosure of what physical features are and are not resolved at this pixel scale",
    )


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
    """Detailed terrain attributes and data-quality flags for a single discrete step along the path."""

    segment_index: int = Field(
        default=0, description="Zero-based index of this segment along the route"
    )
    from_coord: MarsCoordinate
    to_coord: MarsCoordinate
    step_distance_meters: float
    elevation_start_m: float | None = Field(
        default=None,
        description="Start cell elevation in meters, or None if start cell is invalid/nodata",
    )
    elevation_end_m: float | None = Field(
        default=None,
        description="End cell elevation in meters, or None if end cell is invalid/nodata",
    )
    delta_elevation_m: float | None = Field(
        default=None,
        description="Elevation change (end - start) in meters, or None if either endpoint is invalid/nodata",
    )
    slope_deg: float | None = Field(
        default=None,
        description="Target cell physical slope in degrees, or None if invalid/nodata",
    )
    roughness: float | None = Field(
        default=None,
        description="Target cell normalized TRI roughness [0.0 - 1.0], or None if invalid/nodata",
    )
    is_valid_data: bool = Field(
        ...,
        description="True only when both endpoints and derived terrain metrics are backed by valid non-nodata observations",
    )
    segment_cost: float
    quality_flags: list[str] = Field(
        default_factory=list,
        description="Segment-level data quality flags grounded in actual raster/corridor conditions",
    )


class RouteEvidencePassport(BaseModel):
    """
    Structured Terrain Evidence & Route Confidence Passport accompanying each route alternative.
    Quantifies dataset provenance, observation coverage, physical resolution, and segment-level
    evidence flags. Does NOT represent a probability of rover survival or mission success.
    """

    schema_version: str = Field(
        default="1.0.0", description="Evidence passport schema version"
    )
    assessment_scope: str = Field(
        default="regional_terrain_evidence_assessment_not_mission_survival_probability",
        description="Explicit scope declaration distinguishing terrain data quality from mission safety",
    )
    scientific_disclaimer: str = Field(
        default=(
            "Terrain evidence quality measures the provenance, spatial resolution, and observation "
            "completeness of the underlying elevation data. It is NOT a probability of rover survival, "
            "probability of mission success, or calibrated probability of mechanical failure."
        ),
        description="Mandatory scientific interpretation disclaimer",
    )
    quality_tier: EvidenceQualityTier = Field(
        ...,
        description="Deterministic evidence quality tier: high, moderate, low, or unverified",
    )
    tier_explanation: str = Field(
        ...,
        description="Human-readable explanation describing the exact evidence rules that determined quality_tier",
    )
    quality_flags: list[str] = Field(
        default_factory=list,
        description="Route-level evidence and provenance quality flags",
    )
    source: SourceEvidence = Field(
        ..., description="Source dataset identity, provenance verification, and grid metadata"
    )
    coverage: CoverageEvidence = Field(
        ..., description="Independent route sample coverage and cropped corridor cell coverage"
    )
    resolution_assessment: ResolutionAssessment = Field(
        ..., description="Actual vs. nominal resolution assessment and obstacle detection disclaimer"
    )
    known_limitations: list[str] = Field(
        default_factory=list,
        description="Consolidated scientific and engineering limitations applicable to this route",
    )
    segments: list[RouteSegment] = Field(
        default_factory=list,
        description="Ordered segment-by-segment terrain measurements and quality flags (N-1 segments for N route coordinates)",
    )


class RouteSummary(BaseModel):
    """Aggregate quantitative metrics for a planned route corridor."""

    total_distance_meters: float = Field(
        ..., description="Total ground path distance in physical meters"
    )
    elevation_gain_meters: float | None = Field(
        default=None,
        description="Cumulative ascent along valid path elevation transitions in meters, or None if no valid elevation transitions exist",
    )
    elevation_loss_meters: float | None = Field(
        default=None,
        description="Cumulative descent along valid path elevation transitions in meters, or None if no valid elevation transitions exist",
    )
    min_elevation_meters: float | None = Field(
        default=None,
        description="Lowest valid topographic elevation encountered in meters, or None if no valid elevation observations exist",
    )
    max_elevation_meters: float | None = Field(
        default=None,
        description="Highest valid topographic elevation encountered in meters, or None if no valid elevation observations exist",
    )
    max_slope_deg: float | None = Field(
        default=None,
        description="Steepest valid local gradient encountered in degrees, or None if no valid slope observations exist",
    )
    average_slope_deg: float | None = Field(
        default=None,
        description="Mean slope across valid observed cells, or None if no valid slope observations exist",
    )
    average_roughness: float | None = Field(
        default=None,
        description="Mean normalized roughness across valid observed cells, or None if no valid roughness observations exist",
    )
    data_coverage_fraction: float = Field(
        ..., description="Proportion of route passing through valid numeric data [0-1]"
    )
    elevation_sample_coverage_fraction: float = Field(
        default=1.0,
        description="Proportion of route vertices with valid elevation observations [0.0 - 1.0]",
    )
    is_complete_measurement: bool = Field(
        default=True,
        description="True only when 100% of route vertices have valid elevation, slope, and roughness observations; False when summary metrics are partial aggregates over observed subsets or None",
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
    hazard_exposure_meters: float = Field(
        default=0.0,
        description="Physical meters traversed through high-risk terrain (slope > 12° or roughness > 0.5)",
    )
    risk_category: str = Field(
        default="nominal",
        description="Categorical risk classification for mission planning: nominal, moderate, or high",
    )


class GeoJSONGeometry(BaseModel):
    """GeoJSON LineString representation annotated with planetary coordinate details."""

    type: str = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        description=(
            "RFC 7946 LineString positions: 3D [lon, lat, elevation] tuples when all route "
            "vertices have valid elevation observations, or 2D [lon, lat] tuples when any "
            "route vertex lacks a valid elevation observation (never fabricated 0.0 Z values)"
        ),
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
    evidence_passport: RouteEvidencePassport | None = Field(
        default=None,
        description="Structured Terrain Evidence & Route Confidence Passport for this route alternative",
    )


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
    real_data_validation_status: str = Field(
        default="synthetic_test_fixture",
        description="synthetic_test_fixture, valid_numeric_raster_unverified_source, official_endpoint_retrieved_checksum_unverified, verified_source, or incomplete_missing_genuine_dem",
    )
    dem_loaded: bool = Field(
        default=False, description="True only when a non-synthetic numeric DEM raster is loaded"
    )
    real_dem_requested: bool = Field(
        default=False, description="True when MARSPATH_USE_REAL_DEM is enabled"
    )
    real_dem_loaded: bool = Field(
        default=False, description="True when a real numeric DEM raster is loaded and active"
    )
    local_integrity_verified: bool | None = Field(
        default=None, description="True when local file SHA-256 matches its provenance sidecar"
    )
    source_checksum_verified: bool = Field(
        default=False,
        description="True only when the full upstream archive checksum has been independently verified",
    )
    is_synthetic: bool
    active_pilot_region: str
    pilot_bounds: BoundingBox
    crs: CRSInfo
    loaded_dem: str | None
    active_dem_dataset_name: str | None = Field(default=None)
    active_dem_product_id: str | None = Field(default=None)
    active_dem_source_url: str | None = Field(default=None)
    fallback_reason: str | None = Field(default=None)
    dem_resolution_meters: float
    grid_shape: list[int]
    valid_data_fraction: float
    active_dem_provenance: dict[str, Any] = Field(default_factory=dict)
    configured_products: list[dict[str, Any]]
    limitations: list[str]
    blocking_errors: list[str] = Field(default_factory=list)
