/**
 * Client library for MARSPath Mission Intelligence & Risk Fusion Subsystem.
 * Exposes data freshness auditing, spatial/temporal observations, knowledge graph queries,
 * multi-hop evidence/impact traversals, route risk propagation, and what-if scenario simulations.
 */

export async function fetchDataFreshness(apiUrl = '') {
  const res = await fetch(`${apiUrl}/api/v1/intelligence/data-freshness`);
  if (!res.ok) {
    throw new Error(`Data freshness fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchNormalizedObservations(params = {}, apiUrl = '') {
  const query = new URLSearchParams();
  if (params.bbox) query.set('bbox', Array.isArray(params.bbox) ? params.bbox.join(',') : params.bbox);
  if (params.instrument && params.instrument !== 'all') query.set('instrument', params.instrument);
  if (params.provenance_kind && params.provenance_kind !== 'all') query.set('provenance_kind', params.provenance_kind);
  if (params.quality_tier && params.quality_tier !== 'all') query.set('quality_tier', params.quality_tier);
  if (params.measurement_type) query.set('measurement_type', params.measurement_type);
  if (params.min_sol !== undefined) query.set('min_sol', params.min_sol);
  if (params.max_sol !== undefined) query.set('max_sol', params.max_sol);
  if (params.limit) query.set('limit', params.limit);

  const qs = query.toString();
  const url = `${apiUrl}/api/v1/intelligence/observations${qs ? '?' + qs : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Observations fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchKnowledgeGraph(params = {}, apiUrl = '') {
  const query = new URLSearchParams();
  if (params.node_type && params.node_type !== 'all') query.set('node_type', params.node_type);
  if (params.max_nodes) query.set('max_nodes', params.max_nodes);

  const qs = query.toString();
  const url = `${apiUrl}/api/v1/intelligence/graph${qs ? '?' + qs : ''}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Knowledge graph fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchGraphNode(nodeId, apiUrl = '') {
  const url = `${apiUrl}/api/v1/intelligence/graph/${encodeURIComponent(nodeId)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Graph node fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchNodeEvidence(nodeId, maxDepth = 5, apiUrl = '') {
  const url = `${apiUrl}/api/v1/intelligence/graph/${encodeURIComponent(nodeId)}/evidence?max_depth=${maxDepth}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Evidence trace fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchNodeImpacts(nodeId, maxDepth = 5, apiUrl = '') {
  const url = `${apiUrl}/api/v1/intelligence/graph/${encodeURIComponent(nodeId)}/impacts?max_depth=${maxDepth}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Impact trace fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function fetchScenarios(apiUrl = '') {
  const res = await fetch(`${apiUrl}/api/v1/intelligence/scenarios`);
  if (!res.ok) {
    throw new Error(`Scenarios fetch failed: ${res.status}`);
  }
  return await res.json();
}

export async function createScenario(payload, apiUrl = '') {
  const res = await fetch(`${apiUrl}/api/v1/intelligence/scenarios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    throw new Error(`Scenario creation failed: ${res.status}`);
  }
  return await res.json();
}

export async function analyzeScenario(scenarioId, routeData = null, apiUrl = '') {
  const body = routeData ? { route_data: routeData } : {};
  const res = await fetch(`${apiUrl}/api/v1/intelligence/scenarios/${encodeURIComponent(scenarioId)}/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  if (!res.ok) {
    throw new Error(`Scenario analysis failed: ${res.status}`);
  }
  return await res.json();
}

export async function compareScenario(scenarioId, baselineRouteId = 'primary', apiUrl = '') {
  const url = `${apiUrl}/api/v1/intelligence/scenarios/${encodeURIComponent(scenarioId)}/compare?baseline_route_id=${encodeURIComponent(baselineRouteId)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Scenario comparison failed: ${res.status}`);
  }
  return await res.json();
}

export async function evaluateRouteRisk(routeData, maxSlope = 14.0, maxRoughness = 0.85, apiUrl = '') {
  const payload = {
    route_data: routeData,
    max_slope_ceiling_deg: maxSlope,
    max_roughness_limit: maxRoughness
  };
  const res = await fetch(`${apiUrl}/api/v1/intelligence/risk-propagation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    throw new Error(`Risk propagation evaluation failed: ${res.status}`);
  }
  return await res.json();
}
