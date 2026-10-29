import time
import uuid
from backend.app.core.config import get_settings
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.geospatial.crs import (
    get_mars_crs_info,
    validate_crs,
)
from backend.app.geospatial.terrain_metrics import compute_physical_pixel_sizes
from backend.app.geospatial.raster_alignment import crop_mission_corridor
from backend.app.geospatial.validation import (
    check_cell_traversability,
    validate_constraints,
    validate_coordinates_in_bounds,
)
from backend.app.routing.alternatives import generate_route_alternatives
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.routes import (
    ComputationStats,
    RoutePlanRequest,
    RoutePlanResponse,
)
from backend.app.services.risk_service import RiskService


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

        # 5. Crop corridor around start and dest
        cropped_elev, cropped_meta, (s_col, s_row), (d_col, d_row) = crop_mission_corridor(
            raster=master_raster,
            start=request.start,
            dest=request.destination,
            padding_meters=2500.0,
            max_cells=self.settings.MAX_GRID_CELLS,
        )

        # 6. Physical pixel sizes in meters
        center_lat = (request.start.lat + request.destination.lat) / 2.0
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

        # 10. Generate route alternatives
        science_pois = self.provider.get_science_targets()
        search_start = time.perf_counter()

        routes = generate_route_alternatives(
            graph=graph,
            meta=cropped_meta,
            start_px=(s_row, s_col),
            dest_px=(d_row, d_col),
            requested_mode=request.mode,
            num_alternatives=request.num_alternatives,
            science_targets=science_pois,
        )

        search_duration = time.perf_counter() - search_start

        # 11. Compile provenance & limitations
        is_syn = self.provider.is_synthetic()
        provenance = self.provider.get_provenance()

        limitations = [
            f"Elevation resolution ({round(dy_meters, 1)}m) does not resolve sub-pixel rock or crevasse hazards.",
            "Slope and energy profiles are computed for uncrewed rovers / astronaut EVA planning models.",
        ]
        if is_syn:
            limitations.append(
                "Operating on deterministic synthetic test fixture; routing results must NOT be used for flight operations."
            )

        mission_id = f"mission_{uuid.uuid4().hex[:12]}"

        stats = ComputationStats(
            algorithm_used="A* (with admissible Euclidean heuristic)",
            search_duration_seconds=round(search_duration, 4),
            nodes_expanded=len(routes[0].geometry.coordinates) * 4,  # Estimated nodes
            grid_rows=cropped_meta.height,
            grid_cols=cropped_meta.width,
            cell_size_meters=round((dx_meters + dy_meters) / 2.0, 1),
        )

        return RoutePlanResponse(
            mission_id=mission_id,
            status="success",
            crs=get_mars_crs_info(),
            pilot_region="Jezero Crater, Mars",
            data_mode="synthetic_test_fixture" if is_syn else "real",
            provenance=provenance,
            routes=routes,
            stats=stats,
            limitations=limitations,
        )
