"""
Deterministic Route Robustness Stress-Testing Service.

Evaluates how sensitive planned Martian routes are to plausible spatially correlated
Gaussian elevation perturbations applied to a copy of the active mission corridor DEM.

Scientific Integrity Principles:
- Does NOT invent vertical error standard deviations or spatial correlation scales for USGS DEMs.
- Requires explicit user-supplied `vertical_sigma_m` and `correlation_length_m` when enabled.
- Documents that `correlation_length_m` is the physical standard deviation L of the 2D Gaussian
  convolution filter kernel, distinguishing it from the resulting random field's theoretical
  infinite-plane autocorrelation standard deviation (sqrt(2) * L) and e-folding distance (2 * L).
- Preserves original DEM arrays and nodata masks without mutation.
- Evaluates each baseline route under its own `RouteAlternative.mode` (slope ceiling and cost
  weights) and its own required waypoint sequence (`waypoints_visited`).
- Returns `None` (`null`) for aggregate feasibility and retention fractions when zero scenario
  comparisons complete (`evaluated_scenario_count == 0`), never conflating A* search failures
  with physical route infeasibility.
- Separates terrain evidence quality (`evidence_passport.quality_tier`) from route geometric/cost stability.
- Never reports scenario retention or feasibility fractions as probabilities of rover survival or mission success.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
from scipy import ndimage

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    InvalidConstraintError,
    UnreachableDestinationError,
)
from backend.app.geospatial.crs import geo_to_pixel
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.routing.astar import astar_search
from backend.app.routing.cost_model import MODE_WEIGHTS, calculate_edge_cost
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode, RouteConstraints
from backend.app.schemas.routes import (
    BaselineRouteRobustness,
    EvidenceQualityTier,
    RobustnessConfig,
    RobustnessScenarioResult,
    RouteAlternative,
    RouteRobustnessAssessment,
    ScenarioBaselineRouteResult,
    UncertaintyAssumptions,
)
from backend.app.services.evidence_service import compute_nodata_and_boundary_masks

logger = logging.getLogger("marspath.services.robustness_service")

MANDATORY_ROBUSTNESS_DISCLAIMER = (
    "Results describe route stability under the specified hypothetical terrain perturbation "
    "model. They do not establish the actual probability of rover failure or mission success."
)


def derive_scenario_seeds(master_seed: int, scenario_count: int) -> list[int]:
    """
    Derives `scenario_count` deterministic, reproducible integer seeds from `master_seed`
    using NumPy's `SeedSequence`.
    """
    normalized_master = int(master_seed) & 0xFFFFFFFFFFFFFFFF
    seq = np.random.SeedSequence(normalized_master)
    states = seq.generate_state(scenario_count, dtype=np.uint32)
    return [int(s) for s in states]


def compute_effective_max_slope(
    constraints: RouteConstraints,
    route_mode: OptimizationMode,
) -> float:
    """
    Computes the effective slope ceiling in degrees for `route_mode` as the minimum of
    `constraints.max_slope_deg` and the mode's slope ceiling defined in `MODE_WEIGHTS`.

    For example, `OptimizationMode.SAFETY_FIRST` enforces a 14.0° ceiling even when the
    request-level `constraints.max_slope_deg` is 20.0°.
    """
    mode_ceiling = MODE_WEIGHTS[route_mode].slope_ceiling_deg
    return min(float(constraints.max_slope_deg), float(mode_ceiling))


def compute_gaussian_filter_pixel_sigmas(
    correlation_length_m: float,
    dx_meters: float,
    dy_meters: float,
) -> tuple[float, float]:
    """
    Converts the physical Gaussian convolution filter-kernel standard deviation
    `correlation_length_m` (L, in meters) into pixel standard deviations
    `(pixel_sigma_x, pixel_sigma_y)` using actual physical cell dimensions `(dx_meters, dy_meters)`.

    Mathematical definition:
        pixel_sigma_x = correlation_length_m / dx_meters  (along columns / zonal axis)
        pixel_sigma_y = correlation_length_m / dy_meters  (along rows / meridional axis)

    Note on filter-kernel scale vs. random-field autocorrelation scale:
        When an ideal unmasked infinite-plane 2D Gaussian filter with kernel standard deviation L
        is convolved with white noise, the resulting random field has autocorrelation
        rho(dx, dy) = exp(-dx^2 / (4 * L^2) - dy^2 / (4 * L^2)), corresponding to an
        autocorrelation Gaussian standard deviation of sqrt(2) * L and an e-folding distance of 2 * L.
    """
    if correlation_length_m <= 0.0 or not math.isfinite(correlation_length_m):
        raise InvalidConstraintError(
            f"correlation_length_m must be a positive finite number, got {correlation_length_m}."
        )
    if dx_meters <= 0.0 or dy_meters <= 0.0:
        raise InvalidConstraintError(
            f"Physical pixel sizes must be positive: dx={dx_meters}, dy={dy_meters}."
        )
    sigma_x = float(correlation_length_m) / float(dx_meters)
    sigma_y = float(correlation_length_m) / float(dy_meters)
    return sigma_x, sigma_y


def generate_perturbed_elevation(
    baseline_elevation: np.ndarray,
    nodata_mask: np.ndarray,
    vertical_sigma_m: float,
    correlation_length_m: float,
    dx_meters: float,
    dy_meters: float,
    scenario_seed: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Generates a reproducible spatially correlated Gaussian elevation perturbation scenario.

    Steps:
    1. Draw an independent zero-mean unit-variance Gaussian field W ~ N(0, 1) using `scenario_seed`.
    2. Zero out nodata positions prior to convolution so nodata sentinels cannot contaminate neighbors.
    3. Convolve W with a 2D separable Gaussian filter with kernel standard deviations
       (sigma_y = correlation_length_m / dy_meters, sigma_x = correlation_length_m / dx_meters).
    4. Center and normalize the filtered field strictly over valid cells (`~nodata_mask`) to have
       zero sample mean and standard deviation equal to `vertical_sigma_m`.
    5. Add the normalized perturbation to a copy of `baseline_elevation` while preserving exact
       original values at `nodata_mask` cells.

    Returns:
        (perturbed_elevation_f32, perturbation_f64, realized_valid_std_m)
    """
    if vertical_sigma_m <= 0.0 or not math.isfinite(vertical_sigma_m):
        raise InvalidConstraintError(
            f"vertical_sigma_m must be a positive finite number, got {vertical_sigma_m}."
        )

    sigma_x, sigma_y = compute_gaussian_filter_pixel_sigmas(
        correlation_length_m=correlation_length_m,
        dx_meters=dx_meters,
        dy_meters=dy_meters,
    )

    rng = np.random.default_rng(int(scenario_seed))
    raw_noise = rng.standard_normal(baseline_elevation.shape, dtype=np.float64)

    valid_mask = ~nodata_mask
    if np.any(nodata_mask):
        raw_noise[nodata_mask] = 0.0

    # Apply 2D Gaussian filter with (sigma_row, sigma_col) = (sigma_y, sigma_x)
    filtered = ndimage.gaussian_filter(
        raw_noise,
        sigma=(sigma_y, sigma_x),
        mode="nearest",
    )

    perturbation = np.zeros_like(baseline_elevation, dtype=np.float64)
    valid_count = int(np.sum(valid_mask))

    if valid_count >= 2:
        valid_values = filtered[valid_mask]
        mean_val = float(np.mean(valid_values))
        centered_valid = valid_values - mean_val
        std_val = float(np.std(centered_valid, ddof=0))
        if std_val > 1e-12:
            perturbation[valid_mask] = centered_valid * (float(vertical_sigma_m) / std_val)

    # Apply perturbation to a copy of baseline_elevation without mutating the input array
    perturbed_f64 = baseline_elevation.astype(np.float64).copy()
    if valid_count > 0:
        # Ensure valid perturbed cells remain above the -9000.0m nodata threshold sentinel
        perturbed_f64[valid_mask] = np.maximum(
            perturbed_f64[valid_mask] + perturbation[valid_mask],
            -8999.0,
        )

    perturbed_f32 = perturbed_f64.astype(np.float32)
    if np.any(nodata_mask):
        perturbed_f32[nodata_mask] = baseline_elevation[nodata_mask]

    if valid_count >= 2:
        realized_diff = (
            perturbed_f32[valid_mask].astype(np.float64)
            - baseline_elevation[valid_mask].astype(np.float64)
        )
        realized_std = float(np.std(realized_diff, ddof=0))
    else:
        realized_std = 0.0

    return perturbed_f32, perturbation, realized_std


