/**
 * Transparent Marswalk Survivability Scoring Model & Solar Storm Simulator.
 *
 * Implements the normalized 5-factor weighted decision-support index:
 * Score = 100 × (0.25 × SlopeSafety + 0.25 × TerrainSafety + 0.20 × TimeSafety + 0.20 × ReturnSafety + 0.10 × DistanceSafety)
 *
 * Calibrated against Martian terrain mechanics and NASA EVA analog protocols.
 * All factors normalized strictly to [0.0, 1.0].
 */

export const DEFAULT_SURVIVABILITY_WEIGHTS = {
  slope: 0.25,
  terrain: 0.25,
  time: 0.20,
  return: 0.20,
  distance: 0.10,
};

export const SURVIVABILITY_TIERS = {
  HIGHER: {
    min: 80,
    max: 100,
    label: 'Higher modeled survivability',
    badge: 'OPTIMAL',
    color: '#00e676',
    statusClass: 'status-optimal',
  },
  MODERATE: {
    min: 60,
    max: 79,
    label: 'Moderate modeled survivability',
    badge: 'MODERATE',
    color: '#a3e635',
    statusClass: 'status-moderate',
  },
  ELEVATED_RISK: {
    min: 40,
    max: 59,
    label: 'Elevated modeled risk',
    badge: 'ELEVATED RISK',
    color: '#f59e0b',
    statusClass: 'status-caution',
  },
  LOW: {
    min: 0,
    max: 39,
    label: 'Low modeled survivability',
    badge: 'LOW SURVIVABILITY',
    color: '#ef4444',
    statusClass: 'status-critical',
  },
};

export function getSurvivabilityTier(score) {
  const val = Math.max(0, Math.min(100, Number(score) || 0));
  if (val >= 80) return SURVIVABILITY_TIERS.HIGHER;
  if (val >= 60) return SURVIVABILITY_TIERS.MODERATE;
  if (val >= 40) return SURVIVABILITY_TIERS.ELEVATED_RISK;
  return SURVIVABILITY_TIERS.LOW;
}

/**
 * Calculates normalized 0-100 Marswalk Survivability Score and factor breakdown.
 */
