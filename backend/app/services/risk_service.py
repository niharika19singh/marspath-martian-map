from typing import Tuple
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
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Computes slope, roughness, and the traversability mask for the cropped mission grid.
        Adjusts slope thresholds according to optimization mode.
        """
        # Mode-based slope cap: Safety-first restricts slope to min(constraints.max_slope_deg, 14.0)
        effective_max_slope = constraints.max_slope_deg
        if mode == OptimizationMode.SAFETY_FIRST:
            effective_max_slope = min(effective_max_slope, 14.0)

        # Nodata mask
        nodata_mask = np.isnan(elevation) | (elevation < -9000.0)

        # Compute slope in degrees
        slope_deg = compute_slope_degrees(elevation, dx_meters, dy_meters, nodata_mask=nodata_mask)

        # Compute roughness index [0, 1]
        roughness = compute_roughness_index(elevation, kernel_size=3, nodata_mask=nodata_mask)

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
