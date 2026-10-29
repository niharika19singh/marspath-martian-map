import logging
import math
import time
import uuid
from typing import List, Tuple
from backend.app.core.config import get_settings
from backend.app.core.exceptions import UnreachableDestinationError
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import (
    geo_to_pixel,
    get_mars_crs_info,
    pixel_to_geo,
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
from backend.app.schemas.mission import OptimizationMode, ScienceTarget
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
        total_start_time = time.perf_counter()

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
        all_lons = [request.start.lon, request.destination.lon] + [wp.lon for wp in request.science_waypoints]
        all_lats = [request.start.lat, request.destination.lat] + [wp.lat for wp in request.science_waypoints]
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
            request.start.lon, request.start.lat, cropped_meta.min_lon, cropped_meta.max_lat,
            cropped_meta.deg_per_px_lon, cropped_meta.deg_per_px_lat, pixel_center=True
        )
        d_col, d_row = geo_to_pixel(
            request.destination.lon, request.destination.lat, cropped_meta.min_lon, cropped_meta.max_lat,
            cropped_meta.deg_per_px_lon, cropped_meta.deg_per_px_lat, pixel_center=True
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
        check_cell_traversability(d_col, d_row, traversable_mask, request.destination, "Destination location")

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
        routes: List[RouteAlternative] = []

        # 10. Route Search Execution
        if request.science_waypoints:
            # Multi-leg routing visiting user-supplied waypoints in order
            logger.info("Executing multi-leg route via %d user science waypoints.", len(request.science_waypoints))
            waypoint_coords = [request.start] + request.science_waypoints + [request.destination]
            waypoint_pixels: List[Tuple[int, int]] = []

            for idx, wp in enumerate(request.science_waypoints):
                w_col, w_row = geo_to_pixel(
                    wp.lon, wp.lat, cropped_meta.min_lon, cropped_meta.max_lat,
                    cropped_meta.deg_per_px_lon, cropped_meta.deg_per_px_lat, pixel_center=True
                )
                w_col = max(0, min(w_col, cropped_meta.width - 1))
                w_row = max(0, min(w_row, cropped_meta.height - 1))
                check_cell_traversability(w_col, w_row, traversable_mask, wp, f"Science Waypoint #{idx + 1}")
                waypoint_pixels.append((w_row, w_col))

            all_leg_pixels = [(s_row, s_col)] + waypoint_pixels + [(d_row, d_col)]
            full_path: List[Tuple[int, int]] = []
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
                total_cost=round(leg_total_cost, 2),
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
                graph, (s_row, s_col), (d_row, d_col), max_expansions=request.constraints.max_search_nodes
            )
            total_nodes_expanded += dir_expansions

            # 2. Check candidate science POIs in corridor
            candidate_poi = None
            best_detour_nodes: List[Tuple[int, int]] | None = None
            best_detour_cost = float("inf")

            for poi in science_pois:
                p_col, p_row = geo_to_pixel(
                    poi.coordinate.lon, poi.coordinate.lat, cropped_meta.min_lon, cropped_meta.max_lat,
                    cropped_meta.deg_per_px_lon, cropped_meta.deg_per_px_lat, pixel_center=True
                )
                if 0 <= p_col < cropped_meta.width and 0 <= p_row < cropped_meta.height:
                    if traversable_mask[p_row, p_col]:
                        try:
                            # Evaluate start -> poi -> dest
                            leg1_nodes, leg1_cost, exp1, _ = astar_search(graph, (s_row, s_col), (p_row, p_col))
                            leg2_nodes, leg2_cost, exp2, _ = astar_search(graph, (p_row, p_col), (d_row, d_col))
                            total_nodes_expanded += (exp1 + exp2)
                            detour_cost = leg1_cost + leg2_cost

                            # Accept detour if reasonable cost inflation (<2.2x direct cost)
                            if detour_cost < direct_cost * 2.2 and detour_cost < best_detour_cost:
                                best_detour_cost = detour_cost
                                best_detour_nodes = leg1_nodes + leg2_nodes[1:]
                                candidate_poi = poi
                        except Exception:
                            continue

            if best_detour_nodes and candidate_poi:
                # Add science detour as primary route!
                sum_sci, geom_sci, break_sci, vis_sci, near_sci = reconstruct_route_summary(
                    best_detour_nodes, graph, cropped_meta, request.mode, science_targets=science_pois
                )
                sci_route = RouteAlternative(
                    route_id="route_science_primary",
                    name=f"Science-First Detour via {candidate_poi.name}",
                    mode=request.mode,
                    score_rank=1,
                    total_cost=round(best_detour_cost, 2),
                    cost_breakdown=break_sci,
                    summary=sum_sci,
                    geometry=geom_sci,
                    waypoints_visited=[candidate_poi.coordinate],
                    science_targets_visited=vis_sci,
                    science_targets_nearby=near_sci,
                    warnings=[f"Route deliberately diverts to sample high-priority target '{candidate_poi.name}'."],
                )
                routes.append(sci_route)

                # Add direct path as comparative alternative
                if request.num_alternatives > 1:
                    sum_dir, geom_dir, break_dir, vis_dir, near_dir = reconstruct_route_summary(
                        direct_nodes, graph, cropped_meta, request.mode, science_targets=science_pois
                    )
                    dir_route = RouteAlternative(
                        route_id="route_direct_baseline",
                        name="Direct Balanced Path (No Detour)",
                        mode=request.mode,
                        score_rank=2,
                        total_cost=round(direct_cost, 2),
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

        search_duration = time.perf_counter() - search_start

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

        mission_id = f"mission_{uuid.uuid4().hex[:12]}"

        stats = ComputationStats(
            algorithm_used="A* (with admissible Euclidean heuristic)",
            search_duration_seconds=round(search_duration, 4),
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
