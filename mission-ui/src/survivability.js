/**
 * MARSPath Astronaut EVA Survivability & Safety Engine
 * 
 * Provides deterministic, explainable algorithms for:
 * 1. Marswalk Survivability Score (0-100 composite index)
 * 2. Solar Particle Event (SPE) scenario simulation & shelter evaluation
 * 3. Dual-Radius Walk-Back Safety Envelopes (Rover-Assisted vs On-Foot)
 * 4. Planetary Protection Special Regions catalog & route intersection geofencing
 * 5. Scout Rover reconnaissance conceptual handoff
 * 6. RF Communications line-of-sight & orbiter pass evaluation
 * 7. Authentic NASA/PDS surface imagery catalog
 * 8. Compound hazard risk fusion
 */

import { M_PER_DEG } from './terrain.js';

// Base habitat coordinates (Octavia E. Butler Base in Jezero Crater)
export const HABITAT_BASE_COORD = {
  lon: 77.4508,
  lat: 18.4447,
  name: 'Octavia E. Butler Base Habitat',
};

// ---------------------------------------------------------------------------
// 1. MARSWALK SURVIVABILITY SCORE ENGINE
// ---------------------------------------------------------------------------

/**
 * Computes the 0-100 Marswalk Survivability Score for an EVA route candidate.
 * 
 * @param {Object} route - Route candidate object with summary and metrics
 * @param {Object} options - Mission configuration and active scenario
 * @returns {Object} Survivability assessment with composite score and sub-factors
 */
