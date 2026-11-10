import assert from 'node:assert/strict';
import {
  resolveInitialApiUrl,
  isValidOfficialSourceUrl,
  resolveTerrainProvenance,
  resolveAlternativeShortfall,
  canSubmitRoute,
  validateRouteExecutionPreconditions,
} from './src/integration.js';
import { exportGeoJSON } from './src/export.js';

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
assert.ok(
  officialRangeExtractProv.sourceVerificationText.includes('upstream archive checksum unverified'),
  'Must distinguish official-endpoint retrieval with unverified upstream checksum'
);
assert.ok(officialRangeExtractProv.upstreamChecksumText.includes('Unverified'));

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
assert.equal(fullyVerifiedProv.isSynthetic, false);
assert.equal(
  fullyVerifiedProv.officialSourceUrl,
  'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m'
);
assert.ok(
  fullyVerifiedProv.sourceVerificationText.includes('Verified official source'),
  'Must identify fully verified source'
);
assert.ok(fullyVerifiedProv.upstreamChecksumText.includes('Verified'));

// API mode without official_source_url must not fall back to generic USGS URL
const unverifiedLocalApiProv = resolveTerrainProvenance({
  live: true,
  raw: { source_page: 'https://astrogeology.usgs.gov/' },
  loadError: '',
  api: {
    status: {
      data_mode: 'real_unverified_source',
      real_data_validation_status: 'valid_numeric_raster_unverified_source',
      is_synthetic: false,
      active_dem_source_url: null,
    },
  },
  result: { data_mode: 'real_unverified_source' },
  active: {
    evidence_passport: {
      source: {
        dataset_name: 'Custom Local Raster',
        official_source_url: null,
        data_mode: 'real_unverified_source',
        validation_status: 'valid_numeric_raster_unverified_source',
        is_synthetic: false,
      },
    },
  },
});
assert.equal(
  unverifiedLocalApiProv.officialSourceUrl,
  null,
  'API mode must not fall back to generic USGS URL when official_source_url is null'
);

// Browser mode preserves existing local attribution behavior
const browserProv = resolveTerrainProvenance({
  live: false,
  raw: {
    source_name: 'USGS MOLA–HRSC 200m v2',
    source_page: 'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
    is_synthetic: false,
    local_integrity_verified: true,
  },
  loadError: '',
  api: null,
  result: null,
  active: null,
});
assert.equal(browserProv.isSynthetic, false);
assert.equal(
  browserProv.officialSourceUrl,
  'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m'
);
assert.equal(browserProv.headerEngineLabel, 'Local engine');

// 4. Alternative-route shortfall handling (all 4 required scenarios)
// Scenario 4a: All requested alternatives returned (even with 6 limitations)
const allReturned = resolveAlternativeShortfall(
  {
    routes: [{ route_id: 'r1', warnings: [] }, { route_id: 'r2', warnings: [] }, { route_id: 'r3', warnings: [] }],
    limitations: ['lim1', 'lim2', 'lim3', 'lim4', 'lim5', 'lim6'],
  },
  3
);
assert.equal(allReturned.hasShortfall, false);
assert.equal(allReturned.message, null);

// Scenario 4b: Fewer alternatives returned with warnings
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

// Scenario 4c: Fewer alternatives returned without warnings
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

// Scenario 4d: One route explicitly requested
const singleRequested = resolveAlternativeShortfall(
  {
    routes: [{ route_id: 'r1', warnings: ['Some informational warning'] }],
    limitations: ['lim1', 'lim2', 'lim3', 'lim4', 'lim5'],
  },
  1
);
assert.equal(singleRequested.hasShortfall, false);
assert.equal(singleRequested.message, null);

// 5. API route planning without local DEM vs Browser mode requiring local DEM
assert.equal(
  canSubmitRoute({ live: true, raw: null, api: { url: 'http://localhost:8000' }, busy: false }),
  true,
  'API mode must allow submitting routes when connected even if local raw DEM is null'
);
assert.equal(
  canSubmitRoute({ live: true, raw: null, api: null, busy: false }),
  false,
  'API mode must not allow submitting routes when backend is not connected'
);
assert.equal(
  canSubmitRoute({ live: false, raw: null, api: { url: 'http://localhost:8000' }, busy: false }),
  false,
  'Browser mode must require local raw DEM data'
);
assert.equal(
  canSubmitRoute({ live: false, raw: { width: 10 }, api: null, busy: false }),
  true,
  'Browser mode must allow submitting routes when local raw DEM is present'
);

const apiPreNoRaw = validateRouteExecutionPreconditions({
  live: true,
  raw: null,
  loadError: 'The terrain dataset could not be loaded.',
  api: { url: 'http://localhost:8000', algorithmSupported: false },
  algorithm: 'astar',
});
assert.deepEqual(apiPreNoRaw, { ok: true, error: null });

const browserPreNoRaw = validateRouteExecutionPreconditions({
  live: false,
  raw: null,
  loadError: 'The terrain dataset could not be loaded.',
  api: { url: 'http://localhost:8000', algorithmSupported: false },
  algorithm: 'astar',
});
assert.equal(browserPreNoRaw.ok, false);
assert.ok(browserPreNoRaw.error.includes('The terrain dataset could not be loaded.'));

// Export works on API response when local DEM is absent
const mockApiResult = {
  mission_id: 'mission_api_test123',
  provenance: { dataset_name: 'Synthetic Jezero Crater Terrain Model' },
  limitations: ['Synthetic test fixture'],
  routes: [
    {
      route_id: 'route_primary_opt',
      name: 'Primary Route',
      mode: 'balanced',
      score_rank: 1,
      total_cost: 4100.5,
      cost_breakdown: { base_distance_cost: 3200, slope_penalty: 500, roughness_penalty: 400.5, hazard_penalty: 0, extra_penalty: 0 },
      summary: { total_distance_meters: 3200, estimated_duration_hours: 6.2 },
      geometry: { type: 'LineString', coordinates: [[77.4, 18.39, -2512.8], [77.44, 18.42, -2490.1]] },
      evidence_passport: syntheticRoute.evidence_passport,
    },
  ],
};
const exportedGeo = exportGeoJSON(mockApiResult, 'route_primary_opt', { num_alternatives: 2 });
assert.equal(exportedGeo.type, 'FeatureCollection');
assert.equal(exportedGeo.features.length, 1);
assert.equal(exportedGeo.features[0].id, 'route_primary_opt');
assert.equal(isValidOfficialSourceUrl('https://astrogeology.usgs.gov/'), true);
assert.equal(isValidOfficialSourceUrl('ftp://example.com'), false);

console.log(
  JSON.stringify({
    status: 'PASS',
    checks: [
      'VITE_API_URL and localStorage precedence',
      'API synthetic-mode attribution and USGS link suppression',
      'API official-source attribution (unverified checksum vs fully verified)',
      'Browser-mode attribution preservation',
      'Alternative shortfall handling (all returned, shortfall with warnings, shortfall without warnings, 1 requested)',
      'API route planning without local DEM',
      'Browser mode requiring local DEM',
      'API route GeoJSON export without local DEM',
    ],
  })
);
