/**
 * Automated Verification Suite for MARSPath NASA Data Sources & Intelligence Center
 * Tests data contracts, multi-source catalogue filtering, MEDA missing value semantics,
 * THEMIS thermal traversability risk tiers, SPICE geometry calculations, and PDS releases.
 */

import assert from 'node:assert';
import {
  FALLBACK_DATA_SOURCES,
  FALLBACK_GLOBAL_STATUS,
  FALLBACK_CATALOGUE_PRODUCTS,
  FALLBACK_MEDA_OBSERVATIONS,
  FALLBACK_THEMIS_OBSERVATIONS,
  FALLBACK_SPICE_GEOMETRY,
  FALLBACK_PDS_RELEASES,
  fetchDataSources,
  fetchDataSourceStatus,
  fetchDataSourceById,
  searchDataCatalogue,
  fetchCatalogueProduct,
  fetchCatalogueCoverage,
  fetchMedaObservations,
  fetchThemisObservations,
  computeSpiceGeometry,
  fetchDataReleases,
  triggerDataSync
} from './src/nasa_data.js';

console.log('🧪 Starting NASA Data Sources & Intelligence Center Automated Verification...\n');

// 1. Verify Seven Official NASA Sources
console.log('--- 1. Testing Seven Official NASA Sources Registry ---');
assert.strictEqual(FALLBACK_DATA_SOURCES.length, 7, 'Must register exactly 7 official NASA sources');
const expectedSourceIds = [
  'mars_trek',
  'pds_geosciences',
  'pds_atmospheres',
  'themis_viewer',
  'naif_spice',
  'planetary_notebook',
  'pds_releases'
];
expectedSourceIds.forEach(id => {
  const src = FALLBACK_DATA_SOURCES.find(s => s.id === id);
  assert.ok(src, `Source ${id} must exist in registry`);
  assert.ok(src.name.length > 5, `Source ${id} must have descriptive name`);
  assert.ok(src.organization.length > 3, `Source ${id} must list operating organization`);
  assert.ok(src.primary_use_in_marspath.length > 10, `Source ${id} must specify use in MARSPath`);
  assert.ok(src.available_datasets.length >= 3, `Source ${id} must detail at least 3 datasets`);
  assert.ok(src.official_url.startsWith('https://'), `Source ${id} must have secure official NASA URL`);
  assert.strictEqual(src.connection_status, 'CONNECTED', `Source ${id} must be in CONNECTED status`);
  assert.ok(src.indexed_products_count > 0, `Source ${id} must report non-zero indexed products`);
  console.log(`  ✓ Verified source [${src.id}]: ${src.name} (${src.indexed_products_count.toLocaleString()} products)`);
});

// 2. Verify Global Status Dashboard
console.log('\n--- 2. Testing Global Status Metrics ---');
const status = await fetchDataSourceStatus();
assert.strictEqual(status.total_sources, 7, 'Total sources must equal 7');
assert.strictEqual(status.connected_sources, 7, 'Connected sources must equal 7');
assert.strictEqual(status.overall_status, 'ONLINE_SYNCED');
assert.strictEqual(status.ingested_status, 'INGESTED_AND_LIVE');
assert.ok(status.total_indexed_products >= 45000, 'Must index over 45,000 products across Jezero and Mars');
console.log(`  ✓ Global status verified: ${status.connected_sources}/${status.total_sources} connected, ${status.total_indexed_products.toLocaleString()} products indexed.`);

// 3. Verify Multi-Parameter Catalogue Search & Filtering
console.log('\n--- 3. Testing Catalogue Search & Multi-Parameter Discovery ---');
// 3a. Unfiltered search
const allSearch = await searchDataCatalogue();
assert.strictEqual(allSearch.returned_count, FALLBACK_CATALOGUE_PRODUCTS.length);
console.log(`  ✓ Unfiltered search returned ${allSearch.returned_count} catalog products`);

// 3b. Free-text search (HiRISE)
const hiriseSearch = await searchDataCatalogue({ query: 'HiRISE' });
assert.ok(hiriseSearch.products.length >= 2, 'Should match multiple HiRISE products');
hiriseSearch.products.forEach(p => {
  const match = p.instrument.includes('HiRISE') || p.title.includes('HiRISE') || p.product_id.includes('HiRISE');
  assert.ok(match, 'All results must match query term');
});
console.log(`  ✓ Query 'HiRISE' matched ${hiriseSearch.products.length} products`);

// 3c. Source filtering
const pdsGeoSearch = await searchDataCatalogue({ source_id: 'pds_geosciences' });
assert.ok(pdsGeoSearch.products.length >= 3, 'PDS Geosciences must have products');
pdsGeoSearch.products.forEach(p => assert.strictEqual(p.source_id, 'pds_geosciences'));
console.log(`  ✓ Source filter 'pds_geosciences' matched ${pdsGeoSearch.products.length} products`);

// 3d. Spacecraft filtering
const mroSearch = await searchDataCatalogue({ spacecraft: 'mro' });
assert.ok(mroSearch.products.length >= 3, 'MRO spacecraft must match multiple products');
console.log(`  ✓ Spacecraft filter 'mro' matched ${mroSearch.products.length} products`);

// 3e. Product type filtering
const dtmSearch = await searchDataCatalogue({ product_type: 'TERRAIN_DTM' });
assert.strictEqual(dtmSearch.products.length, 1);
assert.strictEqual(dtmSearch.products[0].product_id, 'DTEEC_069176_1985_069242_1985_A01');
console.log(`  ✓ Product type 'TERRAIN_DTM' correctly resolved stereo elevation DTM`);

