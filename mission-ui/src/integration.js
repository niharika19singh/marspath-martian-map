export const API_URL_STORAGE_KEY = 'marspath-api-url';

export function resolveInitialApiUrl(
  storageValue = typeof localStorage !== 'undefined' ? localStorage.getItem(API_URL_STORAGE_KEY) : null,
  envValue = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_API_URL : undefined
) {
  const fromStorage = typeof storageValue === 'string' ? storageValue.trim() : '';
  if (fromStorage) return fromStorage;
  const fromEnv = typeof envValue === 'string' ? envValue.trim() : '';
  if (fromEnv) return fromEnv;
  return '';
}

export function isValidOfficialSourceUrl(url) {
  if (typeof url !== 'string' || !url.trim()) return false;
  try {
    const parsed = new URL(url.trim());
    if (!['https:', 'http:'].includes(parsed.protocol)) return false;
    if (parsed.username || parsed.password) return false;
    return Boolean(parsed.hostname);
  } catch {
    return false;
  }
}

export function resolveTerrainProvenance({ live, raw, loadError, api, result, active }) {
  const passportSource = active?.evidence_passport?.source || null;

  if (live) {
    const status = api?.status || null;
    const healthReadiness = api?.health?.data_readiness || null;
    const resultProv = result?.provenance || null;

    const dataMode =
      passportSource?.data_mode ||
      result?.data_mode ||
      status?.data_mode ||
      healthReadiness?.data_mode ||
      'unknown';

    const validationStatus =
      passportSource?.validation_status ||
      resultProv?.real_data_validation_status ||
      status?.real_data_validation_status ||
      healthReadiness?.real_data_validation_status ||
      'unknown';

    const isSynthetic = Boolean(
      passportSource?.is_synthetic ??
        resultProv?.is_synthetic ??
        status?.is_synthetic ??
        healthReadiness?.is_synthetic ??
        (typeof dataMode === 'string' && dataMode.startsWith('synthetic'))
    );

    const datasetName =
      passportSource?.dataset_name ||
      resultProv?.dataset_name ||
      status?.active_dem_dataset_name ||
      healthReadiness?.dataset_name ||
      status?.loaded_dem ||
      (isSynthetic ? 'Synthetic Jezero Crater Terrain Model' : 'Backend terrain dataset');

    const localIntegrityVerified =
      passportSource?.local_integrity_verified ??
      resultProv?.local_integrity_verified ??
      status?.local_integrity_verified ??
      healthReadiness?.local_integrity_verified ??
      null;

    const sourceChecksumVerified = Boolean(
      passportSource?.source_checksum_verified ??
        resultProv?.source_checksum_verified ??
        status?.source_checksum_verified ??
        healthReadiness?.source_checksum_verified ??
        false
    );

    const candidateUrl =
      passportSource !== null && passportSource !== undefined
        ? passportSource.official_source_url
        : (resultProv?.official_source_url ??
          status?.active_dem_source_url ??
          healthReadiness?.official_source_url ??
          null);

    const officialSourceUrl =
      !isSynthetic && isValidOfficialSourceUrl(candidateUrl) ? candidateUrl.trim() : null;

    let sourceVerificationText;
    let fileIntegrityText;
    let upstreamChecksumText;

    if (isSynthetic) {
      sourceVerificationText = 'Synthetic procedural terrain (not NASA/USGS observation data)';
      fileIntegrityText = 'Synthetic fixture (no observational DEM)';
      upstreamChecksumText = 'Not applicable (synthetic)';
    } else if (sourceChecksumVerified && validationStatus === 'verified_source') {
      sourceVerificationText = 'Verified official source (upstream archive checksum verified)';
      fileIntegrityText = localIntegrityVerified ? 'SHA-256 verified' : 'Unverified';
      upstreamChecksumText = 'Verified against official archive';
    } else if (
      validationStatus === 'official_endpoint_retrieved_checksum_unverified' ||
      (!sourceChecksumVerified && validationStatus === 'verified_source')
    ) {
      sourceVerificationText = 'Official endpoint retrieval (upstream archive checksum unverified)';
      fileIntegrityText = localIntegrityVerified ? 'Local extract SHA-256 verified' : 'Unverified';
      upstreamChecksumText = 'Unverified (official endpoint extract)';
    } else {
      sourceVerificationText = 'Unverified local raster source';
      fileIntegrityText = localIntegrityVerified ? 'SHA-256 verified' : 'Unverified';
      upstreamChecksumText = 'Unverified';
    }

    return {
      isSynthetic,
      dataMode,
      validationStatus,
      datasetName,
      localIntegrityVerified,
      sourceChecksumVerified,
      officialSourceUrl,
      sourceVerificationText,
      fileIntegrityText,
      upstreamChecksumText,
      headerReady: Boolean(api) && !isSynthetic,
      headerStatusText: isSynthetic
        ? `Synthetic terrain (${dataMode})`
        : `API terrain (${dataMode})`,
      headerEngineLabel: isSynthetic ? 'Python API · Synthetic' : 'Python API',
    };
  }

  // Local browser mode: preserve existing browser attribution behavior
  const isSynthetic = Boolean(passportSource?.is_synthetic ?? raw?.is_synthetic);
  const dataMode =
    passportSource?.data_mode ||
    result?.data_mode ||
    raw?.data_mode ||
    (raw ? 'official_endpoint_retrieved_checksum_unverified' : loadError ? 'unavailable' : 'loading');
  const validationStatus =
    passportSource?.validation_status ||
    (isSynthetic ? 'synthetic_test_fixture' : 'official_endpoint_retrieved_checksum_unverified');
  const datasetName = raw?.source_name || (loadError ? 'Local terrain unavailable' : 'Loading terrain');
  const localIntegrityVerified = Boolean(raw?.local_integrity_verified);
  const sourceChecksumVerified = Boolean(passportSource?.source_checksum_verified ?? false);
  const browserSourceUrl = raw?.source_page || raw?.source_url || 'https://astrogeology.usgs.gov/';
  const officialSourceUrl = !isSynthetic && isValidOfficialSourceUrl(browserSourceUrl) ? browserSourceUrl : null;

  return {
    isSynthetic,
    dataMode,
    validationStatus,
    datasetName,
    localIntegrityVerified,
    sourceChecksumVerified,
    officialSourceUrl,
    sourceVerificationText: isSynthetic
      ? 'Synthetic test terrain'
      : sourceChecksumVerified
        ? 'Verified official source'
        : 'Official endpoint extract (upstream archive checksum unverified)',
    fileIntegrityText: raw?.local_integrity_verified
      ? 'SHA-256 verified'
      : loadError
        ? 'Unavailable'
        : 'Checking',
    upstreamChecksumText: sourceChecksumVerified ? 'Verified' : 'Unverified',
    headerReady: Boolean(raw) && !isSynthetic,
    headerStatusText: raw
      ? isSynthetic
        ? 'Synthetic terrain'
        : 'Terrain ready'
      : loadError
        ? 'Local DEM unavailable'
        : 'Loading terrain',
    headerEngineLabel: 'Local engine',
  };
}

