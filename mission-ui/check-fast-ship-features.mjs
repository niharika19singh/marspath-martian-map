/**
 * Automated Verification Suite for MARSPath 3 Priority Features:
 * 1. Astronaut Suit HUD Mode + Web Speech API Hazard Alerts
 * 2. Marswalk Survivability Score + Solar Storm Scenario
 * 3. Planetary Protection Geofence + Perseverance POV Images
 */

import assert from 'node:assert';
import { audioAlerts } from './src/audio_alerts.js';
import { calculateMarswalkScore, getSurvivabilityTier, DEFAULT_SURVIVABILITY_WEIGHTS } from './src/survivability_scoring.js';
import { AUTHENTIC_NASA_SURFACE_IMAGES, getContextualRoverImage } from './src/surface_imagery.js';
import { JEZERO_SPECIAL_REGIONS, evaluateRouteGeofenceClient } from './src/planetary_protection.js';

console.log('🧪 Starting 3 Priority Features Automated Verification...\n');

// ============================================================================
// TEST 1: Feature 1 — Astronaut Suit HUD & Web Speech API Hazard Alerts
// ============================================================================
console.log('--- 1. Testing Feature 1: Suit HUD & Audio Alerts ---');

// Test Audio Alert Manager initialization & toggle
assert.strictEqual(typeof audioAlerts.isSupported, 'function');
assert.strictEqual(typeof audioAlerts.isEnabled, 'function');

audioAlerts.setEnabled(true);
assert.strictEqual(audioAlerts.isEnabled(), true, 'Audio alerts should be enabled');

audioAlerts.setEnabled(false);
assert.strictEqual(audioAlerts.isEnabled(), false, 'Audio alerts should be disabled');

// Test Trigger Alert & Deduplication Cooldown
let receivedAlert = null;
const unsub = audioAlerts.subscribe((state) => {
  receivedAlert = state.currentAlert;
});

audioAlerts.triggerAlert({
  message: 'Terrain hazard detected ahead.',
  severity: 'WARNING',
  key: 'test_hazard',
  force: true,
});

assert.ok(receivedAlert, 'Subscriber should receive triggered alert');
assert.strictEqual(receivedAlert.message, 'Terrain hazard detected ahead.');
assert.strictEqual(receivedAlert.severity, 'WARNING');

// Second identical call within cooldown should be debounced (not re-triggered)
receivedAlert = null;
audioAlerts.triggerAlert({
  message: 'Terrain hazard detected ahead.',
  severity: 'WARNING',
  key: 'test_hazard',
  force: false,
});
assert.strictEqual(receivedAlert, null, 'Identical message within cooldown must be debounced');

unsub();
console.log('  ✓ Web Speech API Audio Alert Manager, state toggling & deduplication verified.');

// ============================================================================
// TEST 2: Feature 2 — Marswalk Survivability Score & Solar Storm Scenario
// ============================================================================
console.log('\n--- 2. Testing Feature 2: Marswalk Survivability Score & Solar Storm ---');

// 2a. Verify weights sum to 1.0
const weightSum = Object.values(DEFAULT_SURVIVABILITY_WEIGHTS).reduce((a, b) => a + b, 0);
assert.strictEqual(Math.round(weightSum * 100) / 100, 1.0, 'Weights must sum to 1.0');

// 2b. Test Nominal Traverse Calculation
const nominal = calculateMarswalkScore({
  maxSlopeDeg: 3.8,
  roughnessTri: 0.18,
  durationHours: 0.75,
  evaBudgetHours: 8.0,
  distanceKm: 1.25,
  emergencyMarginPct: 88.0,
  isStormActive: false,
});

assert.ok(nominal.score >= 80.0 && nominal.score <= 100.0, `Nominal score should be >= 80 (got ${nominal.score})`);
assert.strictEqual(nominal.tier.badge, 'OPTIMAL');
assert.strictEqual(nominal.is_storm_active, false);
assert.strictEqual(nominal.envelope_tightened, false);

// 2c. Verify all 5 normalized factors are strictly in [0.0, 1.0]
for (const [key, factor] of Object.entries(nominal.factors)) {
  assert.ok(factor.normalized >= 0.0 && factor.normalized <= 1.0, `Factor ${key} normalized out of range: ${factor.normalized}`);
  assert.ok(factor.contribution >= 0.0, `Factor ${key} contribution must be positive`);
  assert.ok(factor.assumption.length > 5, `Factor ${key} must have clear documented assumption`);
}

// 2d. Test Solar Storm Scenario Activation
const stormUnsheltered = calculateMarswalkScore({
  maxSlopeDeg: 3.8,
  roughnessTri: 0.18,
  durationHours: 0.75,
  evaBudgetHours: 8.0,
  distanceKm: 1.25,
  emergencyMarginPct: 88.0,
  isStormActive: true,
  shelterDistanceM: 2500, // far from shelter
});