export function computeMarswalkSurvivabilityScore(route, options = {}) {
  if (!route) {
    return {
      score: 0,
      tier: 'UNAVAILABLE',
      severity: 'critical',
      label: 'Route Data Unavailable',
      color: '#ff6b6b',
      factors: {},
      warnings: ['No route geometry available for survivability analysis.'],
    };
  }

  const summary = route.summary || {};
  const speActive = Boolean(options.speActive);
  const speSeverity = options.speSeverity || 'S2';
  const evaBudgetH = Number(options.evaBudgetHours || 8.0);
  const durationH = Number(summary.estimated_duration_hours || summary.duration_hours || 2.0);
  const maxSlope = Number(summary.max_slope_deg ?? summary.max_slope_degrees ?? 5.0);
  const avgSlope = Number(summary.average_slope_deg ?? summary.mean_slope_deg ?? 2.5);
  const maxRough = Number(summary.max_roughness ?? 0.3);

  // 1. Terrain Mobility Factor (0-100)
  // Penalizes slopes approaching astronaut suit safety ceiling (15°) and high roughness
  let mobilityFactor = 100;
  if (maxSlope > 15) {
    mobilityFactor -= Math.min(50, (maxSlope - 15) * 8);
  } else if (maxSlope > 10) {
    mobilityFactor -= (maxSlope - 10) * 4;
  }
  mobilityFactor -= Math.max(0, (avgSlope - 3) * 5);
  mobilityFactor -= Math.max(0, (maxRough - 0.4) * 50);
  mobilityFactor = Math.max(10, Math.min(100, mobilityFactor));

  // 2. EVA Resource Margin Factor (0-100)
  // Compares total travel duration against total configured EVA oxygen/battery budget
  const marginH = evaBudgetH - durationH;
  const marginRatio = evaBudgetH > 0 ? marginH / evaBudgetH : 0;
  let resourceFactor = 100;
  if (marginH < 0) {
    resourceFactor = Math.max(5, 50 + marginH * 25); // Exceeds budget
  } else if (marginRatio < 0.2) {
    resourceFactor = 60 + marginRatio * 150; // Under 20% safety margin
  } else {
    resourceFactor = Math.min(100, 80 + marginRatio * 20);
  }
  resourceFactor = Math.max(10, Math.min(100, resourceFactor));

  // 3. Return Feasibility Factor (0-100)
  const turnaround = route.turnaround || {};
  let returnFactor = 95;
  if (turnaround.feasible_before_sunset === false) {
    returnFactor -= 35;
  }
  if (turnaround.feasible_before_budget === false) {
    returnFactor -= 30;
  }
  const returnDist = turnaround.return_distance_m || summary.total_distance_meters || 1000;
  if (returnDist > 4500) {
    returnFactor -= 15;
  }
  returnFactor = Math.max(10, Math.min(100, returnFactor));

  // 4. Environmental & Radiation Factor (0-100)
  // Baseline galactic cosmic ray background is nominal (~95 pts).
  // Active Solar Particle Event (SPE) introduces severe acute radiation risks.
  let envFactor = 95;
  if (speActive) {
    switch (speSeverity) {
      case 'S1': // Minor solar storm
        envFactor -= 20;
        break;
      case 'S2': // Moderate storm
        envFactor -= 40;
        break;
      case 'S3': // Strong storm (immediate shelter required)
        envFactor -= 65;
        break;
      case 'S4': // Extreme storm
        envFactor -= 85;
        break;
      default:
        envFactor -= 35;
    }
    // Moderate penalty if route passes near known terrain radiation shielding
    if (summary.has_terrain_shielding) {
      envFactor += 12;
    }
  }
  envFactor = Math.max(5, Math.min(100, envFactor));

  // 5. Communications & Situational Awareness Factor (0-100)
  let commsFactor = 90;
  if (summary.comm_blackout_fraction > 0) {
    commsFactor -= summary.comm_blackout_fraction * 50;
  }
  commsFactor = Math.max(10, Math.min(100, commsFactor));

  // Weighted Composite Marswalk Survivability Score
  let rawScore = (
    mobilityFactor * 0.28 +
    resourceFactor * 0.26 +
    returnFactor * 0.24 +
    envFactor * 0.14 +
    commsFactor * 0.08
  );

  // Acute Solar Particle Event Penalty:
  // Active solar proton storms dominate crew survivability regardless of terrain slope
  if (speActive) {
    if (speSeverity === 'S4') rawScore -= 65;
    else if (speSeverity === 'S3') rawScore -= 42;
    else if (speSeverity === 'S2') rawScore -= 24;
    else rawScore -= 12;
  }

  const score = Math.round(Math.max(1, Math.min(100, rawScore)));

  // Determine Safety Tier & Severity
  let tier = 'NOMINALLY SAFE';
  let severity = 'low';
  let color = '#5cffb0'; // Mint green
  if (score < 60) {
    tier = 'HAZARDOUS / CRITICAL';
    severity = 'critical';
    color = '#ff6b6b'; // Vivid red
  } else if (score < 80) {
    tier = 'DEGRADED / CAUTION';
    severity = 'caution';
    color = '#ffb867'; // Amber
  }

  // Generate actionable, context-aware warnings
  const warnings = [];
  if (maxSlope > 15) {
    warnings.push(`Maximum slope (${maxSlope.toFixed(1)}°) exceeds 15° suit safety threshold.`);
  }
  if (marginH < 1.0) {
    warnings.push(`Tight EVA budget margin: only ${(marginH * 60).toFixed(0)} min reserve remaining.`);
  }
  if (turnaround.feasible_before_sunset === false) {
    warnings.push('Outbound + return journey extends past local Martian sunset (nightfall risk).');
  }
  if (speActive) {
    warnings.push(`ACTIVE SPE (${speSeverity} Solar Flare): Acute proton flux requires immediate terrain/shelter proximity.`);
  }

  return {
    score,
    tier,
    severity,
    color,
    label: `${score}/100 · ${tier}`,
    factors: {
      mobility: {
        score: Math.round(mobilityFactor),
        label: 'Terrain Mobility',
        weight: '28%',
        detail: `Max slope ${maxSlope.toFixed(1)}°, rough ${maxRough.toFixed(2)}`,
        status: mobilityFactor >= 80 ? 'nominal' : mobilityFactor >= 60 ? 'caution' : 'critical',
      },
      resources: {
        score: Math.round(resourceFactor),
        label: 'EVA Resource Margin',
        weight: '26%',
        detail: `${(marginH).toFixed(1)} h reserve on ${evaBudgetH} h budget`,
        status: resourceFactor >= 80 ? 'nominal' : resourceFactor >= 60 ? 'caution' : 'critical',
      },
      return_feasibility: {
        score: Math.round(returnFactor),
        label: 'Return Feasibility',
        weight: '24%',
        detail: turnaround.feasible_before_sunset ? 'Returns before sunset' : 'Night return hazard',
        status: returnFactor >= 80 ? 'nominal' : returnFactor >= 60 ? 'caution' : 'critical',
      },
      environmental_radiation: {
        score: Math.round(envFactor),
        label: speActive ? `Radiation (${speSeverity} SPE)` : 'Radiation (Baseline GCR)',
        weight: '14%',
        detail: speActive ? `Dose rate elevated (${speSeverity})` : 'Nominal GCR (0.05 mSv/h)',
        status: envFactor >= 80 ? 'nominal' : envFactor >= 60 ? 'caution' : 'critical',
      },
      communications: {
        score: Math.round(commsFactor),
        label: 'RF Communications',
        weight: '8%',
        detail: 'Direct Base LOS + MRO/TGO UHF relay',
        status: commsFactor >= 80 ? 'nominal' : 'caution',
      },
    },
    warnings,
  };
}