// 4. Verify MEDA In-Situ Surface Weather & Missing-Value Preservation
console.log('\n--- 4. Testing MEDA Weather Telemetry & Missing Value Preservation ---');
const medaObs = await fetchMedaObservations();
assert.ok(medaObs.length >= 5, 'Must provide at least 5 sols of calibrated MEDA telemetry');
const sol2022 = medaObs.find(m => m.sol === 2022);
assert.ok(sol2022, 'Sol 2022 must exist');
assert.strictEqual(typeof sol2022.air_temperature_deg_c, 'number');
assert.strictEqual(typeof sol2022.atmospheric_pressure_pa, 'number');
assert.strictEqual(typeof sol2022.dust_optical_depth_tau, 'number');
assert.strictEqual(sol2022.quality_flag, 'VALID_CALIBRATED');
console.log(`  ✓ Sol 2022 calibrated: Temp ${sol2022.air_temperature_deg_c}°C, Pressure ${sol2022.atmospheric_pressure_pa} Pa, Tau ${sol2022.dust_optical_depth_tau}`);

// Crucial scientific test: Sol 2019 has missing wind sensor readings (-9999.0 flag)
const sol2019 = medaObs.find(m => m.sol === 2019);
assert.ok(sol2019, 'Sol 2019 must exist');
assert.strictEqual(sol2019.wind_speed_m_per_s, null, 'Sol 2019 wind speed must be null, NOT zero or -9999.0');
assert.strictEqual(sol2019.wind_direction_deg, null, 'Sol 2019 wind direction must be null, NOT zero');
console.log('  ✓ Verified -9999.0 missing-value preservation: Sol 2019 wind speed is strictly null');

// 5. Verify THEMIS Thermal Inertia Traversability Risk Tiers
console.log('\n--- 5. Testing THEMIS Thermal Traversability Risk Assessment ---');
const themisObs = await fetchThemisObservations();
assert.ok(themisObs.length >= 3, 'Must provide at least 3 Jezero THEMIS observations');
const sandSheet = themisObs.find(o => o.thermal_inertia_tiu < 150);
assert.ok(sandSheet, 'Must classify low thermal inertia as HIGH_SINKAGE_RISK');
assert.strictEqual(sandSheet.traversability_risk, 'HIGH_SINKAGE_RISK');
console.log(`  ✓ Sand sheet [${sandSheet.observation_id}]: I=${sandSheet.thermal_inertia_tiu} tiu -> ${sandSheet.traversability_risk}`);

const bedrock = themisObs.find(o => o.thermal_inertia_tiu > 300);
assert.ok(bedrock, 'Must classify high thermal inertia as OPTIMAL_TRACTION_BEDROCK');
assert.strictEqual(bedrock.traversability_risk, 'OPTIMAL_TRACTION_BEDROCK');
console.log(`  ✓ Carbonate bedrock [${bedrock.observation_id}]: I=${bedrock.thermal_inertia_tiu} tiu -> ${bedrock.traversability_risk}`);

// 6. Verify NAIF / SPICE Ephemeris Geometry Calculator
console.log('\n--- 6. Testing NAIF / SPICE Ephemeris Calculation ---');
const spice = await computeSpiceGeometry('mro');
assert.strictEqual(spice.spacecraft_id, 'mro');
assert.ok(Number.isFinite(spice.sub_spacecraft_lon), 'Sub-spacecraft lon must be finite');
assert.ok(Number.isFinite(spice.sub_spacecraft_lat), 'Sub-spacecraft lat must be finite');
assert.ok(spice.spacecraft_altitude_km > 200 && spice.spacecraft_altitude_km < 400, 'MRO altitude must be 200-400 km');
assert.ok(spice.solar_incidence_angle_deg >= 0 && spice.solar_incidence_angle_deg <= 180, 'Solar incidence must be valid angle');
assert.ok(spice.local_solar_time.includes(':'), 'Must format Local Solar Time');
console.log(`  ✓ SPICE geometry computed: MRO @ (${spice.sub_spacecraft_lon.toFixed(2)}°E, ${spice.sub_spacecraft_lat.toFixed(2)}°N), Alt ${spice.spacecraft_altitude_km.toFixed(1)} km, θi ${spice.solar_incidence_angle_deg.toFixed(1)}°, LST ${spice.local_solar_time}`);

// 7. Verify PDS Releases Monitor
console.log('\n--- 7. Testing PDS Data Releases Monitor ---');
const releases = await fetchDataReleases();
assert.ok(releases.length >= 4, 'Must monitor at least 4 active flight missions');
const mroRel = releases.find(r => r.release_id === 'MRO_PDS_REL_73');
assert.ok(mroRel, 'MRO Release 73 must be tracked');
assert.strictEqual(mroRel.status, 'COMPLETED_VERIFIED');
assert.ok(mroRel.data_volume_gb > 1000, 'Volume must be realistic');
console.log(`  ✓ Tracked ${releases.length} PDS quarterly releases (${releases.map(r => r.release_id).join(', ')})`);

// 8. Verify Sync Trigger
console.log('\n--- 8. Testing Operational Synchronization ---');
const syncRes = await triggerDataSync(true);
assert.strictEqual(syncRes.success, true);
assert.strictEqual(syncRes.sources_synced, 7);
console.log(`  ✓ Synchronized all ${syncRes.sources_synced} NASA data sources: ${syncRes.message}`);

console.log('\n🎉 ALL NASA DATA SOURCES & INTELLIGENCE VERIFICATIONS PASSED CLEANLY!\n');