def compute_jaccard_route_overlap(
    baseline_nodes: list[tuple[int, int]],
    scenario_nodes: list[tuple[int, int]],
) -> tuple[int, int, int, float]:
    """
    Computes Jaccard route overlap between baseline and scenario-optimal routes using
    their discrete grid-cell identities `(row, col)`:
        Jaccard = |intersection(baseline_nodes, scenario_nodes)| / |union(baseline_nodes, scenario_nodes)|

    Handles empty paths safely.

    Returns:
        (baseline_node_count, scenario_node_count, shared_node_count, jaccard_overlap_fraction)
    """
    base_set = set(baseline_nodes)
    scen_set = set(scenario_nodes)
    base_count = len(base_set)
    scen_count = len(scen_set)

    if base_count == 0 or scen_count == 0:
        return base_count, scen_count, 0, 0.0

    shared = base_set.intersection(scen_set)
    union = base_set.union(scen_set)
    shared_count = len(shared)
    union_count = len(union)
    if union_count == 0:
        return base_count, scen_count, 0, 0.0

    return base_count, scen_count, shared_count, float(shared_count) / float(union_count)


def compute_cost_regret_fraction(
    baseline_cost_in_scenario: float,
    scenario_optimal_cost: float,
) -> float:
    """
    Computes relative route cost regret in a perturbed scenario:
        cost_regret_fraction = (baseline_cost_in_scenario - scenario_optimal_cost) / scenario_optimal_cost

    Clamps only tiny negative values (-1e-9 <= raw_regret < 0.0) attributable to
    floating-point precision; never conceals genuine negative inconsistencies.
    """
    if scenario_optimal_cost <= 0.0 or not math.isfinite(scenario_optimal_cost):
        raise ValueError(
            f"scenario_optimal_cost must be positive and finite, got {scenario_optimal_cost}"
        )
    if not math.isfinite(baseline_cost_in_scenario):
        raise ValueError(
            f"baseline_cost_in_scenario must be finite, got {baseline_cost_in_scenario}"
        )

    raw_regret = (float(baseline_cost_in_scenario) - float(scenario_optimal_cost)) / float(
        scenario_optimal_cost
    )
    if -1e-9 <= raw_regret < 0.0:
        return 0.0
    return raw_regret


