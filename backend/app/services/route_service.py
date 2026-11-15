import logging
import math
import os
import time
import uuid

from backend.app.conditions.mission_clock import evaluate_route_mission_clock
from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    RoutingTimeoutError,
    UnreachableDestinationError,
)
from backend.app.data.planetary_protection import get_all_special_regions
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.hirise import (
    HiRISERasterProvider,
    get_shared_hirise_provider,
)
from backend.app.data.providers.mola_hrsc import (
    MOLAHRSCRasterProvider,
    get_shared_mola_provider,
)
from backend.app.geospatial.crs import (
    geo_to_pixel,
    get_mars_crs_info,
    haversine_distance_mars,
    validate_crs,
)
from backend.app.geospatial.terrain_metrics import compute_physical_pixel_sizes
from backend.app.geospatial.validation import (
    check_cell_traversability,
    validate_constraints,
    validate_coordinates_in_bounds,
)
from backend.app.routing.alternatives import (
    generate_route_alternatives,
    reconstruct_route_summary,
)
from backend.app.routing.astar import astar_search
from backend.app.routing.dijkstra import dijkstra_search
from backend.app.routing.geofence import evaluate_route_geofence
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.routing.return_constraint import (
    compute_backward_time_grid,
    serialize_time_grid_overlay,
)
from backend.app.routing.rf_visibility import evaluate_rf_line_of_sight
from backend.app.routing.survivability import compute_marswalk_survivability
from backend.app.routing.walkback import (
    compute_dual_radius_envelopes,
    evaluate_on_foot_feasibility,
)
from backend.app.schemas.mission import OptimizationMode, RoutingAlgorithm
from backend.app.schemas.routes import (
    AlgorithmComparisonReport,
    AlgorithmRunMetrics,
    ComputationStats,
    RouteAlternative,
    RoutePlanRequest,
    RoutePlanResponse,
)
from backend.app.schemas.safety_envelopes import WalkBackAssessment
from backend.app.services.evidence_service import EvidenceService
from backend.app.services.planning_intelligence import (
    classify_route_uncertainty,
    evaluate_mission_stress_suite,
    evaluate_pareto_frontier,
    evaluate_science_eva_plan,
    generate_mission_brief_markdown,
    plan_next_best_reconnaissance,
)
from backend.app.services.risk_service import RiskService
from backend.app.services.robustness_service import RobustnessService
from backend.app.services.terrain_source_service import TerrainSourceSelector

logger = logging.getLogger("marspath.services.route_service")


