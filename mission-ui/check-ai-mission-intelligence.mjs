/**
 * Automated Verification Script for AI Mission Intelligence Layer
 * Tests natural-language intent parsing, landmark resolution,
 * candidate route comparisons, scientific terrain interpretation,
 * and executive risk briefings with deterministic grounding.
 */

import assert from 'node:assert';
import {
  planMissionFromPrompt,
  compareRouteCandidates,
  interpretScientificTerrain,
  generateMissionRiskBriefing,
} from './src/cloud_ai.js';

console.log('🧪 Starting AI Mission Intelligence Frontend Client Verification...\n');

// 1. Natural Language Mission Planning (Séítah)
console.log('--- 1. Testing Natural-Language Mission Planning (Séítah) ---');
const seitahPlan = await planMissionFromPrompt(
  'Find a safe route from the current rover position to Séítah, prioritizing low slope and sufficient return EVA margin.',
  { lon: 77.2330, lat: 18.4350 }
);

assert(seitahPlan, 'Plan response must not be null');
assert.strictEqual(seitahPlan.routing_profile, 'safety_first', 'Profile must be safety_first');
assert.strictEqual(seitahPlan.resolved_start.is_rover_position, true, 'Start must be rover telemetry position');
assert(seitahPlan.resolved_destination.name.includes('Séítah'), 'Destination must match Séítah');
assert.strictEqual(seitahPlan.requires_clarification, false, 'Should not require clarification');
assert(seitahPlan.validated_route_request, 'Validated route request must be produced');
assert.strictEqual(seitahPlan.validated_route_request.algorithm, 'astar');
assert.strictEqual(seitahPlan.validated_route_request.mode, 'safety_first');
assert.strictEqual(seitahPlan.validated_route_request.include_return_leg, true);
console.log(`  ✓ Resolved target: ${seitahPlan.resolved_destination.name} (${seitahPlan.resolved_destination.lon}°E, ${seitahPlan.resolved_destination.lat}°N)`);
console.log(`  ✓ Validated Route Request: profile=${seitahPlan.routing_profile}, max_slope=${seitahPlan.constraints.max_slope_deg}°, EVA=${seitahPlan.constraints.eva_time_budget_hours}h`);

// 2. Natural Language Mission Planning (Kodiak Butte)
console.log('\n--- 2. Testing Natural-Language Mission Planning (Kodiak Butte) ---');
const kodiakPlan = await planMissionFromPrompt('Traverse to Kodiak to observe deltaic bedding architectures.');
assert(kodiakPlan.resolved_destination.name.includes('Kodiak'), 'Destination must match Kodiak');
assert(kodiakPlan.validated_route_request.destination.lon > 77.4 && kodiakPlan.validated_route_request.destination.lon < 77.5);
console.log(`  ✓ Resolved Kodiak target: ${kodiakPlan.resolved_destination.name}`);

// 3. Multi-Criteria Route Candidate Comparison
console.log('\n--- 3. Testing Candidate Route Comparison ---');
const mockCandidates = [
  {
    route_id: 'primary',
    name: 'Primary Corridor (A*)',
    mode: 'balanced',
    total_cost: 4073.2,
    summary: { total_distance_meters: 3280.0, max_slope_deg: 11.4, avg_slope_deg: 5.8 },
    turnaround: { status: 'FEASIBLE', buffer_margin_minutes: 120.0, total_traverse_duration_hours: 4.2 },
  },
  {
    route_id: 'alternative_1',
    name: 'Alternative Corridor 1 (Low Slope)',
    mode: 'safety_first',
    total_cost: 4350.0,
    summary: { total_distance_meters: 3520.0, max_slope_deg: 8.9, avg_slope_deg: 4.7 },
    turnaround: { status: 'FEASIBLE', buffer_margin_minutes: 95.0, total_traverse_duration_hours: 4.6 },
  },
];

const comparison = await compareRouteCandidates(mockCandidates, 'Low slope preferred');
assert(comparison, 'Comparison must not be null');
assert.strictEqual(comparison.candidate_evaluations.length, 2, 'Must evaluate 2 candidates');
assert.strictEqual(comparison.candidate_evaluations[0].distance_km, 3.28);
assert.strictEqual(comparison.candidate_evaluations[1].distance_km, 3.52);
assert.strictEqual(comparison.candidate_evaluations[0].return_feasibility, 'FEASIBLE');
assert(comparison.tradeoff_analysis.length > 20, 'Tradeoff analysis must be present');
console.log(`  ✓ Evaluated ${comparison.candidate_evaluations.length} candidate corridors with exact distance & cost grounding`);
console.log(`  ✓ Grounding audit: ${comparison.grounding_audit?.candidates_audited} candidates verified`);

// 4. Scientific Terrain Interpretation
console.log('\n--- 4. Testing Scientific Terrain & Evidence Typing ---');
const terrain = await interpretScientificTerrain({ total_distance_meters: 3280.0, max_slope_deg: 11.4 });
assert(terrain, 'Terrain interpretation must not be null');
assert(terrain.geological_setting.includes('Jezero'), 'Geological setting must mention Jezero');
assert(terrain.measured_data_evidence.length >= 1, 'Must contain measured evidence');
assert(terrain.derived_metrics_evidence.length >= 1, 'Must contain derived evidence');
assert(terrain.proxy_indicators_evidence.length >= 1, 'Must contain proxy indicators');

assert.strictEqual(terrain.measured_data_evidence[0].data_type, 'measured');
assert.strictEqual(terrain.derived_metrics_evidence[0].data_type, 'derived');
assert.strictEqual(terrain.proxy_indicators_evidence[0].data_type, 'proxy');
console.log(`  ✓ Measured Data: ${terrain.measured_data_evidence[0].instrument_or_source} (${terrain.measured_data_evidence[0].parameter})`);
console.log(`  ✓ Derived Metrics: ${terrain.derived_metrics_evidence[0].instrument_or_source} (${terrain.derived_metrics_evidence[0].parameter})`);
console.log(`  ✓ Proxy Indicators: ${terrain.proxy_indicators_evidence[0].instrument_or_source} (${terrain.proxy_indicators_evidence[0].parameter})`);

// 5. Executive Mission Risk Briefing
console.log('\n--- 5. Testing Executive Mission Risk Briefing ---');
const risk = await generateMissionRiskBriefing(mockCandidates[0]);
assert(risk, 'Risk briefing must not be null');
assert(risk.mission_overview.includes('Jezero'), 'Overview must reference Jezero');
assert(risk.critical_hazards.length >= 1, 'Must identify critical hazards');
assert(risk.uncertainty_limitations.length >= 1, 'Must identify modeling limitations');
assert(risk.recommended_contingency_corridor.length > 20, 'Must provide contingency corridor');
assert(risk.deterministic_safety_mandate.includes('strictly advisory') || risk.deterministic_safety_mandate.includes('cannot override'), 'Must enforce deterministic safety mandate');
console.log(`  ✓ Return Feasibility Status: ${risk.return_feasibility.status} (Traverse: ${risk.return_feasibility.estimated_traverse_duration_hours}h, Buffer: +${risk.return_feasibility.buffer_margin_minutes}m)`);
console.log(`  ✓ Contingency Corridor: ${risk.recommended_contingency_corridor.substring(0, 60)}...`);
console.log(`  ✓ Deterministic Safety Mandate: ${risk.deterministic_safety_mandate}`);

console.log('\n🎉 ALL AI MISSION INTELLIGENCE FRONTEND CHECKS PASSED CLEANLY!\n');
