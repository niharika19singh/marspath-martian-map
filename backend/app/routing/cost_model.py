import math
from dataclasses import dataclass
from enum import Enum

from backend.app.schemas.mission import OptimizationMode

# Documented physical and modeling constants (see METHODOLOGY.md)
# IAU2000 Mars equatorial/mean surface gravity vs Earth standard gravity
MARS_GRAVITY_M_S2: float = 3.72076
EARTH_GRAVITY_M_S2: float = 9.80665
MARS_EARTH_GRAVITY_RATIO: float = MARS_GRAVITY_M_S2 / EARTH_GRAVITY_M_S2  # ~0.379412

# Minetti et al. (2002) walking energy-cost-of-transport polynomial coefficients C(i) [J / kg / m]
# Evaluated strictly over gradient i = clip(dz / d2d, -0.45, +0.45) and normalized to relative effort.
# NOTE: Used only as a gradient-based relative effort curve ("estimated relative effort"); NEVER calories/physiology.
MINETTI_COEFFS: tuple[float, float, float, float, float, float] = (
    155.4,  # i^5
    -30.4,  # i^4
    -43.3,  # i^3
    46.3,  # i^2
    19.5,  # i^1
    3.6,  # level baseline C(0) [J / kg / m]
)
MINETTI_LEVEL_BASE: float = 3.6
MINETTI_GRADE_CLIP: float = 0.45
MINETTI_MIN_EARTH_NORM: float = 0.50  # Lower bound around optimal ~-0.10 slope (~1.8/3.6)

DEFAULT_CROSS_SLOPE_WEIGHT: float = 0.65
DEFAULT_SUIT_LOAD_FACTOR: float = 1.0


class CostMode(str, Enum):
    """Direction-aware slope cost vs legacy magnitude-only comparison mode."""

    DIRECTIONAL = "directional"
    LEGACY_MAGNITUDE = "legacy_magnitude"


class EffortModel(str, Enum):
    """Switchable slope-penalty vs Minetti-style Mars-gravity relative effort model."""

    SLOPE_PENALTY = "slope_penalty"
    MINETTI_EFFORT = "minetti_effort"


@dataclass
class CostModelWeights:
    weight_slope: float
    weight_roughness: float
    weight_hazard: float
    slope_ceiling_deg: float


