import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

import {
  AUTHORITATIVE_MARS_IMAGERY_CATALOG,
  AUTHORITATIVE_MARS_TERRAIN_CATALOG,
  parseWMTSCapabilitiesXml,
  createOpenLayersWMTSSource,
  verifyCoordinateDatasetCoverage,
} from './src/wmts_capabilities.js';
import { buildTerrain } from './src/terrain.js';
import { plan } from './src/engine.js';
import { resolveTerrainProvenance } from './src/integration.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const publicDir = path.join(__dirname, 'public', 'mission-data');

console.log('🧪 Starting USGS Jezero Imagery & 1 m DTM Integration Verification...');

// 1. WMTS GetCapabilities parsing across all 4 official NASA Mars Trek / USGS layers
const expectedLayerChecks = [
  {
    key: 'viking_global_232m',
    id: 'Mars_Viking_MDIM21_ClrMosaic_global_232m',
    minZoom: 0,
    maxZoom: 7,
    format: 'image/jpeg',
    matrixSet: 'default028mm',
  },
  {
    key: 'ctx_jezero_6m',
    id: 'JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',
    minZoom: 0,
    maxZoom: 13,
    format: 'image/png',
    matrixSet: 'default028mm',
  },
  {
    key: 'hirise_jezero_25cm',
    id: 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd',
    minZoom: 0,
    maxZoom: 17,
    format: 'image/png',
    matrixSet: 'default028mm',
  },
  {
    key: 'mola_hrsc_shaded_200m',
    id: 'Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw',
    minZoom: 0,
    maxZoom: 8,
    format: 'image/jpeg',
    matrixSet: 'default028mm',
  },
];

for (const check of expectedLayerChecks) {
  const xmlPath = path.join(publicDir, 'wmts', `${check.id}.xml`);
  assert.ok(fs.existsSync(xmlPath), `Missing capabilities XML: ${xmlPath}`);
  const xmlText = fs.readFileSync(xmlPath, 'utf8');
  const parsed = parseWMTSCapabilitiesXml(xmlText);

  assert.equal(parsed.layerId, check.id);
  assert.equal(parsed.format, check.format);
  assert.equal(parsed.matrixSet, check.matrixSet);
  assert.equal(parsed.minZoom, check.minZoom);
  assert.equal(parsed.maxZoom, check.maxZoom);
  assert.equal(parsed.matrices.length, check.maxZoom + 1);
  assert.deepEqual(parsed.origin, [-180, 90]);
  assert.equal(parsed.matrices[0].tileWidth, 256);
  assert.equal(parsed.matrices[0].tileHeight, 256);
  assert.equal(parsed.matrices[0].matrixWidth, 2);
  assert.equal(parsed.matrices[0].matrixHeight, 1);

  // 2. TileGrid construction & 3. Tile URL generation
  const source = createOpenLayersWMTSSource(parsed);
  const tileGrid = source.getTileGrid();
  assert.ok(source, `WMTS source should be constructed for ${check.id}`);
  assert.ok(tileGrid, `WMTSTileGrid should be constructed for ${check.id}`);
  assert.equal(tileGrid.getResolutions().length, check.maxZoom + 1);
  assert.equal(tileGrid.getMatrixIds().length, check.maxZoom + 1);
  assert.equal(parsed.resourceUrlTemplate.includes('{TileMatrix}'), true);
  assert.equal(parsed.resourceUrlTemplate.includes('{TileRow}'), true);
  assert.equal(parsed.resourceUrlTemplate.includes('{TileCol}'), true);

  const tileUrlFn = source.getTileUrlFunction();
  const sampleUrl = tileUrlFn([0, 1, 0], 1, 'IAU2000:49900');
  const ext = check.format === 'image/png' ? '.png' : '.jpg';
  assert.ok(
    sampleUrl.endsWith(`/${check.id}/1.0.0/default/default028mm/0/0/1${ext}`),
    `Unexpected WMTS tile URL for ${check.id}: ${sampleUrl}`
  );
  console.log(`  ✓ Parsed WMTSCapabilities.xml, constructed WMTSTileGrid (z=0..${check.maxZoom}), and verified tile URL for [${check.id}]`);
}

