/**
 * Automated Verification Script: Astronaut Walk-Back Safety & RF Visibility Engine.
 */

import assert from 'node:assert';
import {
  WALK_BACK_STATUS,
  MOBILITY_PROFILES,
  formatDurationHours,
  evaluateOnFootFeasibility,
  evaluateRFCommunication,
  VERIFIED_RELAY_ORBITERS,
} from './src/walkback.js';

console.log('🧪 Starting Dual-Radius Walk-Back Safety & RF Automated Verification...\n');

// 1. Mobility Profile Separation
console.log('--- 1. Testing Mobility Profile Independence ---');
assert.strictEqual(MOBILITY_PROFILES.ROVER_ASSISTED.speed_km_h, 10.0);
assert.strictEqual(MOBILITY_PROFILES.ON_FOOT_WALKBACK.speed_km_h, 4.0);
assert.strictEqual(MOBILITY_PROFILES.ROVER_ASSISTED.color, '#00d2ff');
assert.strictEqual(MOBILITY_PROFILES.ON_FOOT_WALKBACK.color, '#00e676');
assert.strictEqual(MOBILITY_PROFILES.ON_FOOT_WALKBACK.emergency_budget_hours, 3.5);
console.log('  ✓ Verified distinct vehicle (10 km/h) and suited pedestrian (4 km/h) mobility models.');

// 2. Safe Walk-Back Feasibility
console.log('\n--- 2. Testing Safe Walk-Back Feasibility ---');
const safeResult = evaluateOnFootFeasibility({
  routeDistanceKm: 2.4,
  routeMaxSlopeDeg: 6.0,
  routeAvgSlopeDeg: 3.5,
  routeRoughnessTri: 0.2,
  walkSpeedMs: 1.1111,
  walkTimeSecondsFromDest: 2700, // 45 mins
  roverTimeSecondsFromDest: 900,  // 15 mins
  maxPermittedWalkingHours: 3.5,
  evaBudgetHours: 8.0,
  coordinates: [
    [77.40, 18.40],
    [77.41, 18.41],
    [77.42, 18.42],
  ],
});

assert.strictEqual(safeResult.status, WALK_BACK_STATUS.SAFE_WITHIN_LIMIT);
assert.strictEqual(safeResult.destination_exceeds_limit, false);
assert.strictEqual(safeResult.warning_message, null);
assert.strictEqual(safeResult.terrain_difficulty, 'MILD');
assert.strictEqual(safeResult.walk_back_duration_formatted, '45m');
assert(safeResult.emergency_resource_margin_pct > 50);
console.log(`  ✓ Nominal return: ${safeResult.walk_back_duration_formatted}, Margin: ${safeResult.emergency_resource_margin_pct}% [${safeResult.status}]`);

// 3. Walk-Back Limit Exceeded
console.log('\n--- 3. Testing Walk-Back Limit Exceeded Warning ---');
const exceededResult = evaluateOnFootFeasibility({
  routeDistanceKm: 15.0,
  routeMaxSlopeDeg: 18.0,
  routeAvgSlopeDeg: 11.0,
  routeRoughnessTri: 0.55,
  walkSpeedMs: 1.1111,
  walkTimeSecondsFromDest: 16200, // 4.5 hours -> exceeds 3.5h!
  roverTimeSecondsFromDest: 5400,
  maxPermittedWalkingHours: 3.5,
  evaBudgetHours: 8.0,
  coordinates: [
    [77.40, 18.40],
    [77.48, 18.48],
  ],
});

assert.strictEqual(exceededResult.status, WALK_BACK_STATUS.LIMIT_EXCEEDED);
assert.strictEqual(exceededResult.destination_exceeds_limit, true);
assert(exceededResult.warning_message.includes('DESTINATION EXCEEDS CONFIGURED ON-FOOT WALK-BACK LIMIT'));
assert.strictEqual(exceededResult.terrain_difficulty, 'SEVERE');
console.log(`  ✓ Exceeded return: ${exceededResult.walk_back_duration_formatted} > 3.5h limit -> Warning verified.`);

// 4. Limited Margin Pacing Advisory
console.log('\n--- 4. Testing Limited Margin Advisory ---');
const limitedResult = evaluateOnFootFeasibility({
  routeDistanceKm: 7.0,
  routeMaxSlopeDeg: 12.0,
  routeAvgSlopeDeg: 7.0,
  routeRoughnessTri: 0.35,
  walkSpeedMs: 1.1111,
  walkTimeSecondsFromDest: 10080, // 2.8 hours
  roverTimeSecondsFromDest: 2800,
  maxPermittedWalkingHours: 3.5,
  evaBudgetHours: 8.0,
  coordinates: [
    [77.40, 18.40],
    [77.45, 18.45],
  ],
});

assert.strictEqual(limitedResult.status, WALK_BACK_STATUS.LIMITED_MARGIN);
assert.strictEqual(limitedResult.destination_exceeds_limit, false);
assert(limitedResult.warning_message.includes('CAUTION: On-foot return margin is limited'));
console.log(`  ✓ Limited return margin: ${limitedResult.walk_back_duration_formatted} -> Advisory verified.`);

// 5. NoData Unobserved Corridor
console.log('\n--- 5. Testing NoData Out-Of-Bounds Handling ---');
const nodataResult = evaluateOnFootFeasibility({
  routeDistanceKm: 0,
  outOfBounds: true,
});
assert.strictEqual(nodataResult.status, WALK_BACK_STATUS.DATA_UNAVAILABLE);
assert.strictEqual(nodataResult.destination_exceeds_limit, true);
console.log('  ✓ NoData corridor: Returns DATA UNAVAILABLE and safe failure mode.');

// 6. RF Line-of-Sight & Relay Spacecraft
console.log('\n--- 6. Testing RF Line-of-Sight Continuity & Relay Tracking ---');
const rfResult = evaluateRFCommunication({
  habitatCoord: { lon: 77.40, lat: 18.40 },
  routeCoords: [
    { lon: 77.40, lat: 18.40 },
    { lon: 77.42, lat: 18.42 },
  ],
  maxSlopeDeg: 5.0,
});

assert.strictEqual(rfResult.direct_habitat_los, 'CONNECTED');
assert.strictEqual(rfResult.terrain_shadow_risk, 'LOW');
assert.strictEqual(rfResult.active_orbiters.length, 5);
assert(rfResult.best_orbiter_contact.includes('MRO'));
console.log(`  ✓ RF Line-of-Sight: ${rfResult.direct_habitat_los}, Primary Relay: ${rfResult.best_orbiter_contact}`);

console.log('\n🎉 ALL DUAL-RADIUS WALK-BACK SAFETY CHECKS PASSED CLEANLY!\n');