# Mode weight definitions
MODE_WEIGHTS: dict[OptimizationMode, CostModelWeights] = {
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


def compute_minetti_relative_effort_factor(
    along_grade: float,
    cross_grade: float = 0.0,
    gravity_ratio: float = MARS_EARTH_GRAVITY_RATIO,
    suit_load_factor: float = DEFAULT_SUIT_LOAD_FACTOR,
    cross_effort_coeff: float = 0.45,
) -> float:
    """
    Computes a dimensionless Minetti-style relative effort factor per unit distance,
    scaled for Mars surface gravity (documented assumption: level baseline = 1.0,
    gravitational grade delta scaled by g_mars / g_earth * suit_load_factor).

    At flat terrain (along_grade=0, cross_grade=0), factor == 1.0.
    Always >= 0.45; never outputs calories or physiological claims.
    """
    i = max(-MINETTI_GRADE_CLIP, min(MINETTI_GRADE_CLIP, float(along_grade)))
    c5, c4, c3, c2, c1, c0 = MINETTI_COEFFS
    c_earth = (((((c5 * i) + c4) * i + c3) * i + c2) * i + c1) * i + c0
    norm_delta = (c_earth - MINETTI_LEVEL_BASE) / MINETTI_LEVEL_BASE
    mars_factor = 1.0 + (gravity_ratio * suit_load_factor * norm_delta)
    cross_term = cross_effort_coeff * gravity_ratio * abs(float(cross_grade))
    return max(0.45, mars_factor + cross_term)


def calculate_edge_cost(
    distance_3d: float,
    slope_deg: float,
    roughness: float,
    delta_z: float,
    mode: OptimizationMode,
    is_nodata: bool = False,
    extra_penalty: float = 0.0,
    along_slope_deg: float | None = None,
    cross_slope_deg: float | None = None,
    d2d: float | None = None,
    cost_mode: str = CostMode.DIRECTIONAL.value,
    effort_model: str = EffortModel.SLOPE_PENALTY.value,
    cross_slope_weight: float = DEFAULT_CROSS_SLOPE_WEIGHT,
    gravity_ratio: float = MARS_EARTH_GRAVITY_RATIO,
    suit_load_factor: float = DEFAULT_SUIT_LOAD_FACTOR,
) -> tuple[float, dict[str, float]]:
    """
    Computes explainable, strictly non-negative edge traversal cost:
    Guarantees:
    - cost >= distance_3d > 0.0 (admissible A* Euclidean heuristic remains valid).
    - In `directional` cost_mode (default): uses signed along-track slope (+ uphill > - downhill)
      AND perpendicular cross-slope (lateral roll penalty).
    - In `legacy_magnitude` cost_mode: symmetric magnitude-only slope penalty (no direction sign,
      no cross-slope), preserved for comparison.
    - When `effort_model == 'minetti_effort'`: replaces the plain directional slope multiplier with
      a Mars-gravity Minetti-style relative effort penalty while maintaining cost >= distance_3d.
    """
    weights = MODE_WEIGHTS[mode]
    ceiling = max(weights.slope_ceiling_deg, 1.0)
    horiz_dist = (
        d2d if (d2d is not None and d2d > 0.0) else max(math.sqrt(max(distance_3d**2 - delta_z**2, 1e-6)), 1e-3)
    )

    if along_slope_deg is None:
        along_grade = delta_z / horiz_dist
        resolved_along_deg = math.degrees(math.atan(along_grade))
    else:
        resolved_along_deg = float(along_slope_deg)
        along_grade = math.tan(math.radians(max(-89.0, min(89.0, resolved_along_deg))))

    resolved_cross_deg = max(0.0, float(cross_slope_deg)) if cross_slope_deg is not None else 0.0

    cost_mode_norm = str(cost_mode or CostMode.DIRECTIONAL.value).lower()
    effort_mode_norm = str(effort_model or EffortModel.SLOPE_PENALTY.value).lower()

    # Cross-slope penalty is active in directional mode; disabled in legacy magnitude-only mode.
    if cost_mode_norm == CostMode.LEGACY_MAGNITUDE.value:
        norm_slope = max(0.0, slope_deg) / ceiling
        slope_factor = norm_slope**1.5
        cross_factor = 0.0
    else:
        if effort_mode_norm == EffortModel.MINETTI_EFFORT.value:
            # Shift relative to theoretical Minetti Mars minimum (~0.70) so penalty >= 0 -> cost >= distance_3d
            eff_factor = compute_minetti_relative_effort_factor(
                along_grade=along_grade,
                cross_grade=0.0,
                gravity_ratio=gravity_ratio,
                suit_load_factor=suit_load_factor,
            )
            min_baseline = 1.0 + (gravity_ratio * suit_load_factor * (MINETTI_MIN_EARTH_NORM - 1.0))
            slope_factor = max(0.0, eff_factor - min_baseline)
        else:
            norm_along = abs(resolved_along_deg) / ceiling
            if resolved_along_deg >= 0.0:
                slope_factor = 1.35 * (norm_along**1.5)
            else:
                slope_factor = 0.55 * (norm_along**1.35)

        norm_cross = resolved_cross_deg / ceiling
        cross_factor = cross_slope_weight * (norm_cross**1.5)

    # Roughness and nodata hazard factors
    rough_factor = max(0.0, min(roughness, 1.0))
    hazard_factor = 4.0 if is_nodata else 0.0

    base_dist_cost = distance_3d
    slope_penalty = distance_3d * (weights.weight_slope * slope_factor)
    cross_slope_penalty = distance_3d * (weights.weight_slope * cross_factor)
    rough_penalty = distance_3d * (weights.weight_roughness * rough_factor)
    hazard_penalty = distance_3d * (weights.weight_hazard * hazard_factor)

    total_cost = base_dist_cost + slope_penalty + cross_slope_penalty + rough_penalty + hazard_penalty + extra_penalty

    breakdown = {
        "base_distance_cost": round(base_dist_cost, 2),
        "slope_penalty": round(slope_penalty + cross_slope_penalty, 2),
        "roughness_penalty": round(rough_penalty, 2),
        "hazard_penalty": round(hazard_penalty, 2),
        "extra_penalty": round(extra_penalty, 2),
    }

    return max(total_cost, distance_3d), breakdown


def calculate_step_relative_effort(
    distance_3d: float,
    along_grade: float,
    cross_grade: float = 0.0,
    gravity_ratio: float = MARS_EARTH_GRAVITY_RATIO,
    suit_load_factor: float = DEFAULT_SUIT_LOAD_FACTOR,
) -> float:
    """Returns dimensionless estimated relative effort (flat-ground equivalent meters)."""
    factor = compute_minetti_relative_effort_factor(
        along_grade=along_grade,
        cross_grade=cross_grade,
        gravity_ratio=gravity_ratio,
        suit_load_factor=suit_load_factor,
    )
    return distance_3d * factor
