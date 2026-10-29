import logging
import time
import uuid

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    UnreachableDestinationError,
)
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import (
    geo_to_pixel,
    get_mars_crs_info,
    validate_crs,
)
from backend.app.geospatial.raster_alignment import crop_mission_corridor
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
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import (
    ComputationStats,
    RouteAlternative,
    RoutePlanRequest,
    RoutePlanResponse,
)
from backend.app.services.risk_service import RiskService

logger = logging.getLogger("marspath.services.route_service")


class RouteService:
    def __init__(self, provider: BaseRasterProvider | None = None):
        self.settings = get_settings()
        self.provider = provider or MOLAHRSCRasterProvider()

    def plan_route(self, request: RoutePlanRequest) -> RoutePlanResponse:
        # 1. Validate CRS
        validate_crs(request.crs_identifier)

        # 2. Validate Constraints
        validate_constraints(request.constraints)

        # 3. Retrieve Raster
        master_raster = self.provider.get_dem_raster()
        meta = master_raster.metadata

        # 4. Validate Coordinates in Master Bounds
        validate_coordinates_in_bounds(request.start, meta, "Start point")
        validate_coordinates_in_bounds(request.destination, meta, "Destination point")
        for idx, wp in enumerate(request.science_waypoints):
            validate_coordinates_in_bounds(wp, meta, f"Science Waypoint #{idx + 1}")

        # 5. Crop corridor around all mission waypoints (start, destination, plus intermediate waypoints)
        # Determine bounding envelope of all query coordinates
        all_lons = [request.start.lon, request.destination.lon] + [
            wp.lon for wp in request.science_waypoints
        ]
        all_lats = [request.start.lat, request.destination.lat] + [
            wp.lat for wp in request.science_waypoints
        ]
        envelope_start = MarsCoordinate(lon=min(all_lons), lat=min(all_lats))
        envelope_dest = MarsCoordinate(lon=max(all_lons), lat=max(all_lats))

        cropped_elev, cropped_meta, _, _ = crop_mission_corridor(
            raster=master_raster,
            start=envelope_start,
            dest=envelope_dest,
            padding_meters=3500.0,
            max_cells=self.settings.MAX_GRID_CELLS,
        )

        # Convert coordinates to cropped subgrid pixel indices
        s_col, s_row = geo_to_pixel(
            request.start.lon,
            request.start.lat,
            cropped_meta.min_lon,
            cropped_meta.max_lat,
            cropped_meta.deg_per_px_lon,
            cropped_meta.deg_per_px_lat,
            pixel_center=True,
        )
        d_col, d_row = geo_to_pixel(
            request.destination.lon,
            request.destination.lat,
            cropped_meta.min_lon,
            cropped_meta.max_lat,
            cropped_meta.deg_per_px_lon,
            cropped_meta.deg_per_px_lat,
            pixel_center=True,
        )
        s_col = max(0, min(s_col, cropped_meta.width - 1))
        s_row = max(0, min(s_row, cropped_meta.height - 1))
        d_col = max(0, min(d_col, cropped_meta.width - 1))
        d_row = max(0, min(d_row, cropped_meta.height - 1))

        # 6. Physical pixel sizes in meters
        center_lat = (envelope_start.lat + envelope_dest.lat) / 2.0
        dx_meters, dy_meters = compute_physical_pixel_sizes(
            center_lat_deg=center_lat,
            deg_per_px_lon=cropped_meta.deg_per_px_lon,
            deg_per_px_lat=cropped_meta.deg_per_px_lat,
        )

        # 7. Evaluate risk: Slope, Roughness, Traversability mask
        slope_deg, roughness, traversable_mask = RiskService.evaluate_terrain_risk(
            elevation=cropped_elev,
            dx_meters=dx_meters,
            dy_meters=dy_meters,
            constraints=request.constraints,
            mode=request.mode,
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
        search_start = time.perf_counter()
        total_nodes_expanded = 0
        routes: list[RouteAlternative] = []

        # 10. Route Search Execution
        if request.science_waypoints:
            # Multi-leg routing visiting user-supplied waypoints in order
            logger.info(
                "Executing multi-leg route via %d user science waypoints.",
                len(request.science_waypoints),
            )
            waypoint_pixels: list[tuple[int, int]] = []

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
                    graph, p_from, p_to, max_expansions=request.constraints.max_search_nodes
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
                    # Evaluate start -> poi -> dest honoring configured max expansions
                    leg1_nodes, leg1_cost, exp1, _ = astar_search(
                        graph, (s_row, s_col), (p_row, p_col), max_expansions=max_exp
                    )
                    leg2_nodes, leg2_cost, exp2, _ = astar_search(
                        graph, (p_row, p_col), (d_row, d_col), max_expansions=max_exp
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
            )
            total_nodes_expanded += alt_nodes

        # 11. Compile provenance & limitations
        is_syn = self.provider.is_synthetic()
        provenance = self.provider.get_provenance()
        active_mode = provenance.get("data_mode", "synthetic_test_fixture" if is_syn else "real")

        limitations = [
            f"Elevation resolution ({round(dy_meters, 1)}m) does not resolve sub-pixel rock or crevasse hazards.",
            "Traversability represents automated optimization corridors, not certified human EVA safety guarantees.",
        ]
        if is_syn:
            if active_mode == "synthetic_fallback":
                limitations.append(
                    f"Warning: Real NASA DEM was requested but failed or was missing; operating on synthetic test model ({provenance.get('fallback_reason', '')})."
                )
            else:
                limitations.append(
                    "Operating on deterministic synthetic test fixture for Jezero Crater. Real NASA DEM is not loaded."
                )
        elif provenance.get("real_data_validation_status") == "valid_numeric_raster_unverified_source":
            limitations.append(
                "Operating on local numeric terrain raster. Official NASA/ESA/USGS provenance is unverified."
            )

        mission_id = f"mission_{uuid.uuid4().hex[:12]}"

        stats = ComputationStats(
            algorithm_used="A* (with admissible Euclidean heuristic)",
            search_duration_seconds=round(time.perf_counter() - search_start, 4),
            nodes_expanded=total_nodes_expanded,  # Real measured count of expanded states
            grid_rows=cropped_meta.height,
            grid_cols=cropped_meta.width,
            cell_size_meters=round((dx_meters + dy_meters) / 2.0, 1),
        )

        return RoutePlanResponse(
            mission_id=mission_id,
            status="success",
            crs=get_mars_crs_info(),
            pilot_region="Jezero Crater, Mars",
            data_mode=active_mode,
            provenance=provenance,
            routes=routes,
            stats=stats,
            limitations=limitations,
        )
