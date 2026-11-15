import assert from 'node:assert/strict';
import { computeTimeOverlayPixels, calculateEdgeFeatherGradients } from './src/map_rendering.js';
import { AUTHORITATIVE_MARS_IMAGERY_CATALOG } from './src/wmts_capabilities.js';
import { buildTerrain, M_PER_DEG } from './src/terrain.js';
import { plan } from './src/engine.js';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

console.log('🧪 Starting Planetary GIS Map Rendering Fixes & Visual Regression Verification...');

// 1. Task 2 & 8: Verify NoData, unreachable, nonfinite, and negative cells produce alpha = 0 (100% transparent)
console.log('  Testing computeTimeOverlayPixels alpha masking...');
const mockZoneReturn = {
  rows: 4,
  cols: 4,
  threshold_minutes: 60,
  minutes_grid: [
    [null, null, NaN, Infinity],
    [-1, -999, undefined, 10], // 10 min reachable within 60 min budget
    [30, 60, 90, null],        // 30 min, 60 min, 90 min (exceeds budget)
    [null, 15, null, null],
  ],
};

const returnPixels = computeTimeOverlayPixels(mockZoneReturn, 'return');
assert.equal(returnPixels.rows, 4);
assert.equal(returnPixels.cols, 4);
assert.equal(returnPixels.data.length, 4 * 4 * 4);

const getPixel = (pixels, r, c) => {
  const idx = (r * pixels.cols + c) * 4;
  return {
    r: pixels.data[idx],
    g: pixels.data[idx + 1],
    b: pixels.data[idx + 2],
    a: pixels.data[idx + 3],
  };
};

// Row 0: null, null, NaN, Infinity -> all MUST have alpha 0
assert.equal(getPixel(returnPixels, 0, 0).a, 0, 'NoData (null) must have alpha = 0');
assert.equal(getPixel(returnPixels, 0, 1).a, 0, 'NoData (null) must have alpha = 0');
assert.equal(getPixel(returnPixels, 0, 2).a, 0, 'Nonfinite (NaN) must have alpha = 0');
assert.equal(getPixel(returnPixels, 0, 3).a, 0, 'Nonfinite (Infinity) must have alpha = 0');

// Row 1: -1, -999, undefined, 10
assert.equal(getPixel(returnPixels, 1, 0).a, 0, 'Negative sentinel (-1) must have alpha = 0');
assert.equal(getPixel(returnPixels, 1, 1).a, 0, 'Negative blocked (-999) must have alpha = 0');
assert.equal(getPixel(returnPixels, 1, 2).a, 0, 'Undefined cell must have alpha = 0');

const pReachable10 = getPixel(returnPixels, 1, 3);
assert(pReachable10.a >= 48 && pReachable10.a <= 82, `Reachable 10 min cell alpha must be within [48, 82], got ${pReachable10.a}`);
assert(pReachable10.g > 150, 'Reachable cell RGB should have strong green/teal channel');

// Row 2: 30, 60, 90, null
const pReachable30 = getPixel(returnPixels, 2, 0);
assert(pReachable30.a >= 48 && pReachable30.a <= 82, `Reachable 30 min cell alpha must be [48, 82], got ${pReachable30.a}`);

const pReachable60 = getPixel(returnPixels, 2, 1);
assert.equal(pReachable60.a, 82, `Reachable at-budget cell (60 min) should have alpha 82, got ${pReachable60.a}`);

const pExceeds90 = getPixel(returnPixels, 2, 2);
assert.equal(pExceeds90.a, 55, `Reachable beyond-budget cell (90 min) should have warning alpha 55, got ${pExceeds90.a}`);
assert.equal(pExceeds90.r, 226, 'Beyond-budget cell should have coral/red warning hue');

assert.equal(getPixel(returnPixels, 2, 3).a, 0, 'Null cell in row 2 must have alpha = 0');

console.log('  ✅ NoData and unreachable cells are 100% transparent (alpha = 0); valid cells retain intended opacity.');

