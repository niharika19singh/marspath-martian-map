import logging
import math

import numpy as np

from backend.app.core.exceptions import ComputationalBoundExceededError, UnreachableDestinationError
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    meters_per_degree_lon,
    pixel_to_geo,
)
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.astar import astar_search
from backend.app.routing.cost_model import calculate_edge_cost
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.mission import OptimizationMode, ScienceTarget
from backend.app.schemas.routes import GeoJSONGeometry, RouteAlternative, RouteSummary

logger = logging.getLogger("marspath.routing.alternatives")


def reconstruct_route_summary(
    path_nodes: list[tuple[int, int]],
    graph: TerrainGridGraph,
    meta: RasterMetadata,
    mode: OptimizationMode,
    penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] | None = None,
    science_targets: list[ScienceTarget] | None = None,
) -> tuple[RouteSummary, GeoJSONGeometry, dict[str, float], list[str], list[str]]:
    """
    Computes detailed summary metrics, GeoJSON geometry, exact cost breakdown,
    and visited/nearby science targets from an ordered sequence of grid nodes.
    Uses the exact active mode cost model for score reconciliation.
    """
    if not path_nodes:
        raise ValueError("Cannot summarize empty path.")

    total_dist = 0.0
    elev_gain = 0.0
    elev_loss = 0.0
    slopes: list[float] = []
    roughnesses: list[float] = []
    elevations: list[float] = []
    geojson_coords: list[list[float]] = []

    cost_base = 0.0
    cost_slope = 0.0
    cost_rough = 0.0
    cost_hazard = 0.0
    cost_extra = 0.0

    total_duration_seconds = 0.0

    prev_r, prev_c = path_nodes[0]
    z_prev = float(graph.elevation[prev_r, prev_c])
    elevations.append(z_prev)

    lon_start, lat_start = pixel_to_geo(
        prev_c,
        prev_r,
        meta.min_lon,
        meta.max_lat,
        meta.deg_per_px_lon,
        meta.deg_per_px_lat,
        pixel_center=True,
    )
    geojson_coords.append([round(lon_start, 6), round(lat_start, 6), round(z_prev, 2)])

    for curr_r, curr_c in path_nodes[1:]:
        z_curr = float(graph.elevation[curr_r, curr_c])
        elevations.append(z_curr)

        dr = curr_r - prev_r
        dc = curr_c - prev_c

        d2d = (
            graph.dist_diag
            if (dr != 0 and dc != 0)
            else (graph.dist_orth_y if dr != 0 else graph.dist_orth_x)
        )
        dz = z_curr - z_prev
        d3d = math.sqrt(d2d**2 + dz**2)
        total_dist += d3d

        if dz > 0:
            elev_gain += dz
        else:
            elev_loss += abs(dz)

        slope = float(graph.slope_deg[curr_r, curr_c])
        slopes.append(slope)
        rough = float(graph.roughness[curr_r, curr_c])
        roughnesses.append(rough)

        extra_pen = 0.0
        if penalized_edges and ((prev_r, prev_c), (curr_r, curr_c)) in penalized_edges:
            extra_pen = penalized_edges[((prev_r, prev_c), (curr_r, curr_c))]

        # Reconcile exact edge cost using active cost model
        _, step_breakdown = calculate_edge_cost(
            distance_3d=d3d,
            slope_deg=slope,
            roughness=rough,
            delta_z=dz,
            mode=mode,
            is_nodata=False,
            extra_penalty=extra_pen,
        )

        cost_base += step_breakdown["base_distance_cost"]
        cost_slope += step_breakdown["slope_penalty"]
        cost_rough += step_breakdown["roughness_penalty"]
        cost_hazard += step_breakdown["hazard_penalty"]
        cost_extra += step_breakdown["extra_penalty"]

        # Motion profile: Rover nominal 0.15 m/s with slope-dependent derating
        speed_mps = 0.15 * max(0.2, 1.0 - (slope / 30.0))
        step_time_sec = d3d / speed_mps
        total_duration_seconds += step_time_sec

        lon, lat = pixel_to_geo(
            curr_c,
            curr_r,
            meta.min_lon,
            meta.max_lat,
            meta.deg_per_px_lon,
            meta.deg_per_px_lat,
            pixel_center=True,
        )
        geojson_coords.append([round(lon, 6), round(lat, 6), round(z_curr, 2)])

        prev_r, prev_c = curr_r, curr_c
        z_prev = z_curr

    avg_slope = float(np.mean(slopes)) if slopes else 0.0
    max_slope = float(np.max(slopes)) if slopes else 0.0
    avg_rough = float(np.mean(roughnesses)) if roughnesses else 0.0

    duration_hrs = total_duration_seconds / 3600.0
    energy_idx = (total_dist * 0.001) + (elev_gain * 0.02)

    # Distinguish science targets visited vs in proximity using Mars metric distance
    visited_target_ids: list[str] = []
    nearby_target_ids: list[str] = []
    science_score = 0.0

    if science_targets:
        for target in science_targets:
            t_lon, t_lat = target.coordinate.lon, target.coordinate.lat
            m_lon = meters_per_degree_lon(t_lat)
            m_lat = METERS_PER_DEGREE_LATITUDE

            # Compute min distance to any point along route geometry
            min_dist_to_route = float("inf")
            for p_lon, p_lat, _ in geojson_coords:
                dx = (p_lon - t_lon) * m_lon
                dy = (p_lat - t_lat) * m_lat
                d = math.sqrt(dx**2 + dy**2)
                if d < min_dist_to_route:
                    min_dist_to_route = d

            if min_dist_to_route <= 100.0:  # Direct encounter / visited (<100m)
                visited_target_ids.append(target.id)
                science_score += target.scientific_priority * 15.0
            elif min_dist_to_route <= 500.0:  # Remote sensor proximity (<500m)
                nearby_target_ids.append(target.id)
                science_score += target.scientific_priority * 5.0

    summary = RouteSummary(
        total_distance_meters=round(total_dist, 1),
        elevation_gain_meters=round(elev_gain, 1),
        elevation_loss_meters=round(elev_loss, 1),
        min_elevation_meters=round(float(min(elevations)), 1),
        max_elevation_meters=round(float(max(elevations)), 1),
        max_slope_deg=round(max_slope, 2),
        average_slope_deg=round(avg_slope, 2),
        average_roughness=round(avg_rough, 3),
        data_coverage_fraction=1.0,
        estimated_duration_hours=round(duration_hrs, 2),
        motion_profile="rover_slope_derated_0.15mps",
        energy_index=round(energy_idx, 2),
        science_score=round(science_score, 1),
    )

    geometry = GeoJSONGeometry(type="LineString", coordinates=geojson_coords)

    breakdown = {
        "base_distance_cost": round(cost_base, 2),
        "slope_penalty": round(cost_slope, 2),
        "roughness_penalty": round(cost_rough, 2),
        "hazard_penalty": round(cost_hazard, 2),
        "extra_penalty": round(cost_extra, 2),
    }

    return summary, geometry, breakdown, visited_target_ids, nearby_target_ids