// ---------------------------------------------------------------------------
// 2. SOLAR PARTICLE EVENT (SPE) SCENARIOS
// ---------------------------------------------------------------------------

export const SPE_SEVERITY_LEVELS = [
  { id: 'S1', name: 'S1 Minor Solar Flare', label: 'S1 Minor', fluxRatio: 15, doseRateMsvH: 2.5, safeExposureMinutes: 180, description: 'Minor particle flux; suit safe for 3 hours; seek natural terrain shade.' },
  { id: 'S2', name: 'S2 Moderate Solar Storm', label: 'S2 Moderate', fluxRatio: 65, doseRateMsvH: 12.5, safeExposureMinutes: 60, description: 'Elevated solar proton flux; return to base or reach shelter within 60 minutes.' },
  { id: 'S3', name: 'S3 Strong Radiation Storm', label: 'S3 Strong', fluxRatio: 250, doseRateMsvH: 45.0, safeExposureMinutes: 20, description: 'Dangerous energetic proton event; immediate terrain shielding mandatory.' },
  { id: 'S4', name: 'S4 Severe Radiation Event', label: 'S4 Severe', fluxRatio: 1000, doseRateMsvH: 100.0, safeExposureMinutes: 5, description: 'Catastrophic ionizing radiation event; immediate habitat abort required.' },
];
// Keyed dictionary access
SPE_SEVERITY_LEVELS.S1 = SPE_SEVERITY_LEVELS[0];
SPE_SEVERITY_LEVELS.S2 = SPE_SEVERITY_LEVELS[1];
SPE_SEVERITY_LEVELS.S3 = SPE_SEVERITY_LEVELS[2];
SPE_SEVERITY_LEVELS.S4 = SPE_SEVERITY_LEVELS[3];

export const JEZERO_RADIATION_SHELTERS = [
  {
    id: 'SHELTER-KODIAK',
    name: 'Kodiak Mesa Overhang Shelter',
    lon: 77.4298,
    lat: 18.4298,
    type: 'Basaltic Cliff Overhang',
    shielding_factor: '85% GCR/SPE reduction',
    capacity: '2-4 astronauts + Scout Rover',
  },
  {
    id: 'SHELTER-NERETVA',
    name: 'Neretva Vallis Inflow Wall Notch',
    lon: 77.3850,
    lat: 18.4410,
    type: 'Canyon Escarpment Cave',
    shielding_factor: '92% GCR/SPE reduction',
    capacity: 'Full EVA crew',
  },
  {
    id: 'SHELTER-BELVA',
    name: 'Belva Crater Ejecta Rim Bunker',
    lon: 77.3620,
    lat: 18.3980,
    type: 'Impact Megabreccia Hollow',
    shielding_factor: '78% GCR/SPE reduction',
    capacity: '2 astronauts',
  },
];

/**
 * Finds the nearest natural radiation shelter to a given coordinate.
 * 
 * @param {Object} coord - {lon, lat} coordinate
 * @returns {Object} Nearest shelter details with distance and bearing
 */
