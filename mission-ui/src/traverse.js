export function validateTraverse(data) {
  if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features) || !data.features.length) {
    throw new Error('No rover drive records were supplied.');
  }
  for (const f of data.features) {
    if (
      f.geometry?.type !== 'LineString' ||
      f.geometry.coordinates.length < 2 ||
      !Number.isFinite(f.properties?.sol) ||
      f.geometry.coordinates.some(
        c => c.length < 2 || !c.slice(0, 2).every(Number.isFinite) || Math.abs(c[1]) > 90 || Math.abs(c[0]) > 360
      )
    ) {
      throw new Error('The rover traverse contains invalid geometry.');
    }
  }
  return data;
}

export function visibleDrives(data, sol) {
  return data?.features.filter(f => f.properties.sol <= sol) || [];
}

export function visibleWaypoints(data, sol) {
  const feats = Array.isArray(data) ? data : data?.features;
  return feats?.filter(f => f.properties.sol <= sol) || [];
}

/**
 * Filter recorded drives within a trailing window of elapsed sols: [endSol - windowSols + 1, endSol].
 * Gaps and days without drives count toward the elapsed sol window.
 */
export function windowedDrives(data, endSol, windowSols = 15) {
  if (!data?.features) return [];
  const startSol = Math.max(0, endSol - windowSols + 1);
  return data.features.filter(f => f.properties.sol >= startSol && f.properties.sol <= endSol);
}

/**
 * Filter recorded waypoints within a trailing window of elapsed sols: [endSol - windowSols + 1, endSol].
 */
export function windowedWaypoints(data, endSol, windowSols = 15) {
  const feats = Array.isArray(data) ? data : data?.features;
  if (!feats) return [];
  const startSol = Math.max(0, endSol - windowSols + 1);
  return feats.filter(f => f.properties.sol >= startSol && f.properties.sol <= endSol);
}

/**
 * Get the latest recorded waypoint up to or at endSol.
 */
export function latestWaypointThroughSol(data, endSol) {
  const feats = Array.isArray(data) ? data : data?.features;
  if (!feats?.length) return null;
  const filtered = feats.filter(f => f.properties.sol <= endSol);
  return filtered.length ? filtered[filtered.length - 1] : null;
}

export function traverseStats(drives, waypoints) {
  const sols = drives.map(f => f.properties.sol);
  const wpList = Array.isArray(waypoints) ? waypoints : waypoints?.features || [];
  const last = wpList.at(-1);
  return {
    segments: drives.length,
    firstSol: sols.length ? Math.min(...sols) : null,
    lastSol: sols.length ? Math.max(...sols) : null,
    distance: last?.properties?.dist_total_m ?? null,
    latest: last,
  };
}

export function exportTraverse(data, sol) {
  return {
    type: 'FeatureCollection',
    name: 'Perseverance recorded traverse',
    target: 'Mars',
    coordinate_system: 'Source east-positive longitude / north-positive latitude, elevation retained as published',
    metadata: {
      ...data.marspath_metadata,
      selected_through_sol: sol,
      kind: 'Recorded travel; not generated routes or executable rover commands',
    },
    features: visibleDrives(data, sol),
  };
}