assert.strictEqual(stormUnsheltered.is_storm_active, true);
assert.strictEqual(stormUnsheltered.envelope_tightened, true);
assert.strictEqual(stormUnsheltered.envelope_tightening_pct, 30);
assert.ok(stormUnsheltered.score < nominal.score, 'Storm scenario must derate score');
assert.ok(nominal.score - stormUnsheltered.score >= 20, 'Unshielded solar storm should heavily penalize score');

// 2e. Test Topographic Shelter Mitigation under Solar Storm
const stormSheltered = calculateMarswalkScore({
  maxSlopeDeg: 3.8,
  roughnessTri: 0.18,
  durationHours: 0.75,
  evaBudgetHours: 8.0,
  distanceKm: 1.25,
  emergencyMarginPct: 88.0,
  isStormActive: true,
  shelterDistanceM: 250, // close to shelter (< 1200m)
});

assert.ok(stormSheltered.shelter_bonus > 0, 'Shelter proximity must grant mitigation bonus');
assert.ok(stormSheltered.score > stormUnsheltered.score, 'Sheltered storm score must exceed exposed score');

// 2f. Verify Score Tiers
assert.strictEqual(getSurvivabilityTier(90).badge, 'OPTIMAL');
assert.strictEqual(getSurvivabilityTier(72).badge, 'MODERATE');
assert.strictEqual(getSurvivabilityTier(52).badge, 'ELEVATED RISK');
assert.strictEqual(getSurvivabilityTier(25).badge, 'LOW SURVIVABILITY');

console.log('  ✓ Transparent 5-factor survivability formula verified (Score: ' + nominal.score + ' -> ' + stormUnsheltered.score + ').');
console.log('  ✓ Solar Storm scenario envelope tightening (-30% margin) and shelter mitigation verified.');

// ============================================================================
// TEST 3: Feature 3 — Planetary Protection Geofence & Perseverance Surface POV
// ============================================================================
console.log('\n--- 3. Testing Feature 3: Planetary Protection Geofence & NASA Surface POV ---');

// 3a. Verify Special Regions Catalog & Classification
assert.ok(JEZERO_SPECIAL_REGIONS.length >= 3, 'Must contain at least 3 special regions');
const classifications = JEZERO_SPECIAL_REGIONS.map(z => z.classification);
assert.ok(classifications.includes('official_restricted_zone'), 'Must include official restricted zone');
assert.ok(classifications.includes('candidate_sensitive_region'), 'Must include candidate sensitive region');
assert.ok(classifications.includes('demonstration_scenario'), 'Must include demonstration scenario');

// 3b. Verify Geofence Intersection & Barring Rule
const routeCrossingDelta = [
  [77.420, 18.445],
  [77.435, 18.455], // Pierces Western Delta Scarp official zone
  [77.450, 18.465],
];
const geofenceResult = evaluateRouteGeofenceClient(routeCrossingDelta);
assert.strictEqual(geofenceResult.human_route_approved, false, 'Route crossing official restricted zone must be BARRED');
assert.ok(geofenceResult.policy_violations.length > 0, 'Must record policy violation');

// 3c. Verify Authentic NASA Perseverance Surface Images
assert.ok(AUTHENTIC_NASA_SURFACE_IMAGES.length >= 5, 'Must contain authentic NASA images');
for (const img of AUTHENTIC_NASA_SURFACE_IMAGES) {
  assert.ok(img.nasa_id.startsWith('PIA'), `NASA ID must be valid PDS product: ${img.nasa_id}`);
  assert.ok(img.camera.length > 0, 'Must record camera instrument');
  assert.ok(img.sol >= 1, 'Must record acquisition Sol');
  assert.ok(img.photojournal_url.includes('photojournal.jpl.nasa.gov'), 'Must link to authentic NASA photojournal');
  assert.ok(img.thumbnail_url.includes('.jpg'), 'Must have image asset URL');
}

// 3d. Verify Contextual Rover Image Resolution
const imgSol1 = getContextualRoverImage({ properties: { sol: 1 } });
assert.strictEqual(imgSol1.nasa_id, 'PIA24487', 'Sol 1 must resolve Octavia E. Butler landing panorama');

const imgSol64 = getContextualRoverImage({ properties: { sol: 64 } });
assert.strictEqual(imgSol64.nasa_id, 'PIA24836', 'Sol 64 must resolve Kodiak Butte telephoto observation');

const imgSol412 = getContextualRoverImage({ properties: { sol: 412 } });
assert.strictEqual(imgSol412.nasa_id, 'PIA25439', 'Sol 412 must resolve Hawksbill Gap delta mudstones');

console.log('  ✓ Planetary protection geofence classification and deterministic human barring verified.');
console.log('  ✓ Authentic NASA Perseverance surface POV catalogue and contextual matching verified.');

console.log('\n🎉 ALL 3 PRIORITY FEATURES AUTOMATED CHECKS PASSED CLEANLY!');
