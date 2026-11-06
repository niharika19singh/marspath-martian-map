import numpy as np

from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.schemas.mission import OptimizationMode, RouteConstraints


class RiskService:
    @staticmethod
    def evaluate_terrain_risk(
        elevation: np.ndarray,
        dx_meters: float,
        dy_meters: float,
        constraints: RouteConstraints,
        mode: OptimizationMode,
        subgrid_max_slope_deg: np.ndarray | None = None,
        subgrid_max_roughness: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Computes slope, roughness, and the traversability mask for the cropped mission grid.
        Adjusts slope thresholds according to optimization mode.
        When conservative block aggregation was applied to a high-resolution DTM, enforces
        `subgrid_max_slope_deg` and `subgrid_max_roughness` as fine-scale hazard floors so
        narrow scarps or boulder fields cannot be smoothed away.
        """
        # Mode-based slope cap: Safety-first restricts slope to min(constraints.max_slope_deg, 14.0)
        effective_max_slope = constraints.max_slope_deg
        if mode == OptimizationMode.SAFETY_FIRST:
            effective_max_slope = min(effective_max_slope, 14.0)

        # Nodata mask
        nodata_mask = np.isnan(elevation) | (elevation < -9000.0)

        # Compute slope in degrees
        slope_deg = compute_slope_degrees(elevation, dx_meters, dy_meters, nodata_mask=nodata_mask)
        if subgrid_max_slope_deg is not None and subgrid_max_slope_deg.shape == slope_deg.shape:
            both_nan_or_any_nan = np.isnan(slope_deg) | np.isnan(subgrid_max_slope_deg)
            slope_deg = np.where(
                both_nan_or_any_nan,
                np.nan,
                np.maximum(slope_deg, subgrid_max_slope_deg),
            ).astype(np.float32)

        # Compute roughness index [0, 1]
        roughness = compute_roughness_index(elevation, kernel_size=3, nodata_mask=nodata_mask)
        if subgrid_max_roughness is not None and subgrid_max_roughness.shape == roughness.shape:
            both_nan_or_any_nan = np.isnan(roughness) | np.isnan(subgrid_max_roughness)
            roughness = np.where(
                both_nan_or_any_nan,
                np.nan,
                np.maximum(roughness, subgrid_max_roughness),
            ).astype(np.float32)

        # Build binary traversability mask
        traversable = build_traversability_mask(
            slope_deg=slope_deg,
            roughness=roughness,
            max_slope_deg=effective_max_slope,
            max_roughness=constraints.max_roughness,
            nodata_mask=nodata_mask,
            avoid_unobserved_terrain=constraints.avoid_unobserved_terrain,
        )

        return slope_deg, roughness, traversable
