import assert from 'node:assert/strict';
import {
  fetchDataFreshness,
  fetchNormalizedObservations,
  fetchKnowledgeGraph,
  fetchNodeEvidence,
  fetchNodeImpacts,
  fetchScenarios,
  createScenario,
  analyzeScenario,
  compareScenario,
  evaluateRouteRisk,
} from './src/fusion_client.js';

console.log('🧪 Starting Mission Intelligence & Risk Fusion Frontend Client Verification...');

// 1. Verify module exports
assert(typeof fetchDataFreshness === 'function', 'fetchDataFreshness should be exported');
assert(typeof fetchNormalizedObservations === 'function', 'fetchNormalizedObservations should be exported');
assert(typeof fetchKnowledgeGraph === 'function', 'fetchKnowledgeGraph should be exported');
assert(typeof fetchNodeEvidence === 'function', 'fetchNodeEvidence should be exported');
assert(typeof fetchNodeImpacts === 'function', 'fetchNodeImpacts should be exported');
assert(typeof fetchScenarios === 'function', 'fetchScenarios should be exported');
assert(typeof createScenario === 'function', 'createScenario should be exported');
assert(typeof analyzeScenario === 'function', 'analyzeScenario should be exported');
assert(typeof compareScenario === 'function', 'compareScenario should be exported');
assert(typeof evaluateRouteRisk === 'function', 'evaluateRouteRisk should be exported');
console.log('  ✓ Verified 10 Mission Intelligence & Risk Fusion client exports');

// 2. Test URL construction with mock fetch
let lastUrl = '';
let lastOptions = null;
globalThis.fetch = async (url, options = {}) => {
  lastUrl = String(url);
  lastOptions = options;

  if (lastUrl.includes('/api/v1/intelligence/data-freshness')) {
    return {
      ok: true,
      json: async () => ({ status: 'healthy', sources_count: 8, connected_count: 8, sources: [] })
    };
  }

  if (lastUrl.includes('/api/v1/intelligence/observations')) {
    return {
      ok: true,
      json: async () => ([
        { observation_id: 'obs_1', instrument: 'HiRISE', spatial_resolution_m: 1.0, quality_tier: 'GOLD' }
      ])
    };
  }

  if (lastUrl.includes('/api/v1/intelligence/graph')) {
    return {
      ok: true,
      json: async () => ({ nodes_count: 10, edges_count: 10, nodes: [], edges: [] })
    };
  }

  if (lastUrl.includes('/api/v1/intelligence/scenarios')) {
    return {
      ok: true,
      json: async () => ([
        { scenario_id: 'sc_1', name: 'Dust Contingency', modifiers: {} }
      ])
    };
  }

  if (lastUrl.includes('/api/v1/intelligence/risk-propagation')) {
    return {
      ok: true,
      json: async () => ({
        overall_traversability_state: 'NOMINAL',
        relative_route_effort_index: 1.15,
        hazard_exposure_distance_m: 0.0,
        segment_evaluations: []
      })
    };
  }

  return { ok: true, json: async () => ({}) };
};

// Test fetchDataFreshness
const fresh = await fetchDataFreshness('http://localhost:8000');
assert.equal(fresh.status, 'healthy');
assert(lastUrl.includes('/api/v1/intelligence/data-freshness'));
console.log('  ✓ Verified fetchDataFreshness request routing');

// Test fetchNormalizedObservations with filters
const obs = await fetchNormalizedObservations({
  bbox: [77.3, 18.3, 77.5, 18.5],
  instrument: 'hirise',
  provenance_kind: 'derived',
  quality_tier: 'GOLD'
}, 'http://localhost:8000');
assert.equal(obs.length, 1);
assert(lastUrl.includes('bbox=77.3%2C18.3%2C77.5%2C18.5'));
assert(lastUrl.includes('instrument=hirise'));
assert(lastUrl.includes('provenance_kind=derived'));
assert(lastUrl.includes('quality_tier=GOLD'));
console.log('  ✓ Verified fetchNormalizedObservations query serialization');

// Test fetchKnowledgeGraph
const graph = await fetchKnowledgeGraph({ node_type: 'hazard', max_nodes: 50 }, 'http://localhost:8000');
assert.equal(graph.nodes_count, 10);
assert(lastUrl.includes('node_type=hazard'));
assert(lastUrl.includes('max_nodes=50'));
console.log('  ✓ Verified fetchKnowledgeGraph query serialization');

// Test evaluateRouteRisk
const risk = await evaluateRouteRisk({ route_id: 'r1', coordinates: [] }, 12.0, 0.8, 'http://localhost:8000');
assert.equal(risk.overall_traversability_state, 'NOMINAL');
assert.equal(lastOptions.method, 'POST');
const sentBody = JSON.parse(lastOptions.body);
assert.equal(sentBody.max_slope_ceiling_deg, 12.0);
console.log('  ✓ Verified evaluateRouteRisk payload & parameters');

console.log('✅ Mission Intelligence & Risk Fusion Frontend Client Verification PASSED!\n');
