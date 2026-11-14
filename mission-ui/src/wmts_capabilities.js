import WMTS from 'ol/source/WMTS.js';
import WMTSTileGrid from 'ol/tilegrid/WMTS.js';

export const AUTHORITATIVE_MARS_IMAGERY_CATALOG = {
  viking_global_232m: {
    key: 'viking_global_232m',
    id: 'Mars_Viking_MDIM21_ClrMosaic_global_232m',
    productId: 'Mars_Viking_MDIM21_ClrMosaic_global_232m',
    sourceLabel: 'NASA Viking global imagery · 232 m/px',
    title: 'NASA Mars Trek Viking MDIM 2.1 Global Color Mosaic (232 m/px)',
    productName: 'Mars Digital Image Model (MDIM 2.1) Global Color Mosaic',
    doi: '10.5066/F71V5C67',
    spacecraft: 'Viking Orbiter 1 & 2',
    instrument: 'VIS (Visual Imaging Subsystem)',
    resolutionMeters: 232.0,
    crs: 'IAU2000:49900 (urn:ogc:def:crs:EPSG::104905)',
    verticalUnits: 'None (visual albedo imagery)',
    nodataValue: 'None (global coverage)',
    bounds: [-180.0, -90.0, 180.0, 90.0],
    dataType: 'imagery',
    license: 'Public Domain (NASA / USGS Astrogeology)',
    accessDate: '2026-11-14',
    format: 'image/jpeg',
    matrixSet: 'default028mm',
    style: 'default',
    minZoom: 0,
    maxZoom: 7,
    capabilitiesUrl:
      'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/WMTSCapabilities.xml',
    localCapabilitiesUrl:
      '/mission-data/wmts/Mars_Viking_MDIM21_ClrMosaic_global_232m.xml',
    resourceUrlTemplate:
      'https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.jpg',
    officialUrl: 'https://trek.nasa.gov/mars/',
  },
  ctx_jezero_6m: {
    key: 'ctx_jezero_6m',
    id: 'JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',
    productId: 'JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',
    sourceLabel: 'USGS CTX orthomosaic · 6 m/px',
    title: 'Mars 2020 Terrain Relative Navigation CTX Orthorectified Image Mosaic (6 m/px)',
    productName: 'Mars 2020 Terrain Relative Navigation Context Camera Orthorectified Image Mosaic',
    doi: '10.5066/P9GV1ND3',
    spacecraft: 'Mars Reconnaissance Orbiter (MRO)',
    instrument: 'CTX (Context Camera)',
    resolutionMeters: 6.0,
    crs: 'IAU2000:49900 (urn:ogc:def:crs:EPSG::104905)',
    verticalUnits: 'None (orthorectified panchromatic imagery)',
    nodataValue: 0,
    bounds: [77.1604655, 18.2110274, 77.6991776, 18.7211945],
    dataType: 'imagery',
    license: 'Public Domain (USGS Astrogeology Science Center / NASA PDS)',
    accessDate: '2026-11-14',
    format: 'image/png',
    matrixSet: 'default028mm',
    style: 'default',
    minZoom: 0,
    maxZoom: 13,
    capabilitiesUrl:
      'https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml',
    localCapabilitiesUrl:
      '/mission-data/wmts/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.xml',
    resourceUrlTemplate:
      'https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png',
    officialUrl:
      'https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0',
    officialGeoTiffUrl:
      'https://planetarymaps.usgs.gov/mosaic/mars2020_trn/CTX/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0.tif',
  },
  hirise_jezero_25cm: {
    key: 'hirise_jezero_25cm',
    id: 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd',
    productId: 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first',
    sourceLabel: 'USGS HiRISE orthomosaic · 0.25 m/px',
    title: 'Mars 2020 Terrain Relative Navigation HiRISE Orthorectified Image Mosaic (0.25 m/px)',
    productName: 'Mars 2020 Terrain Relative Navigation HiRISE Orthorectified Image Mosaic',
    doi: '10.5066/P9QJDP48',
    spacecraft: 'Mars Reconnaissance Orbiter (MRO)',
    instrument: 'HiRISE (High Resolution Imaging Science Experiment)',
    resolutionMeters: 0.25,
    crs: 'IAU2000:49900 (urn:ogc:def:crs:EPSG::104905)',
    verticalUnits: 'None (orthorectified visible grayscale imagery)',
    nodataValue: 0,
    bounds: [77.2229331, 18.3067994, 77.583964, 18.669315],
    dataType: 'imagery',
    license: 'Public Domain (USGS Astrogeology Science Center / NASA PDS)',
    accessDate: '2026-11-14',
    format: 'image/png',
    matrixSet: 'default028mm',
    style: 'default',
    minZoom: 0,
    maxZoom: 17,
    capabilitiesUrl:
      'https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/WMTSCapabilities.xml',
    localCapabilitiesUrl:
      '/mission-data/wmts/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd.xml',
    resourceUrlTemplate:
      'https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png',
    officialUrl:
      'https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first',
    officialGeoTiffUrl:
      'https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first.tif',
  },
  mola_hrsc_shaded_200m: {
    key: 'mola_hrsc_shaded_200m',
    id: 'Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw',
    productId: 'Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw',
    sourceLabel: 'USGS MOLA-HRSC color hillshade · 200 m/px',
    title: 'USGS MOLA–HRSC Global Blended Color Hillshade (200 m/px)',
    productName: 'Mars MGS MOLA - MEX HRSC Blended Colorized Elevation Relief Global 200m',
    doi: '10.5066/P9P7W018',
    spacecraft: 'Mars Global Surveyor & Mars Express',
    instrument: 'MOLA & HRSC',
    resolutionMeters: 200.0,
    crs: 'IAU2000:49900 (urn:ogc:def:crs:EPSG::104905)',
    verticalUnits: 'Color-shaded relief visualization (non-numerical)',
    nodataValue: 'None',
    bounds: [-180.0, -90.0, 180.0, 90.0],
    dataType: 'relief_visualization',
    license: 'Public Domain (USGS Astrogeology Science Center)',
    accessDate: '2026-11-14',
    format: 'image/jpeg',
    matrixSet: 'default028mm',
    style: 'default',
    minZoom: 0,
    maxZoom: 8,
    capabilitiesUrl:
      'https://trek.nasa.gov/tiles/Mars/EQ/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/WMTSCapabilities.xml',
    localCapabilitiesUrl:
      '/mission-data/wmts/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw.xml',
    resourceUrlTemplate:
      'https://trek.nasa.gov/tiles/Mars/EQ/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/{Style}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.jpg',
    officialUrl:
      'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
  },
};

