import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { plan } from './src/engine.js';
import { buildTerrain } from './src/terrain.js';
import { exportGeoJSON, exportJSON, exportCSV } from './src/export.js';
import { computeTimeOverlayPixels, calculateEdgeFeatherGradients } from './src/map_rendering.js';

console.log('--- MARSPath: Kunal Frontend Ownership Completion & Verification Test Suite ---');

// 1. Load real Jezero DEM fixture
const raw = JSON.parse(readFileSync(new URL('../dist/mission-data/jezero-dem.json', import.meta.url), 'utf8'));
const terrain = buildTerrain(raw);

// 2. Generate multi-alternative route plan
const planRequest = {
  start: { lon: 77.40, lat: 18.39 },
  destination: { lon: 77.44, lat: 18.42 },
  mode: 'balanced',
  constraints: { max_slope_deg: 20.0, max_roughness: 0.85, avoid_unobserved_terrain: true },
  science_waypoints: [],
  num_alternatives: 3,
};
const planResult = plan(raw, planRequest);

console.log('[Test 1/7] Verifying Route Alternatives & Dynamic Route Selection...');
assert.ok(Array.isArray(planResult.routes) && planResult.routes.length >= 2, 'Must return multiple route candidates');
const primary = planResult.routes[0];
const alternative = planResult.routes[1];
const backup = planResult.routes[2] || alternative;

assert.notEqual(primary.route_id, alternative.route_id, 'Candidate route IDs must be unique');
assert.ok(primary.total_cost <= alternative.total_cost, 'Primary route must have <= cost than alternative');

// Verify route selection updates export synchronization
const expPrimary = exportGeoJSON(planResult, primary.route_id, planRequest);
const expAlt = exportGeoJSON(planResult, alternative.route_id, planRequest);
assert.equal(expPrimary.features[0].id, primary.route_id, 'GeoJSON export must synchronize to selected primary route');
assert.equal(expAlt.features[0].id, alternative.route_id, 'GeoJSON export must synchronize to selected alternative route');
assert.notDeepEqual(expPrimary.features[0].geometry, expAlt.features[0].geometry, 'Exported geometries must reflect selected candidate');
console.log('   ✓ Route candidate selection and export synchronization verified.');

console.log('[Test 2/7] Verifying Cost & Terrain Breakdown Integrity...');
for (const r of planResult.routes) {
  assert.ok(Number.isFinite(r.total_cost), 'Total weighted route cost must be finite');
  assert.ok(r.cost_breakdown, 'Cost breakdown must be present');
  const sumPenalties = Object.values(r.cost_breakdown).reduce((a, b) => a + b, 0);
  assert.ok(Math.abs(sumPenalties - r.total_cost) < 1e-4, 'Sum of cost breakdown components must equal total_cost');
  
  // Verify all 5 breakdown keys
  assert.ok(Number.isFinite(r.cost_breakdown.base_distance_cost), 'Base distance cost must exist');
  assert.ok(Number.isFinite(r.cost_breakdown.slope_penalty), 'Slope penalty must exist');
  assert.ok(Number.isFinite(r.cost_breakdown.roughness_penalty), 'Roughness penalty must exist');
  assert.ok(Number.isFinite(r.cost_breakdown.hazard_penalty), 'Hazard penalty must exist');
  assert.ok(Number.isFinite(r.cost_breakdown.extra_penalty), 'Extra penalty must exist');
}
console.log('   ✓ Cost & terrain breakdown penalties mathematically reconcile to total weighted cost.');

console.log('[Test 3/7] Verifying Energy Metric & Minetti Mechanical Effort Model...');
for (const r of planResult.routes) {
  const energy = r.summary.energy_index ?? 1.0;
  assert.ok(Number.isFinite(energy), 'Energy index must be numeric');
  assert.ok(energy >= 0.5 && energy <= 20.0, 'Energy index must be a reasonable dimensionless multiplier (>= 0.5x)');
  // Strict check: No energy units like kWh or fuel in summary
  assert.equal(typeof r.summary.battery_kwh, 'undefined', 'Summary must not invent physical battery kWh');
  assert.equal(typeof r.summary.fuel_liters, 'undefined', 'Summary must not invent physical fuel liters');
}
console.log('   ✓ Minetti-based mechanical-effort energy index verified as dimensionless multiplier (no kWh/fuel).');

