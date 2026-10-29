import math
from typing import Dict, List, Optional, Tuple
import numpy as np
from backend.app.geospatial.crs import pixel_to_geo
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.astar import astar_search
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, ScienceTarget
from backend.app.schemas.routes import GeoJSONGeometry, RouteAlternative, RouteSummary


def reconstruct_route_summary(
    path_nodes: List[Tuple[int, int]],
    graph: TerrainGridGraph,
    meta: RasterMetadata,
    mode: OptimizationMode,
    science_targets: Optional[List[ScienceTarget]] = None,
) -> Tuple[RouteSummary, GeoJSONGeometry, Dict[str, float]]:
    """
    Computes detailed summary metrics, GeoJSON geometry, and cost breakdown
    from an ordered sequence of grid nodes.
    """
    if not path_nodes:
        raise ValueError("Cannot summarize empty path.")

    total_dist = 0.0
    elev_gain = 0.0
    elev_loss = 0.0
    slopes: List[float] = []
    roughnesses: List[float] = []
    elevations: List[float] = []
    geojson_coords: List[List[float]] = []

    cost_base = 0.0
    cost_slope = 0.0
    cost_rough = 0.0
    cost_hazard = 0.0

    prev_r, prev_c = path_nodes[0]
    z_prev = float(graph.elevation[prev_r, prev_c])
    elevations.append(z_prev)

    lon_start, lat_start = pixel_to_geo(prev_c, prev_r, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat)
    geojson_coords.append([round(lon_start, 6), round(lat_start, 6), round(z_prev, 2)])

    for curr_r, curr_c in path_nodes[1:]:
        z_curr = float(graph.elevation[curr_r, curr_c])
        elevations.append(z_curr)

        dr = curr_r - prev_r
        dc = curr_c - prev_c

        d2d = graph.dist_diag if (dr != 0 and dc != 0) else (graph.dist_orth_y if dr != 0 else graph.dist_orth_x)
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

        # Cost breakdown
        cost_base += d3d
        norm_slope = slope / 20.0
        cost_slope += d3d * (norm_slope**1.5)
        cost_rough += d3d * rough

        lon, lat = pixel_to_geo(curr_c, curr_r, meta.min_lon, meta.max_lat, meta.deg_per_px_lon, meta.deg_per_px_lat)
        geojson_coords.append([round(lon, 6), round(lat, 6), round(z_curr, 2)])

        prev_r, prev_c = curr_r, curr_c
        z_prev = z_curr

    avg_slope = float(np.mean(slopes)) if slopes else 0.0
    max_slope = float(np.max(slopes)) if slopes else 0.0
    avg_rough = float(np.mean(roughnesses)) if roughnesses else 0.0

    # Rover speed: 0.15 m/s (~0.54 km/h nominal)
    duration_hrs = (total_dist / 0.15) / 3600.0

    # Energy index based on distance and positive elevation gain
    energy_idx = (total_dist * 0.001) + (elev_gain * 0.02)

    # Check science proximity
    science_score = 0.0
    visited_pois = []
    if science_targets:
        for target in science_targets:
            # Check min distance to any point along route
            for p_lon, p_lat, _ in geojson_coords:
                d_target = math.sqrt(((p_lon - target.coordinate.lon) * 56250.0) ** 2 + ((p_lat - target.coordinate.lat) * 59274.0) ** 2)
                if d_target < 250.0:  # Within 250m science observation zone
                    science_score += target.scientific_priority * 10.0
                    visited_pois.append(target)
                    break

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
        energy_index=round(energy_idx, 2),
        science_score=round(science_score, 1),
    )

    geometry = GeoJSONGeometry(type="LineString", coordinates=geojson_coords)

    breakdown = {
        "base_distance_cost": round(cost_base, 1),
        "slope_penalty": round(cost_slope, 1),
        "roughness_penalty": round(cost_rough, 1),
        "hazard_penalty": round(cost_hazard, 1),
    }

    return summary, geometry, breakdown


def generate_route_alternatives(
    graph: TerrainGridGraph,
    meta: RasterMetadata,
    start_px: Tuple[int, int],
    dest_px: Tuple[int, int],
    requested_mode: OptimizationMode,
    num_alternatives: int = 1,
    science_targets: Optional[List[ScienceTarget]] = None,
) -> List[RouteAlternative]:
    """
    Computes 1 to 3 distinct candidate routes.
    Route 1: Optimal route using requested mode.
    Route 2: Backup corridor generated by penalizing primary route edges.
    Route 3: Safety-first or Science-oriented corridor.
    """
    results: List[RouteAlternative] = []

    # 1. Primary route
    primary_nodes, primary_cost, _, _ = astar_search(graph, start_px, dest_px)
    summary_1, geom_1, breakdown_1 = reconstruct_route_summary(primary_nodes, graph, meta, requested_mode, science_targets)

    results.append(
        RouteAlternative(
            route_id="route_primary_opt",
            name=f"Primary Route ({requested_mode.value.replace('_', ' ').title()})",
            mode=requested_mode,
            score_rank=1,
            total_cost=round(primary_cost, 2),
            cost_breakdown=breakdown_1,
            summary=summary_1,
            geometry=geom_1,
            warnings=[],
        )
    )

    if num_alternatives <= 1:
        return results

    # 2. Alternative route: Penalize edges of primary path to find alternative corridor
    penalized_edges: Dict[Tuple[Tuple[int, int], Tuple[int, int]], float] = {}
    for i in range(len(primary_nodes) - 1):
        u, v = primary_nodes[i], primary_nodes[i + 1]
        penalized_edges[(u, v)] = 1500.0  # +1500m cost penalty to divert
        penalized_edges[(v, u)] = 1500.0

    try:
        alt_nodes, alt_cost, _, _ = astar_search(graph, start_px, dest_px, penalized_edges=penalized_edges)
        # Check if alternative is actually distinct
        shared_nodes = set(primary_nodes).intersection(set(alt_nodes))
        overlap_pct = len(shared_nodes) / max(len(primary_nodes), 1)

        if overlap_pct < 0.85:
            summary_2, geom_2, breakdown_2 = reconstruct_route_summary(alt_nodes, graph, meta, requested_mode, science_targets)
            results.append(
                RouteAlternative(
                    route_id="route_alt_corridor",
                    name="Alternative Diverse Corridor",
                    mode=requested_mode,
                    score_rank=2,
                    total_cost=round(alt_cost, 2),
                    cost_breakdown=breakdown_2,
                    summary=summary_2,
                    geometry=geom_2,
                    warnings=["Alternative corridor avoids high-traffic bottlenecks of primary route."],
                )
            )
    except Exception:
        pass  # If no distinct corridor exists, return single route as instructed

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
                safety_nodes, safety_cost, _, _ = astar_search(graph_safety, start_px, dest_px)
                summary_3, geom_3, breakdown_3 = reconstruct_route_summary(safety_nodes, graph_safety, meta, alt_mode, science_targets)
                results.append(
                    RouteAlternative(
                        route_id="route_safety_backup",
                        name="Conservative Safety-First Corridor",
                        mode=alt_mode,
                        score_rank=len(results) + 1,
                        total_cost=round(safety_cost, 2),
                        cost_breakdown=breakdown_3,
                        summary=summary_3,
                        geometry=geom_3,
                        warnings=["Strict 14° slope constraint enforced; prioritizes minimum roughness."],
                    )
                )
            except Exception:
                pass

    return results