export const AUTHORITATIVE_MARS_TERRAIN_CATALOG = {
  hirise_dtm_1m: {
    key: 'hirise_dtm_1m',
    id: 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40',
    productId: 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40',
    sourceLabel: 'USGS HiRISE DTM · 1 m/px',
    title: 'Mars 2020 Terrain Relative Navigation HiRISE DTM Mosaic (1 m/px)',
    productName: 'Mars 2020 Terrain Relative Navigation HiRISE DTM Mosaic',
    doi: '10.5066/P9REJ9JN',
    spacecraft: 'Mars Reconnaissance Orbiter (MRO)',
    instrument: 'HiRISE (Stereo Photogrammetry)',
    resolutionMeters: 1.0,
    crs: 'Equirectangular Mars 2000 Sphere IAU / IAU2000:49900',
    verticalUnits: 'meters',
    verticalDatum: 'Mars 2000 MOLA Geoid (DeltaGeoid blend40)',
    nodataValue: -3.4028226550889045e38,
    bounds: [77.2229331, 18.3067994, 77.583964, 18.669315],
    provisionedCorridorBounds: [77.381989, 18.371988, 77.458008, 18.44001],
    dataType: 'elevation',
    license: 'Public Domain (USGS Astrogeology Science Center / NASA PDS)',
    accessDate: '2026-11-14',
    officialUrl:
      'https://astrogeology.usgs.gov/search/map/mars_2020_terrain_relative_navigation_hirise_dtm_mosaic',
    officialGeoTiffUrl:
      'https://planetarymaps.usgs.gov/mosaic/mars2020_trn/HiRISE/JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40.tif',
  },
  mola_hrsc_dem_200m: {
    key: 'mola_hrsc_dem_200m',
    id: 'Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2',
    productId: 'Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2',
    sourceLabel: 'USGS MOLA-HRSC DEM · 200 m/px',
    title: 'Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2',
    productName: 'Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2',
    doi: '10.5066/P9P7W018',
    spacecraft: 'Mars Global Surveyor & Mars Express',
    instrument: 'MOLA & HRSC',
    resolutionMeters: 200.0,
    crs: 'IAU2000:49900 (Mars 2000 Sphere, R=3,396,190 m)',
    verticalUnits: 'meters',
    verticalDatum: 'Mars Areoid (MOLA 0m reference datum)',
    nodataValue: -32768.0,
    bounds: [77.2008333, 18.1491667, 77.9491667, 18.6508333],
    dataType: 'elevation',
    license: 'Public Domain (USGS Astrogeology Science Center / DLR / ESA)',
    accessDate: '2026-11-14',
    officialUrl:
      'https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m',
    officialGeoTiffUrl:
      'https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif',
  },
};