export function calculateMarswalkScore({
  maxSlopeDeg = 4.2,
  roughnessTri = 0.25,
  durationHours = 0.85,
  evaBudgetHours = 8.0,
  distanceKm = 1.42,
  emergencyMarginPct = 80.0,
  isStormActive = false,
  shelterDistanceM = null,
  weights = DEFAULT_SURVIVABILITY_WEIGHTS,
}) {
  // 1. SlopeSafety [0, 1] — 14.0 deg maximum suited astronaut walking ceiling
  const slopeSafety = Math.max(0, Math.min(1, 1 - (Math.max(0, maxSlopeDeg - 1.5) / 12.5)));

  // 2. TerrainSafety [0, 1] — Terrain Ruggedness Index (TRI) normalized between 0.10m and 0.60m
  const terrainSafety = Math.max(0, Math.min(1, 1 - (Math.max(0, roughnessTri - 0.10) / 0.50)));

  // 3. TimeSafety [0, 1] — Estimated traverse duration relative to configured EVA budget
  const timeSafety = Math.max(0, Math.min(1, 1 - (durationHours / Math.max(1.0, evaBudgetHours))));

  // 4. ReturnSafety [0, 1] — Emergency life-support margin from walk-back return
  // If storm is active, emergency return ceiling tightens by 30%
  let effectiveMarginPct = emergencyMarginPct;
  if (isStormActive) {
    // Tightened envelope adjustment (-30% safety margin buffer)
    effectiveMarginPct = Math.max(0, emergencyMarginPct - 30.0);
  }
  const returnSafety = Math.max(0, Math.min(1, effectiveMarginPct / 100.0));

  // 5. DistanceSafety [0, 1] — Outbound traverse distance relative to 5.0 km nominal radius
  const distanceSafety = Math.max(0, Math.min(1, 1 - (distanceKm / 5.0)));

  // Nominal Weighted Score [0, 100]
  const nominalScore = 100 * (
    (weights.slope * slopeSafety) +
    (weights.terrain * terrainSafety) +
    (weights.time * timeSafety) +
    (weights.return * returnSafety) +
    (weights.distance * distanceSafety)
  );

  // Solar Storm Radiation Adjustment
  let stormDeduction = 0;
  let shelterBonus = 0;
  if (isStormActive) {
    const baseStormPenalty = 28.0; // Simulated acute proton flux penalty (~48.5 mSv/h)
    if (shelterDistanceM !== null && shelterDistanceM <= 1200) {
      // Proximity to natural topographic shelter reduces radiation risk
      const proximityFactor = (1200 - shelterDistanceM) / 1200;
      shelterBonus = Math.round(proximityFactor * 16.0 * 10) / 10;
      stormDeduction = Math.round((baseStormPenalty - shelterBonus) * 10) / 10;
    } else {
      stormDeduction = baseStormPenalty;
    }
  }

  const finalScore = Math.round(Math.max(0, Math.min(100, nominalScore - stormDeduction)) * 10) / 10;
  const tier = getSurvivabilityTier(finalScore);

  return {
    score: finalScore,
    nominal_score: Math.round(nominalScore * 10) / 10,
    tier,
    is_storm_active: isStormActive,
    storm_deduction: stormDeduction,
    shelter_bonus: shelterBonus,
    envelope_tightened: isStormActive,
    envelope_tightening_pct: isStormActive ? 30 : 0,
    factors: {
      slope: {
        name: 'Slope Safety',
        weight: weights.slope,
        raw: `${maxSlopeDeg.toFixed(1)}°`,
        normalized: Math.round(slopeSafety * 100) / 100,
        contribution: Math.round(weights.slope * slopeSafety * 100 * 10) / 10,
        status: maxSlopeDeg <= 6 ? 'NOMINAL' : maxSlopeDeg <= 12 ? 'CAUTION' : 'CRITICAL',
        assumption: 'Max 14.0° suited walking ceiling; metabolic rate scales non-linearly above 6°',
      },
      terrain: {
        name: 'Terrain Ruggedness',
        weight: weights.terrain,
        raw: `TRI ${roughnessTri.toFixed(2)}m`,
        normalized: Math.round(terrainSafety * 100) / 100,
        contribution: Math.round(weights.terrain * terrainSafety * 100 * 10) / 10,
        status: roughnessTri <= 0.20 ? 'NOMINAL' : roughnessTri <= 0.45 ? 'CAUTION' : 'CRITICAL',
        assumption: 'Sub-meter basalt blockiness and tripping hazard; nominal baseline ≤ 0.10m',
      },
      time: {
        name: 'EVA Duration',
        weight: weights.time,
        raw: `${durationHours.toFixed(2)}h`,
        normalized: Math.round(timeSafety * 100) / 100,
        contribution: Math.round(weights.time * timeSafety * 100 * 10) / 10,
        status: durationHours <= 3.0 ? 'NOMINAL' : durationHours <= 5.5 ? 'CAUTION' : 'CRITICAL',
        assumption: `Traverse duration consumed against configured ${evaBudgetHours.toFixed(1)}h PLSS tank`,
      },
      return_safety: {
        name: 'Return-to-Base Feasibility',
        weight: weights.return,
        raw: `${effectiveMarginPct.toFixed(0)}% margin`,
        normalized: Math.round(returnSafety * 100) / 100,
        contribution: Math.round(weights.return * returnSafety * 100 * 10) / 10,
        status: effectiveMarginPct >= 40 ? 'NOMINAL' : effectiveMarginPct >= 20 ? 'CAUTION' : 'CRITICAL',
        assumption: isStormActive
          ? 'Safe return envelope tightened by 30% due to acute radiation hazard'
          : 'Derived from backward-Dijkstra emergency suited walk-back model (≤ 3.5h ceiling)',
      },
      distance: {
        name: 'Traverse Distance',
        weight: weights.distance,
        raw: `${distanceKm.toFixed(2)} km`,
        normalized: Math.round(distanceSafety * 100) / 100,
        contribution: Math.round(weights.distance * distanceSafety * 100 * 10) / 10,
        status: distanceKm <= 2.0 ? 'NOMINAL' : distanceKm <= 3.5 ? 'CAUTION' : 'CRITICAL',
        assumption: 'Distance relative to 5.0 km nominal autonomous pedestrian radius',
      },
    },
    formula: 'Score = 100 × (0.25 × SlopeSafety + 0.25 × TerrainSafety + 0.20 × TimeSafety + 0.20 × ReturnSafety + 0.10 × DistanceSafety)',
    disclaimer: 'Decision-support index based on mathematical analog models; not a scientifically certified flight safety probability.',
  };
}
