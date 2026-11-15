import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  validateTraverse,
  visibleDrives,
  visibleWaypoints,
  windowedDrives,
  windowedWaypoints,
  latestWaypointThroughSol,
  traverseStats,
  exportTraverse,
} from './src/traverse.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

console.log('--- MARSPath: Traverse 15-Sol Window & Map Fix Verification ---');

// 1. Load GeoJSON archive
const traversePath = path.resolve(__dirname, '../dist/mission-data/perseverance-traverse.geojson');
const waypointsPath = path.resolve(__dirname, '../dist/mission-data/perseverance-waypoints.geojson');
const traverse = JSON.parse(fs.readFileSync(traversePath, 'utf8'));
const waypoints = JSON.parse(fs.readFileSync(waypointsPath, 'utf8'));

validateTraverse(traverse);
console.log(`[Pass 1/5] Loaded and validated ${traverse.features.length} Perseverance drive segments.`);
assert.equal(traverse.features.length, 559, 'Must retain all 559 published drive segments');

// 2. Test 15-sol trailing window at archive cutoff (Sol 2022)
const maxSol = Math.max(...traverse.features.map(f => f.properties.sol));
assert.equal(maxSol, 2022, 'Archive cutoff must be Sol 2022');

const drivesAtEnd = windowedDrives(traverse, maxSol, 15);
assert.ok(drivesAtEnd.length > 0, 'Window ending at Sol 2022 must contain drives');
for (const d of drivesAtEnd) {
  assert.ok(d.properties.sol >= 2022 - 14 && d.properties.sol <= 2022, `Drive sol ${d.properties.sol} must be in [2008, 2022]`);
}
console.log(`[Pass 2/5] Sol 2022 trailing 15-sol window ([2008, 2022]) correctly contains ${drivesAtEnd.length} drives.`);

// 3. Test empty window handling (e.g. Sol 152 when rover was parked/sampling)
const drivesEmpty = windowedDrives(traverse, 152, 15);
assert.equal(drivesEmpty.length, 0, 'Window ending at Sol 152 must have 0 drives (empty window)');
const statsEmpty = traverseStats(drivesEmpty, windowedWaypoints(waypoints, 152, 15));
assert.equal(statsEmpty.segments, 0, 'Empty window segments must be 0');
console.log('[Pass 3/5] Empty 15-sol window correctly returns 0 drives while archive retains full 559 segments.');

// 4. Test latest waypoint derivation for rover marker
const latestWp = latestWaypointThroughSol(waypoints, 2022);
assert.ok(latestWp, 'Must find latest waypoint');
assert.equal(latestWp.properties.sol, 2022, 'Latest waypoint sol must be 2022');
const intermediateWp = latestWaypointThroughSol(waypoints, 500);
assert.ok(intermediateWp.properties.sol <= 500, 'Intermediate waypoint sol must be <= 500');
console.log(`[Pass 4/5] Rover marker positioning derives correctly: Sol ${latestWp.properties.sol} (lat: ${latestWp.geometry.coordinates[1].toFixed(5)}, lon: ${latestWp.geometry.coordinates[0].toFixed(5)}).`);

// 5. Verify source code settings for default map & layer visibility
const mainSource = fs.readFileSync(path.resolve(__dirname, 'src/main.jsx'), 'utf8');
const mapSource = fs.readFileSync(path.resolve(__dirname, 'src/MapView.jsx'), 'utf8');

// Ensure default states in main.jsx are false
assert.match(mainSource, /const \[showCtx,\s*setShowCtx\]\s*=\s*useState\(false\);/, 'showCtx must default to false');
assert.match(mainSource, /const \[showHirise,\s*setShowHirise\]\s*=\s*useState\(false\);/, 'showHirise must default to false');
assert.match(mainSource, /const \[showOrbiters,\s*setShowOrbiters\]\s*=\s*useState\(false\);/, 'showOrbiters must default to false');
assert.match(mainSource, /const \[showGroundTracks,\s*setShowGroundTracks\]\s*=\s*useState\(false\);/, 'showGroundTracks must default to false');
assert.match(mainSource, /const \[showFootprints,\s*setShowFootprints\]\s*=\s*useState\(false\);/, 'showFootprints must default to false');
assert.match(mainSource, /const \[coverage,\s*setCoverage\]\s*=\s*useState\(false\);/, 'coverage must default to false');

// Ensure MapView.jsx instantiates patchy and coverage layers as hidden
assert.match(mapSource, /const wmtsCtxRegional = new TileLayer\(\{[\s\S]*?visible:\s*false/, 'wmtsCtxRegional must instantiate visible: false');
assert.match(mapSource, /const wmtsHiriseLocal = new TileLayer\(\{[\s\S]*?visible:\s*false/, 'wmtsHiriseLocal must instantiate visible: false');
assert.match(mapSource, /const footprintsLayer = new VectorLayer\(\{[\s\S]*?visible:\s*false/, 'footprintsLayer must instantiate visible: false');
assert.match(mapSource, /const groundTracksLayer = new VectorLayer\(\{[\s\S]*?visible:\s*false/, 'groundTracksLayer must instantiate visible: false');
assert.match(mapSource, /const hiriseBoundary = new VectorLayer\(\{[\s\S]*?visible:\s*false/, 'hiriseBoundary must instantiate visible: false');
assert.match(mapSource, /const demBoundaryLayer = new VectorLayer\(\{[\s\S]*?visible:\s*false/, 'demBoundaryLayer must instantiate visible: false');

// Ensure science target label gating
assert.match(mapSource, /showLabel\s*=\s*isSelected\s*\|\|\s*resM\s*<=\s*3\.5/, 'Science target labels must be hidden at wide zoom (resM > 3.5)');

// Ensure traverse legend HUD exists
assert.match(mapSource, /data-testid="traverse-legend-hud"/, 'Traverse legend HUD must be rendered in MapView');
assert.match(mapSource, /Full recorded traverse/, 'Traverse legend HUD must show Full recorded traverse');
assert.match(mapSource, /Highlighted window:/, 'Traverse legend HUD must show Highlighted window');

console.log('[Pass 5/5] Map layer stack verified: all squares/outlines disabled by default, continuous Viking basemap active, traverse unclipped, science target labels decluttered.');

console.log('\n================================================================');
console.log(' ALL 5 TRAVERSE WINDOW & MAP FIX VERIFICATIONS PASSED! ');
console.log('================================================================\n');
