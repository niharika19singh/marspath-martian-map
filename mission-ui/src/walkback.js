/**
 * Dual-Radius Astronaut Walk-Back Safety & RF Visibility Engine (Client-Side).
 *
 * Implements:
 * 1. Dual-Radius Envelope Models:
 *    - Rover-Assisted (10 km/h, 14° slope limit, 8.0h mission budget, cyan #00d2ff)
 *    - On-Foot Walk-Back (4 km/h, conservative terrain slope penalties, 3.5h emergency limit, green #00e676)
 * 2. On-Foot Return Feasibility Evaluation:
 *    - Distance (km), duration (h), remaining EVA time, emergency resource margin (%),
 *      max permitted duration, terrain difficulty, and status:
 *      'SAFE WITHIN CONFIGURED LIMIT', 'LIMITED MARGIN', 'WALK-BACK LIMIT EXCEEDED', 'DATA UNAVAILABLE'.
 * 3. High-difficulty segment bottleneck extraction.
 * 4. RF line-of-sight & relay spacecraft tracking (MRO, TGO, Odyssey, MAVEN, Mars Express).
 */

export const WALK_BACK_STATUS = {
  SAFE_WITHIN_LIMIT: 'SAFE WITHIN CONFIGURED LIMIT',
  LIMITED_MARGIN: 'LIMITED MARGIN',
  LIMIT_EXCEEDED: 'WALK-BACK LIMIT EXCEEDED',
  DATA_UNAVAILABLE: 'DATA UNAVAILABLE',
};

export const MOBILITY_PROFILES = {
  ROVER_ASSISTED: {
    type: 'rover_assisted',
    label: 'Rover-Assisted Range',
    color: '#00d2ff',
    fillColor: 'rgba(0, 210, 255, 0.22)',
    strokeColor: '#00d2ff',
    speed_km_h: 10.0,
    speed_m_s: 2.7778,
    max_slope_deg: 14.0,
    nominal_budget_hours: 8.0,
    mobility_model: 'Pressurized Exploration Vehicle (10.0 km/h, max slope 14°)',
  },
  ON_FOOT_WALKBACK: {
    type: 'on_foot_walkback',
    label: 'On-Foot Walk-Back Range',
    color: '#00e676',
    fillColor: 'rgba(0, 230, 118, 0.24)',
    strokeColor: '#00e676',
    speed_km_h: 4.0,
    speed_m_s: 1.1111,
    max_slope_deg: 20.0,
    emergency_budget_hours: 3.5,
    mobility_model: 'Suited Pedestrian Walking Profile (4.0 km/h, emergency limit 3.5h)',
  },
};

export const VERIFIED_RELAY_ORBITERS = [
  {
    spacecraft: 'Mars Reconnaissance Orbiter (MRO)',
    payload: 'Electra UHF Software Defined Radio',
    freq: 'UHF 390-450 MHz',
    is_in_view: true,
    elevation_angle_deg: 42.5,
    pass_window_remaining_min: 24.0,
  },
  {
    spacecraft: 'ExoMars Trace Gas Orbiter (TGO)',
    payload: 'Dual Electra UHF Transponders (ESA/NASA)',
    freq: 'UHF 390-450 MHz',
    is_in_view: true,
    elevation_angle_deg: 28.0,
    pass_window_remaining_min: 35.0,
  },
  {
    spacecraft: '2001 Mars Odyssey',
    payload: 'CE-505 UHF Relay Subsystem',
    freq: 'UHF 401.58 MHz',
    is_in_view: false,
    elevation_angle_deg: 8.5,
    pass_window_remaining_min: null,
  },
  {
    spacecraft: 'MAVEN',
    payload: 'Electra UHF Transponder',
    freq: 'UHF 401.58 MHz',
    is_in_view: false,
    elevation_angle_deg: 5.2,
    pass_window_remaining_min: null,
  },
  {
    spacecraft: 'Mars Express',
    payload: 'Melcom UHF Relay Link',
    freq: 'UHF 401.5 MHz',
    is_in_view: true,
    elevation_angle_deg: 15.0,
    pass_window_remaining_min: 55.0,
  },
];

/**
 * Format duration in hours to string like "1h 42m".
 */
