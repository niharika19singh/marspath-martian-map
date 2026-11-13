import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import {
  resolveInitialApiUrl,
  isValidOfficialSourceUrl,
  resolveTerrainProvenance,
  resolveAlternativeShortfall,
  canSubmitRoute,
  validateRouteExecutionPreconditions,
} from './src/integration.js';
import { exportGeoJSON, exportCSV, exportJSON } from './src/export.js';

// ==========================================
// PART 1: Integration Helpers & Provenance
// ==========================================

// 1. Environment URL precedence
assert.equal(
  resolveInitialApiUrl('https://user-override.example.com', 'https://env-fallback.example.com'),
  'https://user-override.example.com',
  'localStorage must override VITE_API_URL'
);
assert.equal(
  resolveInitialApiUrl('', 'https://env-fallback.example.com'),
  'https://env-fallback.example.com',
  'VITE_API_URL must be used when localStorage is empty'
);
assert.equal(
  resolveInitialApiUrl(null, '  https://env-fallback.example.com  '),
  'https://env-fallback.example.com',
  'VITE_API_URL must be trimmed when localStorage is null'
);
assert.equal(
  resolveInitialApiUrl(null, undefined),
  '',
  'Must resolve to empty string when neither localStorage nor VITE_API_URL is set'
);
assert.equal(
  resolveInitialApiUrl('   ', '   '),
  '',
  'Whitespace-only values must resolve to empty string'
);

// 2. API synthetic-mode attribution
const syntheticApiStatus = {
  status: 'healthy',
  data_mode: 'synthetic_test_fixture',
  real_data_validation_status: 'synthetic_test_fixture',
  is_synthetic: true,
  active_dem_dataset_name: 'Synthetic Jezero Crater Terrain Model',
  active_dem_source_url: null,
  local_integrity_verified: null,
  source_checksum_verified: false,
};
const syntheticRoute = {
  route_id: 'route_primary_opt',
  evidence_passport: {
    quality_tier: 'unverified',
    source: {
      dataset_name: 'Synthetic Jezero Crater Terrain Model',
      official_source_url: null,
      data_mode: 'synthetic_test_fixture',
      validation_status: 'synthetic_test_fixture',
      is_synthetic: true,
      local_integrity_verified: null,
      source_checksum_verified: false,
    },
  },
};
const synProv = resolveTerrainProvenance({
  live: true,
  raw: { source_page: 'https://astrogeology.usgs.gov/search/map/mars_2020' },
  loadError: '',
  api: { status: syntheticApiStatus },
  result: { data_mode: 'synthetic_test_fixture' },
  active: syntheticRoute,
});
assert.equal(synProv.isSynthetic, true);
assert.equal(synProv.dataMode, 'synthetic_test_fixture');
assert.equal(synProv.officialSourceUrl, null, 'Synthetic API mode must never link to USGS');
assert.ok(synProv.headerStatusText.includes('Synthetic terrain'));
assert.ok(synProv.headerStatusText.includes('synthetic_test_fixture'));
assert.ok(synProv.headerEngineLabel.includes('Synthetic'));
assert.ok(synProv.sourceVerificationText.includes('not NASA/USGS observation data'));

// Even if a synthetic payload erroneously carried a URL, synthetic guard must suppress it
const synWithRogueUrl = resolveTerrainProvenance({
  live: true,
  raw: null,
  loadError: '',
  api: { status: syntheticApiStatus },
  result: { data_mode: 'synthetic_fallback' },
  active: {
    evidence_passport: {
      source: {
        dataset_name: 'Synthetic Jezero Crater Terrain Model',
        official_source_url: 'https://astrogeology.usgs.gov/',
        data_mode: 'synthetic_fallback',
        validation_status: 'synthetic_test_fixture',
        is_synthetic: true,
      },
    },
  },
});
assert.equal(synWithRogueUrl.officialSourceUrl, null);
assert.equal(synWithRogueUrl.isSynthetic, true);