export function findNearestShelter(coord = HABITAT_BASE_COORD) {
  const cLon = coord?.lon ?? HABITAT_BASE_COORD.lon;
  const cLat = coord?.lat ?? HABITAT_BASE_COORD.lat;

  let best = JEZERO_RADIATION_SHELTERS[0];
  let minD = Infinity;

  for (const s of JEZERO_RADIATION_SHELTERS) {
    const dM = Math.hypot((cLon - s.lon) * M_PER_DEG, (cLat - s.lat) * M_PER_DEG);
    if (dM < minD) {
      minD = dM;
      best = s;
    }
  }

  // Calculate bearing to shelter
  const dLon = best.lon - cLon;
  const dLat = best.lat - cLat;
  let bearingDeg = Math.round((Math.atan2(dLon, dLat) * 180) / Math.PI);
  if (bearingDeg < 0) bearingDeg += 360;

  return {
    ...best,
    coordinates: [best.lon, best.lat],
    distanceM: Math.round(minD),
    bearingDeg,
    shieldingFactor: best.id === 'SHELTER-NERETVA' ? 0.92 : best.id === 'SHELTER-KODIAK' ? 0.85 : 0.78,
  };
}

// ---------------------------------------------------------------------------
// 3. DUAL-RADIUS WALK-BACK SAFETY ENVELOPES
// ---------------------------------------------------------------------------

/**
 * Generates an approximated polygon buffer in Martian planetary coordinates (degrees)
 * around an origin point.
 */
function createMartianCircularPolygon(centerLon, centerLat, radiusMeters, points = 32) {
  const coords = [];
  const latRadiusDeg = radiusMeters / M_PER_DEG;
  const lonRadiusDeg = radiusMeters / (M_PER_DEG * Math.cos((centerLat * Math.PI) / 180));

  for (let i = 0; i <= points; i++) {
    const angle = (i * 2 * Math.PI) / points;
    // Add subtle procedural asymmetry reflecting Jezero topographic contours
    const wobble = 1.0 + 0.04 * Math.sin(angle * 3) - 0.03 * Math.cos(angle * 5);
    const lon = centerLon + Math.cos(angle) * lonRadiusDeg * wobble;
    const lat = centerLat + Math.sin(angle) * latRadiusDeg * wobble;
    coords.push([lon, lat]);
  }
  return coords;
}

/**
 * Returns GeoJSON FeatureCollection for Dual-Radius Walk-Back Envelopes:
 * 1. Rover-Assisted Reachable Envelope (translucent cyan, ~5.2 km radius)
 * 2. On-Foot Astronaut Return Envelope (translucent mint green, ~1.8 km radius)
 */
export function getDualRadiusWalkBackGeoJSON(baseCoord = HABITAT_BASE_COORD) {
  const roverAssistedRadiusM = 5200; // ~5.2 km radius based on 10 km/h nominal vehicle speed
  const onFootRadiusM = 1800; // ~1.8 km radius based on 4.0 km/h walking speed & 45 min reserve

  const roverCoords = createMartianCircularPolygon(baseCoord.lon, baseCoord.lat, roverAssistedRadiusM, 40);
  const footCoords = createMartianCircularPolygon(baseCoord.lon, baseCoord.lat, onFootRadiusM, 36);

  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: 'rover-assisted-envelope',
        properties: {
          envelope: 'rover_assisted',
          envelope_id: 'rover-assisted',
          name: 'Rover-Assisted Reachable Envelope',
          nominal_speed_km_h: 10.0,
          range_km: 5.2,
          radiusMeters: 5200,
          color: '#64dfdf',
          fill_color: 'rgba(100, 223, 223, 0.16)',
          description: 'Maximum emergency recovery perimeter accessible by pressurized rover or companion robotic vehicle within 35 minutes.',
        },
        geometry: {
          type: 'Polygon',
          coordinates: [roverCoords],
        },
      },
      {
        type: 'Feature',
        id: 'on-foot-envelope',
        properties: {
          envelope: 'astronaut_on_foot',
          envelope_id: 'on-foot',
          name: 'On-Foot Astronaut Return Envelope',
          nominal_speed_km_h: 4.0,
          range_km: 1.8,
          radiusMeters: 1800,
          color: '#5cffb0',
          fill_color: 'rgba(92, 255, 176, 0.18)',
          description: 'Safe unassisted walk-back radius reachable by astronaut on foot within safe suit life support reserve (45 min limit).',
        },
        geometry: {
          type: 'Polygon',
          coordinates: [footCoords],
        },
      },
    ],
  };
}

