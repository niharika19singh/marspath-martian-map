import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ORBITER_SPECS,
  propagateKeplerian,
  fetchSpacecraftList,
  fetchGroundTrack,
  fetchRoverList,
  fetchOrbitalObservations,
  fetchMissionTimeline,
  triggerSync
} from './src/intelligence.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

console.log('🧪 Starting Live Mars Intelligence Frontend & Data Verification...');

// 1. Verify Orbiter Astrodynamics Propagator
const testDate = new Date('2026-11-14T09:00:00Z');
for (const [id, spec] of Object.entries(ORBITER_SPECS)) {
  const pos = propagateKeplerian(id, testDate);
  assert(pos, `Position should be calculated for ${id}`);
  assert.equal(pos.spacecraft_id, spec.id);
  assert(Number.isFinite(pos.lon) && pos.lon >= -180 && pos.lon <= 180, `Invalid longitude for ${id}: ${pos.lon}`);
  assert(Number.isFinite(pos.lat) && pos.lat >= -90 && pos.lat <= 90, `Invalid latitude for ${id}: ${pos.lat}`);
  assert(Number.isFinite(pos.altitude_km) && pos.altitude_km >= 200, `Altitude too low for ${id}: ${pos.altitude_km}`);
  const speed = pos.velocity_kms ?? pos.orbital_speed_km_s;
  assert(Number.isFinite(speed) && speed > 1.0 && speed < 6.0, `Speed out of bounds for ${id}: ${speed}`);
  assert(Number.isFinite(pos.heading_deg) && pos.heading_deg >= 0 && pos.heading_deg <= 360, `Heading out of bounds for ${id}: ${pos.heading_deg}`);
  assert.equal(pos.state, 'PREDICTED');
  assert.equal(pos.coordinate_system, 'IAU2000:49900');
  console.log(`  ✓ Propagated ${spec.name.padEnd(30)}: Lon ${pos.lon.toFixed(2)}°, Lat ${pos.lat.toFixed(2)}°, Alt ${Math.round(pos.altitude_km)} km`);
}

// 2. Verify Ground Track Generator
const mroTrack = await fetchGroundTrack('mro', 120, 60);
assert(mroTrack, 'Ground track should be returned');
assert.equal(mroTrack.spacecraft_id, 'mro');
assert(mroTrack.points.length >= 100, `Ground track point count insufficient: ${mroTrack.points.length}`);
for (const pt of mroTrack.points) {
  assert(Number.isFinite(pt.lon) && pt.lon >= -180 && pt.lon <= 180);
  assert(Number.isFinite(pt.lat) && pt.lat >= -90 && pt.lat <= 90);
}
console.log(`  ✓ Generated MRO Ground Track: ${mroTrack.points.length} nodes over ${mroTrack.duration_minutes} minutes`);

// 3. Verify Curiosity Gale Crater Datasets
const curiosityTraversePath = path.resolve(__dirname, '../dist/mission-data/curiosity-traverse.geojson');
const curiosityWaypointsPath = path.resolve(__dirname, '../dist/mission-data/curiosity-waypoints.geojson');

assert(fs.existsSync(curiosityTraversePath), `Curiosity traverse file missing at ${curiosityTraversePath}`);
assert(fs.existsSync(curiosityWaypointsPath), `Curiosity waypoints file missing at ${curiosityWaypointsPath}`);

const curiosityTraverse = JSON.parse(fs.readFileSync(curiosityTraversePath, 'utf8'));
const curiosityWaypoints = JSON.parse(fs.readFileSync(curiosityWaypointsPath, 'utf8'));

assert.equal(curiosityTraverse.type, 'FeatureCollection');
assert(curiosityTraverse.features.length >= 20, `Traverse features count insufficient: ${curiosityTraverse.features.length}`);
for (const f of curiosityTraverse.features) {
  assert.equal(f.type, 'Feature');
  assert.equal(f.geometry.type, 'LineString');
  assert(f.properties.sol >= 0 && f.properties.sol <= 4400);
  for (const coord of f.geometry.coordinates) {
    assert(coord[0] >= 137.0 && coord[0] <= 138.0, `Gale Crater longitude out of range: ${coord[0]}`);
    assert(coord[1] >= -5.0 && coord[1] <= -4.0, `Gale Crater latitude out of range: ${coord[1]}`);
  }
}

const waypointsList = Array.isArray(curiosityWaypoints) ? curiosityWaypoints : (curiosityWaypoints.features || []);
assert(waypointsList.length >= 20, `Waypoints count insufficient: ${waypointsList.length}`);
const latestWp = waypointsList[waypointsList.length - 1];
assert.equal(latestWp.properties.sol, 4400);
const odom = latestWp.properties.dist_total_m ?? latestWp.properties.odometry_m;
assert(odom > 33000, `Curiosity odometry should exceed 33 km: ${odom}`);
console.log(`  ✓ Verified Curiosity Gale Crater Dataset: ${curiosityTraverse.features.length} drive legs, Sol 0 to 4400, ${odom} m odometry`);

// 4. Verify Intelligence Services Fallback Contracts
const spacecraft = await fetchSpacecraftList();
assert.equal(spacecraft.length, 5, 'Should return 5 spacecraft');
assert(spacecraft.some(s => s.spacecraft_id === 'mro'));
assert(spacecraft.some(s => s.spacecraft_id === 'ody'));
assert(spacecraft.some(s => s.spacecraft_id === 'maven'));
assert(spacecraft.some(s => s.spacecraft_id === 'mex'));
assert(spacecraft.some(s => s.spacecraft_id === 'tgo'));
console.log('  ✓ Verified Spacecraft List Contract (5 Mars orbiters)');

const rovers = await fetchRoverList();
assert.equal(rovers.length, 2, 'Should return 2 rovers');
const m20 = rovers.find(r => r.rover_id === 'perseverance');
const msl = rovers.find(r => r.rover_id === 'curiosity');
assert(m20 && msl);
assert(m20.sol >= 2022);
assert(m20.total_odometry_meters > 45000);
assert(msl.sol >= 4400);
assert(msl.total_odometry_meters > 33000);
assert.equal(m20.state, 'LATEST AVAILABLE');
assert.equal(msl.state, 'LATEST AVAILABLE');
console.log('  ✓ Verified Rover Telemetry Contract (Perseverance Sol 2022+, Curiosity Sol 4400+)');

const observations = await fetchOrbitalObservations();
assert(observations.length >= 2, 'Should return at least 2 observations');
assert(observations.some(o => o.instrument === 'HiRISE'));
assert(observations.some(o => o.instrument === 'CTX'));
for (const obs of observations) {
  assert(obs.footprint_geojson && obs.footprint_geojson.geometry.coordinates);
  assert(obs.pds_product_id);
}
console.log(`  ✓ Verified Orbital Observations Contract (${observations.length} high-resolution footprints)`);

const timeline = await fetchMissionTimeline(10);
assert(timeline.length >= 2);
console.log(`  ✓ Verified Mission Timeline Contract (${timeline.length} events)`);

const syncResult = await triggerSync();
assert.equal(syncResult.success, true);
assert(syncResult.updated_sources.length > 0);
console.log('  ✓ Verified Operational Synchronization Contract');

console.log('🎉 ALL LIVE MARS INTELLIGENCE FRONTEND & DATA CHECKS PASSED!\n');
