"""Marswalk Survivability Scoring Model for Human Astronaut EVA on Mars.

Evaluates human mobility exertion, space suit consumables margin, terrain roughness,
thermal inertia regolith sinkage, return-to-base buffer, and radiation exposure
under nominal Galactic Cosmic Ray (GCR) background and simulated Solar Particle Events (SPE).

REFERENCES:
- Margaria, R. (1938). Sulla fisiologia e specialmente sul consumo energetico della marcia in salita e in discesa.
- Minetti, A. E. et al. (2002). Energy cost of walking and running at extreme uphill and downhill slopes. J. Appl. Physiol.
- Carr, C. E. (2001). Spacesuit metabolic work rates and mobility derating in partial gravity.
- Riley, S. J. et al. (1999). A terrain ruggedness index that quantifies topographic heterogeneity.
- Christensen, P. R. et al. (2001). Mars Global Surveyor THEMIS thermal inertia regolith classification.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContributingFactor(BaseModel):
    """Individual factor contributing to the Marswalk Survivability Index."""

    name: str
    category: str  # "TERRAIN", "CONSUMABLES", "ENVIRONMENT", "RETURN_SAFETY"
    raw_value: float
    unit: str
    penalty_points: float = Field(0.0, description="Deduction from 100 baseline points")
    bonus_points: float = Field(0.0, description="Bonus added (e.g. topographic shielding)")
    status: str  # "NOMINAL", "CAUTION", "CRITICAL", "SHELTERED"
    explanation: str


class MarswalkSurvivabilityScore(BaseModel):
    """Overall Marswalk Survivability Index (0-100) and factor breakdown for an EVA corridor."""

    score: float = Field(..., ge=0.0, le=100.0, description="Overall Marswalk Survivability Index (0-100)")
    category: str = Field(..., description="HIGH_SURVIVABILITY, MODERATE, MARGINAL, CRITICAL")
    mobility_exertion_penalty: float = Field(0.0, description="Penalty for steep uphill/downhill slope exertion")
    terrain_roughness_penalty: float = Field(0.0, description="Penalty for surface roughness (TRI) and tripping hazard")
    eva_consumables_penalty: float = Field(0.0, description="Penalty for suit oxygen and battery consumption margin")
    return_buffer_penalty: float = Field(
        0.0, description="Penalty for insufficient safe turnaround buffer before sunset"
    )
    regolith_sinkage_penalty: float = Field(
        0.0, description="Penalty for low thermal inertia dust and wheel/boot sinkage"
    )
    radiation_exposure_penalty: float = Field(
        0.0, description="Penalty for ambient GCR or acute SPE solar particle flux"
    )
    topographic_shelter_bonus: float = Field(0.0, description="Bonus for proximity to overhang or escarpment shelter")
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    explanation: str = Field(..., description="Plain-language human-understandable evaluation rationale")
    is_spe_active: bool = Field(False, description="Whether simulated Solar Particle Event scenario was evaluated")
    shelter_proximity_meters: float | None = Field(
        None, description="Distance to nearest topographic shelter in meters"
    )
    recommended_shelter_id: str | None = Field(None, description="Identifier of nearest designated terrain shelter")
    disclaimer: str = (
        "Conceptual decision-support score based on terrestrial human terramechanics and NASA analog models. "
        "Not a certified flight safety rating."
    )


# Authoritative Jezero Topographic Shelter Candidates
JEZERO_SHELTER_CANDIDATES = [
    {
        "shelter_id": "shelter_western_rim_overhang",
        "name": "Western Rim North Escarpment Overhang",
        "lon": 77.2150,
        "lat": 18.4600,
        "type": "Basalt Escarpment Overhang",
        "shielding_pct": 82.0,
        "steradian_coverage": 2.6,
        "bearing_strength_kpa": 120.0,
        "description": "12-meter basalt scarp providing >2.6 steradian overhead cosmic ray and solar proton deflection.",
    },
    {
        "shelter_id": "shelter_belva_terraces",
        "name": "Belva Crater Eastern Inner Terraces",
        "lon": 77.3850,
        "lat": 18.4820,
        "type": "Subsurface Impact Depression",
        "shielding_pct": 75.0,
        "steradian_coverage": 2.4,
        "bearing_strength_kpa": 95.0,
        "description": "Depressed crater terrace rim blocking low-angle solar particle flux from eastward trajectory.",
    },
    {
        "shelter_id": "shelter_seitah_swale",
        "name": "Séítah Ridge Inter-Dune Swale",
        "lon": 77.4320,
        "lat": 18.4280,
        "type": "Topographic Trough",
        "shielding_pct": 60.0,
        "steradian_coverage": 1.9,
        "bearing_strength_kpa": 85.0,
        "description": "Competent bedrock pavement swale flanked by 8m olivine cumulate ridges.",
    },
]


def compute_marswalk_survivability(
    distance_km: float,
    max_slope_deg: float,
    average_slope_deg: float,
    roughness_tri: float,
    eva_duration_hours: float,
    turnaround_buffer_min: float,
    thermal_inertia_tiu: float = 385.0,
    is_spe_active: bool = False,
    corridor_midpoint: tuple[float, float] | None = None,
    eva_budget_hours: float = 8.0,
) -> MarswalkSurvivabilityScore:
    """Computes transparent 0-100 Marswalk Survivability Score for an astronaut EVA traverse."""
    factors: list[ContributingFactor] = []

    # 1. Human Mobility & Slope Exertion Penalty (Max 35 pts)
    # Suited astronauts in ~130kg pressurized suits face steep metabolic costs on slopes > 6 deg
    if max_slope_deg <= 6.0:
        p_slope = 0.0
        status_slope = "NOMINAL"
        exp_slope = f"Gentle terrain (peak gradient {max_slope_deg:.1f}° ≤ 6.0°); minimal suited metabolic exertion."
    elif max_slope_deg <= 12.0:
        p_slope = round((max_slope_deg - 6.0) * 3.0, 1)
        status_slope = "CAUTION"
        exp_slope = (
            f"Moderate incline (peak gradient {max_slope_deg:.1f}°); elevated metabolic oxygen and heart rate load."
        )
    elif max_slope_deg <= 14.0:
        p_slope = round(18.0 + (max_slope_deg - 12.0) * 8.5, 1)
        status_slope = "CRITICAL"
        exp_slope = f"Steep escarpment (peak gradient {max_slope_deg:.1f}°); near 14.0° astronaut walking ceiling; severe exertion."
    else:
        p_slope = 35.0
        status_slope = "CRITICAL"
        exp_slope = f"Exceeds 14.0° slope limit ({max_slope_deg:.1f}°); high fall risk and metabolic exhaustion."

    factors.append(
        ContributingFactor(
            name="Human Mobility & Slope Exertion",
            category="TERRAIN",
            raw_value=round(max_slope_deg, 1),
            unit="degrees",
            penalty_points=p_slope,
            bonus_points=0.0,
            status=status_slope,
            explanation=exp_slope,
        )
    )

    # 2. Terrain Roughness & Tripping Hazard (Max 18 pts)
    if roughness_tri <= 0.20:
        p_roughness = 0.0
        status_rough = "NOMINAL"
        exp_rough = f"Smooth competent terrain (TRI {roughness_tri:.2f}m ≤ 0.20m); low ankle/knee torque strain."
    elif roughness_tri <= 0.50:
        p_roughness = round((roughness_tri - 0.20) * 30.0, 1)
        status_rough = "CAUTION"
        exp_rough = f"Moderate surface roughness (TRI {roughness_tri:.2f}m); sub-meter basalt blocks require careful foot placement."
    else:
        p_roughness = min(18.0, round(9.0 + (roughness_tri - 0.50) * 25.0, 1))
        status_rough = "CRITICAL"
        exp_rough = (
            f"High ruggedness (TRI {roughness_tri:.2f}m > 0.50m); elevated spacesuit boot puncture and tripping risk."
        )

    factors.append(
        ContributingFactor(
            name="Surface Ruggedness & Tripping Risk",
            category="TERRAIN",
            raw_value=round(roughness_tri, 2),
            unit="m (TRI)",
            penalty_points=p_roughness,
            bonus_points=0.0,
            status=status_rough,
            explanation=exp_rough,
        )
    )

    # 3. EVA Consumables Reserve Margin (Max 25 pts)
    # Assumes 8.0h nominal PLSS oxygen and battery budget; total transit is outbound + return
    total_transit_hours = eva_duration_hours * 2.0
    margin_hours = max(0.0, eva_budget_hours - total_transit_hours)
    margin_fraction = margin_hours / eva_budget_hours

    if margin_fraction >= 0.40:
        p_eva = 0.0
        status_eva = "NOMINAL"
        exp_eva = f"Ample suit consumables reserve: {margin_hours:.1f}h remaining ({margin_fraction * 100:.0f}% margin ≥ 40%)."
    elif margin_fraction >= 0.20:
        p_eva = round((0.40 - margin_fraction) / 0.20 * 12.0, 1)
        status_eva = "CAUTION"
        exp_eva = f"Moderate consumables reserve: {margin_hours:.1f}h remaining ({margin_fraction * 100:.0f}% margin); plan strict timeline."
    elif margin_fraction > 0.0:
        p_eva = round(12.0 + (0.20 - margin_fraction) / 0.20 * 10.0, 1)
        status_eva = "CRITICAL"
        exp_eva = f"Tight consumables budget: only {margin_hours:.1f}h reserve ({margin_fraction * 100:.0f}% margin < 20%); minimal abort buffer."
    else:
        p_eva = 25.0
        status_eva = "CRITICAL"
        exp_eva = f"Negative consumables margin! Round-trip transit ({total_transit_hours:.1f}h) exceeds suit budget ({eva_budget_hours:.1f}h)."

    factors.append(
        ContributingFactor(
            name="Suit Consumables Reserve Margin",
            category="CONSUMABLES",
            raw_value=round(margin_hours, 1),
            unit="hours reserve",
            penalty_points=p_eva,
            bonus_points=0.0,
            status=status_eva,
            explanation=exp_eva,
        )
    )

    # 4. Safe Turnaround & Sunset Buffer (Max 20 pts)
    # Astronaut must return before local sunset (17:30 LTST)
    if turnaround_buffer_min >= 120.0:
        p_return = 0.0
        status_ret = "NOMINAL"
        exp_ret = f"Robust return buffer: +{turnaround_buffer_min:.0f} min before local sunset; safe return assured."
    elif turnaround_buffer_min >= 60.0:
        p_return = round((120.0 - turnaround_buffer_min) / 60.0 * 8.0, 1)
        status_ret = "CAUTION"
        exp_ret = f"Acceptable return buffer: +{turnaround_buffer_min:.0f} min before local sunset; prioritize timely departure."
    elif turnaround_buffer_min > 0.0:
        p_return = round(8.0 + (60.0 - turnaround_buffer_min) / 60.0 * 8.0, 1)
        status_ret = "CRITICAL"
        exp_ret = (
            f"Narrow return margin: +{turnaround_buffer_min:.0f} min; sunset shadow ingress risks optical navigation."
        )
    else:
        p_return = 20.0
        status_ret = "CRITICAL"
        exp_ret = "Zero or negative return buffer! Nightfall ingress expected before habitat return."

    factors.append(
        ContributingFactor(
            name="Safe Turnaround & Sunset Buffer",
            category="RETURN_SAFETY",
            raw_value=round(turnaround_buffer_min, 0),
            unit="minutes",
            penalty_points=p_return,
            bonus_points=0.0,
            status=status_ret,
            explanation=exp_ret,
        )
    )

    # 5. Regolith Competence & Boot Sinkage (THEMIS proxy) (Max 12 pts)
    if thermal_inertia_tiu >= 300.0:
        p_sinkage = 0.0
        status_sink = "NOMINAL"
        exp_sink = f"Competent cemented bedrock (THEMIS {thermal_inertia_tiu:.0f} tiu ≥ 300 tiu); firm boot traction, sinkage < 1.5 cm."
    elif thermal_inertia_tiu >= 180.0:
        p_sinkage = round((300.0 - thermal_inertia_tiu) / 120.0 * 6.0, 1)
        status_sink = "CAUTION"
        exp_sink = f"Indurated sand/duricrust (THEMIS {thermal_inertia_tiu:.0f} tiu); moderate boot slip, slight metabolic penalty."
    else:
        p_sinkage = min(12.0, round(6.0 + (180.0 - thermal_inertia_tiu) / 80.0 * 6.0, 1))
        status_sink = "CRITICAL"
        exp_sink = f"Unconsolidated aeolian dust mantle (THEMIS {thermal_inertia_tiu:.0f} tiu < 180 tiu); boot sinkage > 5 cm, heavy slip."

    factors.append(
        ContributingFactor(
            name="Regolith Footing & Dust Sinkage (THEMIS)",
            category="TERRAIN",
            raw_value=round(thermal_inertia_tiu, 0),
            unit="tiu (J m⁻² K⁻¹ s⁻½)",
            penalty_points=p_sinkage,
            bonus_points=0.0,
            status=status_sink,
            explanation=exp_sink,
        )
    )

    # 6. Environmental Radiation & Solar Particle Event (SPE) (Max 35 pts)
    nearest_shelter = None
    min_dist_shelter_m = None

    if corridor_midpoint:
        mid_lon, mid_lat = corridor_midpoint
        # Calculate rough Euclidean distance to nearest shelter in meters
        dists = []
        for s in JEZERO_SHELTER_CANDIDATES:
            d_deg = ((mid_lon - s["lon"]) ** 2 + (mid_lat - s["lat"]) ** 2) ** 0.5
            d_m = d_deg * 59200.0  # ~59.2 km per degree on Mars at 18°N
            dists.append((d_m, s))
        dists.sort(key=lambda x: x[0])
        min_dist_shelter_m, nearest_shelter = dists[0]

    if not is_spe_active:
        # Nominal background Galactic Cosmic Ray (GCR) exposure (~0.05 mSv/h)
        p_radiation = 2.0
        b_shelter = 0.0
        status_rad = "NOMINAL"
        exp_rad = "Nominal background GCR flux (~0.05 mSv/h); no acute space weather radiation event detected."
    else:
        # Simulated Solar Particle Event (SPE) active (~48.5 mSv/h unshielded flux)
        base_spe_penalty = 30.0
        # If corridor is within 1,200m of a topographic shelter, apply shielding mitigation
        if min_dist_shelter_m is not None and min_dist_shelter_m <= 1200.0:
            shield_factor = (1200.0 - min_dist_shelter_m) / 1200.0
            p_radiation = round(max(8.0, base_spe_penalty - shield_factor * 18.0), 1)
            b_shelter = round(shield_factor * 8.0, 1)
            status_rad = "SHELTERED"
            exp_rad = (
                f"SIMULATED SPE ACTIVE (Class X2.5): Severe proton flux (~48.5 mSv/h). "
                f"Mitigated by proximity to {nearest_shelter['name']} ({min_dist_shelter_m:.0f}m away, {nearest_shelter['shielding_pct']}% overhead shielding)."
            )
        else:
            p_radiation = 32.0
            b_shelter = 0.0
            status_rad = "CRITICAL"
            exp_rad = (
                "SIMULATED SPE ACTIVE (Class X2.5): Severe unshielded proton flux (~48.5 mSv/h). "
                "Open terrain offers zero overhead deflection; immediate abort to habitat or shelter mandated."
            )

    factors.append(
        ContributingFactor(
            name="Space Environment & Radiation Flux",
            category="ENVIRONMENT",
            raw_value=48.5 if is_spe_active else 0.05,
            unit="mSv/h (flux)",
            penalty_points=p_radiation,
            bonus_points=b_shelter,
            status=status_rad,
            explanation=exp_rad,
        )
    )

    # Total Score Calculation: Start at 100, subtract penalties, add shelter bonus, clamp to [0, 100]
    total_penalty = p_slope + p_roughness + p_eva + p_return + p_sinkage + p_radiation
    raw_score = 100.0 - total_penalty + b_shelter
    final_score = round(max(0.0, min(100.0, raw_score)), 1)

    # Classify Category
    if final_score >= 80.0:
        category = "HIGH_SURVIVABILITY"
    elif final_score >= 60.0:
        category = "MODERATE"
    elif final_score >= 40.0:
        category = "MARGINAL"
    else:
        category = "CRITICAL"

    # Human-understandable summary explanation
    if is_spe_active:
        explanation = (
            f"Marswalk Survivability Score {final_score:.0f}/100 ({category}). "
            f"Simulated Solar Particle Event active. Corridor hazard profile is dominated by acute radiation flux; "
            f"{'shelter proximity mitigates exposure' if b_shelter > 0 else 'distance from natural terrain shelter imposes heavy safety penalty'}. "
            f"Peak slope {max_slope_deg:.1f}°, consumables reserve {margin_hours:.1f}h."
        )
    else:
        explanation = (
            f"Marswalk Survivability Score {final_score:.0f}/100 ({category}). "
            f"Corridor demonstrates {'strong operational margin' if final_score >= 80 else 'moderate operational constraints'}. "
            f"Peak slope {max_slope_deg:.1f}° ({status_slope}), roughness TRI {roughness_tri:.2f}m, "
            f"consumables margin {margin_hours:.1f}h remaining, return buffer +{turnaround_buffer_min:.0f} min before local sunset."
        )

    return MarswalkSurvivabilityScore(
        score=final_score,
        category=category,
        mobility_exertion_penalty=p_slope,
        terrain_roughness_penalty=p_roughness,
        eva_consumables_penalty=p_eva,
        return_buffer_penalty=p_return,
        regolith_sinkage_penalty=p_sinkage,
        radiation_exposure_penalty=p_radiation,
        topographic_shelter_bonus=b_shelter,
        contributing_factors=factors,
        explanation=explanation,
        is_spe_active=is_spe_active,
        shelter_proximity_meters=round(min_dist_shelter_m, 1) if min_dist_shelter_m else None,
        recommended_shelter_id=nearest_shelter["shelter_id"] if nearest_shelter else None,
    )