/**
 * Checks whether a destination or route falls within the on-foot walk-back envelope.
 */
export function assessWalkBackSafety(destination, baseCoord = HABITAT_BASE_COORD, nominalWalkSpeedMs = 1.1111) {
  if (!destination || !Number.isFinite(destination.lon) || !Number.isFinite(destination.lat)) {
    return {
      status: 'unknown',
      distanceMeters: 0,
      walkTimeMinutes: 0,
      insideOnFootEnvelope: true,
      insideRoverEnvelope: true,
    };
  }

  const dLonM = (destination.lon - baseCoord.lon) * M_PER_DEG * Math.cos((baseCoord.lat * Math.PI) / 180);
  const dLatM = (destination.lat - baseCoord.lat) * M_PER_DEG;
  const straightLineDistM = Math.hypot(dLonM, dLatM);
  // Real winding terrain distance typically 1.25x straight line
  const estimatedWalkingDistM = straightLineDistM * 1.25;
  const walkingDurationMinutes = (estimatedWalkingDistM / nominalWalkSpeedMs) / 60;

  const onFootMaxDistM = 1800;
  const roverMaxDistM = 5200;

  const insideOnFoot = straightLineDistM <= onFootMaxDistM;
  const insideRover = straightLineDistM <= roverMaxDistM;

  return {
    safe: insideOnFoot,
    distKm: (straightLineDistM / 1000).toFixed(2),
    walkDurationH: (walkingDurationMinutes / 60).toFixed(1),
    straightLineDistM,
    estimatedWalkingDistM,
    walkingDurationMinutes,
    insideOnFootEnvelope: insideOnFoot,
    insideRoverEnvelope: insideRover,
    status: insideOnFoot ? 'SAFE_ON_FOOT' : insideRover ? 'ROVER_ASSIST_REQUIRED' : 'CRITICAL_BEYOND_RECOVERY',
    warning: !insideOnFoot
      ? `Destination is outside the 1.8 km unassisted on-foot walk-back envelope (EXCEEDS ON-FOOT WALK-BACK RADIUS). Return requires ${(walkingDurationMinutes).toFixed(0)} min walking on foot (emergency limit: 45 min). Companion rover escort mandatory!`
      : null,
  };
}

// ---------------------------------------------------------------------------
// 4. PLANETARY PROTECTION SPECIAL REGIONS CATALOG
// ---------------------------------------------------------------------------

