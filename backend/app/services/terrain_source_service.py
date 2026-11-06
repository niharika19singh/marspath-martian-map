import logging
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.app.core.config import get_settings
from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
)
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.hirise import HiRISERasterProvider
from backend.app.geospatial.crs import (
    METERS_PER_DEGREE_LATITUDE,
    geo_to_pixel,
    haversine_distance_mars,
    meters_per_degree_lon,
    pixel_to_geo,
)
from backend.app.geospatial.raster_alignment import crop_mission_corridor
from backend.app.geospatial.raster_loader import (
    HAS_PYPROJ,
    HAS_RASTERIO,
    RasterData,
    RasterMetadata,
    rasterio,
)
from backend.app.geospatial.terrain_metrics import (
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.geospatial.validation import validate_coordinates_in_bounds
from backend.app.schemas.coordinates import BoundingBox, MarsCoordinate
from backend.app.schemas.routes import TerrainSourceSelectionReport

logger = logging.getLogger("marspath.terrain_source_service")

AGGREGATION_METHOD_NAME = "mean_elevation_strict_nodata_max_subgrid_slope_roughness"


@dataclass
class CorridorSelectionOutcome:
    """
    Encapsulates the selected elevation source, cropped/aggregated corridor grid,
    endpoint pixel coordinates, provenance dictionary, selection report, and
    optional fine-scale hazard floors when block aggregation was applied.
    """

    selected_provider: BaseRasterProvider
    master_raster: RasterData
    corridor_elevation: np.ndarray
    corridor_metadata: RasterMetadata
    start_pixel: tuple[int, int]
    dest_pixel: tuple[int, int]
    provenance: dict[str, Any]
    selection_report: TerrainSourceSelectionReport
    native_resolution_x_meters: float
    native_resolution_y_meters: float
    subgrid_max_slope_deg: np.ndarray | None = None
    subgrid_max_roughness: np.ndarray | None = None


def aggregate_corridor_hazard_preserving(
    native_elev: np.ndarray,
    native_meta: RasterMetadata,
    factor: int,
) -> tuple[np.ndarray, RasterMetadata, np.ndarray, np.ndarray]:
    """
    Aggregates a native high-resolution elevation corridor by an integer block factor k >= 2
    while strictly preserving NoData boundaries and fine-scale slope/roughness hazards.

    Rules:
    1. Native slope (degrees) and native roughness (normalized TRI) are computed on the
       unreduced native resolution grid BEFORE block reduction.
    2. Each output cell represents a disjoint k x k block of native pixels.
    3. Strict NoData propagation: if ANY pixel in a k x k block is NoData/NaN, the output
       block elevation is set to NaN (NEVER 0.0).
    4. For fully valid blocks, output elevation is the arithmetic mean of the k x k block,
       preserving macroscopic elevation differences across step distances k*dx, k*dy.
    5. Fine-scale hazard preservation: for each valid k x k block, the maximum native slope
       and maximum native roughness inside the block are recorded in `subgrid_max_slope_deg`
       and `subgrid_max_roughness` (or NaN if any cell in the block has NaN slope/roughness).
    """
    if factor <= 1:
        nodata_mask = np.isnan(native_elev) | (native_elev < -9000.0) | (native_elev > 1e30)
        native_slope = compute_slope_degrees(
            native_elev,
            native_meta.meters_per_px_x,
            native_meta.meters_per_px_y,
            nodata_mask=nodata_mask,
        )
        native_rough = compute_roughness_index(native_elev, kernel_size=3, nodata_mask=nodata_mask)
        return native_elev.copy(), native_meta, native_slope, native_rough

    h_nat, w_nat = native_elev.shape
    agg_h = h_nat // factor
    agg_w = w_nat // factor
    if agg_h < 2 or agg_w < 2:
        raise ValueError(
            f"Cannot aggregate {h_nat}x{w_nat} grid by factor {factor}: resulting {agg_h}x{agg_w} grid is too small."
        )

    trim_h = agg_h * factor
    trim_w = agg_w * factor

    elev_work = native_elev[:trim_h, :trim_w].astype(np.float64).copy()
    nodata_mask = np.isnan(elev_work) | (elev_work < -9000.0) | (elev_work > 1e30)
    if native_meta.nodata_value is not None:
        nodata_mask = nodata_mask | np.isclose(elev_work, native_meta.nodata_value, atol=1e-3)
    elev_work[nodata_mask] = np.nan

    # Compute fine-scale slope and roughness on the native grid BEFORE aggregation
    native_slope = compute_slope_degrees(
        elev_work,
        native_meta.meters_per_px_x,
        native_meta.meters_per_px_y,
        nodata_mask=nodata_mask,
    )
    native_rough = compute_roughness_index(elev_work, kernel_size=3, nodata_mask=nodata_mask)

    # Reshape into (agg_h, factor, agg_w, factor)
    elev_blocks = elev_work.reshape(agg_h, factor, agg_w, factor)
    nodata_blocks = nodata_mask.reshape(agg_h, factor, agg_w, factor)
    slope_blocks = native_slope.reshape(agg_h, factor, agg_w, factor)
    rough_blocks = native_rough.reshape(agg_h, factor, agg_w, factor)

    # Strict NoData rule: any invalid pixel in the k x k block makes the aggregated cell NaN
    block_has_nodata = np.any(nodata_blocks, axis=(1, 3))

    with np.errstate(invalid="ignore"):
        agg_elev = np.mean(elev_blocks, axis=(1, 3)).astype(np.float32)
    agg_elev[block_has_nodata] = np.nan

    # Propagate NaN in slope/roughness if any cell in block has NaN slope/roughness, else take max
    slope_has_nan = np.any(np.isnan(slope_blocks), axis=(1, 3)) | block_has_nodata
    rough_has_nan = np.any(np.isnan(rough_blocks), axis=(1, 3)) | block_has_nodata

    import warnings

    with warnings.catch_warnings(), np.errstate(invalid="ignore"):
        warnings.simplefilter("ignore", category=RuntimeWarning)
        subgrid_max_slope = np.nanmax(slope_blocks, axis=(1, 3)).astype(np.float32)
        subgrid_max_rough = np.nanmax(rough_blocks, axis=(1, 3)).astype(np.float32)

    subgrid_max_slope[slope_has_nan] = np.nan
    subgrid_max_rough[rough_has_nan] = np.nan

    new_d_lon = native_meta.deg_per_px_lon * factor
    new_d_lat = native_meta.deg_per_px_lat * factor
    new_max_lon = native_meta.min_lon + agg_w * new_d_lon
    new_min_lat = native_meta.max_lat - agg_h * new_d_lat

    agg_meta = RasterMetadata(
        width=agg_w,
        height=agg_h,
        coordinate_type="geographic",
        crs_str=native_meta.crs_str,
        units="degrees",
        min_lon=native_meta.min_lon,
        min_lat=new_min_lat,
        max_lon=new_max_lon,
        max_lat=native_meta.max_lat,
        deg_per_px_lon=new_d_lon,
        deg_per_px_lat=new_d_lat,
        meters_per_px_x=native_meta.meters_per_px_x * factor,
        meters_per_px_y=native_meta.meters_per_px_y * factor,
        affine_transform=(
            new_d_lon,
            0.0,
            native_meta.min_lon,
            0.0,
            -new_d_lat,
            native_meta.max_lat,
        ),
        nodata_value=None,
        vertical_datum=native_meta.vertical_datum,
        metadata_tags=dict(native_meta.metadata_tags),
        is_synthetic=native_meta.is_synthetic,
    )

    return agg_elev, agg_meta, subgrid_max_slope, subgrid_max_rough


class TerrainSourceSelector:
    """
    Deterministic multi-resolution terrain source selector.

    Evaluates whether a route corridor (start, destination, and all science waypoints plus
    corridor padding) is 100% contained within a validated localized HiRISE DTM (~1 m/px)
    and can be analyzed at a resolution strictly finer than the regional MOLA-HRSC blended
    DEM (~200 m/px) within the computational cell budget (`MAX_GRID_CELLS`).

    Enforces the Single-Source Invariant: never combines, stitches, or fills NoData across
    different DEM sources within a single route request.
    """

    DEFAULT_REGIONAL_PADDING_METERS = 3500.0

    @classmethod
    def select_and_prepare_corridor(
        cls,
        start: MarsCoordinate,
        destination: MarsCoordinate,
        waypoints: list[MarsCoordinate] | None,
        regional_provider: BaseRasterProvider,
        hirise_provider: HiRISERasterProvider | None = None,
        max_cells: int | None = None,
        corridor_padding_meters: float | None = None,
    ) -> CorridorSelectionOutcome:
        settings = get_settings()
        effective_max_cells = max_cells if max_cells is not None else settings.MAX_GRID_CELLS
        all_waypoints = list(waypoints or [])

        # 1. Load regional master raster and validate that all points lie inside the pilot region
        regional_raster = regional_provider.get_dem_raster()
        reg_meta = regional_raster.metadata
        validate_coordinates_in_bounds(start, reg_meta, "Start point")
        validate_coordinates_in_bounds(destination, reg_meta, "Destination point")
        for idx, wp in enumerate(all_waypoints):
            validate_coordinates_in_bounds(wp, reg_meta, f"Science Waypoint #{idx + 1}")

        regional_res_m = max(float(reg_meta.meters_per_px_x), float(reg_meta.meters_per_px_y))

        # 2. Evaluate optional localized HiRISE DTM eligibility
        hirise_evaluated = hirise_provider is not None
        hirise_enabled = bool(hirise_provider.enabled) if hirise_provider is not None else False
        hirise_status = "not_configured"
        hirise_rejection_reason: str | None = (
            "No HiRISE provider configured for this route service instance."
        )

        if hirise_provider is not None:
            val_res = hirise_provider.validate_hirise_raster()
            if not val_res.is_valid or val_res.raster is None:
                hirise_status = val_res.status_code
                hirise_rejection_reason = val_res.reason
            else:
                hi_outcome, hi_status, hi_reason = cls._try_prepare_hirise_corridor(
                    hirise_provider=hirise_provider,
                    hirise_raster=val_res.raster,
                    start=start,
                    destination=destination,
                    waypoints=all_waypoints,
                    regional_res_m=regional_res_m,
                    max_cells=effective_max_cells,
                    corridor_padding_meters=corridor_padding_meters,
                )
                if hi_outcome is not None:
                    return hi_outcome
                hirise_status = hi_status
                hirise_rejection_reason = hi_reason

        # 3. Fallback / Regional MOLA-HRSC (or Synthetic) selection path
        reg_padding_m = (
            float(corridor_padding_meters)
            if corridor_padding_meters is not None
            else cls.DEFAULT_REGIONAL_PADDING_METERS
        )
        cropped_elev, cropped_meta, _, _ = crop_mission_corridor(
            regional_raster,
            start,
            destination,
            padding_meters=reg_padding_m,
            max_cells=effective_max_cells,
            waypoints=all_waypoints,
        )

        s_col, s_row = geo_to_pixel(
            start.lon,
            start.lat,
            cropped_meta.min_lon,
            cropped_meta.max_lat,
            cropped_meta.deg_per_px_lon,
            cropped_meta.deg_per_px_lat,
            pixel_center=True,
        )
        d_col, d_row = geo_to_pixel(
            destination.lon,
            destination.lat,
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
        start_px = (s_col, s_row)
        dest_px = (d_col, d_row)
        clean_elev = cropped_elev

        prov = dict(regional_provider.get_provenance())
        is_syn = bool(cropped_meta.is_synthetic)
        selected_id = (
            "synthetic_jezero_test_fixture"
            if is_syn
            else (prov.get("official_product_id") or "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2")
        )
        selected_tier = "synthetic_simulation" if is_syn else "regional_blended_dem"
        dataset_name = str(prov.get("dataset_name", "MOLA-HRSC Regional DEM"))
        eff_res_m = round(
            max(float(cropped_meta.meters_per_px_x), float(cropped_meta.meters_per_px_y)), 3
        )

        selection_reason = (
            f"Selected regional source '{dataset_name}' ({eff_res_m:.1f} m/px) for the entire route corridor. "
            + (
                f"HiRISE evaluation outcome: {hirise_status} ({hirise_rejection_reason})"
                if hirise_evaluated
                else "HiRISE high-resolution DTM was not configured."
            )
        )

        report = TerrainSourceSelectionReport(
            selected_source_id=str(selected_id),
            selected_source_tier=selected_tier,
            selected_dataset_name=dataset_name,
            selection_reason=selection_reason,
            single_source_invariant_enforced=True,
            hirise_evaluated=hirise_evaluated,
            hirise_enabled=hirise_enabled,
            hirise_selected=False,
            hirise_status=hirise_status,
            hirise_rejection_reason=hirise_rejection_reason,
            corridor_bounds=BoundingBox(
                min_lon=round(cropped_meta.min_lon, 6),
                min_lat=round(cropped_meta.min_lat, 6),
                max_lon=round(cropped_meta.max_lon, 6),
                max_lat=round(cropped_meta.max_lat, 6),
            ),
            corridor_padding_meters=round(reg_padding_m, 2),
            native_resolution_meters=eff_res_m,
            effective_resolution_meters=eff_res_m,
            aggregation_applied=False,
            aggregation_factor=1,
            aggregation_method="none",
            corridor_native_grid_shape=[int(cropped_meta.height), int(cropped_meta.width)],
            corridor_analysis_grid_shape=[int(cropped_meta.height), int(cropped_meta.width)],
        )
        prov["source_selection"] = report.model_dump()
        prov["native_resolution_meters"] = eff_res_m
        prov["effective_resolution_meters"] = eff_res_m
        prov["aggregation_applied"] = False
        prov["aggregation_factor"] = 1
        prov["aggregation_method"] = "none"

        return CorridorSelectionOutcome(
            selected_provider=regional_provider,
            master_raster=regional_raster,
            corridor_elevation=clean_elev,
            corridor_metadata=cropped_meta,
            start_pixel=start_px,
            dest_pixel=dest_px,
            provenance=prov,
            selection_report=report,
            native_resolution_x_meters=float(cropped_meta.meters_per_px_x),
            native_resolution_y_meters=float(cropped_meta.meters_per_px_y),
            subgrid_max_slope_deg=None,
            subgrid_max_roughness=None,
        )

    @classmethod
    def _try_prepare_hirise_corridor(
        cls,
        hirise_provider: HiRISERasterProvider,
        hirise_raster: RasterData,
        start: MarsCoordinate,
        destination: MarsCoordinate,
        waypoints: list[MarsCoordinate],
        regional_res_m: float,
        max_cells: int,
        corridor_padding_meters: float | None,
    ) -> tuple[CorridorSelectionOutcome | None, str, str]:
        """
        Attempts to validate full corridor containment inside the HiRISE DTM, extract/warp the
        corridor window, and apply adaptive resolution (native or conservative block aggregation)
        while enforcing `max_cells`.
        """
        hi_meta = hirise_raster.metadata
        all_points = [start, destination] + waypoints
        pts_lons = [p.lon for p in all_points]
        pts_lats = [p.lat for p in all_points]

        pts_min_lon = min(pts_lons)
        pts_max_lon = max(pts_lons)
        pts_min_lat = min(pts_lats)
        pts_max_lat = max(pts_lats)
        center_lat = (pts_min_lat + pts_max_lat) / 2.0

        native_res_x = float(hi_meta.meters_per_px_x)
        native_res_y = float(hi_meta.meters_per_px_y)
        native_res_m = max(native_res_x, native_res_y)

        span_diag_m = haversine_distance_mars(
            MarsCoordinate(lon=pts_min_lon, lat=pts_min_lat),
            MarsCoordinate(lon=pts_max_lon, lat=pts_max_lat),
        )

        # Resolution-aware physical padding for localized high-res corridor
        if corridor_padding_meters is not None:
            hi_pad_m = float(corridor_padding_meters)
        else:
            hi_pad_m = min(
                cls.DEFAULT_REGIONAL_PADDING_METERS,
                max(20.0 * native_res_m, 0.25 * span_diag_m, 30.0),
            )

        pad_lon_deg = hi_pad_m / meters_per_degree_lon(center_lat)
        pad_lat_deg = hi_pad_m / METERS_PER_DEGREE_LATITUDE

        corr_min_lon = pts_min_lon - pad_lon_deg
        corr_max_lon = pts_max_lon + pad_lon_deg
        corr_min_lat = pts_min_lat - pad_lat_deg
        corr_max_lat = pts_max_lat + pad_lat_deg

        # 1. Check full padded corridor containment in HiRISE geographic envelope AND native pixel space
        eps = 1e-7
        if (
            corr_min_lon < hi_meta.min_lon - eps
            or corr_max_lon > hi_meta.max_lon + eps
            or corr_min_lat < hi_meta.min_lat - eps
            or corr_max_lat > hi_meta.max_lat + eps
        ):
            return (
                None,
                "partial_or_no_corridor_coverage",
                (
                    f"Padded route corridor [{corr_min_lon:.5f}, {corr_min_lat:.5f}, "
                    f"{corr_max_lon:.5f}, {corr_max_lat:.5f}] extends outside localized HiRISE DTM "
                    f"bounds [{hi_meta.min_lon:.5f}, {hi_meta.min_lat:.5f}, "
                    f"{hi_meta.max_lon:.5f}, {hi_meta.max_lat:.5f}]. Single-source invariant "
                    f"forbids mixing HiRISE and MOLA-HRSC rasters."
                ),
            )

        # Also check corners, edge midpoints, and all mission points in native HiRISE pixel space
        check_coords = [
            (corr_min_lon, corr_min_lat),
            (corr_min_lon, corr_max_lat),
            (corr_max_lon, corr_min_lat),
            (corr_max_lon, corr_max_lat),
            ((corr_min_lon + corr_max_lon) / 2.0, corr_min_lat),
            ((corr_min_lon + corr_max_lon) / 2.0, corr_max_lat),
            (corr_min_lon, (corr_min_lat + corr_max_lat) / 2.0),
            (corr_max_lon, (corr_min_lat + corr_max_lat) / 2.0),
        ] + [(pt.lon, pt.lat) for pt in all_points]

        for lon_c, lat_c in check_coords:
            col_f, row_f = hirise_raster.geo_to_native_pixel_float(lon_c, lat_c)
            if (
                col_f < -0.5
                or col_f > hi_meta.width + 0.5
                or row_f < -0.5
                or row_f > hi_meta.height + 0.5
            ):
                return (
                    None,
                    "partial_or_no_corridor_coverage",
                    (
                        f"Corridor coordinate ({lon_c:.5f}E, {lat_c:.5f}N) maps to native pixel "
                        f"({col_f:.1f}, {row_f:.1f}) outside HiRISE raster grid "
                        f"(0..{hi_meta.width}, 0..{hi_meta.height})."
                    ),
                )

        # 2. Extract (or warp if projected) the native-resolution corridor onto the Mars geographic grid
        try:
            native_elev, native_corr_meta = cls._extract_native_hirise_corridor(
                hirise_raster=hirise_raster,
                corr_min_lon=corr_min_lon,
                corr_min_lat=corr_min_lat,
                corr_max_lon=corr_max_lon,
                corr_max_lat=corr_max_lat,
            )
        except Exception as exc:
            return (
                None,
                "rejected_corridor_extraction_failed",
                f"Failed to extract/reproject HiRISE corridor window: {exc}",
            )

        nat_h, nat_w = native_elev.shape
        if nat_h < 4 or nat_w < 4:
            return (
                None,
                "rejected_corridor_too_small",
                f"Extracted HiRISE corridor window ({nat_h}x{nat_w}) is smaller than minimum 4x4 grid.",
            )

        # 3. Verify valid observations at mission points and across the extracted corridor
        valid_mask = ~np.isnan(native_elev) & (native_elev >= -9000.0) & (native_elev <= 25000.0)
        corridor_valid_fraction = float(np.sum(valid_mask)) / float(native_elev.size)
        if corridor_valid_fraction < 0.50:
            return (
                None,
                "corridor_contains_excessive_nodata",
                (
                    f"HiRISE corridor window contains only {corridor_valid_fraction * 100:.1f}% "
                    f"valid observations (< 50% required for single-source routing)."
                ),
            )

        for pt in all_points:
            pc, pr = geo_to_pixel(
                pt.lon,
                pt.lat,
                native_corr_meta.min_lon,
                native_corr_meta.max_lat,
                native_corr_meta.deg_per_px_lon,
                native_corr_meta.deg_per_px_lat,
                pixel_center=True,
            )
            pc = max(0, min(pc, nat_w - 1))
            pr = max(0, min(pr, nat_h - 1))
            if not valid_mask[pr, pc]:
                return (
                    None,
                    "corridor_contains_excessive_nodata",
                    (
                        f"Mission coordinate ({pt.lon:.5f}E, {pt.lat:.5f}N) falls on a NoData cell "
                        f"in the HiRISE DTM; falling back to regional MOLA-HRSC DEM."
                    ),
                )

        # 4. Enforce MAX_GRID_CELLS: native resolution vs. conservative block aggregation
        native_cells = nat_h * nat_w
        if native_cells <= max_cells:
            agg_factor = 1
            agg_applied = False
            agg_method = "none"
            analysis_elev = native_elev
            analysis_meta = native_corr_meta
            subgrid_max_slope = None
            subgrid_max_rough = None
        else:
            if max_cells < 16:
                raise ComputationalBoundExceededError(
                    f"Configured max_cells={max_cells} is below the minimum viable 4x4 routing grid (16 cells).",
                    dimensions=(nat_w, nat_h),
                    max_allowed=max_cells,
                )

            agg_factor = max(2, int(math.ceil(math.sqrt(native_cells / float(max_cells)))))
            while (nat_h // agg_factor) * (nat_w // agg_factor) > max_cells:
                agg_factor += 1

            eff_res_candidate = native_res_m * agg_factor
            agg_h = nat_h // agg_factor
            agg_w = nat_w // agg_factor

            # If required aggregation degrades resolution to >= 95% of regional MOLA-HRSC resolution
            # or collapses the grid below 4x4, reject HiRISE and select MOLA-HRSC
            if eff_res_candidate >= regional_res_m * 0.95 or agg_h < 4 or agg_w < 4:
                return (
                    None,
                    "rejected_aggregated_resolution_no_better_than_regional",
                    (
                        f"Native HiRISE corridor ({nat_h}x{nat_w} = {native_cells} cells) exceeds "
                        f"max_cells={max_cells}, requiring aggregation factor k={agg_factor} "
                        f"(effective resolution {eff_res_candidate:.1f} m/px vs regional "
                        f"{regional_res_m:.1f} m/px, grid {agg_h}x{agg_w}). Selecting regional MOLA-HRSC DEM."
                    ),
                )

            analysis_elev, analysis_meta, subgrid_max_slope, subgrid_max_rough = (
                aggregate_corridor_hazard_preserving(
                    native_elev=native_elev,
                    native_meta=native_corr_meta,
                    factor=agg_factor,
                )
            )
            agg_applied = True
            agg_method = AGGREGATION_METHOD_NAME

            # Ensure all mission points still map to valid (non-NaN) aggregated blocks
            for pt in all_points:
                pc, pr = geo_to_pixel(
                    pt.lon,
                    pt.lat,
                    analysis_meta.min_lon,
                    analysis_meta.max_lat,
                    analysis_meta.deg_per_px_lon,
                    analysis_meta.deg_per_px_lat,
                    pixel_center=True,
                )
                pc = max(0, min(pc, analysis_meta.width - 1))
                pr = max(0, min(pr, analysis_meta.height - 1))
                if np.isnan(analysis_elev[pr, pc]):
                    return (
                        None,
                        "corridor_contains_excessive_nodata",
                        (
                            f"Mission coordinate ({pt.lon:.5f}E, {pt.lat:.5f}N) falls inside an "
                            f"aggregated {agg_factor}x{agg_factor} block containing NoData."
                        ),
                    )

        # Compute local start and destination pixel indices on analysis_meta
        s_col, s_row = geo_to_pixel(
            start.lon,
            start.lat,
            analysis_meta.min_lon,
            analysis_meta.max_lat,
            analysis_meta.deg_per_px_lon,
            analysis_meta.deg_per_px_lat,
            pixel_center=True,
        )
        d_col, d_row = geo_to_pixel(
            destination.lon,
            destination.lat,
            analysis_meta.min_lon,
            analysis_meta.max_lat,
            analysis_meta.deg_per_px_lon,
            analysis_meta.deg_per_px_lat,
            pixel_center=True,
        )
        s_col = max(0, min(s_col, analysis_meta.width - 1))
        s_row = max(0, min(s_row, analysis_meta.height - 1))
        d_col = max(0, min(d_col, analysis_meta.width - 1))
        d_row = max(0, min(d_row, analysis_meta.height - 1))

        eff_res_m = round(
            max(float(analysis_meta.meters_per_px_x), float(analysis_meta.meters_per_px_y)), 3
        )
        nat_res_m = round(native_res_m, 3)

        prov = dict(hirise_provider.get_provenance())
        selected_id = prov.get("official_product_id") or "dem_hirise_jezero_delta_1m"
        dataset_name = str(prov.get("dataset_name", "HiRISE Jezero Western Delta DTM"))

        if agg_applied:
            selection_reason = (
                f"Selected localized HiRISE DTM '{dataset_name}': padded corridor is 100% contained "
                f"within HiRISE coverage; native {nat_h}x{nat_w} window ({nat_res_m:.2f} m/px) was "
                f"conservatively aggregated by factor k={agg_factor} to {analysis_meta.height}x{analysis_meta.width} "
                f"({eff_res_m:.2f} m/px <= max_cells={max_cells}) while preserving sub-block maximum slope and roughness."
            )
        else:
            selection_reason = (
                f"Selected localized HiRISE DTM '{dataset_name}' at native resolution ({nat_res_m:.2f} m/px, "
                f"{nat_h}x{nat_w} cells <= max_cells={max_cells}): padded corridor is 100% contained within HiRISE coverage."
            )

        report = TerrainSourceSelectionReport(
            selected_source_id=str(selected_id),
            selected_source_tier="localized_high_resolution_dtm",
            selected_dataset_name=dataset_name,
            selection_reason=selection_reason,
            single_source_invariant_enforced=True,
            hirise_evaluated=True,
            hirise_enabled=True,
            hirise_selected=True,
            hirise_status="selected",
            hirise_rejection_reason=None,
            corridor_bounds=BoundingBox(
                min_lon=round(analysis_meta.min_lon, 6),
                min_lat=round(analysis_meta.min_lat, 6),
                max_lon=round(analysis_meta.max_lon, 6),
                max_lat=round(analysis_meta.max_lat, 6),
            ),
            corridor_padding_meters=round(hi_pad_m, 2),
            native_resolution_meters=nat_res_m,
            effective_resolution_meters=eff_res_m,
            aggregation_applied=agg_applied,
            aggregation_factor=agg_factor,
            aggregation_method=agg_method,
            corridor_native_grid_shape=[int(nat_h), int(nat_w)],
            corridor_analysis_grid_shape=[int(analysis_meta.height), int(analysis_meta.width)],
        )

        prov["source_selection"] = report.model_dump()
        prov["resolution_meters"] = eff_res_m
        prov["native_resolution_meters"] = nat_res_m
        prov["effective_resolution_meters"] = eff_res_m
        prov["aggregation_applied"] = agg_applied
        prov["aggregation_factor"] = agg_factor
        prov["aggregation_method"] = agg_method

        return (
            CorridorSelectionOutcome(
                selected_provider=hirise_provider,
                master_raster=hirise_raster,
                corridor_elevation=analysis_elev,
                corridor_metadata=analysis_meta,
                start_pixel=(s_col, s_row),
                dest_pixel=(d_col, d_row),
                provenance=prov,
                selection_report=report,
                native_resolution_x_meters=native_res_x,
                native_resolution_y_meters=native_res_y,
                subgrid_max_slope_deg=subgrid_max_slope,
                subgrid_max_roughness=subgrid_max_rough,
            ),
            "selected",
            selection_reason,
        )

    @classmethod
    def _extract_native_hirise_corridor(
        cls,
        hirise_raster: RasterData,
        corr_min_lon: float,
        corr_min_lat: float,
        corr_max_lon: float,
        corr_max_lat: float,
    ) -> tuple[np.ndarray, RasterMetadata]:
        """
        Extracts the corridor window from `hirise_raster` at native resolution.
        - If `hirise_raster` is already in Mars geographic coordinates, slices the exact pixel window
          and converts any NoData cells to `np.nan`.
        - If `hirise_raster` is in a projected Mars metric CRS, reprojects the corridor window
          onto the Mars planetocentric geographic grid using `rasterio.warp.reproject` while
          strictly propagating NoData masks so NoData is NEVER interpolated or turned into 0.0.
        """
        hi_meta = hirise_raster.metadata

        if (
            hi_meta.coordinate_type == "projected"
            and HAS_RASTERIO
            and HAS_PYPROJ
            and hi_meta.crs_str not in ("", "Unknown / Unspecified")
        ):
            from rasterio.transform import Affine, from_bounds
            from rasterio.warp import Resampling, reproject

            center_lat = (corr_min_lat + corr_max_lat) / 2.0
            deg_lon_px = hi_meta.meters_per_px_x / meters_per_degree_lon(center_lat)
            deg_lat_px = hi_meta.meters_per_px_y / METERS_PER_DEGREE_LATITUDE

            dst_w = max(4, int(round((corr_max_lon - corr_min_lon) / deg_lon_px)))
            dst_h = max(4, int(round((corr_max_lat - corr_min_lat) / deg_lat_px)))

            dst_transform = from_bounds(
                corr_min_lon, corr_min_lat, corr_max_lon, corr_max_lat, dst_w, dst_h
            )
            src_transform = Affine(*hi_meta.affine_transform)
            src_crs = rasterio.crs.CRS.from_user_input(hi_meta.crs_str)
            dst_crs = rasterio.crs.CRS.from_string("+proj=longlat +R=3396190 +no_defs")

            src_elev = hirise_raster.data.astype(np.float32).copy()
            src_elev[hirise_raster.nodata_mask] = np.nan

            # Pass src_nodata=None so IEEE-754 NaN values in src_elev are NOT ignored by
            # GDAL's warper during bilinear interpolation across NoData boundaries.
            dst_elev = np.full((dst_h, dst_w), np.nan, dtype=np.float32)
            reproject(
                source=src_elev,
                destination=dst_elev,
                src_transform=src_transform,
                src_crs=src_crs,
                src_nodata=None,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )

            # Conservatively propagate the binary invalid-data mask (0.0 = valid, 1.0 = invalid/NoData).
            # CRITICAL: Do NOT set src_nodata=1.0 or dst_nodata=1.0 (which would cause GDAL to ignore
            # or clamp invalid source pixels!). Instead use src_nodata=-1.0 and dst_nodata=-1.0
            # (outside {0.0, 1.0}; any unmapped out-of-bounds pixel gets -1.0), combining both
            # bilinear footprint weighting (> 0 when any contributing kernel neighbor is invalid)
            # and conservative Resampling.max.
            src_bad = hirise_raster.nodata_mask.astype(np.float32)
            dst_bad_bilin = np.full((dst_h, dst_w), -1.0, dtype=np.float32)
            reproject(
                source=src_bad,
                destination=dst_bad_bilin,
                src_transform=src_transform,
                src_crs=src_crs,
                src_nodata=-1.0,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=-1.0,
                resampling=Resampling.bilinear,
            )
            dst_bad_max = np.full((dst_h, dst_w), -1.0, dtype=np.float32)
            reproject(
                source=src_bad,
                destination=dst_bad_max,
                src_transform=src_transform,
                src_crs=src_crs,
                src_nodata=-1.0,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=-1.0,
                resampling=Resampling.max,
            )
            invalid_dst = (
                (dst_bad_bilin < 0.0)
                | (dst_bad_bilin > 1e-6)
                | (dst_bad_max < 0.0)
                | (dst_bad_max > 1e-6)
            )
            dst_elev[invalid_dst] = np.nan

            actual_d_lon = (corr_max_lon - corr_min_lon) / dst_w
            actual_d_lat = (corr_max_lat - corr_min_lat) / dst_h
            out_meta = RasterMetadata(
                width=dst_w,
                height=dst_h,
                coordinate_type="geographic",
                crs_str="IAU2000:49900",
                units="degrees",
                min_lon=corr_min_lon,
                min_lat=corr_min_lat,
                max_lon=corr_max_lon,
                max_lat=corr_max_lat,
                deg_per_px_lon=actual_d_lon,
                deg_per_px_lat=actual_d_lat,
                meters_per_px_x=actual_d_lon * meters_per_degree_lon(center_lat),
                meters_per_px_y=actual_d_lat * METERS_PER_DEGREE_LATITUDE,
                affine_transform=(
                    actual_d_lon,
                    0.0,
                    corr_min_lon,
                    0.0,
                    -actual_d_lat,
                    corr_max_lat,
                ),
                nodata_value=None,
                vertical_datum=hi_meta.vertical_datum,
                metadata_tags=dict(hi_meta.metadata_tags),
                is_synthetic=hi_meta.is_synthetic,
            )
            return dst_elev, out_meta

        # Geographic CRS window slice
        c_min, r_min = geo_to_pixel(
            corr_min_lon,
            corr_max_lat,
            hi_meta.min_lon,
            hi_meta.max_lat,
            hi_meta.deg_per_px_lon,
            hi_meta.deg_per_px_lat,
        )
        c_max, r_max = geo_to_pixel(
            corr_max_lon,
            corr_min_lat,
            hi_meta.min_lon,
            hi_meta.max_lat,
            hi_meta.deg_per_px_lon,
            hi_meta.deg_per_px_lat,
        )
        c_min = max(0, min(c_min, hi_meta.width - 1))
        c_max = max(c_min + 1, min(c_max + 1, hi_meta.width))
        r_min = max(0, min(r_min, hi_meta.height - 1))
        r_max = max(r_min + 1, min(r_max + 1, hi_meta.height))

        crop_h = r_max - r_min
        crop_w = c_max - c_min

        cropped_elev = hirise_raster.data[r_min:r_max, c_min:c_max].astype(np.float32).copy()
        cropped_mask = hirise_raster.nodata_mask[r_min:r_max, c_min:c_max]
        cropped_elev[cropped_mask] = np.nan

        sub_min_lon, sub_max_lat = pixel_to_geo(
            c_min,
            r_min,
            hi_meta.min_lon,
            hi_meta.max_lat,
            hi_meta.deg_per_px_lon,
            hi_meta.deg_per_px_lat,
        )
        sub_max_lon, sub_min_lat = pixel_to_geo(
            c_max,
            r_max,
            hi_meta.min_lon,
            hi_meta.max_lat,
            hi_meta.deg_per_px_lon,
            hi_meta.deg_per_px_lat,
        )

        out_meta = RasterMetadata(
            width=crop_w,
            height=crop_h,
            coordinate_type="geographic",
            crs_str=hi_meta.crs_str,
            units="degrees",
            min_lon=sub_min_lon,
            min_lat=sub_min_lat,
            max_lon=sub_max_lon,
            max_lat=sub_max_lat,
            deg_per_px_lon=hi_meta.deg_per_px_lon,
            deg_per_px_lat=hi_meta.deg_per_px_lat,
            meters_per_px_x=hi_meta.meters_per_px_x,
            meters_per_px_y=hi_meta.meters_per_px_y,
            affine_transform=(
                hi_meta.deg_per_px_lon,
                0.0,
                sub_min_lon,
                0.0,
                -hi_meta.deg_per_px_lat,
                sub_max_lat,
            ),
            nodata_value=None,
            vertical_datum=hi_meta.vertical_datum,
            metadata_tags=dict(hi_meta.metadata_tags),
            is_synthetic=hi_meta.is_synthetic,
        )
        return cropped_elev, out_meta