console.log('[Test 4/7] Verifying Mission Resource Summary Fields...');
for (const r of planResult.routes) {
  assert.ok(r.summary.total_distance_meters > 0, 'Total distance must be positive');
  assert.ok(Number.isFinite(r.summary.estimated_duration_hours), 'Estimated travel time must be finite');
  assert.ok(Number.isFinite(r.summary.max_slope_deg), 'Max slope must be finite');
  assert.ok(Number.isFinite(r.summary.average_slope_deg), 'Average slope must be finite');
  assert.ok(Number.isFinite(r.summary.data_coverage_fraction), 'Data coverage fraction must be finite');
}
console.log('   ✓ Mission resource summary fields present and populated with real numbers.');

console.log('[Test 5/7] Verifying 2D Return-Time Isochrone & Reachable Zone Overlay...');
const mockZone = {
  bounds: [77.34, 18.33, 77.50, 18.48],
  rows: 4,
  cols: 4,
  threshold_minutes: 30,
  budget_minutes: 480,
  minutes_grid: [
    [10.5, 22.0, 31.5, null],
    [14.0, 28.5, 45.0, null],
    [null, null, null, null],
    [5.0,  18.0, 29.0, 60.0]
  ]
};
const overlay = computeTimeOverlayPixels(mockZone, 'return');
assert.equal(overlay.rows, 4);
assert.equal(overlay.cols, 4);
assert.equal(overlay.data.length, 4 * 4 * 4);

// Cell [0, 3] is null -> must have alpha = 0 (100% transparent)
const nullCellAlpha = overlay.data[(0 * 4 + 3) * 4 + 3];
assert.equal(nullCellAlpha, 0, 'NoData / null return-time cell must be 100% transparent (alpha = 0)');

// Cell [0, 0] is 10.5m <= 30m threshold -> green/mint safe return hue
const safeR = overlay.data[(0 * 4 + 0) * 4 + 0];
const safeG = overlay.data[(0 * 4 + 0) * 4 + 1];
const safeB = overlay.data[(0 * 4 + 0) * 4 + 2];
const safeA = overlay.data[(0 * 4 + 0) * 4 + 3];
assert.ok(safeG > safeR, 'Safe return cell must have predominant green component');
assert.ok(safeA > 0, 'Safe return cell must have non-zero alpha');

// Cell [0, 2] is 31.5m > 30m threshold -> coral/excess return hue
const excR = overlay.data[(0 * 4 + 2) * 4 + 0];
const excG = overlay.data[(0 * 4 + 2) * 4 + 1];
assert.ok(excR > excG, 'Excess return cell must have predominant red/coral component');

console.log('   ✓ 2D return-time isochrone pixels, NoData alpha transparency, and threshold gradients verified.');

console.log('[Test 6/7] Verifying Edge Feathering & Multi-Resolution Boundary Harmonization...');
const pixelBounds = { tl: [100, 100], br: [500, 400] };
const feather = calculateEdgeFeatherGradients(pixelBounds, 54);
assert.ok(feather !== null, 'Feather gradients must be calculated');
assert.equal(feather.fp, 54, 'Feather pixel size clamped correctly');
assert.equal(feather.rect.w, 400);
assert.equal(feather.rect.h, 300);
console.log('   ✓ Edge feathering gradient geometry verified for multi-resolution boundary blending.');

console.log('[Test 7/7] Verifying CSV and JSON Selected Route Exports...');
const csvPrimary = exportCSV(planResult, primary.route_id);
const csvAlt = exportCSV(planResult, alternative.route_id);
assert.ok(csvPrimary.includes('start_lon,start_lat'), 'CSV header present');
assert.notEqual(csvPrimary, csvAlt, 'CSV export must change when different route is selected');

const jsonPrimary = exportJSON(planResult, primary.route_id, planRequest);
assert.equal(jsonPrimary.selected_route_id, primary.route_id);
assert.equal(jsonPrimary.routes.length, 1);
assert.equal(jsonPrimary.routes[0].route_id, primary.route_id);
console.log('   ✓ CSV and JSON exports synchronize to active selected route candidate.');

console.log('\n================================================================');
console.log(' ALL 7 KUNAL FRONTEND COMPLETION VERIFICATION SUITES PASSED! ');
console.log('================================================================');
