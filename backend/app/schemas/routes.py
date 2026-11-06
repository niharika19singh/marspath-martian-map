import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

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


class RobustnessConfig(BaseModel):
    """
    Optional configuration for deterministic route robustness stress testing under
    hypothetical spatially correlated Gaussian elevation perturbations.

    NOTE: The default USGS HRSC/MOLA blended DEM does not publish a validated per-cell
    vertical error standard deviation or spatial correlation length in its metadata.
    Therefore, when `enabled` is True, `vertical_sigma_m` and `correlation_length_m`
    must be explicitly supplied by the caller as hypothetical stress-test assumptions.
    """

    enabled: bool = Field(
        default=False,
        description="Whether deterministic terrain perturbation stress testing is enabled",
    )
    vertical_sigma_m: float | None = Field(
        default=None,
        description=(
            "Assumed one-standard-deviation vertical perturbation amplitude in meters "
            "(strictly positive float required when enabled=True; never invented automatically)"
        ),
    )
    correlation_length_m: float | None = Field(
        default=None,
        description=(
            "Gaussian spatial correlation length scale in meters "
            "(strictly positive float required when enabled=True; never invented automatically)"
        ),
    )
    scenario_count: int = Field(
        default=5,
        ge=3,
        le=20,
        description="Number of independently generated perturbation scenarios (bounded between 3 and 20)",
    )
    seed: int = Field(
        default=42,
        description="Deterministic integer random seed for reproducible scenario generation",
    )
    cost_regret_threshold_fraction: float = Field(
        default=0.05,
        ge=0.0,
        description=(
            "Configurable non-negative relative cost-regret reporting threshold fraction "
            "(default 0.05). Reporting criterion only, NOT a physical safety threshold."
        ),
    )

    @model_validator(mode="after")
    def validate_required_assumptions_when_enabled(self) -> "RobustnessConfig":
        if self.enabled:
            if (
                self.vertical_sigma_m is None
                or isinstance(self.vertical_sigma_m, bool)
                or not math.isfinite(self.vertical_sigma_m)
                or self.vertical_sigma_m <= 0.0
            ):
                raise ValueError(
                    "vertical_sigma_m must be explicitly provided as a positive number when "
                    "robustness_config.enabled is True. The backend does not invent unverified "
                    "USGS DEM vertical uncertainty parameters."
                )
            if (
                self.correlation_length_m is None
                or isinstance(self.correlation_length_m, bool)
                or not math.isfinite(self.correlation_length_m)
                or self.correlation_length_m <= 0.0
            ):
                raise ValueError(
                    "correlation_length_m must be explicitly provided as a positive number when "
                    "robustness_config.enabled is True. The backend does not invent unverified "
                    "USGS DEM spatial correlation parameters."
                )
        else:
            if self.vertical_sigma_m is not None and (
                isinstance(self.vertical_sigma_m, bool)
                or not math.isfinite(self.vertical_sigma_m)
                or self.vertical_sigma_m <= 0.0
            ):
                raise ValueError("vertical_sigma_m must be a positive finite float when provided.")
            if self.correlation_length_m is not None and (
                isinstance(self.correlation_length_m, bool)
                or not math.isfinite(self.correlation_length_m)
                or self.correlation_length_m <= 0.0
            ):
                raise ValueError(
                    "correlation_length_m must be a positive finite float when provided."
                )
        if (
            isinstance(self.cost_regret_threshold_fraction, bool)
            or not math.isfinite(self.cost_regret_threshold_fraction)
            or self.cost_regret_threshold_fraction < 0.0
        ):
            raise ValueError(
                "cost_regret_threshold_fraction must be a non-negative finite float."
            )
        return self


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
    robustness_config: RobustnessConfig | None = Field(
        default=None,
        description=(
            "Optional configuration for deterministic route robustness stress testing under "
            "hypothetical terrain perturbations. Disabled when omitted or enabled=False."
        ),
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
        ...,
        description=(
            "Total path distance in physical meters: 3D topographic surface distance when all "
            "route elevation observations are valid, or 2D horizontal ground distance when "
            "elevation observations are incomplete (see distance_measurement_basis)"
        ),
    )
    horizontal_distance_meters: float = Field(
        default=0.0,
        description="Total 2D horizontal ground distance in physical meters (always complete from grid geometry)",
    )
    surface_3d_distance_meters: float | None = Field(
        default=None,
        description="Complete 3D topographic surface distance in meters when all route elevation transitions are valid, or None when any elevation observation is missing",
    )
    distance_measurement_basis: str = Field(
        default="complete_3d_surface",
        description="'complete_3d_surface' when all route vertices have valid elevations, or 'horizontal_2d_only_incomplete_elevation' when any elevation sample is missing",
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
    estimated_duration_hours: float | None = Field(
        default=None,
        description="Complete estimated traversal time in hours assuming rover motion profile when all route steps have valid elevation and slope observations, or None when observations are incomplete",
    )
    observed_duration_hours_partial: float | None = Field(
        default=None,
        description="Partial traversal duration in hours summed strictly over fully observed steps without substituting zero slope, or None if no steps are fully observed",
    )
    motion_profile: str = Field(
        default="rover_slope_derated_0.15mps",
        description="Physical velocity profile: nominal 0.15 m/s with slope-dependent speed derating",
    )
    energy_index: float | None = Field(
        default=None,
        description="Complete relative energy consumption score factoring 3D distance and ascent when all route elevation transitions are valid, or None when elevation observations are incomplete",
    )
    observed_energy_index_partial: float | None = Field(
        default=None,
        description="Partial energy consumption score computed strictly over valid elevation transitions, or None if no valid elevation transitions exist",
    )
    science_score: float = Field(
        ..., description="Science acquisition score based on visited targets and proximity"
    )
    hazard_exposure_meters: float | None = Field(
        default=0.0,
        description="Complete physical meters traversed through high-risk terrain (slope > 12° or roughness > 0.5) when all route steps are fully observed, or None when slope/roughness/elevation observations are incomplete",
    )
    observed_hazard_exposure_meters_min: float = Field(
        default=0.0,
        description="Confirmed lower-bound physical meters traversed through observed high-risk steps",
    )
    unobserved_step_distance_meters: float = Field(
        default=0.0,
        description="Physical horizontal meters traversed across steps with missing elevation, slope, or roughness observations where hazard exposure is unknown",
    )
    risk_category: str = Field(
        default="nominal",
        description=(
            "Categorical risk classification: 'nominal', 'moderate', or 'high' when terrain "
            "observations are complete; 'unverified_incomplete_terrain_data', "
            "'moderate_observed_incomplete_data', 'high_observed_incomplete_data', or "
            "'unverified_no_valid_terrain_data' when observations are incomplete"
        ),
    )
    risk_assessment_status: str = Field(
        default="complete_observed",
        description="'complete_observed', 'incomplete_partial_observations', or 'unverified_no_valid_observations'",
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


class UncertaintyAssumptions(BaseModel):
    """Explicit hypothetical terrain perturbation assumptions used in robustness stress testing."""

    vertical_sigma_m: float = Field(
        ...,
        description="Assumed one-standard-deviation vertical perturbation amplitude in meters over valid cells",
    )
    correlation_length_m: float = Field(
        ...,
        description="Assumed Gaussian spatial correlation length scale in meters",
    )
    pixel_sigma_x: float = Field(
        ...,
        description="Gaussian filter kernel standard deviation along columns (correlation_length_m / actual_dx_meters)",
    )
    pixel_sigma_y: float = Field(
        ...,
        description="Gaussian filter kernel standard deviation along rows (correlation_length_m / actual_dy_meters)",
    )
    actual_dx_meters: float = Field(
        ...,
        description="Actual zonal pixel width in meters used to derive pixel_sigma_x",
    )
    actual_dy_meters: float = Field(
        ...,
        description="Actual meridional pixel height in meters used to derive pixel_sigma_y",
    )
    cost_regret_threshold_fraction: float = Field(
        ...,
        description="Configured relative cost-regret reporting threshold fraction",
    )
    cost_regret_threshold_interpretation: str = Field(
        default=(
            "Reporting criterion for comparing baseline route cost against scenario-optimal route cost; "
            "NOT a physical rover safety threshold or survival boundary."
        ),
        description="Explicit clarification that the regret threshold is a comparative reporting criterion",
    )
    filter_kernel_definition: str = Field(
        default=(
            "2D separable Gaussian convolution K(dr, dc) proportional to "
            "exp(-dr^2 / (2 * pixel_sigma_y^2) - dc^2 / (2 * pixel_sigma_x^2)), "
            "where pixel_sigma_y = correlation_length_m / actual_dy_meters and "
            "pixel_sigma_x = correlation_length_m / actual_dx_meters, followed by zero-mean "
            "and vertical_sigma_m standard-deviation normalization strictly over valid non-nodata cells."
        ),
        description="Mathematical definition of the spatial filter and normalization",
    )
    parameters_are_user_assumed_not_measured_dem_error: bool = Field(
        default=True,
        description="True because perturbation parameters are user-supplied stress-test assumptions, not empirically measured USGS DEM errors",
    )
    source_uncertainty_metadata_available: bool = Field(
        default=False,
        description="False when the active DEM metadata does not publish a validated per-cell vertical error sigma or spatial correlation scale",
    )
    assumption_disclosure: str = Field(
        default=(
            "The USGS HRSC/MOLA blended DEM does not publish a validated per-pixel vertical error "
            "distribution or spatial correlation length in its provenance metadata. The vertical_sigma_m "
            "and correlation_length_m values are hypothetical user-specified stress-test assumptions."
        ),
        description="Explicit disclosure of the origin of uncertainty parameters",
    )


class ScenarioBaselineRouteResult(BaseModel):
    """Evaluation of a single baseline route alternative under a single perturbed terrain scenario."""

    route_id: str = Field(..., description="Identifier of the evaluated baseline route")
    feasible: bool = Field(
        ...,
        description=(
            "True only if every node and step along the baseline route remains traversable in "
            "the perturbed scenario, including diagonal corner-cutting constraints"
        ),
    )
    infeasibility_reason: str | None = Field(
        default=None,
        description="Diagnostic explanation if the baseline route failed scenario traversability or corner-cutting checks",
    )
    baseline_node_count: int = Field(
        ..., description="Number of distinct grid nodes in the baseline route"
    )
    scenario_optimal_node_count: int = Field(
        default=0,
        description="Number of distinct grid nodes in the scenario-optimal route (0 if scenario search failed)",
    )
    shared_node_count: int = Field(
        default=0,
        description="Number of grid nodes shared in the intersection of baseline and scenario-optimal routes",
    )
    jaccard_overlap_fraction: float | None = Field(
        default=None,
        description=(
            "Jaccard route overlap |intersection(baseline_nodes, scenario_nodes)| / "
            "|union(baseline_nodes, scenario_nodes)| over grid cell identities, or None if scenario search failed"
        ),
    )
    baseline_cost_in_scenario: float | None = Field(
        default=None,
        description="Total cost of traversing the baseline route on the perturbed scenario graph when feasible, or None when infeasible",
    )
    scenario_optimal_cost: float | None = Field(
        default=None,
        description="Optimal A* route cost on the perturbed scenario graph, or None if scenario search failed",
    )
    cost_regret_fraction: float | None = Field(
        default=None,
        description=(
            "(baseline_cost_in_scenario - scenario_optimal_cost) / scenario_optimal_cost "
            "when baseline route is feasible and scenario optimal cost is valid, else None"
        ),
    )
    within_regret_threshold: bool = Field(
        default=False,
        description="True when baseline route is feasible, has valid scenario cost, and cost_regret_fraction <= cost_regret_threshold_fraction",
    )
    exceeds_regret_threshold: bool = Field(
        default=False,
        description="True when baseline route is feasible with valid cost regret strictly exceeding cost_regret_threshold_fraction",
    )


class RobustnessScenarioResult(BaseModel):
    """Outcome of a single deterministic terrain perturbation scenario."""

    scenario_index: int = Field(..., description="Zero-based index of the perturbation scenario")
    scenario_seed: int = Field(
        ..., description="Deterministic integer seed used to generate this scenario's random field"
    )
    scenario_status: str = Field(
        ...,
        description=(
            "Scenario execution status: 'completed', 'failed_untraversable_endpoint', "
            "'failed_unreachable', 'failed_computational_bound', or 'failed_error'"
        ),
    )
    realized_perturbation_std_m: float | None = Field(
        default=None,
        description="Measured standard deviation of the elevation perturbation across valid raster cells in meters",
    )
    scenario_optimal_cost: float | None = Field(
        default=None,
        description="Optimal A* traversal cost in the perturbed scenario, or None if scenario search failed",
    )
    scenario_nodes_expanded: int = Field(
        default=0,
        description="Number of priority queue states expanded by A* in this scenario",
    )
    scenario_route_length_meters: float | None = Field(
        default=None,
        description="3D surface length of the scenario-optimal route in meters, or None if scenario search failed",
    )
    baseline_route_results: list[ScenarioBaselineRouteResult] = Field(
        default_factory=list,
        description="Per-route comparison results for each baseline route alternative in this scenario",
    )
    error_reason: str | None = Field(
        default=None,
        description="Detailed failure reason when scenario_status is not 'completed', else None",
    )


class BaselineRouteRobustness(BaseModel):
    """Aggregate stability metrics for a baseline route across evaluated perturbation scenarios."""

    route_id: str = Field(..., description="Identifier of the baseline route alternative")
    evaluated_scenario_count: int = Field(
        default=0,
        description="Number of completed scenarios against which route retention and overlap were evaluated",
    )
    scenario_feasible_count: int = Field(
        ..., description="Number of scenarios in which the baseline route remained fully traversable"
    )
    scenario_infeasible_count: int = Field(
        ...,
        description="Number of scenarios in which at least one baseline route node or diagonal step failed traversability",
    )
    baseline_route_feasibility_fraction: float = Field(
        ...,
        description="Fraction of evaluated scenarios in which the baseline route remained traversable [0.0 - 1.0]",
    )
    mean_route_overlap_fraction: float | None = Field(
        default=None,
        description="Mean Jaccard grid-cell overlap between baseline and scenario-optimal routes across completed scenarios",
    )
    minimum_route_overlap_fraction: float | None = Field(
        default=None,
        description="Minimum Jaccard grid-cell overlap between baseline and scenario-optimal routes across completed scenarios",
    )
    mean_cost_regret_fraction: float | None = Field(
        default=None,
        description="Mean relative cost regret across feasible completed scenarios, or None if no feasible completed scenarios exist",
    )
    maximum_cost_regret_fraction: float | None = Field(
        default=None,
        description="Maximum relative cost regret across feasible completed scenarios, or None if no feasible completed scenarios exist",
    )
    within_regret_threshold_count: int = Field(
        ...,
        description="Number of evaluated scenarios where the baseline route was feasible, had valid cost, and stayed within the regret threshold",
    )
    exceeding_regret_threshold_count: int = Field(
        default=0,
        description="Number of feasible evaluated scenarios where the baseline route exceeded the configured cost-regret threshold",
    )
    baseline_route_retention_fraction: float = Field(
        ...,
        description=(
            "Fraction of evaluated scenarios in which the baseline route remained traversable, had valid "
            "scenario cost, and fell within the configured cost-regret threshold. "
            "Fraction of explicitly tested scenarios ONLY; NOT a probability of mission success."
        ),
    )
    interpretation: str = Field(
        ...,
        description="Non-probabilistic engineering summary of route geometry overlap, feasibility, and cost regret",
    )


class RouteRobustnessAssessment(BaseModel):
    """
    Deterministic terrain perturbation stress-test assessment for planned routes.
    Describes route geometric and cost stability under user-specified hypothetical
    terrain perturbations; never represents a probability of rover survival or mission success.
    """

    enabled: bool = Field(default=True, description="True when robustness stress testing was executed")
    model_name: str = Field(
        default="spatially_correlated_gaussian_elevation_perturbation",
        description="Identifier of the deterministic terrain perturbation model",
    )
    model_description: str = Field(
        ...,
        description="Detailed explanation of how spatially correlated Gaussian elevation perturbations are generated and evaluated",
    )
    uncertainty_assumptions: UncertaintyAssumptions = Field(
        ...,
        description="Explicit user-supplied perturbation assumptions and derived pixel filter scales",
    )
    seed: int = Field(..., description="Master deterministic random seed used for scenario generation")
    requested_scenario_count: int = Field(
        ..., description="Total number of perturbation scenarios requested"
    )
    completed_scenario_count: int = Field(
        ..., description="Number of perturbation scenarios that completed route optimization"
    )
    failed_scenario_count: int = Field(
        ...,
        description="Number of perturbation scenarios where route optimization failed (e.g., untraversable endpoint, unreachable corridor, or search bound exceeded)",
    )
    baseline_data_mode: str = Field(
        ...,
        description="Active data mode of the baseline terrain (e.g., real, real_official_endpoint_unverified_checksum, synthetic_test_fixture)",
    )
    baseline_quality_tier: EvidenceQualityTier = Field(
        ...,
        description="Evidence quality tier of the primary baseline route (preserved independently of route robustness)",
    )
    baseline_is_synthetic: bool = Field(
        default=False,
        description="True when stress testing was executed on synthetic procedural terrain rather than a genuine planetary DEM",
    )
    baseline_route_assessments: list[BaselineRouteRobustness] = Field(
        default_factory=list,
        description="Aggregated robustness metrics for each baseline route alternative",
    )
    scenario_results: list[RobustnessScenarioResult] = Field(
        default_factory=list,
        description="Per-scenario optimization outcomes and route comparisons",
    )
    scientific_disclaimer: str = Field(
        default=(
            "Results describe route stability under the specified hypothetical terrain perturbation "
            "model. They do not establish the actual probability of rover failure or mission success."
        ),
        description="Mandatory scientific disclaimer for route robustness stress testing",
    )
    known_limitations: list[str] = Field(
        default_factory=list,
        description="Explicit scientific and methodological limitations of the robustness assessment",
    )


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
    robustness_assessment: RouteRobustnessAssessment | None = Field(
        default=None,
        description=(
            "Optional deterministic terrain perturbation route stability assessment when "
            "robustness_config.enabled is True; None when disabled or omitted"
        ),
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
