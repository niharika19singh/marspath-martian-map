import logging
import time
import uuid

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    RoutingTimeoutError,
    UnreachableDestinationError,
)
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.hirise import (
    HiRISERasterProvider,
    get_shared_hirise_provider,
)
from backend.app.data.providers.mola_hrsc import (
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
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import (
    ComputationStats,
    RouteAlternative,
    RoutePlanRequest,
    RoutePlanResponse,
)
from backend.app.services.evidence_service import EvidenceService
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

        # 3. Early bounds validation & MAX_SEARCH_RADIUS_METERS guard
        # Validate that start, destination, and all waypoints lie within pilot region bounds before any expensive operations.
        regional_master_meta = self.provider.get_dem_raster().metadata
        validate_coordinates_in_bounds(request.start, regional_master_meta, "Start point")
        validate_coordinates_in_bounds(request.destination, regional_master_meta, "Destination point")
        for idx, wp in enumerate(request.science_waypoints or []):
            validate_coordinates_in_bounds(wp, regional_master_meta, f"Science Waypoint #{idx + 1}")

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
        selection_outcome = TerrainSourceSelector.select_and_prepare_corridor(
            start=request.start,
            destination=request.destination,
            waypoints=request.science_waypoints,
            regional_provider=self.provider,
            hirise_provider=self.hirise_provider,
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
        check_cell_traversability(
            d_col, d_row, traversable_mask, request.destination, "Destination location"
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
                check_cell_traversability(
                    w_col, w_row, traversable_mask, wp, f"Science Waypoint #{idx + 1}"
                )
                waypoint_pixels.append((w_row, w_col))

            all_leg_pixels = [(s_row, s_col)] + waypoint_pixels + [(d_row, d_col)]
            full_path: list[tuple[int, int]] = []
            leg_total_cost = 0.0

            for leg_idx in range(len(all_leg_pixels) - 1):
                p_from = all_leg_pixels[leg_idx]
                p_to = all_leg_pixels[leg_idx + 1]
                leg_nodes, leg_cost, leg_expansions, _ = astar_search(
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
                )
                total_nodes_expanded += alt_nodes
                for a in alts:
                    a.score_rank = len(routes) + 1
                    routes.append(a)

        elif request.mode == OptimizationMode.SCIENCE_FIRST:
            # Autonomous science detour evaluation
            logger.info("Evaluating science-first mode candidate detours.")
            # 1. Compute direct route
            direct_nodes, direct_cost, dir_expansions, _ = astar_search(
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
                    leg1_nodes, leg1_cost, exp1, _ = astar_search(
                        graph,
                        (s_row, s_col),
                        (p_row, p_col),
                        max_expansions=max_exp,
                        timeout_seconds=timeout_seconds,
                        deadline=deadline,
                        overall_start_time=search_start,
                    )
                    leg2_nodes, leg2_cost, exp2, _ = astar_search(
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
                        rejected_candidates.append({
                            "poi": poi.name,
                            "reason": f"Detour ratio {detour_ratio:.2f}x exceeds maximum allowance (2.50x)"
                        })
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

        stats = ComputationStats(
            algorithm_used="A* (with admissible Euclidean heuristic)",
            search_duration_seconds=round(time.perf_counter() - search_start, 4),
            nodes_expanded=total_nodes_expanded,  # Real measured count of expanded states
            grid_rows=cropped_meta.height,
            grid_cols=cropped_meta.width,
            cell_size_meters=round((dx_meters + dy_meters) / 2.0, 2),
        )

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
        )