/**
 * Strips XML comments (`<!-- ... -->`) before parsing so commented-out example
 * `<TileMatrix>` blocks in NASA Mars Trek WMTSCapabilities.xml are never matched.
 */
function stripXmlComments(xmlText) {
  return String(xmlText || '').replace(/<!--[\s\S]*?-->/g, '');
}

/**
 * Parses an OGC WMTS 1.0.0 `GetCapabilities` XML document and extracts the actual
 * Layer, BoundingBox, Style, Format, ResourceURL template, TileMatrixSet, and
 * TileMatrix definitions (`Identifier`, `ScaleDenominator`, `TopLeftCorner`,
 * `TileWidth`, `TileHeight`, `MatrixWidth`, `MatrixHeight`).
 */
export function parseWMTSCapabilitiesXml(xmlText) {
  const clean = stripXmlComments(xmlText);
  if (!clean.includes('<Capabilities') || !clean.includes('<TileMatrixSet>')) {
    throw new Error('Invalid OGC WMTS GetCapabilities XML document.');
  }

  const layerBlockMatch = clean.match(/<Layer>([\s\S]*?)<\/Layer>/);
  if (!layerBlockMatch) {
    throw new Error('WMTS Capabilities document contains no <Layer> definition.');
  }
  const layerXml = layerBlockMatch[1];

  const extractTag = (src, tag) => {
    const m = src.match(new RegExp(`<(?:ows:)?${tag}[^>]*>([\\s\\S]*?)<\\/(?:ows:)?${tag}>`, 'i'));
    return m ? m[1].trim() : null;
  };

  const layerId = extractTag(layerXml, 'Identifier');
  const title = extractTag(layerXml, 'Title') || layerId;
  const format = extractTag(layerXml, 'Format') || 'image/png';

  const styleBlockMatch = layerXml.match(/<Style[^>]*>([\s\S]*?)<\/Style>/i);
  const style = styleBlockMatch ? extractTag(styleBlockMatch[1], 'Identifier') || 'default' : 'default';

  const matrixSetLinkMatch = layerXml.match(/<TileMatrixSetLink>([\s\S]*?)<\/TileMatrixSetLink>/i);
  const matrixSetId = matrixSetLinkMatch
    ? extractTag(matrixSetLinkMatch[1], 'TileMatrixSet') || 'default028mm'
    : 'default028mm';

  const bboxMatch = layerXml.match(/<ows:(?:WGS84)?BoundingBox[^>]*>([\s\S]*?)<\/ows:(?:WGS84)?BoundingBox>/i);
  let bounds = [-180.0, -90.0, 180.0, 90.0];
  if (bboxMatch) {
    const lowerStr = extractTag(bboxMatch[1], 'LowerCorner');
    const upperStr = extractTag(bboxMatch[1], 'UpperCorner');
    if (lowerStr && upperStr) {
      const [minLon, minLat] = lowerStr.split(/\s+/).map(Number);
      const [maxLon, maxLat] = upperStr.split(/\s+/).map(Number);
      if ([minLon, minLat, maxLon, maxLat].every(Number.isFinite)) {
        bounds = [minLon, minLat, maxLon, maxLat];
      }
    }
  }

  const resUrlMatch = layerXml.match(/<ResourceURL[^>]*template="([^"]+)"/i);
  const rawTemplate = resUrlMatch ? resUrlMatch[1].trim() : null;
  const resourceUrlTemplate = rawTemplate ? rawTemplate.replace(/\/1\.0\.0\/\/\{/g, '/1.0.0/{') : null;

  const tmsBlockMatch = [...clean.matchAll(/<TileMatrixSet>([\s\S]*?)<\/TileMatrixSet>/gi)].find(m =>
    m[1].includes('<TileMatrix>')
  );
  if (!tmsBlockMatch) {
    throw new Error('WMTS Capabilities document lacks a <TileMatrixSet> section.');
  }
  const tmsXml = tmsBlockMatch[1];
  const supportedCrs = extractTag(tmsXml, 'SupportedCRS') || 'urn:ogc:def:crs:EPSG::104905';

  const matrixMatches = [...tmsXml.matchAll(/<TileMatrix>([\s\S]*?)<\/TileMatrix>/gi)];
  if (!matrixMatches.length) {
    throw new Error('WMTS TileMatrixSet contains no <TileMatrix> entries.');
  }

  const matrices = matrixMatches.map(m => {
    const body = m[1];
    const identifier = extractTag(body, 'Identifier');
    const scaleDenominator = Number(extractTag(body, 'ScaleDenominator'));
    const tlcStr = extractTag(body, 'TopLeftCorner') || '-180.0 90.0';
    const [originLon, originLat] = tlcStr.split(/\s+/).map(Number);
    const tileWidth = Math.round(Number(extractTag(body, 'TileWidth')) || 256);
    const tileHeight = Math.round(Number(extractTag(body, 'TileHeight')) || 256);
    const matrixWidth = Math.round(Number(extractTag(body, 'MatrixWidth')));
    const matrixHeight = Math.round(Number(extractTag(body, 'MatrixHeight')));
    const resolutionDegPerPx = 180.0 / (tileHeight * matrixHeight);

    return {
      identifier,
      scaleDenominator,
      topLeftCorner: [originLon, originLat],
      tileWidth,
      tileHeight,
      matrixWidth,
      matrixHeight,
      resolutionDegPerPx,
    };
  });

  return {
    layerId,
    title,
    format,
    style,
    matrixSet: matrixSetId,
    supportedCrs,
    bounds,
    resourceUrlTemplate,
    origin: matrices[0].topLeftCorner,
    matrixIds: matrices.map(m => m.identifier),
    resolutions: matrices.map(m => m.resolutionDegPerPx),
    sizes: matrices.map(m => [m.matrixWidth, m.matrixHeight]),
    tileSizes: matrices.map(m => [m.tileWidth, m.tileHeight]),
    minZoom: 0,
    maxZoom: matrices.length - 1,
    matrices,
  };
}