export function resolveAlternativeShortfall(result, requestedCount) {
  if (!result || !Array.isArray(result.routes)) {
    return {
      hasShortfall: false,
      requestedCount: 0,
      returnedCount: 0,
      warnings: [],
      message: null,
    };
  }

  const returnedCount = result.routes.length;
  const reqCount = Number(requestedCount ?? result?.request?.num_alternatives ?? returnedCount);

  if (!Number.isFinite(reqCount) || reqCount <= 1 || returnedCount >= reqCount) {
    return {
      hasShortfall: false,
      requestedCount: Number.isFinite(reqCount) ? reqCount : returnedCount,
      returnedCount,
      warnings: [],
      message: null,
    };
  }

  const rawWarnings = result.routes[0]?.warnings;
  const warnings = Array.isArray(rawWarnings)
    ? rawWarnings.filter(w => typeof w === 'string' && w.trim().length > 0).map(w => w.trim())
    : [];

  const message =
    warnings.length > 0
      ? `Returned ${returnedCount} of ${reqCount} requested routes. ${warnings.join(' ')}`
      : `Returned ${returnedCount} of ${reqCount} requested routes: fewer distinct traversable alternatives were found within the selected constraints.`;

  return {
    hasShortfall: true,
    requestedCount: reqCount,
    returnedCount,
    warnings,
    message,
  };
}

export function canSubmitRoute({ live, raw, api, busy }) {
  if (busy) return false;
  return live ? Boolean(api) : Boolean(raw);
}

export function validateRouteExecutionPreconditions({ live, raw, loadError, api, algorithm }) {
  if (!live) {
    if (!raw) {
      return {
        ok: false,
        error:
          loadError ||
          'Local terrain dataset is required for the browser engine. Wait for it to load or connect a Python backend.',
      };
    }
    return { ok: true, error: null };
  }

  if (!api) {
    return { ok: false, error: 'Connect a Python backend first.' };
  }

  if (algorithm === 'dijkstra' && !api.algorithmSupported) {
    return {
      ok: false,
      error:
        'This backend only exposes A* through its API. Select A*, or use the bundled-grid planner for Dijkstra.',
    };
  }

  return { ok: true, error: null };
}