// 3. API official-source attribution: unverified upstream checksum vs fully verified source
const officialRangeExtractProv = resolveTerrainProvenance({
  live: true,
  raw: null,
  loadError: '',
  api: {
    status: {
      data_mode: 'real_official_endpoint_unverified_checksum',
      real_data_validation_status: 'official_endpoint_retrieved_checksum_unverified',
      is_synthetic: false,
      active_dem_dataset_name: 'Mars HRSC MOLA Blended Global DEM 200m v2',
      active_dem_source_url:
        'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
      local_integrity_verified: true,
      source_checksum_verified: false,
    },
  },
  result: { data_mode: 'real_official_endpoint_unverified_checksum' },
  active: {
    evidence_passport: {
      quality_tier: 'moderate',
      source: {
        dataset_name: 'Mars HRSC MOLA Blended Global DEM 200m v2',
        official_source_url:
          'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
        data_mode: 'real_official_endpoint_unverified_checksum',
        validation_status: 'official_endpoint_retrieved_checksum_unverified',
        is_synthetic: false,
        local_integrity_verified: true,
        source_checksum_verified: false,
      },
    },
  },
});
assert.equal(officialRangeExtractProv.isSynthetic, false);
assert.equal(
  officialRangeExtractProv.officialSourceUrl,
  'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m'
);
assert.equal(officialRangeExtractProv.sourceChecksumVerified, false);
assert.equal(officialRangeExtractProv.localIntegrityVerified, true);
assert.ok(officialRangeExtractProv.sourceVerificationText.includes('upstream archive checksum unverified'));
assert.equal(officialRangeExtractProv.upstreamChecksumText, 'Unverified (official endpoint extract)');

const fullyVerifiedProv = resolveTerrainProvenance({
  live: true,
  raw: null,
  loadError: '',
  api: {
    status: {
      data_mode: 'real',
      real_data_validation_status: 'verified_source',
      is_synthetic: false,
      active_dem_dataset_name: 'Mars HRSC MOLA Blended Global DEM 200m v2',
      active_dem_source_url:
        'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
      local_integrity_verified: true,
      source_checksum_verified: true,
    },
  },
  result: { data_mode: 'real' },
  active: {
    evidence_passport: {
      quality_tier: 'high',
      source: {
        dataset_name: 'Mars HRSC MOLA Blended Global DEM 200m v2',
        official_source_url:
          'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
        data_mode: 'real',
        validation_status: 'verified_source',
        is_synthetic: false,
        local_integrity_verified: true,
        source_checksum_verified: true,
      },
    },
  },
});
assert.equal(fullyVerifiedProv.sourceChecksumVerified, true);
assert.ok(fullyVerifiedProv.sourceVerificationText.includes('upstream archive checksum verified'));
assert.equal(fullyVerifiedProv.upstreamChecksumText, 'Verified against official archive');

// 4. Alternative shortfall handling
const shortfallWithWarnings = resolveAlternativeShortfall(
  {
    routes: [
      {
        route_id: 'r1',
        warnings: [
          'Secondary corridor search suppressed: generated path overlapped 92% with primary route.',
          'Safety-first alternative unviable: Destination slope exceeds 14° ceiling.',
        ],
      },
    ],
    limitations: ['lim1', 'lim2', 'lim3', 'lim4'],
  },
  3
);
assert.equal(shortfallWithWarnings.hasShortfall, true);
assert.equal(shortfallWithWarnings.returnedCount, 1);
assert.equal(shortfallWithWarnings.requestedCount, 3);
assert.ok(shortfallWithWarnings.message.includes('Returned 1 of 3 requested routes.'));
assert.ok(shortfallWithWarnings.message.includes('overlapped 92%'));
assert.ok(shortfallWithWarnings.message.includes('exceeds 14° ceiling'));