/**
 * Builds a deterministic fallback WMTS capabilities descriptor from an authoritative
 * NASA Mars Trek catalog entry when offline or before XML fetch completes.
 */
export function buildCapabilitiesFromCatalogEntry(entry) {
  const maxZ = entry.maxZoom ?? 7;
  const matrices = Array.from({ length: maxZ + 1 }, (_, z) => {
    const matrixHeight = Math.pow(2, z);
    const matrixWidth = Math.pow(2, z + 1);
    const tileWidth = 256;
    const tileHeight = 256;
    return {
      identifier: String(z),
      scaleDenominator: 279227636.29807472 / Math.pow(2, z),
      topLeftCorner: [-180.0, 90.0],
      tileWidth,
      tileHeight,
      matrixWidth,
      matrixHeight,
      resolutionDegPerPx: 180.0 / (tileHeight * matrixHeight),
    };
  });

  return {
    layerId: entry.id,
    title: entry.title,
    format: entry.format,
    style: entry.style || 'default',
    matrixSet: entry.matrixSet || 'default028mm',
    supportedCrs: 'urn:ogc:def:crs:EPSG::104905',
    bounds: entry.bounds,
    resourceUrlTemplate: entry.resourceUrlTemplate,
    origin: [-180.0, 90.0],
    matrixIds: matrices.map(m => m.identifier),
    resolutions: matrices.map(m => m.resolutionDegPerPx),
    sizes: matrices.map(m => [m.matrixWidth, m.matrixHeight]),
    tileSizes: matrices.map(m => [m.tileWidth, m.tileHeight]),
    minZoom: 0,
    maxZoom: maxZ,
    matrices,
  };
}

