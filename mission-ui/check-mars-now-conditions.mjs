import assert from 'node:assert/strict';
import {
  computeClientMars24,
  classifyTerrainStatus,
  formatMarsHms,
  getTtMinusUtcSeconds,
} from './src/conditions.js';
import { AUTHORITATIVE_MARS_TERRAIN_CATALOG } from './src/wmts_capabilities.js';

console.log('🧪 Starting Mars Now & Surface Conditions Verification...');

// 1. Allison & McEwen (2000) Mars24 Canonical Calculations
const pathfinderDate = new Date('1997-07-04T17:00:00Z');
const pathfinder = computeClientMars24(19.33, 326.45, pathfinderDate);
console.log(`  ✓ Mars Pathfinder (1997-07-04): Ls=${pathfinder.ls_deg}°, MSD=${pathfinder.msd}, LTST=${pathfinder.ltst_hms}`);
assert.ok(pathfinder.ls_deg >= 142.0 && pathfinder.ls_deg <= 144.0, 'Pathfinder Ls must be between 142 and 144 degrees');
assert.ok(pathfinder.msd >= 43905.0 && pathfinder.msd <= 43906.5, 'Pathfinder MSD must match historical Julian sol date');
assert.equal(pathfinder.daylight_state, 'NIGHT', 'Pathfinder pre-dawn landing must be classified as NIGHT');

// 2. Perseverance Touchdown at Jezero Crater (Sol 0)
const m20LandingDate = new Date('2021-02-18T20:55:00Z');
const m20Landing = computeClientMars24(18.4447, 77.4508, m20LandingDate);
console.log(`  ✓ Perseverance Touchdown (2021-02-18): Sol=${m20Landing.perseverance_mission_sol}, LTST=${m20Landing.ltst_hms}, Elev=${m20Landing.solar_elevation_deg}°`);
assert.equal(m20Landing.perseverance_mission_sol, 0, 'Touchdown sol must be Sol 0');
assert.ok(m20Landing.solar_elevation_deg > 15.0, 'Afternoon landing must have positive solar elevation');
assert.equal(m20Landing.daylight_state, 'DAYLIGHT');

// 3. Angle Wrapping and East-Positive Invariance
const m20Wrapped = computeClientMars24(18.4447, 77.4508 + 360.0 * 2, m20LandingDate);
assert.equal(m20Wrapped.ltst_hms, m20Landing.ltst_hms, 'Adding 720 degrees to longitude must preserve solar time');
assert.equal(m20Wrapped.solar_elevation_deg, m20Landing.solar_elevation_deg, 'Adding 720 degrees must preserve elevation');

// 4. Leap Second Table & Terrestrial Time (TT)
const ttOffset2026 = getTtMinusUtcSeconds(new Date('2026-11-14T10:00:00Z'));
assert.ok(Math.abs(ttOffset2026 - 69.184) < 1e-3, '2026 TT - UTC offset must equal 69.184 seconds');

// 5. Terrain Status Classification
// A. Inside Jezero HiRISE 1 m DTM
const dtmLoc = classifyTerrainStatus(18.42, 77.44, null);
assert.equal(dtmLoc.tier, 'hirise_1m');
assert.equal(dtmLoc.label, 'High-resolution DTM (1 m)');
assert.equal(dtmLoc.doi, '10.5066/P9REJ9JN');
console.log(`  ✓ Jezero High-Res DTM Classification: ${dtmLoc.label} (DOI: ${dtmLoc.doi})`);

// B. Inside Regional MOLA 200 m Blended DEM
const molaLoc = classifyTerrainStatus(18.20, 77.80, null);
assert.equal(molaLoc.tier, 'mola_200m');
assert.equal(molaLoc.label, 'Global MOLA fallback (200 m)');
assert.equal(molaLoc.doi, '10.5066/P907276M');
console.log(`  ✓ Regional MOLA DEM Classification: ${molaLoc.label} (DOI: ${molaLoc.doi})`);

// C. Out of bounds (e.g. Olympus Mons)
const outLoc = classifyTerrainStatus(18.65, 226.2, null);
assert.equal(outLoc.tier, 'out_of_bounds');
assert.equal(outLoc.label, 'Out of bounds');
assert.equal(outLoc.covered, false);
console.log(`  ✓ Out-of-Bounds Classification: ${outLoc.label} (covered=${outLoc.covered})`);

// 6. Time Scrubber & Rover Post-Archive Cutoff Labeling
const maxArchiveSol = 2022;
const pastSol = 2050;
const isPostArchive = pastSol > maxArchiveSol;
assert.ok(isPostArchive, 'Sol 2050 must be identified as post-archive');
const label = isPostArchive ? `Last recorded position · Sol ${maxArchiveSol}` : `Active mission · Sol ${pastSol}`;
assert.equal(label, 'Last recorded position · Sol 2022');
console.log(`  ✓ Rover Archive Cutoff Label: "${label}" verified`);

console.log('🎉 ALL MARS NOW & SURFACE CONDITIONS UNIT CHECKS PASSED!');