class RouteService:
    def __init__(
        self,
        provider: BaseRasterProvider | None = None,
        hirise_provider: HiRISERasterProvider | None = None,
        max_cells: int | None = None,
        corridor_padding_meters: float | None = None,
    ):
        self.settings = get_settings()
        if isinstance(provider, HiRISERasterProvider) and hirise_provider is None:
            self.provider: BaseRasterProvider = get_shared_mola_provider()
            self.hirise_provider: HiRISERasterProvider | None = provider
        else:
            self.provider = provider or get_shared_mola_provider()
            self.hirise_provider = (
                hirise_provider
                if hirise_provider is not None
                else (get_shared_hirise_provider() if provider is None else None)
            )
        self.max_cells = max_cells
        self.corridor_padding_meters = corridor_padding_meters

    def plan_route(self, request: RoutePlanRequest) -> RoutePlanResponse:
        # 1. Validate CRS
        validate_crs(request.crs_identifier)

        # 2. Validate Constraints & Optional Robustness Config
        validate_constraints(request.constraints)
        RobustnessService.validate_config(request.robustness_config)

        # 3. Resolve per-request DEM source preference if explicitly supplied by the caller
        active_regional_provider = self.provider
        active_hirise_provider = self.hirise_provider
        pref_dem = (getattr(request, "preferred_dem_source", None) or "").strip().lower()
        if pref_dem in (
            "hirise_1m",
            "auto",
            "hirise",
            "jez_hirise_soc_006_dtm_molatopography_deltageoid_1m_eqc_latts0_lon0_blend40",
            "dem_hirise_jezero_delta_1m",
        ):
            if (
                os.path.exists(self.settings.DEM_PATH)
                and getattr(active_regional_provider, "is_synthetic", lambda: False)()
            ):
                active_regional_provider = MOLAHRSCRasterProvider(dem_path=self.settings.DEM_PATH, use_real_dem=True)
            hi_path = (
                active_hirise_provider.dem_path if active_hirise_provider is not None else self.settings.HIRISE_DEM_PATH
            )
            if active_hirise_provider is None or not active_hirise_provider.enabled:
                active_hirise_provider = HiRISERasterProvider(dem_path=hi_path, enabled=True)
        elif pref_dem in (
            "mola_hrsc_200m",
            "mola",
            "regional",
            "mars_hrsc_mola_blenddem_global_200mp_v2",
            "dem_mola_hrsc_blended_200m",
        ):
            if (
                os.path.exists(self.settings.DEM_PATH)
                and getattr(active_regional_provider, "is_synthetic", lambda: False)()
            ):
                active_regional_provider = MOLAHRSCRasterProvider(dem_path=self.settings.DEM_PATH, use_real_dem=True)
            hi_path = (
                active_hirise_provider.dem_path if active_hirise_provider is not None else self.settings.HIRISE_DEM_PATH
            )
            active_hirise_provider = HiRISERasterProvider(dem_path=hi_path, enabled=False)

        # Early bounds validation & MAX_SEARCH_RADIUS_METERS guard
        # Validate that start, destination, and all waypoints lie within pilot region bounds before any expensive operations.
        regional_master_meta = active_regional_provider.get_dem_raster().metadata
        validate_coordinates_in_bounds(request.start, regional_master_meta, "Start point")
        validate_coordinates_in_bounds(request.destination, regional_master_meta, "Destination point")
        for idx, wp in enumerate(request.science_waypoints or []):
            validate_coordinates_in_bounds(wp, regional_master_meta, f"Science Waypoint #{idx + 1}")
        if getattr(request, "habitat", None) is not None:
            validate_coordinates_in_bounds(request.habitat, regional_master_meta, "Habitat base")

        # Enforce MAX_SEARCH_RADIUS_METERS before terrain selection, corridor preparation, or grid construction
        max_search_radius = self.settings.MAX_SEARCH_RADIUS_METERS
        direct_dist_m = haversine_distance_mars(request.start, request.destination)
        if direct_dist_m > max_search_radius:
            raise ComputationalBoundExceededError(
                f"Direct distance {direct_dist_m:.1f}m between start and destination exceeds configured maximum search radius of {max_search_radius:.1f}m.",
                dimensions=(0, 0),
                max_allowed=int(max_search_radius),
            )
        if request.science_waypoints:
            mission_pts = [request.start] + list(request.science_waypoints) + [request.destination]
            for idx in range(len(mission_pts) - 1):
                leg_dist_m = haversine_distance_mars(mission_pts[idx], mission_pts[idx + 1])
                if leg_dist_m > max_search_radius:
                    raise ComputationalBoundExceededError(
                        f"Direct leg distance {leg_dist_m:.1f}m between mission points exceeds configured maximum search radius of {max_search_radius:.1f}m.",
                        dimensions=(0, 0),
                        max_allowed=int(max_search_radius),
                    )

        # 4. Deterministic Multi-Resolution Terrain Source Selection & Corridor Preparation
        corridor_waypoints = list(request.science_waypoints or [])
        if getattr(request, "habitat", None) is not None:
            corridor_waypoints.append(request.habitat)
        selection_outcome = TerrainSourceSelector.select_and_prepare_corridor(
            start=request.start,
            destination=request.destination,
            waypoints=corridor_waypoints or None,
            regional_provider=active_regional_provider,
            hirise_provider=active_hirise_provider,
            max_cells=self.max_cells if self.max_cells is not None else self.settings.MAX_GRID_CELLS,
            corridor_padding_meters=self.corridor_padding_meters,
        )

        master_raster = selection_outcome.master_raster
        meta = master_raster.metadata
        cropped_elev = selection_outcome.corridor_elevation
        cropped_meta = selection_outcome.corridor_metadata
        s_col, s_row = selection_outcome.start_pixel
        d_col, d_row = selection_outcome.dest_pixel
        provenance = selection_outcome.provenance
        selection_report = selection_outcome.selection_report
        subgrid_max_slope_deg = selection_outcome.subgrid_max_slope_deg
        subgrid_max_roughness = selection_outcome.subgrid_max_roughness

        # 6. Physical pixel sizes in meters
        center_lat = (cropped_meta.min_lat + cropped_meta.max_lat) / 2.0
        dx_meters, dy_meters = compute_physical_pixel_sizes(
            center_lat_deg=center_lat,
            deg_per_px_lon=cropped_meta.deg_per_px_lon,
            deg_per_px_lat=cropped_meta.deg_per_px_lat,
        )

        # 7. Evaluate risk: Slope, Roughness, Traversability mask (preserving subgrid hazards if aggregated)
        slope_deg, roughness, traversable_mask = RiskService.evaluate_terrain_risk(
            elevation=cropped_elev,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
            constraints=request.constraints,
            mode=request.mode,
            subgrid_max_slope_deg=subgrid_max_slope_deg,
            subgrid_max_roughness=subgrid_max_roughness,
        )

        # 8. Check start and dest cell traversability
        check_cell_traversability(s_col, s_row, traversable_mask, request.start, "Start location")
        check_cell_traversability(d_col, d_row, traversable_mask, request.destination, "Destination location")

        # Resolve habitat base cell (defaults to start)
        if getattr(request, "habitat", None) is not None:
            hab_col, hab_row = geo_to_pixel(
                request.habitat.lon,
                request.habitat.lat,
                cropped_meta.min_lon,
                cropped_meta.max_lat,
                cropped_meta.deg_per_px_lon,
                cropped_meta.deg_per_px_lat,
                pixel_center=True,
            )
            hab_col = max(0, min(hab_col, cropped_meta.width - 1))
            hab_row = max(0, min(hab_row, cropped_meta.height - 1))
            check_cell_traversability(hab_col, hab_row, traversable_mask, request.habitat, "Habitat base")
        else:
            hab_row, hab_col = s_row, s_col

        # Stage 1 parameters
        cost_mode = str(getattr(request, "cost_mode", "directional") or "directional").lower()
        effort_model = str(getattr(request, "effort_model", "slope_penalty") or "slope_penalty").lower()
        cross_slope_weight = float(
            getattr(request, "cross_slope_weight", 0.35)
            if getattr(request, "cross_slope_weight", None) is not None
            else 0.35
        )
        suit_load_factor = float(getattr(request, "suit_load_factor", 1.0) or 1.0)
        return_mode = str(getattr(request, "return_constraint_mode", "flag") or "flag").lower()
        dep_utc = getattr(request, "departure_utc", None) or "2026-06-15T08:00:00Z"
        walk_speed = getattr(request, "walking_speed_m_s", None) or 1.1111
        max_eva_h = float(getattr(request, "max_eva_hours", 8.0) or 8.0)
        daylight_buf_min = float(getattr(request, "daylight_buffer_minutes", 0.0) or 0.0)
        rescue_enabled = bool(getattr(request, "rescue_enabled", True))
        rescue_speed_m_s = float(getattr(request, "rescue_speed_m_s", 2.7778) or 2.7778)
        rescue_max_slope_deg = float(getattr(request, "rescue_max_slope_deg", 12.0) or 12.0)
        rescue_threshold_min = float(getattr(request, "rescue_threshold_minutes", 30.0) or 30.0)

        # 8b. Backward-Dijkstra Habitat Return-Time Solver
        return_grid_res = None
        return_blocked_mask = None
        if return_mode != "off":
            return_grid_res = compute_backward_time_grid(
                elevation=cropped_elev,
                slope_deg=slope_deg,
                traversable_mask=traversable_mask,
                dx_meters=dx_meters,
                dy_meters=dy_meters,
                habitat_node=(hab_row, hab_col),
                base_speed_m_s=walk_speed,
                budget_seconds=max_eva_h * 3600.0,
            )
            if return_mode == "block":
                return_blocked_mask = return_grid_res.reachable_mask
                if not bool(return_blocked_mask[d_row, d_col]):
                    ret_s = float(return_grid_res.time_seconds_grid[d_row, d_col])
                    ret_desc = f"{ret_s / 60.0:.1f} min" if math.isfinite(ret_s) else "unreachable"
                    raise UnreachableDestinationError(
                        reason=(
                            f"Destination exceeds EVA return-time budget ({ret_desc} > {max_eva_h * 60.0:.1f} min) "
                            "to habitat under return_constraint_mode='block'."
                        ),
                        start=(hab_row, hab_col),
                        dest=(d_row, d_col),
                    )
                if not bool(return_blocked_mask[s_row, s_col]):
                    ret_s = float(return_grid_res.time_seconds_grid[s_row, s_col])
                    ret_desc = f"{ret_s / 60.0:.1f} min" if math.isfinite(ret_s) else "unreachable"
                    raise UnreachableDestinationError(
                        reason=(
                            f"Start coordinate exceeds EVA return-time budget ({ret_desc} > {max_eva_h * 60.0:.1f} min) "
                            "to habitat under return_constraint_mode='block'."
                        ),
                        start=(hab_row, hab_col),
                        dest=(s_row, s_col),
                    )

        # 8c. Backward-Dijkstra Rescue-Time Solver (reuses same solver with rescue vehicle profile)
        rescue_grid_res = None
        if rescue_enabled:
            rescue_grid_res = compute_backward_time_grid(
                elevation=cropped_elev,
                slope_deg=slope_deg,
                traversable_mask=traversable_mask,
                dx_meters=dx_meters,
                dy_meters=dy_meters,
                habitat_node=(hab_row, hab_col),
                base_speed_m_s=rescue_speed_m_s,
                budget_seconds=rescue_threshold_min * 60.0,
                max_drivable_slope_deg=rescue_max_slope_deg,
            )

        # 9. Build terrain grid graph
        graph = TerrainGridGraph(
            elevation=cropped_elev,
            slope_deg=slope_deg,
            roughness=roughness,
            traversable_mask=traversable_mask,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
            mode=request.mode,
            cost_mode=cost_mode,
            effort_model=effort_model,
            cross_slope_weight=cross_slope_weight,
            suit_load_factor=suit_load_factor,
            return_blocked_mask=return_blocked_mask,
        )

        science_pois = self.provider.get_science_targets()
        is_syn = bool(cropped_meta.is_synthetic)
        search_start = time.perf_counter()
        timeout_seconds = float(self.settings.ROUTING_TIMEOUT_SECONDS)
        deadline = search_start + timeout_seconds if timeout_seconds > 0 else None
        total_nodes_expanded = 0
        routes: list[RouteAlternative] = []
        baseline_route_nodes: dict[str, list[tuple[int, int]]] = {}
        waypoint_pixels: list[tuple[int, int]] = []
        algorithm_comparison_report: AlgorithmComparisonReport | None = None

        req_algo_raw = getattr(request, "algorithm", None) or RoutingAlgorithm.ASTAR
        req_algo = str(req_algo_raw.value if hasattr(req_algo_raw, "value") else req_algo_raw).lower()
        search_fn = dijkstra_search if req_algo == "dijkstra" else astar_search

        if req_algo == "compare":
            logger.info(
                "Executing A* vs Dijkstra comparative benchmark on corridor (%d,%d) -> (%d,%d)",
                s_row,
                s_col,
                d_row,
                d_col,
            )
            astar_nodes, astar_cost, astar_exp, astar_sec = astar_search(
                graph,
                (s_row, s_col),
                (d_row, d_col),
                max_expansions=request.constraints.max_search_nodes,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                overall_start_time=search_start,
            )
            sum_astar, _, _, _, _ = reconstruct_route_summary(
                astar_nodes, graph, cropped_meta, request.mode, science_targets=science_pois
            )
            metrics_astar = AlgorithmRunMetrics(
                algorithm="A*",
                path_length_km=round((sum_astar.total_distance_meters or 0.0) / 1000.0, 3),
                total_cost=round(astar_cost, 2),
                execution_time_seconds=round(astar_sec, 4),
                nodes_expanded=astar_exp,
                max_slope_deg=round(sum_astar.max_slope_deg or 0.0, 1),
                risk_category=sum_astar.risk_category or "low_risk",
                waypoint_count=len(astar_nodes),
            )

            dijkstra_nodes, dijkstra_cost, dijkstra_exp, dijkstra_sec = dijkstra_search(
                graph,
                (s_row, s_col),
                (d_row, d_col),
                max_expansions=request.constraints.max_search_nodes,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                overall_start_time=search_start,
            )
            sum_dijkstra, _, _, _, _ = reconstruct_route_summary(
                dijkstra_nodes, graph, cropped_meta, request.mode, science_targets=science_pois
            )
            metrics_dijkstra = AlgorithmRunMetrics(
                algorithm="Dijkstra",
                path_length_km=round((sum_dijkstra.total_distance_meters or 0.0) / 1000.0, 3),
                total_cost=round(dijkstra_cost, 2),
                execution_time_seconds=round(dijkstra_sec, 4),
                nodes_expanded=dijkstra_exp,
                max_slope_deg=round(sum_dijkstra.max_slope_deg or 0.0, 1),
                risk_category=sum_dijkstra.risk_category or "low_risk",
                waypoint_count=len(dijkstra_nodes),
            )

            cost_diff = round(abs(astar_cost - dijkstra_cost), 2)
            costs_equal = cost_diff <= 0.05
            ratio = round(dijkstra_exp / max(astar_exp, 1), 2)
            faster = "A*" if astar_sec <= dijkstra_sec else "Dijkstra"
            opt_statement = (
                f"Both A* and Dijkstra achieved optimal cost equivalence ({astar_cost:.2f} vs {dijkstra_cost:.2f}). "
                f"A* expanded {astar_exp} states in {astar_sec * 1000:.1f}ms, achieving a {ratio}x state reduction "
                f"over Dijkstra ({dijkstra_exp} states in {dijkstra_sec * 1000:.1f}ms)."
                if costs_equal
                else (
                    f"A* cost ({astar_cost:.2f}) and Dijkstra cost ({dijkstra_cost:.2f}) differ by {cost_diff:.2f} units. "
                    f"A* expanded {astar_exp} states vs Dijkstra {dijkstra_exp} states."
                )
            )

            algorithm_comparison_report = AlgorithmComparisonReport(
                astar=metrics_astar,
                dijkstra=metrics_dijkstra,
                cost_difference=cost_diff,
                costs_equal=costs_equal,
                faster_algorithm=faster,
                node_expansion_ratio=ratio,
                optimality_verified=costs_equal,
                comparison_statement=opt_statement,
            )
            total_nodes_expanded += astar_exp + dijkstra_exp

        # 10. Route Search Execution
        if request.science_waypoints:
            # Multi-leg routing visiting user-supplied waypoints in order
            logger.info(
                "Executing multi-leg route via %d user science waypoints.",
                len(request.science_waypoints),
            )

            for idx, wp in enumerate(request.science_waypoints):
                w_col, w_row = geo_to_pixel(
                    wp.lon,
                    wp.lat,
                    cropped_meta.min_lon,
                    cropped_meta.max_lat,
                    cropped_meta.deg_per_px_lon,
                    cropped_meta.deg_per_px_lat,
                    pixel_center=True,
                )
                w_col = max(0, min(w_col, cropped_meta.width - 1))
                w_row = max(0, min(w_row, cropped_meta.height - 1))
                check_cell_traversability(w_col, w_row, traversable_mask, wp, f"Science Waypoint #{idx + 1}")
                waypoint_pixels.append((w_row, w_col))

            all_leg_pixels = [(s_row, s_col)] + waypoint_pixels + [(d_row, d_col)]
            full_path: list[tuple[int, int]] = []
            leg_total_cost = 0.0

            for leg_idx in range(len(all_leg_pixels) - 1):
                p_from = all_leg_pixels[leg_idx]
                p_to = all_leg_pixels[leg_idx + 1]
                leg_nodes, leg_cost, leg_expansions, _ = search_fn(
                    graph,
                    p_from,
                    p_to,
                    max_expansions=request.constraints.max_search_nodes,
                    timeout_seconds=timeout_seconds,
                    deadline=deadline,
                    overall_start_time=search_start,
                )
                total_nodes_expanded += leg_expansions
                leg_total_cost += leg_cost

                if full_path:
                    full_path.extend(leg_nodes[1:])  # Avoid duplicate seam node
                else:
                    full_path.extend(leg_nodes)

            summary_wp, geom_wp, breakdown_wp, visited_wp, nearby_wp = reconstruct_route_summary(
                full_path, graph, cropped_meta, request.mode, science_targets=science_pois
            )
            passport_wp = EvidenceService.build_route_evidence_passport(
                path_nodes=full_path,
                graph=graph,
                master_meta=meta,
                cropped_meta=cropped_meta,
                provenance=provenance,
                mode=request.mode,
            )

            baseline_route_nodes["route_primary_waypoint_guided"] = list(full_path)
            primary_route = RouteAlternative(
                route_id="route_primary_waypoint_guided",
                name=f"Primary Route via {len(request.science_waypoints)} Science Waypoint(s)",
                mode=request.mode,
                score_rank=1,
                total_cost=round(sum(breakdown_wp.values()), 2),
                cost_breakdown=breakdown_wp,
                summary=summary_wp,
                geometry=geom_wp,
                waypoints_visited=request.science_waypoints,
                science_targets_visited=visited_wp,
                science_targets_nearby=nearby_wp,
                warnings=[],
                evidence_passport=passport_wp,
            )
            routes.append(primary_route)

            # Generate alternative if requested
            if request.num_alternatives > 1:
                alts, alt_nodes = generate_route_alternatives(
                    graph=graph,
                    meta=cropped_meta,
                    start_px=(s_row, s_col),
                    dest_px=(d_row, d_col),
                    requested_mode=request.mode,
                    num_alternatives=request.num_alternatives - 1,
                    science_targets=science_pois,
                    master_meta=meta,
                    provenance=provenance,
                    route_nodes_out=baseline_route_nodes,
                    timeout_seconds=timeout_seconds,
                    deadline=deadline,
                    overall_start_time=search_start,
                    algorithm=req_algo if req_algo != "compare" else "astar",
                )
                total_nodes_expanded += alt_nodes
                for a in alts:
                    a.score_rank = len(routes) + 1
                    routes.append(a)

        elif request.mode == OptimizationMode.SCIENCE_FIRST:
            # Autonomous science detour evaluation
            logger.info("Evaluating science-first mode candidate detours.")
            # 1. Compute direct route
            direct_nodes, direct_cost, dir_expansions, _ = search_fn(
                graph,
                (s_row, s_col),
                (d_row, d_col),
                max_expansions=request.constraints.max_search_nodes,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                overall_start_time=search_start,
            )
            total_nodes_expanded += dir_expansions

            # 2. Check candidate science POIs in corridor using multi-criteria scoring
            candidate_poi = None
            best_detour_nodes: list[tuple[int, int]] | None = None
            best_detour_cost = float("inf")
            best_detour_ratio = 1.0
            best_candidate_score = -1.0
            rejected_candidates: list[dict[str, str]] = []

            max_exp = request.constraints.max_search_nodes

            for poi in science_pois:
                p_col, p_row = geo_to_pixel(
                    poi.coordinate.lon,
                    poi.coordinate.lat,
                    cropped_meta.min_lon,
                    cropped_meta.max_lat,
                    cropped_meta.deg_per_px_lon,
                    cropped_meta.deg_per_px_lat,
                    pixel_center=True,
                )
                if not (0 <= p_col < cropped_meta.width and 0 <= p_row < cropped_meta.height):
                    rejected_candidates.append({"poi": poi.name, "reason": "Outside cropped corridor"})
                    continue

                if not traversable_mask[p_row, p_col]:
                    rejected_candidates.append({"poi": poi.name, "reason": "Target cell is untraversable"})
                    continue

                try:
                    # Evaluate start -> poi -> dest honoring configured max expansions and deadline
                    leg1_nodes, leg1_cost, exp1, _ = search_fn(
                        graph,
                        (s_row, s_col),
                        (p_row, p_col),
                        max_expansions=max_exp,
                        timeout_seconds=timeout_seconds,
                        deadline=deadline,
                        overall_start_time=search_start,
                    )
                    leg2_nodes, leg2_cost, exp2, _ = search_fn(
                        graph,
                        (p_row, p_col),
                        (d_row, d_col),
                        max_expansions=max_exp,
                        timeout_seconds=timeout_seconds,
                        deadline=deadline,
                        overall_start_time=search_start,
                    )
                    total_nodes_expanded += exp1 + exp2
                    detour_cost = leg1_cost + leg2_cost
                    detour_ratio = detour_cost / max(direct_cost, 1e-3)

                    # Hard constraint: Reject detours exceeding 2.5x direct cost
                    if detour_ratio > 2.5:
                        rejected_candidates.append(
                            {
                                "poi": poi.name,
                                "reason": f"Detour ratio {detour_ratio:.2f}x exceeds maximum allowance (2.50x)",
                            }
                        )
                        continue

                    # Multi-criteria scoring: prioritize high scientific priority relative to detour ratio
                    candidate_score = poi.scientific_priority / max(detour_ratio, 1.0)

                    if candidate_score > best_candidate_score or (
                        abs(candidate_score - best_candidate_score) < 1e-4 and detour_cost < best_detour_cost
                    ):
                        best_candidate_score = candidate_score
                        best_detour_cost = detour_cost
                        best_detour_ratio = detour_ratio
                        best_detour_nodes = leg1_nodes + leg2_nodes[1:]
                        candidate_poi = poi

                except RoutingTimeoutError:
                    raise
                except (UnreachableDestinationError, ComputationalBoundExceededError) as re:
                    logger.info("Science target '%s' route evaluation rejected: %s", poi.name, re)
                    rejected_candidates.append({"poi": poi.name, "reason": str(re)})
                except Exception as unexpected_err:
                    logger.warning("Unexpected error evaluating detour for '%s': %s", poi.name, unexpected_err)
                    rejected_candidates.append({"poi": poi.name, "reason": f"Unexpected error: {unexpected_err}"})

            if best_detour_nodes and candidate_poi:
                # Add science detour as primary route
                sum_sci, geom_sci, break_sci, vis_sci, near_sci = reconstruct_route_summary(
                    best_detour_nodes,
                    graph,
                    cropped_meta,
                    request.mode,
                    science_targets=science_pois,
                )
                passport_sci = EvidenceService.build_route_evidence_passport(
                    path_nodes=best_detour_nodes,
                    graph=graph,
                    master_meta=meta,
                    cropped_meta=cropped_meta,
                    provenance=provenance,
                    mode=request.mode,
                )
                baseline_route_nodes["route_science_primary"] = list(best_detour_nodes)
                sci_route = RouteAlternative(
                    route_id="route_science_primary",
                    name=f"Science-First Detour via {candidate_poi.name}",
                    mode=request.mode,
                    score_rank=1,
                    total_cost=round(sum(break_sci.values()), 2),
                    cost_breakdown=break_sci,
                    summary=sum_sci,
                    geometry=geom_sci,
                    waypoints_visited=[candidate_poi.coordinate],
                    science_targets_visited=vis_sci,
                    science_targets_nearby=near_sci,
                    warnings=[
                        f"Selected science target '{candidate_poi.name}' (Priority {candidate_poi.scientific_priority:.1f}, "
                        f"detour ratio {best_detour_ratio:.2f}x direct cost, candidate score {best_candidate_score:.2f})."
                    ],
                    evidence_passport=passport_sci,
                )
                routes.append(sci_route)

                # Add direct path as comparative alternative
                if request.num_alternatives > 1:
                    sum_dir, geom_dir, break_dir, vis_dir, near_dir = reconstruct_route_summary(
                        direct_nodes,
                        graph,
                        cropped_meta,
                        request.mode,
                        science_targets=science_pois,
                    )
                    passport_dir = EvidenceService.build_route_evidence_passport(
                        path_nodes=direct_nodes,
                        graph=graph,
                        master_meta=meta,
                        cropped_meta=cropped_meta,
                        provenance=provenance,
                        mode=request.mode,
                    )
                    baseline_route_nodes["route_direct_baseline"] = list(direct_nodes)
                    dir_route = RouteAlternative(
                        route_id="route_direct_baseline",
                        name="Direct Balanced Path (No Detour)",
                        mode=request.mode,
                        score_rank=2,
                        total_cost=round(sum(break_dir.values()), 2),
                        cost_breakdown=break_dir,
                        summary=sum_dir,
                        geometry=geom_dir,
                        science_targets_visited=vis_dir,
                        science_targets_nearby=near_dir,
                        warnings=["Bypasses science targets in favor of direct traversal."],
                        evidence_passport=passport_dir,
                    )
                    routes.append(dir_route)
            else:
                # Fallback to standard generation
                routes, alt_nodes = generate_route_alternatives(
                    graph=graph,
                    meta=cropped_meta,
                    start_px=(s_row, s_col),
                    dest_px=(d_row, d_col),
                    requested_mode=request.mode,
                    num_alternatives=request.num_alternatives,
                    science_targets=science_pois,
                    master_meta=meta,
                    provenance=provenance,
                    route_nodes_out=baseline_route_nodes,
                    timeout_seconds=timeout_seconds,
                    deadline=deadline,
                    overall_start_time=search_start,
                    algorithm=req_algo if req_algo != "compare" else "astar",
                )
                total_nodes_expanded += alt_nodes
        else:
            # Standard single / multi-alternative generation
            routes, alt_nodes = generate_route_alternatives(
                graph=graph,
                meta=cropped_meta,
                start_px=(s_row, s_col),
                dest_px=(d_row, d_col),
                requested_mode=request.mode,
                num_alternatives=request.num_alternatives,
                science_targets=science_pois,
                master_meta=meta,
                provenance=provenance,
                route_nodes_out=baseline_route_nodes,
                timeout_seconds=timeout_seconds,
                deadline=deadline,
                overall_start_time=search_start,
                algorithm=req_algo if req_algo != "compare" else "astar",
            )
            total_nodes_expanded += alt_nodes

        # 10b. Optional Route Robustness Stress Testing
        if deadline is not None and time.perf_counter() > deadline:
            elapsed = time.perf_counter() - search_start
            raise RoutingTimeoutError(
                f"Route planning exceeded routing timeout of {timeout_seconds:.2f}s before robustness evaluation.",
                timeout_seconds=timeout_seconds,
                elapsed_seconds=elapsed,
            )
        robustness_assessment = RobustnessService.evaluate_route_robustness(
            config=request.robustness_config,
            cropped_elevation=cropped_elev,
            cropped_meta=cropped_meta,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
            start_px=(s_row, s_col),
            dest_px=(d_row, d_col),
            requested_mode=request.mode,
            constraints=request.constraints,
            baseline_routes=routes,
            baseline_route_nodes=baseline_route_nodes,
            waypoint_pixels=waypoint_pixels,
            provenance=provenance,
            is_synthetic=is_syn,
            max_cells=self.max_cells if self.max_cells is not None else self.settings.MAX_GRID_CELLS,
            subgrid_max_slope_deg=subgrid_max_slope_deg,
            subgrid_max_roughness=subgrid_max_roughness,
        )

        # 11. Compile provenance & limitations
        active_mode = provenance.get("data_mode", "synthetic_test_fixture" if is_syn else "real")
        val_status = provenance.get("real_data_validation_status", "synthetic_test_fixture")

        if selection_report.hirise_selected:
            if selection_report.aggregation_applied:
                res_lim = (
                    f"Localized HiRISE DTM (native {selection_report.native_resolution_meters:.2f}m/px) "
                    f"was conservatively aggregated by factor k={selection_report.aggregation_factor} to "
                    f"{round(dy_meters, 1)}m/px to satisfy MAX_GRID_CELLS while preserving sub-block maximum "
                    "slope and roughness; does NOT provide flight-grade obstacle detection."
                )
            else:
                res_lim = (
                    f"Localized HiRISE DTM ({round(dy_meters, 2)}m/px post spacing) supports local landform "
                    "and scarp assessment, but orbital stereo DTMs (~2-4m feature resolution) do NOT provide "
                    "flight-grade obstacle detection for wheel-scale (<0.5m) rocks or regolith traps."
                )
        else:
            res_lim = (
                f"Elevation resolution ({round(dy_meters, 1)}m/px) supports regional corridor terrain "
                "assessment, not metre-scale obstacle detection or flight-grade rover navigation."
            )

        limitations = [
            res_lim,
            "Route cost weights, hazard penalties, and categorical risk levels are deterministic multi-criteria decision heuristics, not empirically calibrated probabilities of failure.",
        ]
        if is_syn:
            if active_mode == "synthetic_fallback":
                limitations.append(
                    f"Warning: Real NASA/USGS DEM was requested but failed or was missing; operating on Synthetic Jezero Crater Terrain Model ({provenance.get('fallback_reason', '')})."
                )
            else:
                limitations.append(
                    "Operating on Synthetic Jezero Crater Terrain Model. Real NASA/USGS DEM is not loaded."
                )
        elif val_status in (
            "verified_source",
            "official_endpoint_retrieved_checksum_unverified",
        ):
            if not selection_report.hirise_selected:
                limitations.append(
                    "USGS warns of HRSC/MOLA blending seam inconsistencies and notes the global blended DEM (200m/px nominal) was originally generated for thermal-modelling (THEMIS thermal inertia) rather than precision local navigation."
                )
            if val_status == "official_endpoint_retrieved_checksum_unverified":
                limitations.append(
                    "Retrieved via HTTP range extraction from official USGS endpoint; local GeoTIFF SHA-256 integrity is verified, but full 11.38 GB upstream file checksum was not computed over all upstream source bytes."
                )
        elif val_status == "valid_numeric_raster_unverified_source":
            limitations.append(
                "Operating on an unverified local numerical terrain raster. Official NASA/ESA/USGS provenance and product identity are not established."
            )

        for prov_lim in provenance.get("provenance_limitations", []):
            if prov_lim not in limitations:
                limitations.append(prov_lim)

        mission_id = f"mission_{uuid.uuid4().hex[:12]}"

        if req_algo == "compare":
            algo_label = "A* vs Dijkstra Comparative Benchmark"
        elif req_algo == "dijkstra":
            algo_label = "Dijkstra (uniform-cost search)"
        else:
            algo_label = "A* (with admissible Euclidean heuristic)"

        stats = ComputationStats(
            algorithm_used=algo_label,
            search_duration_seconds=round(time.perf_counter() - search_start, 4),
            nodes_expanded=total_nodes_expanded,  # Real measured count of expanded states
            grid_rows=cropped_meta.height,
            grid_cols=cropped_meta.width,
            cell_size_meters=round((dx_meters + dy_meters) / 2.0, 2),
        )

        # 12. Phase 2-4 + Stage 1 Mission Intelligence Enrichment
        inc_return = bool(getattr(request, "include_return_leg", True))
        eff_res_m = float(selection_report.effective_resolution_meters or round((dx_meters + dy_meters) / 2.0, 2))
        dem_src_name = str(provenance.get("dataset_name") or selection_report.selected_source_id)
        dem_res_label = f"{dem_src_name} ({round(eff_res_m, 1)} m/px)"
        wp_tuples = [(wp.lon, wp.lat) for wp in (request.science_waypoints or [])]
        wp_dicts = [{"lon": wp.lon, "lat": wp.lat, "stop_minutes": 20.0} for wp in (request.science_waypoints or [])]

        pareto_inputs: list[dict] = []
        for r_alt in routes:
            coords = r_alt.geometry.coordinates if r_alt.geometry else []
            path_nodes = baseline_route_nodes.get(r_alt.route_id, [])

            # Stage 1: Attach return-time and rescue-time metrics per segment & summary
            ret_vals_min: list[float] = []
            res_vals_min: list[float] = []
            exceeds_ret = False
            rescue_flagged_dist = 0.0
            has_unreach_ret = False
            has_unreach_res = False

            segs_raw = []
            if r_alt.evidence_passport and r_alt.evidence_passport.segments:
                for seg in r_alt.evidence_passport.segments:
                    node_idx = min(seg.segment_index + 1, len(path_nodes) - 1) if path_nodes else -1
                    if node_idx >= 0:
                        nr, nc = path_nodes[node_idx]
                        if return_grid_res is not None:
                            rt_s = float(return_grid_res.time_seconds_grid[nr, nc])
                            if math.isfinite(rt_s):
                                rt_m = round(rt_s / 60.0, 1)
                                seg.return_time_minutes = rt_m
                                ret_vals_min.append(rt_m)
                                if rt_m > max_eva_h * 60.0:
                                    exceeds_ret = True
                                    if "exceeds_eva_return_budget" not in seg.quality_flags:
                                        seg.quality_flags.append("exceeds_eva_return_budget")
                            else:
                                seg.return_time_minutes = None
                                has_unreach_ret = True
                                exceeds_ret = True
                                if "exceeds_eva_return_budget" not in seg.quality_flags:
                                    seg.quality_flags.append("exceeds_eva_return_budget")
                        if rescue_grid_res is not None:
                            rs_s = float(rescue_grid_res.time_seconds_grid[nr, nc])
                            if math.isfinite(rs_s):
                                rs_m = round(rs_s / 60.0, 1)
                                seg.rescue_time_minutes = rs_m
                                res_vals_min.append(rs_m)
                                if rs_m > rescue_threshold_min:
                                    rescue_flagged_dist += float(seg.step_distance_meters)
                                    if "exceeds_rescue_time_threshold" not in seg.quality_flags:
                                        seg.quality_flags.append("exceeds_rescue_time_threshold")
                            else:
                                seg.rescue_time_minutes = None
                                has_unreach_res = True
                                rescue_flagged_dist += float(seg.step_distance_meters)
                                if "exceeds_rescue_time_threshold" not in seg.quality_flags:
                                    seg.quality_flags.append("exceeds_rescue_time_threshold")

                    segs_raw.append(
                        {
                            "start_lon": seg.from_coord.lon,
                            "start_lat": seg.from_coord.lat,
                            "end_lon": seg.to_coord.lon,
                            "end_lat": seg.to_coord.lat,
                            "length_meters": seg.step_distance_meters,
                            "is_valid_data": seg.is_valid_data,
                            "slope_deg": seg.slope_deg,
                            "roughness": seg.roughness,
                            "quality_flags": seg.quality_flags,
                        }
                    )

            r_alt.summary.max_return_time_minutes = (
                round(max(ret_vals_min), 1) if (ret_vals_min and not has_unreach_ret) else None
            )
            r_alt.summary.exceeds_return_budget = bool(exceeds_ret)
            r_alt.summary.max_rescue_time_minutes = (
                round(max(res_vals_min), 1) if (res_vals_min and not has_unreach_res) else None
            )
            r_alt.summary.rescue_flagged_distance_meters = round(rescue_flagged_dist, 1)
            r_alt.summary.provenance = {
                "kind": "computed",
                "source": dem_src_name,
                "resolution": f"{round(eff_res_m, 2)} m/px",
                "as_of": dep_utc,
            }
            if exceeds_ret:
                r_alt.warnings.append(
                    f"Habitat return-time constraint flagged: route reaches cells exceeding {max_eva_h:.1f}h EVA budget."
                )
            if rescue_flagged_dist > 0.0:
                r_alt.warnings.append(
                    f"Rescue response time exceeds {rescue_threshold_min:.0f} min threshold across {round(rescue_flagged_dist, 1)} m."
                )

            unc = classify_route_uncertainty(
                segments=segs_raw,
                coordinates=coords,
                dem_resolution_m=eff_res_m,
                dem_source_id=selection_report.selected_source_id,
            )
            dur_h = float(
                r_alt.summary.estimated_duration_hours
                or r_alt.summary.observed_duration_hours_partial
                or ((r_alt.summary.total_distance_meters or 1000.0) / (walk_speed * 3600.0))
            )
            sci_plan = evaluate_science_eva_plan(
                coordinates=coords,
                duration_hours=dur_h,
                user_waypoints=wp_dicts,
                max_eva_hours=max_eva_h,
            )
            m_clock = evaluate_route_mission_clock(
                coordinates=coords,
                departure_utc=dep_utc,
                base_speed_m_s=walk_speed,
                waypoint_coords=wp_tuples,
                include_return_leg=inc_return,
                max_eva_duration_hours=max_eva_h,
                daylight_buffer_minutes=daylight_buf_min,
                dem_resolution_label=dem_res_label,
            )
            r_alt.uncertainty_summary = unc
            r_alt.science_eva_plan = sci_plan
            r_alt.mission_clock = m_clock
            r_alt.turnaround = m_clock.get("turnaround")

            cb = r_alt.cost_breakdown or {}
            hazard_idx = (
                float(cb.get("slope_penalty", 0.0))
                + float(cb.get("cross_slope_penalty", 0.0))
                + float(cb.get("roughness_penalty", 0.0))
                + float(cb.get("hazard_penalty", 0.0))
            )
            pareto_inputs.append(
                {
                    "route_id": r_alt.route_id,
                    "label": r_alt.name,
                    "duration_hours": float(m_clock["outbound_leg"]["walking_duration_hours"]),
                    "distance_m": float(r_alt.summary.total_distance_meters or 0.0),
                    "terrain_hazard_score": round(hazard_idx, 2),
                    "uncertainty_exposure_score": float(unc["uncertainty_exposure_score"]),
                    "science_return_score": float(sci_plan["total_science_score"]),
                    "science_return_per_eva_hour": float(sci_plan["science_return_per_eva_hour"]),
                }
            )

        pareto_frontier = evaluate_pareto_frontier(pareto_inputs)
        pareto_by_id = {c["route_id"]: c for c in pareto_frontier.get("candidates", [])}
        for r_alt in routes:
            p_info = pareto_by_id.get(r_alt.route_id)
            if p_info:
                r_alt.is_pareto_optimal = bool(p_info["is_pareto_optimal"])
                r_alt.pareto_archetype = p_info["pareto_archetype"]

        primary_route = routes[0] if routes else None
        if (
            primary_route
            and primary_route.uncertainty_summary
            and primary_route.science_eva_plan
            and primary_route.mission_clock
        ):
            recon_plan = plan_next_best_reconnaissance(
                uncertainty_summary=primary_route.uncertainty_summary,
                coordinates=primary_route.geometry.coordinates,
            )
            stress_suite = evaluate_mission_stress_suite(
                coordinates=primary_route.geometry.coordinates,
                baseline_duration_hours=float(primary_route.mission_clock["total_duration_hours"]),
                baseline_cost=float(primary_route.total_cost),
                max_slope_deg=float(request.constraints.max_slope_deg),
                uncertainty_summary=primary_route.uncertainty_summary,
                science_plan=primary_route.science_eva_plan,
                departure_utc=dep_utc,
                base_speed_m_s=walk_speed,
                max_eva_hours=max_eva_h,
                alternative_routes_count=max(0, len(routes) - 1),
            )
            brief_md = generate_mission_brief_markdown(
                mission_title=f"Jezero Traverse ({request.start.lon:.4f}°E, {request.start.lat:.4f}°N -> {request.destination.lon:.4f}°E, {request.destination.lat:.4f}°N)",
                route_summary=primary_route.summary.model_dump(),
                mission_clock=primary_route.mission_clock,
                uncertainty=primary_route.uncertainty_summary,
                science_plan=primary_route.science_eva_plan,
                pareto=pareto_frontier,
                recon=recon_plan,
                stress_suite=stress_suite,
            )
        else:
            recon_plan = None
            stress_suite = None
            brief_md = None

        return_zone_payload = None
        if return_grid_res is not None:
            return_zone_payload = serialize_time_grid_overlay(
                return_grid_res.time_seconds_grid,
                cropped_meta,
                budget_minutes=max_eva_h * 60.0,
                as_of=dep_utc,
                source_name=f"{dem_src_name} (Backward Dijkstra Return)",
                resolution_m=eff_res_m,
            )
            return_zone_payload["mode"] = return_mode
            return_zone_payload["reachable_fraction"] = return_grid_res.reachable_fraction

        rescue_zone_payload = None
        if rescue_grid_res is not None:
            rescue_zone_payload = serialize_time_grid_overlay(
                rescue_grid_res.time_seconds_grid,
                cropped_meta,
                budget_minutes=rescue_threshold_min,
                as_of=dep_utc,
                source_name=f"{dem_src_name} (Rescue Profile <= {rescue_max_slope_deg:.0f} deg)",
                resolution_m=eff_res_m,
            )
            rescue_zone_payload["reachable_fraction"] = rescue_grid_res.reachable_fraction
            rescue_zone_payload["speed_m_s"] = round(rescue_speed_m_s, 3)
            rescue_zone_payload["max_slope_deg"] = round(rescue_max_slope_deg, 1)
            rescue_zone_payload["threshold_minutes"] = round(rescue_threshold_min, 1)

        # 11. Compute Dual-Radius Envelopes (Rover-Assisted vs On-Foot Walk-Back)
        hab_coord = request.habitat if getattr(request, "habitat", None) is not None else request.start
        dest_coord = request.destination
        walk_emergency_budget_h = min(4.0, max_eva_h * 0.5) if max_eva_h < 7.0 else 3.5

        dual_envelopes, rover_env_grid, walk_env_grid = compute_dual_radius_envelopes(
            elevation=cropped_elev,
            slope_deg=slope_deg,
            traversable_mask=traversable_mask,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
            habitat_node=(hab_row, hab_col),
            meta=cropped_meta,
            habitat_coord=hab_coord,
            dest_coord=dest_coord,
            rover_speed_m_s=rescue_speed_m_s,
            rover_max_slope_deg=rescue_max_slope_deg,
            rover_budget_hours=max_eva_h,
            walk_speed_m_s=walk_speed,
            walk_max_slope_deg=20.0,
            walk_budget_hours=walk_emergency_budget_h,
            as_of=dep_utc,
            dem_src_name=dem_src_name,
            eff_res_m=eff_res_m,
        )

        # 12. Compute Marswalk Survivability, Walk-Back Feasibility & Geofence Evaluation
        is_spe = bool(getattr(request, "is_spe_scenario", False))
        eva_budget = float(getattr(request, "max_eva_hours", 8.0) or 8.0)

        for r in routes:
            r_dist_km = (r.summary.total_distance_meters or 0.0) / 1000.0
            r_max_slope = float(r.summary.max_slope_deg or 0.0)
            r_avg_slope = float(getattr(r.summary, "average_slope_deg", r_max_slope * 0.5) or 0.0)
            r_tri = float(getattr(r.summary, "roughness_tri", 0.35) or 0.35)
            r_dur_h = float(r.summary.estimated_duration_hours or 1.0)

            t_buf = 120.0
            if r.turnaround and isinstance(r.turnaround, dict):
                t_buf = float(r.turnaround.get("safe_turnaround_buffer_min", 120.0) or 120.0)

            mid_coords = None
            route_pts = []
            if r.geometry and hasattr(r.geometry, "coordinates") and r.geometry.coordinates:
                route_pts = r.geometry.coordinates
                mid_idx = len(route_pts) // 2
                mid_coords = (float(route_pts[mid_idx][0]), float(route_pts[mid_idx][1]))

            r.marswalk_survivability = compute_marswalk_survivability(
                distance_km=r_dist_km,
                max_slope_deg=r_max_slope,
                average_slope_deg=r_avg_slope,
                roughness_tri=r_tri,
                eva_duration_hours=r_dur_h,
                turnaround_buffer_min=t_buf,
                thermal_inertia_tiu=385.0,
                is_spe_active=is_spe,
                corridor_midpoint=mid_coords,
                eva_budget_hours=eva_budget,
            )

            # Walk-back return time lookups
            walk_time_s = None
            rover_time_s = None
            if (
                0 <= d_row < walk_env_grid.time_seconds_grid.shape[0]
                and 0 <= d_col < walk_env_grid.time_seconds_grid.shape[1]
            ):
                walk_val = float(walk_env_grid.time_seconds_grid[d_row, d_col])
                if math.isfinite(walk_val):
                    walk_time_s = walk_val
                rov_val = float(rover_env_grid.time_seconds_grid[d_row, d_col])
                if math.isfinite(rov_val):
                    rover_time_s = rov_val

            feasibility, rover_ret_h, ratio = evaluate_on_foot_feasibility(
                route_coords=route_pts,
                route_distance_km=r_dist_km,
                route_max_slope_deg=r_max_slope,
                route_avg_slope_deg=r_avg_slope,
                route_roughness_tri=r_tri,
                walk_speed_m_s=walk_speed,
                walk_time_seconds_from_dest=walk_time_s,
                rover_time_seconds_from_dest=rover_time_s,
                max_permitted_walking_hours=walk_emergency_budget_h,
                eva_budget_hours=eva_budget,
            )

            rf_status = evaluate_rf_line_of_sight(
                habitat_coord=hab_coord,
                route_coords=route_pts,
                max_slope_deg=r_max_slope,
            )

            r.walk_back_assessment = WalkBackAssessment(
                on_foot_feasibility=feasibility,
                rover_assisted_return_hours=rover_ret_h,
                rover_vs_foot_ratio=ratio,
                dual_envelopes=dual_envelopes,
                rf_communication=rf_status,
            )

            # Planetary Protection geofence evaluation
            geofence_assessment = evaluate_route_geofence(route_pts)
            r.planetary_protection_assessment = geofence_assessment

            if not geofence_assessment.human_route_approved:
                r.warnings.append(
                    "PLANETARY PROTECTION RESTRICTION: Route intersects an official COSPAR Category IVc Special Region. Human crew routing is barred."
                )
            for w in geofence_assessment.warnings:
                if w not in r.warnings:
                    r.warnings.append(w)

        return RoutePlanResponse(
            mission_id=mission_id,
            status="success",
            crs=get_mars_crs_info(),
            pilot_region="Jezero Crater, Mars",
            data_mode=active_mode,
            provenance=provenance,
            source_selection=selection_report,
            routes=routes,
            stats=stats,
            limitations=limitations,
            robustness_assessment=robustness_assessment,
            algorithm_comparison=algorithm_comparison_report,
            pareto_frontier=pareto_frontier,
            reconnaissance_plan=recon_plan,
            operational_stress_suite=stress_suite,
            mission_brief_markdown=brief_md,
            return_zone=return_zone_payload,
            rescue_zone=rescue_zone_payload,
            dual_envelopes=dual_envelopes,
            walk_back_assessment=routes[0].walk_back_assessment if routes else None,
            planetary_protection=routes[0].planetary_protection_assessment if routes else None,
            special_regions=get_all_special_regions(),
        )
