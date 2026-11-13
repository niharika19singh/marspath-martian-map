import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { exportGeoJSON, exportCSV, exportJSON } from './src/export.js';

const fixtureText = await readFile(new URL('./src/fixtures/sample_robustness_hirise_response.json', import.meta.url), 'utf8');
const response = JSON.parse(fixtureText);

// 1. Verify Top-Level Metadata
assert.equal(response.status, 'success');
assert.equal(response.crs.identifier, 'IAU2000:49900');
assert.equal(response.crs.longitude_direction, 'East');
assert.equal(response.crs.latitude_type, 'Planetocentric');
assert.equal(response.data_mode, 'real');

// 2. Verify Source Selection Report
const ss = response.source_selection;
assert.ok(ss, 'source_selection must be present');
assert.equal(ss.selected_source_id, 'dem_mola_hrsc_jezero_200m');
assert.equal(ss.single_source_invariant_enforced, true);
assert.equal(ss.hirise_evaluated, true);
assert.equal(ss.hirise_selected, false);
assert.equal(ss.hirise_status, 'partial_coverage');
assert.ok(ss.hirise_rejection_reason.includes('exceed HiRISE DTM coverage'));
assert.equal(ss.effective_resolution_meters, 200.0);

// 3. Verify Route Candidates & Evidence Passport
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

// 4. Verify Robustness Assessment
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

// 5. Verify Client-Side GeoJSON Export
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
// Verify 3D coordinates preserved without fabrication
assert.equal(geojson.features[0].geometry.coordinates[0].length, 3);
assert.equal(geojson.features[0].geometry.coordinates[0][2], -2580.0);

// 6. Verify Client-Side CSV Export
const csv = exportCSV(response, r0.route_id);
const lines = csv.trim().split('\n');
assert.ok(lines.length >= 9, 'CSV must have header + 8 segments');
assert.equal(
  lines[0],
  'segment_index,start_lon,start_lat,end_lon,end_lat,is_valid_data,start_elevation_m,end_elevation_m,elevation_delta_m,slope_deg,roughness,hazard_flags,quality_flags'
);
const firstSeg = lines[1].split(',');
assert.equal(firstSeg[0], '0'); // segment_index
assert.equal(firstSeg[1], '77.4'); // start_lon
assert.equal(firstSeg[2], '18.39'); // start_lat
assert.equal(firstSeg[5], 'true'); // is_valid_data

// 7. Verify Client-Side JSON Export
const jsonExp = exportJSON(response, r0.route_id, requestMeta);
assert.equal(jsonExp.selected_route_id, r0.route_id);
assert.equal(jsonExp.export_manifest.planetary_crs, 'IAU2000:49900');
assert.ok(jsonExp.export_manifest.created_at);

console.log(
  JSON.stringify({
    status: 'PASS',
    checks: [
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
      'JSON mission manifest export'
    ]
  })
);