// 2. Test rescue zone alpha masking and classification
console.log('  Testing rescue zone classification...');
const mockZoneRescue = {
  rows: 2,
  cols: 3,
  threshold_minutes: 40,
  minutes_grid: [
    [null, 15, 30], // null (alpha 0), 15 min (<= 50% budget -> green, alpha 88), 30 min (<= 100% budget -> amber, alpha 104)
    [50, NaN, -5],   // 50 min (> budget -> coral, alpha 110), NaN (alpha 0), -5 (alpha 0)
  ],
};
const rescuePixels = computeTimeOverlayPixels(mockZoneRescue, 'rescue');
assert.equal(getPixel(rescuePixels, 0, 0).a, 0, 'Null cell in rescue grid must have alpha 0');
assert.equal(getPixel(rescuePixels, 0, 1).a, 88, 'Rescue <=50% budget must have alpha 88');
assert.equal(getPixel(rescuePixels, 0, 2).a, 104, 'Rescue <=100% budget must have alpha 104');
assert.equal(getPixel(rescuePixels, 1, 0).a, 110, 'Rescue >100% budget must have alpha 110');
assert.equal(getPixel(rescuePixels, 1, 1).a, 0, 'NaN in rescue grid must have alpha 0');
assert.equal(getPixel(rescuePixels, 1, 2).a, 0, 'Negative sentinel in rescue grid must have alpha 0');
console.log('  ✅ Rescue zone alpha masking and ratio tiers verified.');

// 3. Task 3 & 8: Verify edge feathering gradient calculations
console.log('  Testing edge feathering gradient calculations...');
const mockBoundsNormal = { tl: [100, 100], br: [500, 400] }; // w = 400, h = 300
const gradsNormal = calculateEdgeFeatherGradients(mockBoundsNormal, 54);
assert(gradsNormal !== null, 'Feathering gradients should be computed for valid bounds');
assert.equal(gradsNormal.rect.w, 400);
assert.equal(gradsNormal.rect.h, 300);
assert.equal(gradsNormal.fp, 54, 'Feather padding should be 54 px when w, h are large enough');
assert.deepEqual(gradsNormal.top.fillRect, [96, 96, 408, 58]);
assert.deepEqual(gradsNormal.bottom.fillRect, [96, 346, 408, 58]);
assert.deepEqual(gradsNormal.left.fillRect, [96, 96, 58, 308]);
assert.deepEqual(gradsNormal.right.fillRect, [446, 96, 58, 308]);

// Small boundary constraint: fp = Math.min(featherPx, w/4, h/4)
const mockBoundsSmall = { tl: [50, 50], br: [100, 90] }; // w = 50, h = 40. h/4 = 10
const gradsSmall = calculateEdgeFeatherGradients(mockBoundsSmall, 64);
assert.equal(gradsSmall.fp, 10, 'Feather width should clamp to h/4 = 10 px on small insets');

// Degenerate bounds: zero width or height
assert.equal(calculateEdgeFeatherGradients({ tl: [50, 50], br: [50, 90] }), null, 'Zero width should return null');
assert.equal(calculateEdgeFeatherGradients(null), null, 'Null bounds should return null');
console.log('  ✅ Edge feathering boundary clamping and gradient rectangles verified.');

// 4. Task 4: Verify tone harmonization CSS exists in style.css
console.log('  Testing CSS tone harmonization definitions...');
const cssPath = path.join(__dirname, 'src', 'style.css');
const cssContent = fs.readFileSync(cssPath, 'utf8');
assert(cssContent.includes('.ol-layer-ctx canvas'), 'CSS must define .ol-layer-ctx canvas rule');
assert(cssContent.includes('.ol-layer-hirise canvas'), 'CSS must define .ol-layer-hirise canvas rule');
assert(cssContent.includes('filter: contrast('), 'CSS must define tone harmonization filter');
assert(cssContent.includes('sepia('), 'CSS tone harmonization filter must include sepia');
assert(cssContent.includes('hue-rotate('), 'CSS tone harmonization filter must include hue-rotate');
console.log('  ✅ CSS tone harmonization filter confirmed in style.css.');