/**
 * Creates an OpenLayers `WMTS` source (`ol/source/WMTS.js`) with an exact `WMTSTileGrid`
 * (`ol/tilegrid/WMTS.js`) derived from parsed WMTS capabilities.
 */
export function createOpenLayersWMTSSource(parsedCaps, onTileLoad, onTileError) {
  const tileGrid = new WMTSTileGrid({
    extent: [-180.0, -90.0, 180.0, 90.0],
    origin: parsedCaps.origin || [-180.0, 90.0],
    resolutions: parsedCaps.resolutions,
    matrixIds: parsedCaps.matrixIds,
    sizes: parsedCaps.sizes,
    tileSizes: parsedCaps.tileSizes,
  });

  const src = new WMTS({
    layer: parsedCaps.layerId,
    style: parsedCaps.style || 'default',
    matrixSet: parsedCaps.matrixSet || 'default028mm',
    format: parsedCaps.format || 'image/png',
    projection: 'IAU2000:49900',
    requestEncoding: 'REST',
    urls: [parsedCaps.resourceUrlTemplate],
    tileGrid,
    crossOrigin: 'anonymous',
    wrapX: false,
    reprojectionErrorThreshold: 0.5,
  });

  if (onTileLoad) src.on('tileloadend', onTileLoad);
  if (onTileError) src.on('tileloaderror', onTileError);
  return src;
}

/**
 * Fetches and parses the official WMTS GetCapabilities XML for a given catalog entry,
 * trying the local verbatim snapshot first for instant zero-latency initialization
 * and falling back to the upstream NASA Mars Trek capabilities URL.
 */
export async function fetchAndParseWMTSCapabilities(entry) {
  const urlsToTry = [entry.localCapabilitiesUrl, entry.capabilitiesUrl].filter(Boolean);
  for (const url of urlsToTry) {
    try {
      const resp = await fetch(url);
      if (resp.ok) {
        const xmlText = await resp.text();
        if (xmlText.includes('<Capabilities')) {
          const parsed = parseWMTSCapabilitiesXml(xmlText);
          return { ...parsed, sourceXmlUrl: url, capabilitiesVerified: true };
        }
      }
    } catch {
      // Continue to next candidate URL
    }
  }
  return { ...buildCapabilitiesFromCatalogEntry(entry), sourceXmlUrl: null, capabilitiesVerified: false };
}

/**
 * Checks whether a planetocentric coordinate `(lon, lat)` lies inside a `[minLon, minLat, maxLon, maxLat]` bounding box.
 */
export function isCoordinateInBounds(lon, lat, bounds) {
  if (!Number.isFinite(lon) || !Number.isFinite(lat) || !Array.isArray(bounds) || bounds.length < 4) {
    return false;
  }
  return lon >= bounds[0] && lon <= bounds[2] && lat >= bounds[1] && lat <= bounds[3];
}

/**
 * Evaluates which authoritative imagery and terrain datasets cover a given `(lon, lat)` coordinate
 * or a route `(start, destination, hiriseTerrain)` pair.
 */
