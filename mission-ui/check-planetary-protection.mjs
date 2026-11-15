/**
 * Automated Verification Script: Planetary Protection Geofence & Scout Rover Engine.
 */

import assert from 'node:assert';
import {
  JEZERO_SPECIAL_REGIONS,
  pointInPolygon,
  evaluateRouteGeofenceClient,
  dispatchScoutRoverRecon,
} from './src/planetary_protection.js';

console.log('🧪 Starting Planetary Protection Geofence & Scout Reconnaissance Automated Verification...\n');

// 1. Catalog Categories & Scientific Provenance
console.log('--- 1. Testing Special Regions Catalog & Provenance ---');
assert.strictEqual(JEZERO_SPECIAL_REGIONS.length, 3);

const official = JEZERO_SPECIAL_REGIONS.find((z) => z.classification === 'official_restricted_zone');
const candidate = JEZERO_SPECIAL_REGIONS.find((z) => z.classification === 'candidate_sensitive_region');
const demo = JEZERO_SPECIAL_REGIONS.find((z) => z.classification === 'demonstration_scenario');

assert(official, 'Official restricted zone must be defined');
assert(candidate, 'Candidate sensitive region must be defined');
assert(demo, 'Demonstration scenario must be defined');

assert.strictEqual(official.human_access_status, 'STRICTLY_PROHIBITED');
assert.strictEqual(official.boundary_color, '#ef4444');
assert(official.dataset.includes('CRISM'));
assert.strictEqual(official.scout_rover_eligible, true);

assert.strictEqual(candidate.human_access_status, 'ASSESSMENT_REQUIRED');
assert.strictEqual(candidate.boundary_color, '#f59e0b');

assert.strictEqual(demo.human_access_status, 'SIMULATED_EXERCISE');
assert.strictEqual(demo.stroke_style, 'dashed');
console.log('  ✓ Verified 3 distinct categories: Official Restricted (Red), Candidate (Amber), Demo (Purple dashed).');

// 2. Clear Safe Route
console.log('\n--- 2. Testing Route Clear of All Geofences ---');
const safeCoords = [
  [77.30, 18.30],
  [77.32, 18.32],
];
const safeAssessment = evaluateRouteGeofenceClient(safeCoords);
assert.strictEqual(safeAssessment.human_route_approved, true);
assert.strictEqual(safeAssessment.total_intersections, 0);
assert.strictEqual(safeAssessment.policy_violations.length, 0);
assert.strictEqual(safeAssessment.highest_restriction_level, 'NONE');
console.log('  ✓ Safe route: human_route_approved=true, total_intersections=0.');

// 3. Piercing Official Restricted Zone
console.log('\n--- 3. Testing Route Piercing Official Restricted Zone ---');
const officialPiercingCoords = [
  [77.4200, 18.4550], // West of Delta Scarp
  [77.4360, 18.4550], // Inside Western Delta Scarp zone
  [77.4500, 18.4550], // East
];
const officialAssessment = evaluateRouteGeofenceClient(officialPiercingCoords);
assert.strictEqual(officialAssessment.human_route_approved, false);
assert.strictEqual(officialAssessment.highest_restriction_level, 'OFFICIAL_RESTRICTED');
assert(officialAssessment.policy_violations.length >= 1);
assert(officialAssessment.policy_violations[0].includes('CRITICAL PLANETARY PROTECTION VIOLATION'));
assert.strictEqual(officialAssessment.alternative_routes_suggested, true);

const officialHit = officialAssessment.intersected_regions.find((r) => r.region_id === 'ppz_jezero_delta_aquifer');
assert(officialHit);
assert.strictEqual(officialHit.action_required, 'REROUTE_MANDATORY');
console.log(`  ✓ Official restriction: Human route barred! Violation logged: ${officialHit.action_required}.`);

// 4. Piercing Candidate Sensitive Region
console.log('\n--- 4. Testing Route Piercing Candidate Sensitive Region ---');
const candidateCoords = [
  [77.4300, 18.4330],
  [77.4460, 18.4330], // Inside Séítah candidate
  [77.4600, 18.4330],
];
const candidateAssessment = evaluateRouteGeofenceClient(candidateCoords);
assert.strictEqual(candidateAssessment.human_route_approved, true);
assert.strictEqual(candidateAssessment.highest_restriction_level, 'CANDIDATE_SENSITIVE');
assert(candidateAssessment.warnings.length >= 1);
assert(candidateAssessment.warnings[0].includes('PLANETARY PROTECTION ADVISORY'));
assert.strictEqual(candidateAssessment.policy_violations.length, 0);

const candidateHit = candidateAssessment.intersected_regions.find((r) => r.region_id === 'ppz_seitah_carbonate_rsl');
assert(candidateHit);
assert.strictEqual(candidateHit.action_required, 'SCOUT_SURVEY_RECOMMENDED');
assert.strictEqual(candidateHit.scout_dispatch_recommended, true);
console.log(`  ✓ Candidate advisory: human_route_approved=true with advisory warning and scout recommendation.`);

// 5. Simulated Scout Rover Dispatch
console.log('\n--- 5. Testing Simulated Scout Rover Reconnaissance Dispatch ---');
const scoutSortie = await dispatchScoutRoverRecon('ppz_seitah_carbonate_rsl');
assert.strictEqual(scoutSortie.target_region_id, 'ppz_seitah_carbonate_rsl');
assert.strictEqual(scoutSortie.status, 'SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST');
assert(scoutSortie.simulation_disclaimer.includes('MOCK MISSION SIMULATION ONLY'));
assert(scoutSortie.recon_mission_id.startsWith('SCOUT-SORTIE-'));
assert(scoutSortie.bio_cleanliness_level.includes('Cat IVb'));
console.log(`  ✓ Generated simulated scout sortie: ${scoutSortie.recon_mission_id} (${scoutSortie.bio_cleanliness_level})`);

console.log('\n🎉 ALL PLANETARY PROTECTION GEOFENCE & SCOUT RECON CHECKS PASSED CLEANLY!\n');