def evaluate_path_on_scenario_graph(
    path_nodes: list[tuple[int, int]],
    scenario_graph: TerrainGridGraph,
) -> tuple[bool, float | None, float | None, str | None]:
    """
    Evaluates whether a sequence of grid cells `path_nodes` remains feasible on `scenario_graph`
    and calculates its exact scenario traversal cost under `scenario_graph.mode`.

    Enforces:
    1. All path nodes must lie within grid bounds and be marked traversable in `scenario_graph.traversable`.
    2. Every step `(r1, c1) -> (r2, c2)` must be a valid 8-connected neighbor step.
    3. Diagonal corner-cutting prevention: if `dr != 0 and dc != 0`, both orthogonal adjacent
       cells `(r1 + dr, c1)` and `(r1, c1 + dc)` must also be traversable in `scenario_graph.traversable`.

    Returns:
        (is_feasible, total_scenario_cost, total_3d_length_meters, infeasibility_reason)
    """
    if not path_nodes:
        return False, None, None, "Baseline path is empty."

    r0, c0 = path_nodes[0]
    if not scenario_graph.is_in_bounds(r0, c0):
        return False, None, None, f"Start node ({r0}, {c0}) is out of scenario grid bounds."
    if not bool(scenario_graph.traversable[r0, c0]):
        return (
            False,
            None,
            None,
            f"Start node ({r0}, {c0}) became untraversable in perturbed scenario (mode={scenario_graph.mode.value}).",
        )

    total_cost = 0.0
    total_length_3d = 0.0

    for step_idx in range(len(path_nodes) - 1):
        r1, c1 = path_nodes[step_idx]
        r2, c2 = path_nodes[step_idx + 1]

        if not scenario_graph.is_in_bounds(r2, c2):
            return (
                False,
                None,
                None,
                f"Node ({r2}, {c2}) at step {step_idx + 1} is out of scenario grid bounds.",
            )

        if not bool(scenario_graph.traversable[r2, c2]):
            return (
                False,
                None,
                None,
                f"Node ({r2}, {c2}) at step {step_idx + 1} failed scenario traversability constraints (mode={scenario_graph.mode.value}).",
            )

        dr = r2 - r1
        dc = c2 - c1
        if abs(dr) > 1 or abs(dc) > 1 or (dr == 0 and dc == 0):
            return (
                False,
                None,
                None,
                f"Invalid non-adjacent grid step ({r1}, {c1}) -> ({r2}, {c2}) at step {step_idx + 1}.",
            )

        # Enforce diagonal corner-cutting constraint
        if dr != 0 and dc != 0:
            orth_1_ok = bool(scenario_graph.traversable[r1 + dr, c1])
            orth_2_ok = bool(scenario_graph.traversable[r1, c1 + dc])
            if not (orth_1_ok and orth_2_ok):
                return (
                    False,
                    None,
                    None,
                    f"Diagonal step ({r1}, {c1}) -> ({r2}, {c2}) at step {step_idx + 1} blocked by "
                    "diagonal corner-cutting constraint (orthogonal neighbor untraversable).",
                )
            d2d = scenario_graph.dist_diag
        elif dr != 0:
            d2d = scenario_graph.dist_orth_y
        else:
            d2d = scenario_graph.dist_orth_x

        z1 = float(scenario_graph.elevation[r1, c1])
        z2 = float(scenario_graph.elevation[r2, c2])
        slope = float(scenario_graph.slope_deg[r2, c2])
        rough = float(scenario_graph.roughness[r2, c2])

        if math.isnan(z1) or math.isnan(z2) or math.isnan(slope) or math.isnan(rough):
            return (
                False,
                None,
                None,
                f"Step ({r1}, {c1}) -> ({r2}, {c2}) encountered NaN terrain metric in scenario.",
            )

        delta_z = z2 - z1
        dist_3d = math.sqrt(d2d**2 + delta_z**2)
        step_cost, _ = calculate_edge_cost(
            distance_3d=dist_3d,
            slope_deg=slope,
            roughness=rough,
            delta_z=delta_z,
            mode=scenario_graph.mode,
            is_nodata=False,
            extra_penalty=0.0,
        )
        total_cost += step_cost
        total_length_3d += dist_3d

    return True, total_cost, total_length_3d, None


def _compute_path_3d_length(
    path_nodes: list[tuple[int, int]],
    scenario_graph: TerrainGridGraph,
) -> float:
    total_len = 0.0
    for idx in range(len(path_nodes) - 1):
        r1, c1 = path_nodes[idx]
        r2, c2 = path_nodes[idx + 1]
        dr = r2 - r1
        dc = c2 - c1
        if dr != 0 and dc != 0:
            d2d = scenario_graph.dist_diag
        elif dr != 0:
            d2d = scenario_graph.dist_orth_y
        else:
            d2d = scenario_graph.dist_orth_x
        dz = float(scenario_graph.elevation[r2, c2]) - float(scenario_graph.elevation[r1, c1])
        total_len += math.sqrt(d2d**2 + dz**2)
    return total_len


def _solve_scenario_objective(
    scenario_graph: TerrainGridGraph,
    start_px: tuple[int, int],
    dest_px: tuple[int, int],
    required_waypoints: tuple[tuple[int, int], ...],
    max_expansions: int,
    scenario_idx: int,
) -> tuple[str, list[tuple[int, int]], float | None, float | None, int, str | None]:
    """
    Runs A* search on `scenario_graph` from `start_px` through `required_waypoints` to `dest_px`.

    Returns:
        (status, opt_nodes, opt_cost, opt_len_m, nodes_expanded, error_reason)
    """
    s_row, s_col = start_px
    d_row, d_col = dest_px
    mode_label = scenario_graph.mode.value

    if not scenario_graph.is_in_bounds(s_row, s_col) or not bool(
        scenario_graph.traversable[s_row, s_col]
    ):
        return (
            "failed_untraversable_endpoint",
            [],
            None,
            None,
            0,
            f"Start cell ({s_row}, {s_col}) became untraversable under mode '{mode_label}' in scenario {scenario_idx}.",
        )

    if not scenario_graph.is_in_bounds(d_row, d_col) or not bool(
        scenario_graph.traversable[d_row, d_col]
    ):
        return (
            "failed_untraversable_endpoint",
            [],
            None,
            None,
            0,
            f"Destination cell ({d_row}, {d_col}) became untraversable under mode '{mode_label}' in scenario {scenario_idx}.",
        )

    for w_idx, (w_row, w_col) in enumerate(required_waypoints):
        if not scenario_graph.is_in_bounds(w_row, w_col) or not bool(
            scenario_graph.traversable[w_row, w_col]
        ):
            return (
                "failed_untraversable_waypoint",
                [],
                None,
                None,
                0,
                f"Required waypoint #{w_idx + 1} at ({w_row}, {w_col}) became untraversable under mode '{mode_label}' in scenario {scenario_idx}.",
            )

    leg_endpoints = [(s_row, s_col)] + list(required_waypoints) + [(d_row, d_col)]
    full_opt_nodes: list[tuple[int, int]] = []
    total_opt_cost = 0.0
    total_expanded = 0

    try:
        for leg_i in range(len(leg_endpoints) - 1):
            leg_nodes, leg_cost, leg_exp, _ = astar_search(
                scenario_graph,
                leg_endpoints[leg_i],
                leg_endpoints[leg_i + 1],
                max_expansions=max_expansions,
            )
            total_expanded += leg_exp
            total_opt_cost += leg_cost
            if full_opt_nodes:
                full_opt_nodes.extend(leg_nodes[1:])
            else:
                full_opt_nodes.extend(leg_nodes)

        opt_len_m = round(_compute_path_3d_length(full_opt_nodes, scenario_graph), 2)
        return ("completed", full_opt_nodes, total_opt_cost, opt_len_m, total_expanded, None)
    except UnreachableDestinationError as ue:
        return ("failed_unreachable", [], None, None, total_expanded, ue.message)
    except ComputationalBoundExceededError as ce:
        return ("failed_computational_bound", [], None, None, total_expanded, ce.message)
    except Exception as ex:
        return (
            "failed_error",
            [],
            None,
            None,
            total_expanded,
            f"Unexpected scenario search error: {ex}",
        )