def generate_route_alternatives(
    graph: TerrainGridGraph,
    meta: RasterMetadata,
    start_px: tuple[int, int],
    dest_px: tuple[int, int],
    requested_mode: OptimizationMode,
    num_alternatives: int = 1,
    science_targets: list[ScienceTarget] | None = None,
) -> tuple[list[RouteAlternative], int]:
    """
    Computes 1 to 3 distinct candidate routes.
    Route 1: Primary route for the requested mode.
    Route 2: Backup corridor generated by penalizing primary route edges.
    Route 3: Safety-first or Science-oriented corridor.

    Returns:
        (routes_list, total_nodes_expanded)
    """
    results: list[RouteAlternative] = []
    total_nodes_expanded = 0

    # 1. Primary route
    primary_nodes, primary_cost, nodes_1, _ = astar_search(graph, start_px, dest_px)
    total_nodes_expanded += nodes_1

    summary_1, geom_1, breakdown_1, visited_1, nearby_1 = reconstruct_route_summary(
        primary_nodes, graph, meta, requested_mode, science_targets=science_targets
    )

    results.append(
        RouteAlternative(
            route_id="route_primary_opt",
            name=f"Primary Route ({requested_mode.value.replace('_', ' ').title()})",
            mode=requested_mode,
            score_rank=1,
            total_cost=round(sum(breakdown_1.values()), 2),
            cost_breakdown=breakdown_1,
            summary=summary_1,
            geometry=geom_1,
            science_targets_visited=visited_1,
            science_targets_nearby=nearby_1,
            warnings=[],
        )
    )

    if num_alternatives <= 1:
        return results, total_nodes_expanded

    # 2. Alternative route: Penalize edges of primary path to find alternative corridor
    penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] = {}
    for i in range(len(primary_nodes) - 1):
        u, v = primary_nodes[i], primary_nodes[i + 1]
        penalized_edges[(u, v)] = 1500.0  # +1500m cost penalty to divert
        penalized_edges[(v, u)] = 1500.0

    try:
        alt_nodes, alt_cost, nodes_2, _ = astar_search(
            graph, start_px, dest_px, penalized_edges=penalized_edges
        )
        total_nodes_expanded += nodes_2

        # Check if alternative is genuinely distinct
        shared_nodes = set(primary_nodes).intersection(set(alt_nodes))
        overlap_pct = len(shared_nodes) / max(len(primary_nodes), 1)

        if overlap_pct < 0.85:
            summary_2, geom_2, breakdown_2, visited_2, nearby_2 = reconstruct_route_summary(
                alt_nodes,
                graph,
                meta,
                requested_mode,
                penalized_edges=penalized_edges,
                science_targets=science_targets,
            )
            results.append(
                RouteAlternative(
                    route_id="route_alt_corridor",
                    name="Alternative Diverse Corridor",
                    mode=requested_mode,
                    score_rank=2,
                    total_cost=round(sum(breakdown_2.values()), 2),
                    cost_breakdown=breakdown_2,
                    summary=summary_2,
                    geometry=geom_2,
                    science_targets_visited=visited_2,
                    science_targets_nearby=nearby_2,
                    warnings=[
                        "Alternative corridor avoids high-traffic bottlenecks of primary route."
                    ],
                )
            )
        else:
            logger.info(
                "Secondary alternative discarded: overlap (%.1f%%) exceeds 85%% threshold.",
                overlap_pct * 100.0,
            )
            results[0].warnings.append(
                f"Secondary corridor search suppressed: generated path overlapped {int(overlap_pct * 100)}% with primary route."
            )
    except (UnreachableDestinationError, ComputationalBoundExceededError) as e:
        logger.info("Secondary alternative search failed: %s", e)
        results[0].warnings.append(f"Secondary corridor search unviable: {e.message}")
    except Exception as e:
        logger.warning("Unexpected error during secondary alternative search: %s", e)
        results[0].warnings.append(
            "Secondary corridor search encountered an unexpected traversal barrier."
        )

    # 3. Third alternative if requested and mode was not safety_first
    if num_alternatives >= 3 and len(results) < 3:
        if requested_mode != OptimizationMode.SAFETY_FIRST:
            alt_mode = OptimizationMode.SAFETY_FIRST
            graph_safety = TerrainGridGraph(
                elevation=graph.elevation,
                slope_deg=graph.slope_deg,
                roughness=graph.roughness,
                traversable_mask=graph.traversable,
                dx_meters=graph.dx,
                dy_meters=graph.dy,
                mode=alt_mode,
            )
            try:
                safety_nodes, safety_cost, nodes_3, _ = astar_search(
                    graph_safety, start_px, dest_px
                )
                total_nodes_expanded += nodes_3

                summary_3, geom_3, breakdown_3, visited_3, nearby_3 = reconstruct_route_summary(
                    safety_nodes, graph_safety, meta, alt_mode, science_targets=science_targets
                )
                results.append(
                    RouteAlternative(
                        route_id="route_safety_backup",
                        name="Conservative Safety-First Corridor",
                        mode=alt_mode,
                        score_rank=len(results) + 1,
                        total_cost=round(sum(breakdown_3.values()), 2),
                        cost_breakdown=breakdown_3,
                        summary=summary_3,
                        geometry=geom_3,
                        science_targets_visited=visited_3,
                        science_targets_nearby=nearby_3,
                        warnings=[
                            "Strict 14° slope constraint enforced; prioritizes minimum roughness."
                        ],
                    )
                )
            except (UnreachableDestinationError, ComputationalBoundExceededError) as e:
                logger.info("Safety-first alternative search failed: %s", e)
                results[0].warnings.append(f"Safety-first alternative unviable: {e.message}")
            except Exception as e:
                logger.warning("Unexpected error during safety alternative search: %s", e)

    return results, total_nodes_expanded