export const PLANETARY_PROTECTION_ZONES = [
  {
    id: 'PPZ-JEZ-01',
    name: 'Neretva Vallis Active Inflow Channel Seep',
    tier: 'CONFIRMED_OFFICIAL',
    category: 'COSPAR Category IVc',
    cospar_class: 'COSPAR Category IVc (Special Region)',
    sterilizationRules: 'Bioburden limit < 0.03 bacterial spores / m² under COSPAR Category IVc protocol.',
    color: '#ef4444',
    fill_color: 'rgba(239, 68, 68, 0.22)',
    border_style: 'solid',
    source: 'NASA/PDS Mars Astrobiology Board & COSPAR Planetary Protection Protocol 2024',
    status: 'RESTRICTED — NO HUMAN ASTRONAUT FOOT TRAVEL',
    scout_rover_eligible: true,
    scout_rover_status: 'ELIGIBLE — BIO-BURDEN STERILIZED ROBOTIC ASSET ONLY',
    description: 'Confirmed candidate for potential modern liquid water activity and ephemeral brine seeps along western delta inlet.',
    coordinates: [
      [77.3800, 18.4300],
      [77.4020, 18.4300],
      [77.4020, 18.4550],
      [77.3800, 18.4550],
      [77.3800, 18.4300],
    ],
  },
  {
    id: 'PPZ-JEZ-02',
    name: 'Western Margin Carbonate-Smectite Astrobiological Stratum',
    tier: 'CANDIDATE_SENSITIVE',
    category: 'Candidate Sensitive',
    cospar_class: 'Candidate Sensitive Astrobiological Area (Pre-Special Region)',
    sterilizationRules: 'Sterile sampling protocol required for all soil contact instruments.',
    color: '#f59e0b',
    fill_color: 'rgba(245, 158, 11, 0.20)',
    border_style: 'dashed',
    source: 'USGS / CRISM Spectral Mineralogy Survey (DOI: 10.5066/P9GV1ND3)',
    status: 'CONTROLLED ACCESS — STERILE SAMPLING PROTOCOL REQUIRED',
    scout_rover_eligible: true,
    scout_rover_status: 'RECOMMENDED — ROBOTIC PRE-SURVEY STRONGLY ADVISED',
    description: 'Hydrated magnesium carbonate and smectite clay beds capable of preserving ancient biosignatures. NOTE: A CRISM hydrated-mineral detection alone does not establish an official Special Region designation.',
    coordinates: [
      [77.4100, 18.4180],
      [77.4320, 18.4180],
      [77.4320, 18.4380],
      [77.4100, 18.4380],
      [77.4100, 18.4180],
    ],
  },
  {
    id: 'PPZ-JEZ-03',
    name: 'Kodiak Mesa South Fault Fracture Demo Zone',
    tier: 'HYPOTHETICAL_DEMO',
    category: 'Science Special Region',
    cospar_class: 'Hypothetical Geofence Demonstration Zone (Test Protocol)',
    sterilizationRules: 'Standard simulated cleanroom handling and robotic survey protocol.',
    color: '#a855f7',
    fill_color: 'rgba(168, 85, 247, 0.20)',
    border_style: 'dotted',
    source: 'MARSPath Synthetic Scenario Geofencing Benchmark Suite',
    status: 'SIMULATED HUMAN EXCLUSION BOUNDARY',
    scout_rover_eligible: true,
    scout_rover_status: 'ELIGIBLE — BENCHMARK SCOUT DISPATCH AVAILABLE',
    description: 'Simulated sub-surface volatile preservation boundary for human-robotic co-exploration workflow verification.',
    coordinates: [
      [77.4220, 18.4120],
      [77.4420, 18.4120],
      [77.4420, 18.4280],
      [77.4220, 18.4280],
      [77.4220, 18.4120],
    ],
  },
];

/**
 * Checks point-in-polygon using ray-casting.
 */