const shortfallWithoutWarnings = resolveAlternativeShortfall(
  {
    routes: [{ route_id: 'r1', warnings: [] }, { route_id: 'r2', warnings: [] }],
    limitations: ['lim1', 'lim2'],
  },
  3
);
assert.equal(shortfallWithoutWarnings.hasShortfall, true);
assert.equal(shortfallWithoutWarnings.returnedCount, 2);
assert.equal(shortfallWithoutWarnings.requestedCount, 3);
assert.ok(
  shortfallWithoutWarnings.message.includes(
    'Returned 2 of 3 requested routes: fewer distinct traversable alternatives were found within the selected constraints.'
  )
);

// 5. Preconditions and submittability
assert.equal(
  canSubmitRoute({ live: true, raw: null, api: { url: 'http://localhost:8000' }, busy: false }),
  true
);
assert.equal(
  canSubmitRoute({ live: true, raw: null, api: null, busy: false }),
  false
);
assert.equal(
  canSubmitRoute({ live: false, raw: null, api: { url: 'http://localhost:8000' }, busy: false }),
  false
);
assert.equal(
  canSubmitRoute({ live: false, raw: { width: 10 }, api: null, busy: false }),
  true
);

// ==========================================
// PART 2: Phase 7.2.1 Contract & Exports
// ==========================================

const fixtureText = await readFile(new URL('./src/fixtures/sample_robustness_hirise_response.json', import.meta.url), 'utf8');
const response = JSON.parse(fixtureText);

// 6. Verify Top-Level Metadata
assert.equal(response.status, 'success');
assert.equal(response.crs.identifier, 'IAU2000:49900');
assert.equal(response.crs.longitude_direction, 'East');
assert.equal(response.crs.latitude_type, 'Planetocentric');
assert.equal(response.data_mode, 'real');

// 7. Verify Source Selection Report
const ss = response.source_selection;
assert.ok(ss, 'source_selection must be present');
assert.equal(ss.selected_source_id, 'dem_mola_hrsc_jezero_200m');
assert.equal(ss.single_source_invariant_enforced, true);
assert.equal(ss.hirise_evaluated, true);
assert.equal(ss.hirise_selected, false);
assert.equal(ss.hirise_status, 'partial_coverage');
assert.ok(ss.hirise_rejection_reason.includes('exceed HiRISE DTM coverage'));
assert.equal(ss.effective_resolution_meters, 200.0);

// 8. Verify Route Candidates & Evidence Passport
assert.equal(response.routes.length, 2);
const r0 = response.routes[0];
assert.equal(r0.score_rank, 1);
assert.equal(r0.summary.risk_category, 'nominal');
assert.equal(r0.summary.risk_assessment_status, 'complete_observed');
assert.equal(r0.summary.data_coverage_fraction, 1.0);
assert.equal(r0.waypoints_visited.length, 1);
assert.deepEqual(r0.science_targets_visited, ['poi_delta_front']);

const ep = r0.evidence_passport;
assert.ok(ep, 'evidence_passport must be present');
assert.equal(ep.quality_tier, 'moderate');
assert.ok(ep.tier_explanation.length > 10);
assert.ok(ep.quality_flags.includes('single_source_enforced'));
assert.equal(ep.source.local_integrity_verified, true);
assert.equal(ep.source.source_checksum_verified, true);
assert.equal(ep.coverage.route_data_coverage_fraction, 1.0);
assert.equal(ep.coverage.corridor_data_coverage_fraction, 0.992);
assert.equal(ep.segments.length, 8);

// 9. Verify Robustness Assessment
const ra = response.robustness_assessment;
assert.ok(ra, 'robustness_assessment must be present');
assert.equal(ra.enabled, true);
assert.equal(ra.requested_scenario_count, 5);
assert.equal(ra.completed_scenario_count, 5);
assert.equal(ra.failed_scenario_count, 0);
assert.equal(ra.uncertainty_assumptions.vertical_sigma_m, 1.5);
assert.equal(ra.uncertainty_assumptions.correlation_length_m, 400.0);
assert.ok(ra.scientific_disclaimer.includes('hypothetical terrain perturbation model'));
assert.ok(ra.scientific_disclaimer.includes('not establish the actual probability of rover failure'));