export function verifyCoordinateDatasetCoverage(arg1, arg2, hiriseTerrain = undefined) {
  if (arg1 && typeof arg1 === 'object' && 'lon' in arg1) {
    const start = { lon: Number(arg1.lon), lat: Number(arg1.lat) };
    const dest = arg2 && typeof arg2 === 'object' ? { lon: Number(arg2.lon), lat: Number(arg2.lat) } : start;

    const sHiOrtho = isCoordinateInBounds(start.lon, start.lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.bounds);
    const dHiOrtho = isCoordinateInBounds(dest.lon, dest.lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.bounds);
    const sHiDtmOff = isCoordinateInBounds(start.lon, start.lat, AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.bounds);
    const dHiDtmOff = isCoordinateInBounds(dest.lon, dest.lat, AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.bounds);
    const sHiDtmLoc = isCoordinateInBounds(
      start.lon,
      start.lat,
      AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.provisionedCorridorBounds
    );
    const dHiDtmLoc = isCoordinateInBounds(
      dest.lon,
      dest.lat,
      AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.provisionedCorridorBounds
    );
    const sCtx = isCoordinateInBounds(start.lon, start.lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.bounds);
    const dCtx = isCoordinateInBounds(dest.lon, dest.lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.bounds);

    let activeHiriseDtmStatus = { covered: sHiDtmLoc && dHiDtmLoc, reason: sHiDtmLoc && dHiDtmLoc ? 'VALIDATED' : 'OUTSIDE_COVERAGE' };
    if (hiriseTerrain !== undefined) {
      if (!hiriseTerrain) {
        activeHiriseDtmStatus = {
          covered: false,
          reason: 'NOT_DOWNLOADED_OR_NOT_LOADED',
          detail: 'USGS HiRISE 1 m DTM (10.5066/P9REJ9JN) is not loaded in memory.',
        };
      } else if (!sHiDtmLoc || !dHiDtmLoc) {
        activeHiriseDtmStatus = {
          covered: false,
          reason: 'OUTSIDE_COVERAGE',
          detail: 'One or both route endpoints lie outside the active 1 m HiRISE DTM coverage window.',
        };
      } else {
        activeHiriseDtmStatus = {
          covered: true,
          reason: 'VALIDATED',
          detail: 'Both endpoints lie inside the validated USGS HiRISE 1 m DTM (10.5066/P9REJ9JN).',
        };
      }
    }

    return {
      start,
      destination: dest,
      hiriseOrthoCovered: sHiOrtho && dHiOrtho,
      hiriseDtmOfficialCovered: sHiDtmOff && dHiDtmOff,
      bothInOfficialHiriseDtmBounds: sHiDtmOff && dHiDtmOff,
      bothInLocalHiriseDtmCorridor: sHiDtmLoc && dHiDtmLoc,
      ctxOrthoCovered: sCtx && dCtx,
      activeHiriseDtmStatus,
    };
  }

  const lon = Number(arg1);
  const lat = Number(arg2);
  const inViking = isCoordinateInBounds(lon, lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m.bounds);
  const inCtx = isCoordinateInBounds(lon, lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.bounds);
  const inHiriseOrtho = isCoordinateInBounds(lon, lat, AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.bounds);
  const inHiriseDtmOfficial = isCoordinateInBounds(lon, lat, AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.bounds);
  const inHiriseDtmProvisioned = isCoordinateInBounds(
    lon,
    lat,
    AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.provisionedCorridorBounds
  );
  const inMolaHrscDem = isCoordinateInBounds(lon, lat, AUTHORITATIVE_MARS_TERRAIN_CATALOG.mola_hrsc_dem_200m.bounds);

  return {
    coordinate: { lon, lat },
    bothInLocalHiriseDtmCorridor: inHiriseDtmProvisioned,
    imagery: {
      viking_global_232m: inViking,
      ctx_jezero_6m: inCtx,
      hirise_jezero_25cm: inHiriseOrtho,
      finestAvailableImagery: inHiriseOrtho
        ? AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm
        : inCtx
          ? AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m
          : AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m,
    },
    terrain: {
      mola_hrsc_dem_200m: inMolaHrscDem,
      hirise_dtm_1m_official_bounds: inHiriseDtmOfficial,
      hirise_dtm_1m_provisioned_window: inHiriseDtmProvisioned,
      finestAvailableTerrain: inHiriseDtmOfficial
        ? AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m
        : inMolaHrscDem
          ? AUTHORITATIVE_MARS_TERRAIN_CATALOG.mola_hrsc_dem_200m
          : null,
    },
  };
}