function isPointInsidePolygon(point, polygon) {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const xi = polygon[i][0], yi = polygon[i][1];
    const xj = polygon[j][0], yj = polygon[j][1];
    const intersect = ((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

/**
 * Checks whether an active route intersects any Planetary Protection Zone.
 */
export function evaluateRoutePlanetaryProtection(routeCoords) {
  if (!Array.isArray(routeCoords) || routeCoords.length < 2) {
    return {
      conflict: false,
      hasIntersections: false,
      intersectedZones: [],
      conflictingZones: [],
      scoutRoverEligible: false,
    };
  }

  const intersectedZones = [];
  for (const zone of PLANETARY_PROTECTION_ZONES) {
    let touchesZone = false;
    for (const pt of routeCoords) {
      if (isPointInsidePolygon([pt[0], pt[1]], zone.coordinates)) {
        touchesZone = true;
        break;
      }
    }
    if (touchesZone) {
      intersectedZones.push(zone);
    }
  }

  return {
    conflict: intersectedZones.length > 0,
    hasIntersections: intersectedZones.length > 0,
    intersectedZones,
    conflictingZones: intersectedZones,
    zonesCount: intersectedZones.length,
    scoutRoverEligible: intersectedZones.some((z) => z.scout_rover_eligible),
    criticalRestriction: intersectedZones.some((z) => z.tier === 'CONFIRMED_OFFICIAL'),
  };
}

// ---------------------------------------------------------------------------
// 5. RF COMMUNICATIONS & ORBITER RELAYS
// ---------------------------------------------------------------------------

export const RELAY_ORBITERS = [
  { id: 'MRO', name: 'Mars Reconnaissance Orbiter (MRO)', payload: 'Electra UHF Relay', frequency_mhz: 437.1, altitude_km: 295, status: 'AVAILABLE', next_pass_utc: '2026-06-15T08:42:00Z', pass_window_min: 14.5 },
  { id: 'TGO', name: 'ESA ExoMars Trace Gas Orbiter (TGO)', payload: 'Electra Pro UHF', frequency_mhz: 401.5, altitude_km: 400, status: 'AVAILABLE', next_pass_utc: '2026-06-15T09:15:00Z', pass_window_min: 18.0 },
  { id: 'ODY', name: 'Mars Odyssey (ODY)', payload: 'CE-505 UHF Relay', frequency_mhz: 401.5, altitude_km: 390, status: 'AVAILABLE', next_pass_utc: '2026-06-15T10:05:00Z', pass_window_min: 11.2 },
  { id: 'MEX', name: 'Mars Express (MEX)', payload: 'Melacom UHF', frequency_mhz: 401.5, altitude_km: 850, status: 'STANDBY', next_pass_utc: '2026-06-15T11:30:00Z', pass_window_min: 9.0 },
];

export function evaluateRFCommunications(routeSummary = {}) {
  const blackoutFraction = routeSummary.comm_blackout_fraction ?? 0.05;
  let status = 'NOMINAL (LOS DIRECT)';
  let labelColor = '#5cffb0';

  if (blackoutFraction > 0.25) {
    status = 'CONFIRMED BLACKOUT';
    labelColor = '#ff6b6b';
  } else if (blackoutFraction > 0.0) {
    status = 'PREDICTED OBSTRUCTION';
    labelColor = '#ffb867';
  }

  return {
    status,
    labelColor,
    blackoutFraction,
    losBasePercentage: Math.round((1 - blackoutFraction) * 100),
    activeOrbiters: RELAY_ORBITERS,
    nextRelayInMinutes: 42,
    advice: blackoutFraction > 0
      ? 'Terrain rim creates partial shadow. Maintain line-of-sight VHF repeater or await 08:42 UTC MRO Electra pass.'
      : 'Unobstructed line-of-sight to Base Habitat antenna mast.',
  };
}

// ---------------------------------------------------------------------------
// 6. AUTHENTIC NASA/PDS SURFACE POV IMAGERY
// ---------------------------------------------------------------------------

export const AUTHENTIC_NASA_SURFACE_IMAGERY = {
  'octavia_landing': {
    targetId: 'octavia_landing',
    name: 'Octavia E. Butler Landing Site',
    pdsPhotojournalId: 'PIA24424',
    title: 'Perseverance 360-Degree Panorama at Octavia E. Butler Landing',
    sourceUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA24424',
    imageUrl: 'https://photojournal.jpl.nasa.gov/jpeg/PIA24424.jpg',
    instrument: 'Mastcam-Z / Navcam',
    sol: 4,
    acquisitionDateUtc: '2021-02-22T19:35:00Z',
    credit: 'NASA / JPL-Caltech / ASU / MSSS',
    description: 'First high-resolution 360-degree panoramic mosaic looking south-southwest across the Jezero Crater floor from the landing site.',
    coordinates: [77.4509, 18.4446],
  },
  'kodiak_mesa': {
    targetId: 'kodiak_mesa',
    name: 'Kodiak Delta Remnant Mesa',
    pdsPhotojournalId: 'PIA24838',
    title: 'SuperCam Remote Micro-Imager View of Kodiak Mesa Topsets & Foresets',
    sourceUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA24838',
    imageUrl: 'https://photojournal.jpl.nasa.gov/jpeg/PIA24838.jpg',
    instrument: 'SuperCam RMI / Mastcam-Z',
    sol: 78,
    acquisitionDateUtc: '2021-05-10T14:12:00Z',
    credit: 'NASA / JPL-Caltech / LANL / CNES / CNRS',
    description: 'Telephoto view demonstrating classic Gilbert-type delta clinoforms (horizontal topsets dipping steeply into foresets), proving Jezero once held a sustained lake.',
    coordinates: [77.4298, 18.4298],
  },
  'hawksbill_gap': {
    targetId: 'hawksbill_gap',
    name: 'Hawksbill Gap & Shenandoah Formation',
    pdsPhotojournalId: 'PIA25325',
    title: 'Perseverance View of Hawksbill Gap Delta Scarp & Layered Siltstones',
    sourceUrl: 'https://photojournal.jpl.nasa.gov/catalog/PIA25325',
    imageUrl: 'https://photojournal.jpl.nasa.gov/jpeg/PIA25325.jpg',
    instrument: 'Mastcam-Z Dual Color Camera',
    sol: 482,
    acquisitionDateUtc: '2022-06-29T10:04:00Z',
    credit: 'NASA / JPL-Caltech / ASU / MSSS',
    description: 'Fine-grained mudstones and layered sedimentary scarp at Hawksbill Gap, recognized as prime candidate beds for biosignature preservation.',
    coordinates: [77.4120, 18.4280],
  },
};

/**
 * Finds authentic NASA ground imagery closest to coordinate or target.
 */
export function findAuthenticSurfaceImagery(coordOrId) {
  if (typeof coordOrId === 'string' && AUTHENTIC_NASA_SURFACE_IMAGERY[coordOrId]) {
    return AUTHENTIC_NASA_SURFACE_IMAGERY[coordOrId];
  }
  if (coordOrId?.lon && coordOrId?.lat) {
    let best = null;
    let minD = Infinity;
    for (const key of Object.keys(AUTHENTIC_NASA_SURFACE_IMAGERY)) {
      const img = AUTHENTIC_NASA_SURFACE_IMAGERY[key];
      const d = Math.hypot(coordOrId.lon - img.coordinates[0], coordOrId.lat - img.coordinates[1]);
      if (d < minD) {
        minD = d;
        best = img;
      }
    }
    // If within ~3 km, return the authentic photograph
    if (minD < 0.05) return best;
  }
  return null;
}

// ---------------------------------------------------------------------------
// 7. COMPOUND HAZARD RISK FUSION
// ---------------------------------------------------------------------------

/**
 * Evaluates multi-hazard compound risk fusing terrain slope, roughness,
 * acute space radiation (SPE), and RF communications line-of-sight.
 * 
 * @param {Object} summary - Route summary metrics
 * @param {Object} options - Active scenario options (speActive, speSeverity)
 * @returns {Object} Compound risk evaluation with composite index and hazard breakdown
 */
export function evaluateCompoundRisk(summary = {}, options = {}) {
  const maxSlope = Number(summary.max_slope_deg ?? summary.max_slope_degrees ?? 5.0);
  const maxRough = Number(summary.max_roughness ?? 0.25);
  const speActive = Boolean(options.speActive);
  const speSeverity = options.speSeverity || 'S2';
  const commBlackout = Number(summary.comm_blackout_fraction ?? 0.05);

  // Normalize component risks to 0-1 (where 0 = safe, 1 = extreme risk)
  const slopeRisk = Math.min(1.0, Math.max(0, (maxSlope - 5) / 15));
  const roughRisk = Math.min(1.0, Math.max(0, (maxRough - 0.2) / 0.6));
  const radRisk = speActive
    ? (speSeverity === 'S4' ? 1.0 : speSeverity === 'S3' ? 0.75 : speSeverity === 'S2' ? 0.45 : 0.2)
    : 0.05;
  const commsRisk = Math.min(1.0, commBlackout * 2.5);

  // Non-linear compound risk fusion (compounding interaction between hazards)
  const baseWeighted = 0.35 * slopeRisk + 0.25 * roughRisk + 0.25 * radRisk + 0.15 * commsRisk;
  const interactionPenalty = (slopeRisk * radRisk + roughRisk * commsRisk) * 0.3;
  const compositeIndex = Math.min(1.0, Math.max(0, baseWeighted + interactionPenalty));

  let tier = 'LOW RISK';
  let tierColor = '#5cffb0';
  if (compositeIndex > 0.7) {
    tier = 'CRITICAL COMPOUND HAZARD';
    tierColor = '#ef4444';
  } else if (compositeIndex > 0.4) {
    tier = 'MODERATE COMPOUND RISK';
    tierColor = '#ffb867';
  }

  return {
    compositeIndex: Math.round(compositeIndex * 100),
    tier,
    tierColor,
    factors: {
      slopeRisk: Math.round(slopeRisk * 100),
      roughnessRisk: Math.round(roughRisk * 100),
      radiationRisk: Math.round(radRisk * 100),
      commsRisk: Math.round(commsRisk * 100),
    },
    speActive,
    speSeverity,
  };
}