const bra = ra.baseline_route_assessments.find(b => b.route_id === r0.route_id);
assert.ok(bra, 'baseline_route_assessment for primary route must be present');
assert.equal(bra.baseline_route_feasibility_fraction, 1.0);
assert.equal(bra.baseline_route_retention_fraction, 1.0);
assert.equal(bra.mean_route_overlap_fraction, 0.92);
assert.equal(bra.mean_cost_regret_fraction, 0.021);

// 10. Verify Client-Side GeoJSON Export
const requestMeta = {
  start: { lon: 77.40, lat: 18.39 },
  destination: { lon: 77.44, lat: 18.42 },
  crs_identifier: 'IAU2000:49900',
  mode: 'balanced',
  constraints: { max_slope_deg: 20, max_roughness: 0.85, avoid_unobserved_terrain: true },
  science_waypoints: [{ lon: 77.42, lat: 18.405 }],
  num_alternatives: 3
};
const geojson = exportGeoJSON(response, r0.route_id, requestMeta);
assert.equal(geojson.type, 'FeatureCollection');
assert.equal(geojson.planetary_crs, 'IAU2000:49900');
assert.equal(geojson.selected_route_id, r0.route_id);
assert.ok(geojson.source_selection);
assert.ok(geojson.robustness_assessment);
assert.equal(geojson.features.length, 1);
assert.equal(geojson.features[0].id, r0.route_id);
assert.equal(geojson.features[0].geometry.type, 'LineString');
assert.equal(geojson.features[0].geometry.coordinates.length, 9);
assert.equal(geojson.features[0].geometry.coordinates[0].length, 3);
assert.equal(geojson.features[0].geometry.coordinates[0][2], -2580.0);

// 11. Verify Client-Side CSV Export
const csv = exportCSV(response, r0.route_id);
const lines = csv.trim().split('\n');
assert.ok(lines.length >= 9, 'CSV must have header + 8 segments');
assert.equal(
  lines[0],
  'segment_index,start_lon,start_lat,end_lon,end_lat,is_valid_data,start_elevation_m,end_elevation_m,elevation_delta_m,slope_deg,roughness,hazard_flags,quality_flags'
);
const firstSeg = lines[1].split(',');
assert.equal(firstSeg[0], '0');
assert.equal(firstSeg[1], '77.4');
assert.equal(firstSeg[2], '18.39');
assert.equal(firstSeg[5], 'true');

// 12. Verify Client-Side JSON Export
const jsonExp = exportJSON(response, r0.route_id, requestMeta);
assert.equal(jsonExp.selected_route_id, r0.route_id);
assert.equal(jsonExp.export_manifest.planetary_crs, 'IAU2000:49900');
assert.ok(jsonExp.export_manifest.created_at);

console.log(
  JSON.stringify({
    status: 'PASS',
    checks: [
      'VITE_API_URL and localStorage precedence',
      'API synthetic-mode attribution and USGS link suppression',
      'API official-source attribution (unverified checksum vs fully verified)',
      'Browser-mode attribution preservation',
      'Alternative shortfall handling (with and without warnings)',
      'API route planning without local DEM',
      'Browser mode requiring local DEM',
      'Top-level CRS IAU2000:49900',
      'Source selection report & single-source invariant',
      'HiRISE evaluation & partial coverage rejection',
      'Route metrics & cost reconciliation',
      'Terrain Evidence Passport & quality tier',
      'Route & corridor coverage metrics',
      'Robustness stress testing assumptions & stability fractions',
      'Non-probabilistic scientific disclaimer',
      'GeoJSON 3D feature export',
      'Segment-level CSV export',
      'JSON mission manifest export',
    ]
  })
);