def _build_route_interpretation(
    route_id: str,
    evaluated_count: int,
    failed_search_count: int,
    feasible_count: int,
    confirmed_baseline_infeasible_count: int,
    mean_overlap: float | None,
    mean_regret: float | None,
    retention_fraction: float | None,
    regret_threshold: float,
) -> str:
    if evaluated_count == 0:
        if confirmed_baseline_infeasible_count > 0:
            return (
                f"Aggregate stability metrics (feasibility, overlap, cost regret, and retention fractions) "
                f"for route '{route_id}' are unavailable because 0 scenario comparisons completed route "
                f"optimization ({confirmed_baseline_infeasible_count} scenario(s) failed baseline path "
                f"traversability checks; {failed_search_count} scenario search(es) did not complete). "
                f"{MANDATORY_ROBUSTNESS_DISCLAIMER}"
            )
        return (
            f"Aggregate stability metrics (feasibility, overlap, cost regret, and retention fractions) "
            f"for route '{route_id}' are unavailable because 0 scenario comparisons completed route "
            f"optimization ({failed_search_count} scenario search(es) did not complete; baseline path "
            f"traversability was not invalidated by failed A* search). "
            f"{MANDATORY_ROBUSTNESS_DISCLAIMER}"
        )

    assert retention_fraction is not None
    parts = [
        f"Across {evaluated_count} evaluated perturbation scenario(s), route '{route_id}' "
        f"remained traversable in {feasible_count}/{evaluated_count} scenario(s) "
        f"(feasibility fraction {feasible_count / evaluated_count:.2f}) and met the "
        f"<= {regret_threshold * 100:.1f}% relative cost-regret reporting criterion in "
        f"retention fraction {retention_fraction:.2f}."
    ]
    if failed_search_count > 0:
        parts.append(
            f"({failed_search_count} additional scenario search(es) failed to complete and were "
            "excluded from the evaluated denominator.)"
        )
    if mean_overlap is not None:
        if mean_overlap >= 0.75:
            parts.append(
                f"High mean Jaccard grid-cell overlap ({mean_overlap:.2f}) indicates the route "
                "geometry remained similar across evaluated terrain perturbations."
            )
        elif mean_overlap >= 0.40:
            parts.append(
                f"Moderate mean Jaccard grid-cell overlap ({mean_overlap:.2f}) indicates partial "
                "corridor shifts under the assumed terrain perturbations."
            )
        else:
            parts.append(
                f"Low mean Jaccard grid-cell overlap ({mean_overlap:.2f}) indicates the optimal "
                "corridor shifted materially under the assumed terrain perturbations."
            )
    if mean_regret is not None:
        parts.append(
            f"Mean relative cost regret across feasible scenarios was {mean_regret:.4f}."
        )
    parts.append(MANDATORY_ROBUSTNESS_DISCLAIMER)
    return " ".join(parts)