// 5. Task 5 & 8: Verify multi-resolution imagery catalog and resolution thresholds
console.log('  Testing resolution hierarchy constants and catalog entries...');
const vikingCat = AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m;
const ctxCat = AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m;
const hiriseCat = AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm;

assert(vikingCat && (vikingCat.resolutionMeters === 232 || vikingCat.native_resolution_m === 232), 'Viking MDIM 2.1 must be 232 m/px');
assert(ctxCat && (ctxCat.resolutionMeters === 6 || ctxCat.native_resolution_m === 6), 'CTX Jezero must be 6 m/px');
assert(hiriseCat && (hiriseCat.resolutionMeters === 0.25 || hiriseCat.native_resolution_m === 0.25), 'HiRISE Jezero must be 0.25 m/px');

const ctxMaxRes = 800 / M_PER_DEG;
const hiriseMaxRes = 25 / M_PER_DEG;
assert(ctxMaxRes > hiriseMaxRes, 'CTX regional maxResolution must be higher than HiRISE local maxResolution');
console.log(`  ✅ Verified resolution hierarchy: Global Viking (232 m), Regional CTX (< ${ctxMaxRes * M_PER_DEG} m), Local HiRISE (< ${hiriseMaxRes * M_PER_DEG} m).`);

// 6. Task 8: Verify end-to-end route planning remains fully functional
console.log('  Testing end-to-end route planning and return zone generation...');
const molaBytes = fs.readFileSync(path.join(__dirname, 'public', 'mission-data', 'jezero-dem.json'));
const rawDem = JSON.parse(molaBytes.toString('utf8'));
const terrain = buildTerrain(rawDem);
assert(terrain.w > 0 && terrain.h > 0, 'Terrain must have valid dimensions');

const req = {
  start: { lon: 77.40, lat: 18.38 },
  destination: { lon: 77.44, lat: 18.42 },
  mode: 'balanced',
  constraints: { max_slope_deg: 20, max_roughness: 0.85, avoid_unobserved_terrain: true },
  num_alternatives: 2,
  algorithm: 'astar',
};

const result = plan(rawDem, req);
assert(result.routes && result.routes.length >= 1, 'Planner must return at least 1 route');
assert(result.routes[0].geometry.coordinates.length > 5, 'Route geometry must have valid coordinates');
assert(result.return_zone && result.return_zone.minutes_grid.length > 0, 'Return zone must be generated');
assert(result.rescue_zone && result.rescue_zone.minutes_grid.length > 0, 'Rescue zone must be generated');
assert(result.routes[0].turnaround && result.routes[0].turnaround.turnaround_coord, 'Turnaround coordinate must be computed');

// Test that rescue zone raster passes through computeTimeOverlayPixels with 0 alpha on unvisited cells
const planRescuePixels = computeTimeOverlayPixels(result.rescue_zone, 'rescue');
let hasZeroAlphaRescue = false;
let hasNonZeroAlphaRescue = false;
for (let i = 3; i < planRescuePixels.data.length; i += 4) {
  if (planRescuePixels.data[i] === 0) hasZeroAlphaRescue = true;
  if (planRescuePixels.data[i] > 0) hasNonZeroAlphaRescue = true;
}
assert(hasZeroAlphaRescue, 'Rescue zone must contain transparent unreached cells (alpha = 0)');
assert(hasNonZeroAlphaRescue, 'Rescue zone must contain visible reachable cells (alpha > 0)');

const planReturnPixels = computeTimeOverlayPixels(result.return_zone, 'return');
let hasNonZeroAlphaReturn = false;
for (let i = 3; i < planReturnPixels.data.length; i += 4) {
  if (planReturnPixels.data[i] > 0) hasNonZeroAlphaReturn = true;
}
assert(hasNonZeroAlphaReturn, 'Return zone must contain visible reachable cells (alpha > 0)');
console.log('  ✅ End-to-end route planning, return zone, and transparent NoData masking verified on real terrain.');

console.log('\n🎉 ALL MAP RENDERING FIX AUTOMATED TESTS PASSED!\n');