// 4. Coordinate coverage checks for 77.4000°E, 18.3900°N and 77.4400°E, 18.4200°N
const startPoint = { lon: 77.4000, lat: 18.3900 };
const destPoint = { lon: 77.4400, lat: 18.4200 };
const outOfBoundsPoint = { lon: 137.4, lat: -4.6 }; // Gale Crater

const hiriseBytes = fs.readFileSync(path.join(publicDir, 'jezero-hirise-dtm.json'));
const hiriseShaExpected = fs.readFileSync(path.join(publicDir, 'jezero-hirise-dtm.sha256'), 'utf8').trim();
const hiriseShaActual = createHash('sha256').update(hiriseBytes).digest('hex');
assert.equal(hiriseShaActual, hiriseShaExpected, 'jezero-hirise-dtm.json SHA-256 verification failed');
const hiriseRaw = { ...JSON.parse(hiriseBytes.toString('utf8')), local_integrity_verified: true, file_sha256: hiriseShaActual };
const hiriseTerrain = buildTerrain(hiriseRaw);

const molaBytes = fs.readFileSync(path.join(publicDir, 'jezero-dem.json'));
const molaShaExpected = fs.readFileSync(path.join(publicDir, 'jezero-dem.sha256'), 'utf8').trim();
const molaShaActual = createHash('sha256').update(molaBytes).digest('hex');
assert.equal(molaShaActual, molaShaExpected, 'jezero-dem.json SHA-256 verification failed');
const molaRaw = { ...JSON.parse(molaBytes.toString('utf8')), local_integrity_verified: true, file_sha256: molaShaActual };

const coverageReport = verifyCoordinateDatasetCoverage(startPoint, destPoint, hiriseTerrain);
assert.equal(coverageReport.hiriseOrthoCovered, true, 'Start & Destination must be inside USGS HiRISE orthomosaic bounds (10.5066/P9QJDP48)');
assert.equal(coverageReport.hiriseDtmOfficialCovered, true, 'Start & Destination must be inside USGS HiRISE DTM official bounds (10.5066/P9REJ9JN)');
assert.equal(coverageReport.bothInLocalHiriseDtmCorridor, true, 'Start & Destination must be inside provisioned 1 m HiRISE DTM corridor');
assert.equal(coverageReport.ctxOrthoCovered, true, 'Start & Destination must be inside USGS CTX orthomosaic bounds (10.5066/P9GV1ND3)');
assert.equal(coverageReport.activeHiriseDtmStatus.covered, true, 'Start & Destination must be covered by active 1 m HiRISE DTM');
assert.equal(coverageReport.activeHiriseDtmStatus.reason, 'VALIDATED');
console.log('  ✓ Verified Start (77.4000°E, 18.3900°N) & Destination (77.4400°E, 18.4200°N) are inside official USGS bounds and active 1 m DTM');