class RobustnessService:
    """
    Executes deterministic spatially correlated Gaussian elevation perturbation stress tests
    against baseline planned routes without mutating original terrain data or provider state.
    """

    @staticmethod
    def validate_config(config: RobustnessConfig | None) -> bool:
        """
        Returns True if robustness testing is enabled and valid, False if absent or disabled.
        Raises InvalidConstraintError if enabled=True with missing or invalid parameters.
        """
        if config is None or not config.enabled:
            return False

        if (
            config.vertical_sigma_m is None
            or isinstance(config.vertical_sigma_m, bool)
            or not math.isfinite(config.vertical_sigma_m)
            or config.vertical_sigma_m <= 0.0
        ):
            raise InvalidConstraintError(
                "robustness_config.vertical_sigma_m must be explicitly provided and > 0 when "
                "robustness testing is enabled. The backend does not invent DEM error parameters."
            )

        if (
            config.correlation_length_m is None
            or isinstance(config.correlation_length_m, bool)
            or not math.isfinite(config.correlation_length_m)
            or config.correlation_length_m <= 0.0
        ):
            raise InvalidConstraintError(
                "robustness_config.correlation_length_m must be explicitly provided and > 0 when "
                "robustness testing is enabled. The backend does not invent correlation scales."
            )

        if config.scenario_count < 3 or config.scenario_count > 20:
            raise InvalidConstraintError(
                f"robustness_config.scenario_count must be between 3 and 20, got {config.scenario_count}."
            )

        if (
            isinstance(config.cost_regret_threshold_fraction, bool)
            or not math.isfinite(config.cost_regret_threshold_fraction)
            or config.cost_regret_threshold_fraction < 0.0
        ):
            raise InvalidConstraintError(
                "robustness_config.cost_regret_threshold_fraction must be a non-negative finite float."
            )

        return True

    @staticmethod
    def _resolve_baseline_route_nodes(
        route: RouteAlternative,
        cropped_meta: RasterMetadata,
        baseline_route_nodes: dict[str, list[tuple[int, int]]] | None = None,
    ) -> list[tuple[int, int]]:
        if baseline_route_nodes and route.route_id in baseline_route_nodes:
            return list(baseline_route_nodes[route.route_id])

        # Fallback: convert GeoJSON coordinates back to cropped subgrid (row, col) indices
        resolved: list[tuple[int, int]] = []
        for coord in route.geometry.coordinates:
            lon, lat = float(coord[0]), float(coord[1])
            col, row = geo_to_pixel(
                lon,
                lat,
                cropped_meta.min_lon,
                cropped_meta.max_lat,
                cropped_meta.deg_per_px_lon,
                cropped_meta.deg_per_px_lat,
                pixel_center=True,
            )
            col = max(0, min(col, cropped_meta.width - 1))
            row = max(0, min(row, cropped_meta.height - 1))
            resolved.append((row, col))
        return resolved

    @staticmethod
    def _resolve_route_waypoint_pixels(
        route: RouteAlternative,
        cropped_meta: RasterMetadata,
        fallback_waypoint_pixels: list[tuple[int, int]] | None = None,
    ) -> tuple[tuple[int, int], ...]:
        """
        Resolves the ordered sequence of required intermediate `(row, col)` waypoint cells
        for `route` from `route.waypoints_visited` (covering both explicit `science_waypoints`
        and automatic `science_first` selected target detours).
        """
        if route.waypoints_visited:
            wp_cells: list[tuple[int, int]] = []
            for wp in route.waypoints_visited:
                col, row = geo_to_pixel(
                    wp.lon,
                    wp.lat,
                    cropped_meta.min_lon,
                    cropped_meta.max_lat,
                    cropped_meta.deg_per_px_lon,
                    cropped_meta.deg_per_px_lat,
                    pixel_center=True,
                )
                col = max(0, min(col, cropped_meta.width - 1))
                row = max(0, min(row, cropped_meta.height - 1))
                wp_cells.append((row, col))
            return tuple(wp_cells)

        if route.route_id == "route_primary_waypoint_guided" and fallback_waypoint_pixels:
            return tuple(fallback_waypoint_pixels)

        return ()

    @classmethod
    def evaluate_route_robustness(
        cls,
        config: RobustnessConfig | None,
        cropped_elevation: np.ndarray,
        cropped_meta: RasterMetadata,
        dx_meters: float,
        dy_meters: float,
        start_px: tuple[int, int],
        dest_px: tuple[int, int],
        requested_mode: OptimizationMode,
        constraints: RouteConstraints,
        baseline_routes: list[RouteAlternative],
        baseline_route_nodes: dict[str, list[tuple[int, int]]] | None = None,
        waypoint_pixels: list[tuple[int, int]] | None = None,
        provenance: dict[str, Any] | None = None,
        is_synthetic: bool = False,
        max_cells: int | None = None,
        subgrid_max_slope_deg: np.ndarray | None = None,
        subgrid_max_roughness: np.ndarray | None = None,
    ) -> RouteRobustnessAssessment | None:
        """
        Executes the requested deterministic terrain perturbation stress test and returns a
        structured `RouteRobustnessAssessment`, or `None` when `config` is absent or disabled.
        """
        if not cls.validate_config(config):
            return None

        assert config is not None
        assert config.vertical_sigma_m is not None
        assert config.correlation_length_m is not None

        settings = get_settings()
        allowed_cells = max_cells if max_cells is not None else settings.MAX_GRID_CELLS
        total_cells = int(cropped_elevation.size)
        if total_cells > allowed_cells:
            raise ComputationalBoundExceededError(
                f"Cropped terrain grid ({cropped_elevation.shape[0]}x{cropped_elevation.shape[1]} = "
                f"{total_cells} cells) exceeds maximum cell budget ({allowed_cells}) for robustness stress testing.",
                dimensions=cropped_elevation.shape,
                max_allowed=allowed_cells,
            )

        # Snapshot read-only copy of baseline elevation and nodata mask
        baseline_elev_copy = np.array(cropped_elevation, copy=True)
        baseline_nodata_mask, _ = compute_nodata_and_boundary_masks(
            baseline_elev_copy, cropped_meta.nodata_value
        )

        sigma_x, sigma_y = compute_gaussian_filter_pixel_sigmas(
            correlation_length_m=config.correlation_length_m,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
        )

        # Resolve discrete (row, col) node paths and required waypoint objectives for each baseline route
        resolved_paths: dict[str, list[tuple[int, int]]] = {}
        route_waypoints: dict[str, tuple[tuple[int, int], ...]] = {}
        distinct_modes: list[OptimizationMode] = []

        for route in baseline_routes:
            resolved_paths[route.route_id] = cls._resolve_baseline_route_nodes(
                route=route,
                cropped_meta=cropped_meta,
                baseline_route_nodes=baseline_route_nodes,
            )
            route_waypoints[route.route_id] = cls._resolve_route_waypoint_pixels(
                route=route,
                cropped_meta=cropped_meta,
                fallback_waypoint_pixels=waypoint_pixels,
            )
            if route.mode not in distinct_modes:
                distinct_modes.append(route.mode)
        if requested_mode not in distinct_modes:
            distinct_modes.append(requested_mode)

        scenario_seeds = derive_scenario_seeds(config.seed, config.scenario_count)
        scenario_results: list[RobustnessScenarioResult] = []
        completed_count = 0
        failed_count = 0

        for idx, scen_seed in enumerate(scenario_seeds):
            try:
                perturbed_elev, _, realized_std = generate_perturbed_elevation(
                    baseline_elevation=baseline_elev_copy,
                    nodata_mask=baseline_nodata_mask,
                    vertical_sigma_m=config.vertical_sigma_m,
                    correlation_length_m=config.correlation_length_m,
                    dx_meters=dx_meters,
                    dy_meters=dy_meters,
                    scenario_seed=scen_seed,
                )

                scen_nodata_mask, _ = compute_nodata_and_boundary_masks(
                    perturbed_elev, cropped_meta.nodata_value
                )
                scen_slope = compute_slope_degrees(
                    perturbed_elev,
                    dx_meters=dx_meters,
                    dy_meters=dy_meters,
                    nodata_mask=scen_nodata_mask,
                )
                if subgrid_max_slope_deg is not None and subgrid_max_slope_deg.shape == scen_slope.shape:
                    both_nan_slope = np.isnan(scen_slope) | np.isnan(subgrid_max_slope_deg)
                    scen_slope = np.where(
                        both_nan_slope,
                        np.nan,
                        np.maximum(scen_slope, subgrid_max_slope_deg),
                    ).astype(np.float32)

                scen_roughness = compute_roughness_index(
                    perturbed_elev,
                    kernel_size=3,
                    nodata_mask=scen_nodata_mask,
                )
                if subgrid_max_roughness is not None and subgrid_max_roughness.shape == scen_roughness.shape:
                    both_nan_rough = np.isnan(scen_roughness) | np.isnan(subgrid_max_roughness)
                    scen_roughness = np.where(
                        both_nan_rough,
                        np.nan,
                        np.maximum(scen_roughness, subgrid_max_roughness),
                    ).astype(np.float32)

                # Build mode-specific traversability masks and TerrainGridGraphs
                mode_graphs: dict[OptimizationMode, TerrainGridGraph] = {}
                for r_mode in distinct_modes:
                    eff_max_slope = compute_effective_max_slope(constraints, r_mode)
                    r_trav = build_traversability_mask(
                        slope_deg=scen_slope,
                        roughness=scen_roughness,
                        max_slope_deg=eff_max_slope,
                        max_roughness=constraints.max_roughness,
                        nodata_mask=scen_nodata_mask,
                        avoid_unobserved_terrain=constraints.avoid_unobserved_terrain,
                    )
                    mode_graphs[r_mode] = TerrainGridGraph(
                        elevation=perturbed_elev,
                        slope_deg=scen_slope,
                        roughness=scen_roughness,
                        traversable_mask=r_trav,
                        dx_meters=dx_meters,
                        dy_meters=dy_meters,
                        mode=r_mode,
                    )
            except Exception as gen_err:
                logger.warning("Scenario %d terrain generation failed: %s", idx, gen_err)
                failed_count += 1
                empty_route_results = [
                    ScenarioBaselineRouteResult(
                        route_id=r.route_id,
                        route_mode=r.mode,
                        required_waypoint_count=len(route_waypoints.get(r.route_id, ())),
                        comparison_status="failed_error",
                        comparison_error_reason=f"Scenario terrain generation failed: {gen_err}",
                        feasible=False,
                        infeasibility_reason=f"Scenario terrain generation failed: {gen_err}",
                        baseline_node_count=len(set(resolved_paths.get(r.route_id, []))),
                        scenario_optimal_node_count=0,
                        shared_node_count=0,
                        jaccard_overlap_fraction=None,
                        baseline_cost_in_scenario=None,
                        scenario_optimal_cost=None,
                        cost_regret_fraction=None,
                        within_regret_threshold=False,
                        exceeds_regret_threshold=False,
                        scenario_nodes_expanded=0,
                        scenario_route_length_meters=None,
                    )
                    for r in baseline_routes
                ]
                scenario_results.append(
                    RobustnessScenarioResult(
                        scenario_index=idx,
                        scenario_seed=scen_seed,
                        terrain_generation_status="failed_error",
                        scenario_status="failed_error",
                        realized_perturbation_std_m=None,
                        scenario_optimal_cost=None,
                        scenario_nodes_expanded=0,
                        scenario_route_length_meters=None,
                        baseline_route_results=empty_route_results,
                        error_reason=f"Scenario terrain generation failed: {gen_err}",
                    )
                )
                continue

            # Evaluate each baseline route under its own mode graph and its own waypoint objective
            objective_cache: dict[
                tuple[OptimizationMode, tuple[tuple[int, int], ...]],
                tuple[str, list[tuple[int, int]], float | None, float | None, int, str | None],
            ] = {}
            scen_total_expanded = 0
            route_scen_results: list[ScenarioBaselineRouteResult] = []

            for route in baseline_routes:
                r_mode = route.mode
                r_graph = mode_graphs[r_mode]
                r_nodes = resolved_paths.get(route.route_id, [])
                r_wps = route_waypoints.get(route.route_id, ())

                # 1. Evaluate physical feasibility and scenario cost of the baseline path on its mode graph
                is_feas, base_scen_cost, _, infeas_reason = evaluate_path_on_scenario_graph(
                    path_nodes=r_nodes,
                    scenario_graph=r_graph,
                )

                # 2. Solve or reuse the route-specific scenario-optimal path for (r_mode, r_wps)
                obj_key = (r_mode, r_wps)
                if obj_key not in objective_cache:
                    obj_res = _solve_scenario_objective(
                        scenario_graph=r_graph,
                        start_px=start_px,
                        dest_px=dest_px,
                        required_waypoints=r_wps,
                        max_expansions=constraints.max_search_nodes,
                        scenario_idx=idx,
                    )
                    objective_cache[obj_key] = obj_res
                    scen_total_expanded += obj_res[4]
                else:
                    obj_res = objective_cache[obj_key]

                comp_status, opt_nodes, opt_cost, opt_len_m, obj_expanded, comp_err = obj_res

                if comp_status == "completed" and opt_cost is not None and opt_nodes:
                    base_cnt, scen_cnt, shared_cnt, jaccard = compute_jaccard_route_overlap(
                        r_nodes, opt_nodes
                    )
                    jaccard_val: float | None = round(jaccard, 4)
                else:
                    base_cnt = len(set(r_nodes))
                    scen_cnt = 0
                    shared_cnt = 0
                    jaccard_val = None

                if (
                    comp_status == "completed"
                    and is_feas
                    and base_scen_cost is not None
                    and opt_cost is not None
                    and opt_cost > 0.0
                ):
                    regret = compute_cost_regret_fraction(base_scen_cost, opt_cost)
                    regret_rounded: float | None = round(regret, 6)
                    within_thresh = regret <= (config.cost_regret_threshold_fraction + 1e-12)
                    exceeds_thresh = not within_thresh
                else:
                    regret_rounded = None
                    within_thresh = False
                    exceeds_thresh = False

                route_scen_results.append(
                    ScenarioBaselineRouteResult(
                        route_id=route.route_id,
                        route_mode=r_mode,
                        required_waypoint_count=len(r_wps),
                        comparison_status=comp_status,
                        comparison_error_reason=comp_err,
                        feasible=is_feas,
                        infeasibility_reason=infeas_reason,
                        baseline_node_count=base_cnt,
                        scenario_optimal_node_count=scen_cnt,
                        shared_node_count=shared_cnt,
                        jaccard_overlap_fraction=jaccard_val,
                        baseline_cost_in_scenario=(
                            round(base_scen_cost, 2) if base_scen_cost is not None else None
                        ),
                        scenario_optimal_cost=(
                            round(opt_cost, 2)
                            if (comp_status == "completed" and opt_cost is not None)
                            else None
                        ),
                        cost_regret_fraction=regret_rounded,
                        within_regret_threshold=within_thresh,
                        exceeds_regret_threshold=exceeds_thresh,
                        scenario_nodes_expanded=obj_expanded,
                        scenario_route_length_meters=(
                            opt_len_m if comp_status == "completed" else None
                        ),
                    )
                )

            # Determine scenario-level status while preserving per-route statuses
            completed_routes_in_scen = [
                r_res for r_res in route_scen_results if r_res.comparison_status == "completed"
            ]
            failed_routes_in_scen = [
                r_res for r_res in route_scen_results if r_res.comparison_status != "completed"
            ]

            if len(completed_routes_in_scen) == len(route_scen_results) and route_scen_results:
                scen_status = "completed"
                scen_error: str | None = None
                completed_count += 1
            elif completed_routes_in_scen:
                scen_status = "completed_partial"
                scen_error = "; ".join(
                    f"{r_res.route_id}: {r_res.comparison_error_reason}"
                    for r_res in failed_routes_in_scen
                    if r_res.comparison_error_reason
                )
                completed_count += 1
            else:
                scen_status = (
                    route_scen_results[0].comparison_status
                    if route_scen_results
                    else "failed_error"
                )
                scen_error = (
                    route_scen_results[0].comparison_error_reason
                    if route_scen_results
                    else "No baseline routes available for scenario comparison."
                )
                failed_count += 1

            primary_ref = (
                route_scen_results[0]
                if (route_scen_results and route_scen_results[0].comparison_status == "completed")
                else (completed_routes_in_scen[0] if completed_routes_in_scen else None)
            )

            scenario_results.append(
                RobustnessScenarioResult(
                    scenario_index=idx,
                    scenario_seed=scen_seed,
                    terrain_generation_status="completed",
                    scenario_status=scen_status,
                    realized_perturbation_std_m=round(realized_std, 4),
                    scenario_optimal_cost=(
                        primary_ref.scenario_optimal_cost if primary_ref is not None else None
                    ),
                    scenario_nodes_expanded=scen_total_expanded,
                    scenario_route_length_meters=(
                        primary_ref.scenario_route_length_meters
                        if primary_ref is not None
                        else None
                    ),
                    baseline_route_results=route_scen_results,
                    error_reason=scen_error,
                )
            )

        # Aggregate per-baseline-route robustness summaries
        baseline_assessments: list[BaselineRouteRobustness] = []
        for route in baseline_routes:
            r_id = route.route_id
            r_wps = route_waypoints.get(r_id, ())
            completed_route_outcomes: list[ScenarioBaselineRouteResult] = []
            all_route_outcomes: list[ScenarioBaselineRouteResult] = []
            confirmed_baseline_infeasible_count = 0

            for s_res in scenario_results:
                for b_res in s_res.baseline_route_results:
                    if b_res.route_id == r_id:
                        all_route_outcomes.append(b_res)
                        if (
                            s_res.terrain_generation_status == "completed"
                            and not b_res.feasible
                        ):
                            confirmed_baseline_infeasible_count += 1
                        if b_res.comparison_status == "completed":
                            completed_route_outcomes.append(b_res)

            eval_count = len(completed_route_outcomes)
            route_failed_count = len(all_route_outcomes) - eval_count

            if eval_count > 0:
                feas_count = sum(1 for o in completed_route_outcomes if o.feasible)
                infeas_count = eval_count - feas_count
                feas_fraction: float | None = round(feas_count / eval_count, 4)

                overlaps = [
                    o.jaccard_overlap_fraction
                    for o in completed_route_outcomes
                    if o.jaccard_overlap_fraction is not None
                ]
                mean_overlap: float | None = (
                    round(float(np.mean(overlaps)), 4) if overlaps else None
                )
                min_overlap: float | None = (
                    round(float(np.min(overlaps)), 4) if overlaps else None
                )

                regrets = [
                    o.cost_regret_fraction
                    for o in completed_route_outcomes
                    if o.feasible and o.cost_regret_fraction is not None
                ]
                mean_regret: float | None = (
                    round(float(np.mean(regrets)), 6) if regrets else None
                )
                max_regret: float | None = (
                    round(float(np.max(regrets)), 6) if regrets else None
                )

                within_cnt = sum(1 for o in completed_route_outcomes if o.within_regret_threshold)
                exceed_cnt = sum(1 for o in completed_route_outcomes if o.exceeds_regret_threshold)
                retention_fraction: float | None = round(within_cnt / eval_count, 4)
            else:
                # Zero completed scenarios: do not fabricate 0.0 fractions when denominator is 0,
                # and do not count A* search failures as physical traversability failures.
                feas_count = 0
                infeas_count = 0
                feas_fraction = None
                mean_overlap = None
                min_overlap = None
                mean_regret = None
                max_regret = None
                within_cnt = 0
                exceed_cnt = 0
                retention_fraction = None

            interp = _build_route_interpretation(
                route_id=r_id,
                evaluated_count=eval_count,
                failed_search_count=route_failed_count,
                feasible_count=feas_count,
                confirmed_baseline_infeasible_count=confirmed_baseline_infeasible_count,
                mean_overlap=mean_overlap,
                mean_regret=mean_regret,
                retention_fraction=retention_fraction,
                regret_threshold=config.cost_regret_threshold_fraction,
            )

            baseline_assessments.append(
                BaselineRouteRobustness(
                    route_id=r_id,
                    route_mode=route.mode,
                    required_waypoint_count=len(r_wps),
                    evaluated_scenario_count=eval_count,
                    failed_scenario_count=route_failed_count,
                    scenario_feasible_count=feas_count,
                    scenario_infeasible_count=infeas_count,
                    baseline_route_feasibility_fraction=feas_fraction,
                    mean_route_overlap_fraction=mean_overlap,
                    minimum_route_overlap_fraction=min_overlap,
                    mean_cost_regret_fraction=mean_regret,
                    maximum_cost_regret_fraction=max_regret,
                    within_regret_threshold_count=within_cnt,
                    exceeding_regret_threshold_count=exceed_cnt,
                    baseline_route_retention_fraction=retention_fraction,
                    interpretation=interp,
                )
            )

        prov = provenance or {}
        active_data_mode = str(
            prov.get("data_mode", "synthetic_test_fixture" if is_synthetic else "real")
        )
        primary_tier = (
            baseline_routes[0].evidence_passport.quality_tier
            if (baseline_routes and baseline_routes[0].evidence_passport is not None)
            else (
                EvidenceQualityTier.UNVERIFIED
                if is_synthetic
                else EvidenceQualityTier.LOW
            )
        )

        L_kernel = float(config.correlation_length_m)
        autocorr_sigma_m = math.sqrt(2.0) * L_kernel
        efolding_dist_m = 2.0 * L_kernel

        known_limitations = [
            "The active MOLA-HRSC DEM does not establish a validated per-pixel vertical error standard deviation or spatial correlation length in its provenance metadata; vertical_sigma_m and correlation_length_m are user-supplied hypothetical stress-test assumptions.",
            f"correlation_length_m ({L_kernel:.1f}m) specifies the physical standard deviation L of the 2D Gaussian convolution filter kernel. For an ideal unmasked infinite-plane Gaussian filter applied to white noise, the resulting field autocorrelation is rho(dx, dy) = exp(-dx^2 / (4*L^2) - dy^2 / (4*L^2)), with autocorrelation Gaussian standard deviation sqrt(2)*L = {autocorr_sigma_m:.1f}m and e-folding distance 2*L = {efolding_dist_m:.1f}m; finite-grid boundaries, nodata masking, and valid-cell normalization modify empirical finite-window correlations.",
            "Scenario feasibility, overlap, and retention fractions are deterministic frequencies across the finite set of evaluated scenarios conditional on user-specified assumptions; they are NOT calibrated probabilities of rover survival or mission success.",
            f"Cost-regret threshold ({config.cost_regret_threshold_fraction:.4f}) is a comparative routing efficiency criterion, not a physical rover safety threshold.",
            f"Perturbations are evaluated at grid scale ({round(dx_meters, 2)}m x {round(dy_meters, 2)}m) and do not resolve metre-scale boulders, regolith cohesion hazards, or sub-pixel obstacles.",
        ]
        if is_synthetic or primary_tier == EvidenceQualityTier.UNVERIFIED:
            known_limitations.append(
                "Baseline terrain is synthetic or unverified (`quality_tier: unverified`). Perturbation stress testing evaluates geometric stability on synthetic/unverified elevations and does not validate genuine Martian topography."
            )
        if failed_count > 0 or any(b.failed_scenario_count > 0 for b in baseline_assessments):
            known_limitations.append(
                "One or more scenario route optimizations did not complete and are reported in scenario_results and failed_scenario_count without being treated as positive stability evidence or false traversability failures."
            )

        assumptions = UncertaintyAssumptions(
            vertical_sigma_m=round(float(config.vertical_sigma_m), 4),
            correlation_length_m=round(L_kernel, 4),
            pixel_sigma_x=round(sigma_x, 4),
            pixel_sigma_y=round(sigma_y, 4),
            actual_dx_meters=round(dx_meters, 3),
            actual_dy_meters=round(dy_meters, 3),
            theoretical_autocorrelation_sigma_m=round(autocorr_sigma_m, 4),
            theoretical_efolding_distance_m=round(efolding_dist_m, 4),
            cost_regret_threshold_fraction=round(
                float(config.cost_regret_threshold_fraction), 6
            ),
        )

        return RouteRobustnessAssessment(
            enabled=True,
            model_name="spatially_correlated_gaussian_elevation_perturbation",
            model_description=(
                "Zero-mean Gaussian random fields convolved with a 2D separable Gaussian filter "
                f"of kernel standard deviation L={L_kernel:.1f}m (sigma_x={sigma_x:.3f} px, "
                f"sigma_y={sigma_y:.3f} px derived from physical cell sizes dx={dx_meters:.2f}m, "
                f"dy={dy_meters:.2f}m; theoretical infinite-plane field autocorrelation Gaussian "
                f"sigma sqrt(2)*L={autocorr_sigma_m:.1f}m, e-folding distance 2*L={efolding_dist_m:.1f}m), "
                f"normalized over valid non-nodata cells to vertical_sigma_m={config.vertical_sigma_m:.2f}m."
            ),
            uncertainty_assumptions=assumptions,
            seed=config.seed,
            requested_scenario_count=config.scenario_count,
            completed_scenario_count=completed_count,
            failed_scenario_count=failed_count,
            baseline_data_mode=active_data_mode,
            baseline_quality_tier=primary_tier,
            baseline_is_synthetic=bool(is_synthetic),
            baseline_route_assessments=baseline_assessments,
            scenario_results=scenario_results,
            scientific_disclaimer=MANDATORY_ROBUSTNESS_DISCLAIMER,
            known_limitations=known_limitations,
        )
