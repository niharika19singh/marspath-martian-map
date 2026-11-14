import assert from 'node:assert/strict';
import {
  getCloudStatus,
  listStorageObjects,
  getAiStatus,
  sendMarsScienceChat,
  explainRoute,
  compareAiModels,
} from './src/cloud_ai.js';

console.log('🧪 Starting Cloud & AI Integration Automated Verification...\n');

// 1. Verify Google Cloud Status Contract
console.log('--- 1. Testing Google Cloud Platform Architecture & Status ---');
const cloudStatus = await getCloudStatus();
assert(cloudStatus.project_id, 'Project ID should be defined');
assert.equal(cloudStatus.location, 'us-central1', 'Location should be us-central1');
assert(cloudStatus.gcs_status, 'GCS status object required');
assert.equal(cloudStatus.gcs_status.bucket, 'marspath-data', 'Bucket should be marspath-data');
assert(cloudStatus.cloud_run_status, 'Cloud Run status object required');
assert.equal(cloudStatus.cloud_run_status.total_registered_jobs, 8, 'Must have 8 registered Cloud Run jobs');
console.log(`  ✓ Project: ${cloudStatus.project_id} (${cloudStatus.location})`);
console.log(`  ✓ GCS Bucket: gs://${cloudStatus.gcs_status.bucket} (${cloudStatus.gcs_status.total_objects} objects, ${cloudStatus.cost_report?.storage_used_mb} MB)`);
console.log(`  ✓ Cloud Run: ${cloudStatus.cloud_run_status.total_registered_jobs} containerized batch engines registered`);

// 2. Verify Cloud Run 8 Batch Jobs Specifications
console.log('\n--- 2. Testing 8 Cloud Run Scientific Batch Jobs ---');
const expectedJobs = [
  'nasa_catalog_sync',
  'planetary_imagery_processor',
  'dem_processor',
  'meda_processor',
  'themis_processor',
  'crism_processor',
  'provenance_validator',
  'imagery_tile_generator',
];
const registeredNames = cloudStatus.cloud_run_status.jobs.map((j) => j.name);
for (const jName of expectedJobs) {
  assert(registeredNames.includes(jName), `Expected job '${jName}' to be registered`);
  const job = cloudStatus.cloud_run_status.jobs.find((j) => j.name === jName);
  assert(job.cpu_limit, `Job ${jName} missing CPU limit`);
  assert(job.memory_limit_mb, `Job ${jName} missing memory limit`);
  assert(job.timeout_seconds, `Job ${jName} missing timeout limit`);
  console.log(`  ✓ Job [${jName}]: ${job.cpu_limit} CPU, ${job.memory_limit_mb}MB RAM, timeout ${job.timeout_seconds}s`);
}

// 3. Verify Storage Objects Explorer
console.log('\n--- 3. Testing GCS Storage Objects Explorer ---');
const objects = await listStorageObjects();
assert(objects.length > 0, 'Storage objects list should not be empty');
for (const obj of objects) {
  assert(obj.object_name, 'Object name required');
  assert(obj.size_bytes > 0, 'Object size should be positive');
  assert(obj.sha256_hash, 'SHA-256 hash required');
}
console.log(`  ✓ Listed ${objects.length} planetary assets with SHA-256 hashes`);

// 4. Verify AI Status & Provider Registry
console.log('\n--- 4. Testing AI Status & Dual-Provider Configuration ---');
const aiStatus = await getAiStatus();
assert.equal(aiStatus.active_provider, 'Google Gemini (Primary)', 'Gemini should be primary');
assert(aiStatus.available_providers.some((p) => p.provider_id === 'gemini'), 'Gemini provider missing');
assert(aiStatus.available_providers.some((p) => p.provider_id === 'azure_foundry'), 'Azure Foundry missing');
console.log(`  ✓ Primary AI: ${aiStatus.active_provider}`);
console.log(`  ✓ Evaluation AI: ${aiStatus.secondary_provider}`);

// 5. Verify Mars Science Copilot Chat & Citations
console.log('\n--- 5. Testing Mars Science Copilot Grounded Chat ---');
const chatRes = await sendMarsScienceChat('What is the mineralogical significance of carbonates in Jezero delta front?', 'gemini');
assert(chatRes.reply, 'Reply text required');
assert(chatRes.provider_used, 'Provider used required');
assert(chatRes.scientific_citations.length > 0, 'Scientific citations required');
assert(chatRes.uncertainty_notice, 'Uncertainty notice required');
console.log(`  ✓ Response from ${chatRes.provider_used} (${chatRes.model_used}):`);
console.log(`    Citations: ${chatRes.scientific_citations.map((c) => `${c.instrument}: ${c.product_id}`).join(', ')}`);
console.log(`    Uncertainty Notice: ${chatRes.uncertainty_notice.slice(0, 60)}...`);

// 6. Verify Deterministic Route Explanation
console.log('\n--- 6. Testing AI Route Explanation Grounding ---');
const routeExpl = await explainRoute('primary', 'Why was this path chosen over steeper slopes?');
assert(routeExpl.explanation, 'Explanation required');
assert(routeExpl.total_distance_km >= 0, 'Distance required');
assert(routeExpl.total_cost >= 0, 'Cost required');
assert(routeExpl.max_slope_deg >= 0, 'Max slope required');
console.log(`  ✓ Route ${routeExpl.route_id}: ${routeExpl.total_distance_km} km, cost ${routeExpl.total_cost}, slope ${routeExpl.max_slope_deg}°`);
console.log(`    Safety: ${routeExpl.risk_category}`);

// 7. Verify Dual-Model Comparison Workbench
console.log('\n--- 7. Testing Dual-Model Comparative Evaluation ---');
const comp = await compareAiModels('Compare traversability risk on Jezero crater rim versus crater floor.');
assert(comp.gemini_response, 'Gemini response required');
assert(comp.comparison_summary, 'Comparison summary required');
assert(comp.citation_alignment_score >= 0 && comp.citation_alignment_score <= 1, 'Alignment score between 0 and 1');
console.log(`  ✓ Gemini response: ${comp.gemini_response.reply.slice(0, 75)}...`);
console.log(`  ✓ Summary: ${comp.comparison_summary}`);
console.log(`  ✓ Citation Alignment: ${(comp.citation_alignment_score * 100).toFixed(0)}%`);

console.log('\n🎉 ALL CLOUD & AI INTEGRATION VERIFICATIONS PASSED CLEANLY!\n');