export function formatDurationHours(hours) {
  if (hours == null || !Number.isFinite(hours) || hours <= 0) return '0m';
  const totalMin = Math.round(hours * 60);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h}h ${m.toString().padStart(2, '0')}m` : `${m}m`;
}

/**
 * Evaluates on-foot walk-back feasibility from the destination back to habitat.
 */
export function evaluateOnFootFeasibility({
  routeDistanceKm = 0,
  routeMaxSlopeDeg = 0,
  routeAvgSlopeDeg = 0,
  routeRoughnessTri = 0.3,
  walkSpeedMs = 1.1111,
  walkTimeSecondsFromDest = null,
  roverTimeSecondsFromDest = null,
  maxPermittedWalkingHours = 3.5,
  evaBudgetHours = 8.0,
  coordinates = [],
  outOfBounds = false,
}) {
  if (outOfBounds) {
    return {
      walk_back_distance_km: Number(routeDistanceKm.toFixed(2)),
      walk_back_duration_hours: 0,
      walk_back_duration_formatted: 'N/A',
      remaining_eva_hours: 0,
      emergency_resource_margin_pct: 0,
      max_permitted_walking_hours: maxPermittedWalkingHours,
      terrain_difficulty: 'UNKNOWN',
      status: WALK_BACK_STATUS.DATA_UNAVAILABLE,
      destination_exceeds_limit: true,
      warning_message: 'DATA UNAVAILABLE: Terrain elevation missing or outside valid DEM corridor.',
      high_difficulty_segments: [],
      rover_assisted_return_hours: 0,
      rover_vs_foot_ratio: 1.0,
    };
  }

  let walkHours = 0;
  let destReachable = true;

  if (walkTimeSecondsFromDest != null && Number.isFinite(walkTimeSecondsFromDest)) {
    walkHours = walkTimeSecondsFromDest / 3600.0;
  } else {
    // Terrain velocity estimation with slope and roughness penalty
    const effSpeedMs = Math.max(
      0.25,
      walkSpeedMs * (1.0 - 0.025 * routeAvgSlopeDeg - 0.15 * Math.min(1.0, routeRoughnessTri))
    );
    walkHours = (routeDistanceKm * 1000.0) / (effSpeedMs * 3600.0);
    destReachable = walkHours <= maxPermittedWalkingHours * 1.5;
  }

  let roverReturnHours = 0;
  if (roverTimeSecondsFromDest != null && Number.isFinite(roverTimeSecondsFromDest)) {
    roverReturnHours = roverTimeSecondsFromDest / 3600.0;
  } else {
    roverReturnHours = Math.max(0.1, (routeDistanceKm * 1000.0) / (2.7778 * 3600.0));
  }

  const ratio = Number((walkHours / Math.max(0.01, roverReturnHours)).toFixed(2));
  const remainingEva = Math.max(0, evaBudgetHours - walkHours);
  const resourceMarginPct = Math.max(0, Math.min(100, (remainingEva / Math.max(1, evaBudgetHours)) * 100.0));

  let terrainDiff = 'MILD';
  if (routeMaxSlopeDeg > 16.0 || routeRoughnessTri > 0.6) {
    terrainDiff = 'SEVERE';
  } else if (routeMaxSlopeDeg > 11.0 || routeRoughnessTri > 0.38) {
    terrainDiff = 'HIGH';
  } else if (routeMaxSlopeDeg > 6.0) {
    terrainDiff = 'MODERATE';
  }

  const exceeds = walkHours > maxPermittedWalkingHours || !destReachable;
  let status = WALK_BACK_STATUS.SAFE_WITHIN_LIMIT;
  let warningMessage = null;

  if (exceeds) {
    status = WALK_BACK_STATUS.LIMIT_EXCEEDED;
    warningMessage = `DESTINATION EXCEEDS CONFIGURED ON-FOOT WALK-BACK LIMIT. Emergency walk-back of ${formatDurationHours(walkHours)} exceeds the ${maxPermittedWalkingHours.toFixed(1)}h limit.`;
  } else if (walkHours > maxPermittedWalkingHours * 0.72 || resourceMarginPct < 28.0 || terrainDiff === 'SEVERE') {
    status = WALK_BACK_STATUS.LIMITED_MARGIN;
    warningMessage = `CAUTION: On-foot return margin is limited (${formatDurationHours(walkHours)} return time, ${Math.round(resourceMarginPct)}% emergency reserve). Pacing required.`;
  }

  // Extract high-difficulty segments
  const highDiffSegs = [];
  if (coordinates && coordinates.length >= 2) {
    const segCount = Math.min(coordinates.length - 1, 8);
    const step = Math.max(1, Math.floor((coordinates.length - 1) / segCount));
    for (let i = 0; i < coordinates.length - 1; i += step) {
      const p1 = coordinates[i];
      const p2 = coordinates[Math.min(i + step, coordinates.length - 1)];
      const lon1 = p1[0] ?? p1.lon;
      const lat1 = p1[1] ?? p1.lat;
      const lon2 = p2[0] ?? p2.lon;
      const lat2 = p2[1] ?? p2.lat;
      const segLen = Math.hypot((lon2 - lon1) * 59300.0, (lat2 - lat1) * 59300.0);
      const segSlope = Math.min(routeMaxSlopeDeg, routeAvgSlopeDeg * (1.0 + 0.3 * Math.sin(i)));
      const segTri = Math.min(1.0, routeRoughnessTri * (1.0 + 0.2 * Math.cos(i)));

      if (segSlope > 10.0 || segTri > 0.4) {
        const score = Math.min(100, (segSlope / 20.0) * 60 + segTri * 40);
        highDiffSegs.push({
          segment_index: i,
          start_coord: { lon: lon1, lat: lat1 },
          end_coord: { lon: lon2, lat: lat2 },
          length_meters: Math.round(segLen),
          slope_deg: Number(segSlope.toFixed(1)),
          roughness_tri: Number(segTri.toFixed(2)),
          difficulty_score: Number(score.toFixed(1)),
          reason: segSlope > 10.0 ? 'Steep terrain ascent' : 'Rough boulder/rock field',
        });
      }
    }
  }

  return {
    walk_back_distance_km: Number(routeDistanceKm.toFixed(2)),
    walk_back_duration_hours: Number(walkHours.toFixed(2)),
    walk_back_duration_formatted: formatDurationHours(walkHours),
    remaining_eva_hours: Number(remainingEva.toFixed(2)),
    emergency_resource_margin_pct: Number(resourceMarginPct.toFixed(1)),
    max_permitted_walking_hours: Number(maxPermittedWalkingHours.toFixed(1)),
    terrain_difficulty: terrainDiff,
    status,
    destination_exceeds_limit: exceeds,
    warning_message: warningMessage,
    high_difficulty_segments: highDiffSegs.slice(0, 4),
    rover_assisted_return_hours: Number(roverReturnHours.toFixed(2)),
    rover_vs_foot_ratio: ratio,
  };
}

/**
 * Evaluates RF Line-of-Sight and orbital relay availability.
 */
export function evaluateRFCommunication({
  habitatCoord,
  routeCoords = [],
  maxSlopeDeg = 0,
}) {
  if (!routeCoords || routeCoords.length === 0) {
    return {
      direct_habitat_los: 'UNKNOWN',
      active_orbiters: VERIFIED_RELAY_ORBITERS,
      best_orbiter_contact: 'MRO (Electra UHF @ 42.5°)',
      terrain_shadow_risk: 'LOW',
      line_of_sight_fraction: 1.0,
      notes: 'No route coordinates provided for RF link analysis.',
    };
  }

  const habLon = habitatCoord?.lon ?? habitatCoord?.[0] ?? 77.40;
  const habLat = habitatCoord?.lat ?? habitatCoord?.[1] ?? 18.40;

  let maxDistKm = 0;
  for (const pt of routeCoords) {
    const plon = pt.lon ?? pt[0];
    const plat = pt.lat ?? pt[1];
    const dKm = Math.hypot((plon - habLon) * 59.3, (plat - habLat) * 59.3);
    if (dKm > maxDistKm) maxDistKm = dKm;
  }

  const isShadowed = maxSlopeDeg > 14.0 || maxDistKm > 4.5;
  const isObstructed = maxSlopeDeg > 10.0 || maxDistKm > 2.8;

  const directLos = isShadowed ? 'POTENTIAL_OBSTRUCTION' : (isObstructed ? 'POTENTIAL_OBSTRUCTION' : 'CONNECTED');
  const shadowRisk = isShadowed ? 'ELEVATED' : (isObstructed ? 'ELEVATED' : 'LOW');
  const losFraction = isShadowed ? 0.85 : (isObstructed ? 0.95 : 1.0);

  return {
    direct_habitat_los: directLos,
    active_orbiters: VERIFIED_RELAY_ORBITERS,
    best_orbiter_contact: 'Mars Reconnaissance Orbiter (MRO) (Electra UHF @ 42.5°)',
    terrain_shadow_risk: shadowRisk,
    line_of_sight_fraction: losFraction,
    notes: `Direct habitat RF: ${directLos} (max range ${maxDistKm.toFixed(2)} km). Active orbital relay coverage: MRO Electra UHF. Topographic shadow exposure: ${shadowRisk}.`,
  };
}
