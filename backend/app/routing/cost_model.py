from dataclasses import dataclass
from typing import Dict, Tuple
from backend.app.schemas.mission import OptimizationMode


@dataclass
class CostModelWeights:
    weight_slope: float
    weight_roughness: float
    weight_hazard: float
    slope_ceiling_deg: float


# Mode weight definitions
MODE_WEIGHTS: Dict[OptimizationMode, CostModelWeights] = {
    OptimizationMode.SAFETY_FIRST: CostModelWeights(
        weight_slope=3.5,
        weight_roughness=2.5,
        weight_hazard=5.0,
        slope_ceiling_deg=14.0,
    ),
    OptimizationMode.BALANCED: CostModelWeights(
        weight_slope=1.2,
        weight_roughness=1.0,
        weight_hazard=2.0,
        slope_ceiling_deg=20.0,
    ),
    OptimizationMode.SCIENCE_FIRST: CostModelWeights(
        weight_slope=0.7,
        weight_roughness=0.6,
        weight_hazard=1.0,
        slope_ceiling_deg=22.0,
    ),
}


def calculate_edge_cost(
    distance_3d: float,
    slope_deg: float,
    roughness: float,
    delta_z: float,
    mode: OptimizationMode,
    is_nodata: bool = False,
    extra_penalty: float = 0.0,
) -> Tuple[float, Dict[str, float]]:
    """
    Computes explainable, strictly non-negative edge traversal cost:
    cost = distance_3d * (1.0 + w_slope * normalized_slope + w_rough * roughness + w_hazard * hazard) + extra_penalty

    Guarantees:
    - cost >= distance_3d > 0.0 (strictly positive, non-negative edge weights).
    - Uphill climbs (delta_z > 0) are penalized more than level/downhill travel.
    - Missing/no-data terrain incurs high hazard penalty.
    """
    weights = MODE_WEIGHTS[mode]

    # Normalized slope factor (0.0 to 1.0+)
    # Slopes up to ceiling scale linearly; slopes approaching ceiling scale quadratically
    norm_slope = max(0.0, slope_deg) / max(weights.slope_ceiling_deg, 1.0)
    # Directional uphill modifier: +20% penalty if climbing uphill
    uphill_mod = 1.2 if delta_z > 0.0 else 0.95
    slope_factor = (norm_slope**1.5) * uphill_mod

    # Roughness factor
    rough_factor = max(0.0, min(roughness, 1.0))

    # Hazard / missing data factor
    hazard_factor = 4.0 if is_nodata else 0.0

    multiplier = 1.0 + (
        (weights.weight_slope * slope_factor)
        + (weights.weight_roughness * rough_factor)
        + (weights.weight_hazard * hazard_factor)
    )

    base_dist_cost = distance_3d
    slope_penalty = distance_3d * (weights.weight_slope * slope_factor)
    rough_penalty = distance_3d * (weights.weight_roughness * rough_factor)
    hazard_penalty = distance_3d * (weights.weight_hazard * hazard_factor)

    total_cost = (distance_3d * multiplier) + extra_penalty

    breakdown = {
        "base_distance_cost": round(base_dist_cost, 2),
        "slope_penalty": round(slope_penalty, 2),
        "roughness_penalty": round(rough_penalty, 2),
        "hazard_penalty": round(hazard_penalty, 2),
        "extra_penalty": round(extra_penalty, 2),
    }

    return max(total_cost, distance_3d), breakdown
