export function exportGeoJSON(response, selectedRouteId, request) {
  const selectedRoute = response?.routes?.find(r => r.route_id === selectedRouteId) || response?.routes?.[0];
  return {
    type: 'FeatureCollection',
    name: 'MARSPath Jezero Route Plan',
    planetary_target: 'Mars',
    planetary_crs: 'IAU2000:49900',
    coordinate_convention: 'East longitude, planetocentric latitude; optional elevation in meters above Mars areoid',
    selected_route_id: selectedRoute?.route_id || selectedRouteId,
    request: request || null,
    provenance: response?.provenance || null,
    source_selection: response?.source_selection || null,
    limitations: response?.limitations || [],
    robustness_assessment: response?.robustness_assessment || null,
    features: response?.routes
      ? response.routes
          .filter(r => r.route_id === (selectedRoute?.route_id || selectedRouteId))
          .map(r => ({
            type: 'Feature',
            id: r.route_id,
            geometry: r.geometry,
            properties: {
              route_id: r.route_id,
              name: r.name,
              mode: r.mode,
              score_rank: r.score_rank,
              total_cost: r.total_cost,
              cost_breakdown: r.cost_breakdown,
              summary: r.summary,
              evidence_passport: r.evidence_passport,
              warnings: r.warnings || []
            }
          }))
      : []
  };
}

export function exportCSV(response, selectedRouteId) {
  const selectedRoute = response?.routes?.find(r => r.route_id === selectedRouteId) || response?.routes?.[0];
  const segments = selectedRoute?.evidence_passport?.segments;
  const headers = [
    'segment_index',
    'start_lon',
    'start_lat',
    'end_lon',
    'end_lat',
    'is_valid_data',
    'start_elevation_m',
    'end_elevation_m',
    'elevation_delta_m',
    'slope_deg',
    'roughness',
    'hazard_flags',
    'quality_flags'
  ];

  const escapeCSV = (val) => {
    if (val === null || val === undefined) return '';
    const str = String(val);
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  const rows = [];
  if (Array.isArray(segments) && segments.length > 0) {
    for (const s of segments) {
      rows.push([
        s.segment_index ?? '',
        s.from_coord?.lon ?? s.start_lon ?? '',
        s.from_coord?.lat ?? s.start_lat ?? '',
        s.to_coord?.lon ?? s.end_lon ?? '',
        s.to_coord?.lat ?? s.end_lat ?? '',
        s.is_valid_data ?? '',
        s.from_elevation_m ?? s.start_elevation_m ?? '',
        s.to_elevation_m ?? s.end_elevation_m ?? '',
        s.elevation_delta_m ?? '',
        s.slope_deg ?? '',
        s.roughness ?? '',
        Array.isArray(s.hazard_flags) ? s.hazard_flags.join(';') : (s.hazard_flags ?? ''),
        Array.isArray(s.quality_flags) ? s.quality_flags.join(';') : (s.quality_flags ?? '')
      ].map(escapeCSV).join(','));
    }
  } else if (Array.isArray(selectedRoute?.geometry?.coordinates)) {
    const coords = selectedRoute.geometry.coordinates;
    for (let i = 0; i < coords.length - 1; i++) {
      const c1 = coords[i];
      const c2 = coords[i + 1];
      rows.push([
        i,
        c1[0],
        c1[1],
        c2[0],
        c2[1],
        true,
        c1[2] ?? '',
        c2[2] ?? '',
        (c1[2] !== undefined && c2[2] !== undefined) ? (c2[2] - c1[2]) : '',
        '',
        '',
        '',
        ''
      ].map(escapeCSV).join(','));
    }
  }

  return [headers.join(','), ...rows].join('\n');
}

export function exportJSON(response, selectedRouteId, request) {
  const selectedRoute = response?.routes?.find(r => r.route_id === selectedRouteId) || response?.routes?.[0];
  return {
    ...response,
    routes: selectedRoute ? [selectedRoute] : (response?.routes || []),
    selected_route_id: selectedRoute?.route_id || selectedRouteId,
    request: request || null,
    export_manifest: {
      created_at: new Date().toISOString(),
      planetary_target: 'Mars',
      planetary_crs: 'IAU2000:49900',
      purpose: 'Regional mission corridor planning data; not executable rover commands',
      source_selection: response?.source_selection || null,
      robustness_assessment: response?.robustness_assessment || null
    }
  };
}