// 5. USGS HiRISE orthomosaic metadata validation (10.5066/P9QJDP48)
const orthoMeta = AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm;
assert.equal(orthoMeta.doi, '10.5066/P9QJDP48');
assert.equal(orthoMeta.productId, 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first');
assert.equal(orthoMeta.id, 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd');
assert.equal(orthoMeta.resolutionMeters, 0.25);
assert.equal(orthoMeta.dataType, 'imagery');
assert.deepEqual(orthoMeta.bounds, [77.2229331, 18.3067994, 77.583964, 18.669315]);
console.log('  ✓ Validated USGS HiRISE 25 cm Orthomosaic metadata (DOI: 10.5066/P9QJDP48)');

// 6. USGS HiRISE DTM metadata validation (10.5066/P9REJ9JN)
const dtmMeta = AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m;
assert.equal(dtmMeta.doi, '10.5066/P9REJ9JN');
assert.equal(dtmMeta.productId, 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40');
assert.equal(dtmMeta.resolutionMeters, 1.0);
assert.equal(dtmMeta.dataType, 'elevation');
assert.equal(dtmMeta.verticalUnits, 'meters');
assert.equal(hiriseRaw.doi, '10.5066/P9REJ9JN');
assert.equal(hiriseRaw.product_id, 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40');
assert.equal(hiriseRaw.native_resolution_m ?? hiriseRaw.native_resolution_meters, 1.0);
assert.equal(hiriseRaw.units, 'meters');
console.log('  ✓ Validated USGS HiRISE 1 m DTM metadata and bundled terrain grid (DOI: 10.5066/P9REJ9JN)');

// 7. Route calculation using the active DEM (1 m HiRISE DTM vs 200 m MOLA-HRSC DEM)
const routeRequest = {
  start: startPoint,
  destination: destPoint,
  mode: 'balanced',
  algorithm: 'astar',
  num_alternatives: 2,
  constraints: { max_slope_deg: 20, max_roughness: 0.85, avoid_unobserved_terrain: true },
  science_waypoints: [],
};
const routeResultHirise = plan(hiriseRaw, routeRequest);
const routeResultMola = plan(molaRaw, routeRequest);

assert.ok(routeResultHirise.routes.length >= 1, 'HiRISE DTM route calculation should return at least 1 candidate');
assert.ok(routeResultMola.routes.length >= 1, 'MOLA-HRSC DEM route calculation should return at least 1 candidate');
assert.equal(routeResultHirise.source_selection.doi, '10.5066/P9REJ9JN');
assert.equal(routeResultHirise.source_selection.native_resolution_meters, 1.0);
assert.equal(routeResultMola.source_selection.doi, '10.5066/P907276M');
assert.equal(routeResultMola.source_selection.native_resolution_meters, 200.0);
assert.notEqual(
  routeResultHirise.routes[0].total_cost,
  routeResultMola.routes[0].total_cost,
  'Switching the active DEM between 1 m HiRISE DTM and 200 m MOLA-HRSC DEM must update terrain calculations and route cost'
);
console.log(
  `  ✓ Verified route engine DEM differentiation: HiRISE 1 m DTM cost=${routeResultHirise.routes[0].total_cost.toFixed(1)} (${routeResultHirise.routes[0].geometry.coordinates.length} pts) vs MOLA-HRSC 200 m DEM cost=${routeResultMola.routes[0].total_cost.toFixed(1)} (${routeResultMola.routes[0].geometry.coordinates.length} pts)`
);

// 8. Fallback reason reporting when high-resolution data is unavailable or out of coverage
const missingDtmReport = verifyCoordinateDatasetCoverage(startPoint, destPoint, null);
assert.equal(missingDtmReport.activeHiriseDtmStatus.covered, false);
assert.equal(missingDtmReport.activeHiriseDtmStatus.reason, 'NOT_DOWNLOADED_OR_NOT_LOADED');

const outOfCoverageReport = verifyCoordinateDatasetCoverage(startPoint, outOfBoundsPoint, hiriseTerrain);
assert.equal(outOfCoverageReport.activeHiriseDtmStatus.covered, false);
assert.equal(outOfCoverageReport.activeHiriseDtmStatus.reason, 'OUTSIDE_COVERAGE');

const provHirise = resolveTerrainProvenance({
  live: false,
  raw: hiriseRaw,
  loadError: '',
  api: null,
  result: routeResultHirise,
  active: routeResultHirise.routes[0],
});
assert.equal(provHirise.datasetDoi, '10.5066/P9REJ9JN');
assert.equal(provHirise.activeDemSourceLabel, 'USGS HiRISE DTM · 1 m/px');

const provMola = resolveTerrainProvenance({
  live: false,
  raw: molaRaw,
  loadError: '',
  api: null,
  result: routeResultMola,
  active: routeResultMola.routes[0],
});
assert.equal(provMola.datasetDoi, '10.5066/P907276M');
assert.equal(provMola.activeDemSourceLabel, 'USGS MOLA-HRSC DEM · 200 m/px');
console.log('  ✓ Verified explicit fallback reason reporting (NOT_DOWNLOADED_OR_NOT_LOADED, OUTSIDE_COVERAGE) and provenance labels');

console.log('🎉 ALL USGS JEZERO IMAGERY & 1 m DTM FRONTEND CHECKS PASSED!');
