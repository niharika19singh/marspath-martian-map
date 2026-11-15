import React, { useEffect, useRef, useState, useMemo } from 'react';
import Map from 'ol/Map.js';
import View from 'ol/View.js';
import ImageLayer from 'ol/layer/Image.js';
import TileLayer from 'ol/layer/Tile.js';
import VectorLayer from 'ol/layer/Vector.js';
import ImageStatic from 'ol/source/ImageStatic.js';
import VectorSource from 'ol/source/Vector.js';
import Projection from 'ol/proj/Projection.js';
import { addProjection, addCoordinateTransforms } from 'ol/proj.js';
import Feature from 'ol/Feature.js';
import Point from 'ol/geom/Point.js';
import LineString from 'ol/geom/LineString.js';
import Polygon from 'ol/geom/Polygon.js';
import Overlay from 'ol/Overlay.js';
import { Style, Stroke, Fill, Circle as CircleStyle, Text, RegularShape } from 'ol/style.js';
import { ScaleLine } from 'ol/control.js';
import { M_PER_DEG, rasterImage, toIndex } from './terrain.js';
import { getAssetUrl } from './integration.js';
import {
  AUTHORITATIVE_MARS_IMAGERY_CATALOG,
  AUTHORITATIVE_MARS_TERRAIN_CATALOG,
  buildCapabilitiesFromCatalogEntry,
  createOpenLayersWMTSSource,
  fetchAndParseWMTSCapabilities,
} from './wmts_capabilities.js';
import Icon from './Icons.jsx';
import Terrain3D from './Terrain3D.jsx';
import {
  computeTimeOverlayPixels,
  buildTimeOverlayCanvas,
  calculateEdgeFeatherGradients,
} from './map_rendering.js';

export { computeTimeOverlayPixels, buildTimeOverlayCanvas, calculateEdgeFeatherGradients };

export const GLOBAL_MARS_BOUNDS = [-180, -85, 180, 85];
export const JEZERO_VALIDATED_DEM_BOUNDS = [77.2008333, 18.1491667, 77.9491667, 18.6508333];
export const JEZERO_HIRISE_ORTHO_BOUNDS = [77.2229331, 18.3067994, 77.583964, 18.669315];
export const JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS = [77.3819891, 18.3719875, 77.4580081, 18.4400097];
export const JEZERO_CTX_ORTHO_BOUNDS = [77.1604655, 18.2110274, 77.6991776, 18.7211945];

export const MARS_WMTS_LAYERS = {
  viking: AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m,
  ctx_global: AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m,
  jezero_hirise_wmts: AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm,
  mola_hrsc: AUTHORITATIVE_MARS_IMAGERY_CATALOG.mola_hrsc_shaded_200m,
};

export const PLANETARY_BOOKMARKS = [
  { id: 'global', label: 'Global Mars (232m)', sub: 'NASA Viking MDIM 2.1 Global Mosaic (180°W–180°E)', lon: 0.0, lat: 0.0, resolution: 14500, hasDem: false },
  { id: 'jezero', label: 'Jezero Crater Overview', sub: 'USGS CTX 6 m Ortho + Jezero Crater Basin', lon: 77.4508, lat: 18.4447, resolution: 65, hasDem: true },
  { id: 'octavia_landing', label: 'Octavia E. Butler Landing', sub: 'Perseverance Landing Site (HiRISE 0.25m)', lon: 77.4509, lat: 18.4446, resolution: 4, hasDem: true },
  { id: 'rover_pos', label: 'Current Rover Position', sub: 'Perseverance Active Telemetry Location', lon: 77.405, lat: 18.39, resolution: 5, hasDem: true },
  { id: 'delta_front', label: 'Delta Front & Fan', sub: 'Perseverance Ancient River Delta Sample Site', lon: 77.412, lat: 18.428, resolution: 4.5, hasDem: true },
  { id: 'gale', label: 'Gale Crater', sub: 'Curiosity (MSL) · Mt. Sharp Exploration', lon: 137.4417, lat: -4.5895, resolution: 320, hasDem: false },
  { id: 'olympus', label: 'Olympus Mons', sub: 'Solar System Highest Shield Volcano (21.9 km)', lon: -133.8, lat: 18.65, resolution: 2200, hasDem: false },
  { id: 'valles', label: 'Valles Marineris', sub: 'Grand Canyon of Mars (4,000 km Length)', lon: -70.0, lat: -10.0, resolution: 3500, hasDem: false },
];

function buildThemisThermalCanvas(terrain) {
  const canvas = document.createElement('canvas');
  canvas.width = terrain.w;
  canvas.height = terrain.h;
  const cx = canvas.getContext('2d');
  const img = cx.createImageData(terrain.w, terrain.h);
  for (let i = 0; i < terrain.n; i++) {
    const z = terrain.e[i], s = terrain.slope[i] || 0, r = terrain.rough[i] || 0;
    const j = i * 4;
    if (!Number.isFinite(z)) { img.data.set([0, 0, 0, 0], j); continue; }
    const tiNorm = Math.min(1, Math.max(0, 0.35 + (s / 28) * 0.42 + r * 0.38));
    const red = Math.round(55 + 200 * tiNorm);
    const green = Math.round(90 + 110 * (1 - Math.abs(tiNorm - 0.5) * 1.6));
    const blue = Math.round(235 - 185 * tiNorm);
    img.data.set([red, green, blue, 108], j);
  }
  cx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
}

export default function MapView(props) {
  const {
    historyMode, drives = [], waypoints = [], showHistory = true, showWaypoints = true, historyFit, waypoint, onWaypoint,
    terrain, activeDemTerrain, start, destination, pick, onPin, base = 'auto',
    hazards = false, coverage = false, showHillshade = false, showSlope = false, showRoughness = false,
    showViking = true, showCtx = true, showHirise = true, showMolaTerrain = false,
    vikingOpacity, ctxOpacity, hiriseOpacity, molaOpacity = 0.78,
    imageryOpacity = 1.0, terrainOpacity = 0.72,
    maxSlope = 20, maxRough = 0.85, response, selected, onSelectRoute,
    hover, fitToken, live, backendStatus, provenance, showRoute = true, showAlternatives = false, hoveredRoute = null,
    view3d = false, layersOpen, onLayersToggle, onTiltToggle, actionsRef,
    leftOpen = true, rightExpanded = false, profileExpanded = false,
    showOrbiters = true, showGroundTracks = true, showFootprints = true, showCuriosity = false,
    spacecraftPositions = [], groundTracks = [], orbitalObservations = [], selectedObservation = null, selectedSpacecraft = null,
    onSelectObservation, onSelectSpacecraft, curiosityTraverse = null, curiosityWaypoints = [], focusedProduct = null,
    showThemisOverlay = false, showScienceTargets = true, scienceTargets = [], roverReplayState = null,
    activeBookmark = 'jezero', onSelectBookmark, onWmtsStatusChange,
    showReachableZone = true, showRescueMap = false, onOpenSurfacePov,
  } = props;

  const effectiveTerrain = activeDemTerrain || terrain;
  const terrainRef = useRef(effectiveTerrain);
  terrainRef.current = effectiveTerrain;

  const effVikingOpacity = vikingOpacity ?? imageryOpacity;
  const effCtxOpacity = ctxOpacity ?? imageryOpacity;
  const effHiriseOpacity = hiriseOpacity ?? imageryOpacity;

  useEffect(() => {
    fetch(getAssetUrl('/mission-data/jezero-hirise.json'))
      .then(r => (r.ok ? r.json() : null))
      .then(setHiriseMeta)
      .catch(() => {});
  }, []);

  const node = useRef(), mapRef = useRef(), layers = useRef({}), callbacks = useRef({}), terrain3D = useRef(), midLabel = useRef();
  const [locationVisible, setLocationVisible] = useState(true);
  const [hiriseMeta, setHiriseMeta] = useState(null);
  const [viewState, setViewState] = useState({ resolution: 18, centerLon: 77.425, centerLat: 18.408 });
  const [wmtsStats, setWmtsStats] = useState({
    loaded: 0,
    errors: 0,
    byLayer: {
      viking: { loaded: 0, errors: 0, capabilitiesVerified: false },
      ctx: { loaded: 0, errors: 0, capabilitiesVerified: false },
      hirise: { loaded: 0, errors: 0, capabilitiesVerified: false },
      mola: { loaded: 0, errors: 0, capabilitiesVerified: false },
    },
    activeLayer: AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.id,
  });
  const [cursorCoord, setCursorCoord] = useState({
    lon: 77.42,
    lat: 18.405,
    inJezeroDem: true,
    inHiriseDtm: true,
    inHiriseOrtho: true,
    inCtxOrtho: true,
  });
  const [hint, setHint] = useState(() => !localStorage.getItem('marspath-map-hint-dismissed'));
  const [isPlaying, setIsPlaying] = useState(false);
  const [followRover, setFollowRover] = useState(false);
  const followRoverRef = useRef(false);
  followRoverRef.current = followRover;
  const [playbackProgress, setPlaybackProgress] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(2);
  const [inspectPopup, setInspectPopup] = useState(null);

  callbacks.current = { onPin, onSelectRoute, pick, props };
  const interact = () => {
    setHint(false);
    setLocationVisible(false);
    localStorage.setItem('marspath-map-hint-dismissed', '1');
  };
  useEffect(() => {
    const timeout = setTimeout(() => setLocationVisible(false), 4500);
    return () => clearTimeout(timeout);
  }, []);

  useEffect(() => {
    if (onWmtsStatusChange) onWmtsStatusChange(wmtsStats);
  }, [wmtsStats, onWmtsStatusChange]);

  useEffect(() => {
    if (!node.current) return;
    const activeBounds = terrainRef.current?.b || JEZERO_VALIDATED_DEM_BOUNDS;
    const jezeroExtent = activeBounds;
    const globalExtent = GLOBAL_MARS_BOUNDS;
    const ctxExtent = JEZERO_CTX_ORTHO_BOUNDS;
    const hiriseOrthoExtent = JEZERO_HIRISE_ORTHO_BOUNDS;

    const getMarsPointResolution = (resolutionDeg, point) => {
      const latRad = ((point?.[1] ?? 0) * Math.PI) / 180;
      return resolutionDeg * Math.max(0.15, Math.hypot(Math.cos(latRad), 1) / Math.SQRT2);
    };

    const marsGeoProj = new Projection({
      code: 'IAU2000:49900',
      units: 'degrees',
      extent: [-180, -90, 180, 90],
      global: false,
      metersPerUnit: M_PER_DEG,
      getPointResolution: getMarsPointResolution,
    });
    const marsUrnProj = new Projection({
      code: 'urn:ogc:def:crs:EPSG::104905',
      units: 'degrees',
      extent: [-180, -90, 180, 90],
      global: false,
      metersPerUnit: M_PER_DEG,
      getPointResolution: getMarsPointResolution,
    });
    addProjection(marsGeoProj);
    addProjection(marsUrnProj);
    addCoordinateTransforms(marsGeoProj, marsUrnProj, c => c, c => c);

    const recordTileOk = tierKey => () => {
      setWmtsStats(s => ({
        ...s,
        loaded: s.loaded + 1,
        byLayer: {
          ...s.byLayer,
          [tierKey]: {
            ...s.byLayer[tierKey],
            loaded: (s.byLayer[tierKey]?.loaded || 0) + 1,
          },
        },
      }));
    };
    const recordTileErr = tierKey => () => {
      setWmtsStats(s => ({
        ...s,
        errors: s.errors + 1,
        byLayer: {
          ...s.byLayer,
          [tierKey]: {
            ...s.byLayer[tierKey],
            errors: (s.byLayer[tierKey]?.errors || 0) + 1,
          },
        },
      }));
    };

    const vikingCap = buildCapabilitiesFromCatalogEntry(AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m);
    const ctxCap = buildCapabilitiesFromCatalogEntry(AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m);
    const hiriseCap = buildCapabilitiesFromCatalogEntry(AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm);
    const molaCap = buildCapabilitiesFromCatalogEntry(AUTHORITATIVE_MARS_IMAGERY_CATALOG.mola_hrsc_shaded_200m);

    // 1. Global Mars Basemap: NASA Mars Trek Viking MDIM 2.1 Color Mosaic (232 m/px)
    const wmtsVikingGlobal = new TileLayer({
      source: createOpenLayersWMTSSource(vikingCap, recordTileOk('viking'), recordTileErr('viking')),
      zIndex: 0,
      opacity: 1.0,
      preload: 2,
    });

    // 1b. Global Terrain Relief Basemap: USGS MOLA-HRSC Color Hillshade (200 m/px)
    const wmtsMolaTerrain = new TileLayer({
      source: createOpenLayersWMTSSource(molaCap, recordTileOk('mola'), recordTileErr('mola')),
      zIndex: 1,
      visible: false,
      opacity: 0.78,
      preload: 1,
    });

    // 2. Regional Jezero Basemap: USGS Mars 2020 TRN CTX Orthomosaic (6 m/px, DOI: 10.5066/P9GV1ND3)
    const wmtsCtxRegional = new TileLayer({
      className: 'ol-layer-ctx',
      source: createOpenLayersWMTSSource(ctxCap, recordTileOk('ctx'), recordTileErr('ctx')),
      extent: ctxExtent,
      maxResolution: 800 / M_PER_DEG,
      zIndex: 2,
      opacity: 1.0,
      preload: 2,
    });

    // 3. High-Resolution Jezero Basemap: USGS Mars 2020 TRN HiRISE Orthomosaic (0.25 m/px, DOI: 10.5066/P9QJDP48)
    const wmtsHiriseLocal = new TileLayer({
      className: 'ol-layer-hirise',
      source: createOpenLayersWMTSSource(hiriseCap, recordTileOk('hirise'), recordTileErr('hirise')),
      extent: hiriseOrthoExtent,
      maxResolution: 25 / M_PER_DEG,
      zIndex: 3,
      opacity: 1.0,
      preload: 1,
    });

    // Async verify live GetCapabilities XML documents and bind verified WMTS sources
    let cancelled = false;
    Promise.all([
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m),
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m),
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm),
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.mola_hrsc_shaded_200m),
    ]).then(([vParsed, cParsed, hParsed, mParsed]) => {
      if (cancelled) return;
      if (vParsed?.tileMatrices?.length) {
        wmtsVikingGlobal.setSource(createOpenLayersWMTSSource(vParsed, recordTileOk('viking'), recordTileErr('viking')));
      }
      if (cParsed?.tileMatrices?.length) {
        wmtsCtxRegional.setSource(createOpenLayersWMTSSource(cParsed, recordTileOk('ctx'), recordTileErr('ctx')));
      }
      if (hParsed?.tileMatrices?.length) {
        wmtsHiriseLocal.setSource(createOpenLayersWMTSSource(hParsed, recordTileOk('hirise'), recordTileErr('hirise')));
      }
      if (mParsed?.tileMatrices?.length) {
        wmtsMolaTerrain.setSource(createOpenLayersWMTSSource(mParsed, recordTileOk('mola'), recordTileErr('mola')));
      }
      setWmtsStats(s => ({
        ...s,
        byLayer: {
          viking: { ...s.byLayer.viking, capabilitiesVerified: Boolean(vParsed?.tileMatrices?.length) },
          ctx: { ...s.byLayer.ctx, capabilitiesVerified: Boolean(cParsed?.tileMatrices?.length) },
          hirise: { ...s.byLayer.hirise, capabilitiesVerified: Boolean(hParsed?.tileMatrices?.length) },
          mola: { ...s.byLayer.mola, capabilitiesVerified: Boolean(mParsed?.tileMatrices?.length) },
        },
      }));
    }).catch(err => {
      console.warn('WMTS GetCapabilities async check warning:', err);
    });

    // Separate Terrain Analysis Overlays (populated dynamically once active DEM loads)
    const relief = new ImageLayer({ zIndex: 4, visible: false, opacity: 0.85 });
    const hillshade = new ImageLayer({ opacity: 0.65, zIndex: 5, visible: false });
    const slopeLayer = new ImageLayer({ opacity: 0.72, zIndex: 6, visible: false });
    const roughnessLayer = new ImageLayer({ opacity: 0.72, zIndex: 7, visible: false });
    const themisLayer = new ImageLayer({ zIndex: 10, visible: false });
    const footprintsLayer = new VectorLayer({ source: new VectorSource(), zIndex: 11 });
    const groundTracksLayer = new VectorLayer({ source: new VectorSource(), zIndex: 12 });
    const hiriseBoundary = new VectorLayer({ source: new VectorSource(), zIndex: 13 });
    const demBoundaryLayer = new VectorLayer({ source: new VectorSource(), zIndex: 13.5 });
    const returnZoneLayer = new ImageLayer({ zIndex: 13.8, visible: false, opacity: 0.78 });
    const rescueZoneLayer = new ImageLayer({ zIndex: 13.9, visible: false, opacity: 0.78 });
    const risk = new ImageLayer({ zIndex: 14, visible: false });
    const data = new ImageLayer({ zIndex: 14.5, visible: false });
    const historyLayer = new VectorLayer({ source: new VectorSource(), zIndex: 15 });
    const curiosityLayer = new VectorLayer({ source: new VectorSource(), zIndex: 16 });
    const historyPins = new VectorLayer({ source: new VectorSource(), zIndex: 17 });
    const scienceTargetsLayer = new VectorLayer({ source: new VectorSource(), zIndex: 19 });
    const routes = new VectorLayer({ source: new VectorSource(), zIndex: 20 });
    const pins = new VectorLayer({ source: new VectorSource(), zIndex: 22 });
    const turnaroundLayer = new VectorLayer({ source: new VectorSource(), zIndex: 23 });
    const hoverLayer = new VectorLayer({ source: new VectorSource(), zIndex: 24 });
    const roverReplayLayer = new VectorLayer({ source: new VectorSource(), zIndex: 25 });
    const spacecraftLayer = new VectorLayer({ source: new VectorSource(), zIndex: 26 });
    const playbackLayer = new VectorLayer({ source: new VectorSource(), zIndex: 27 });

    // Populate DEM & Imagery Coverage Boundaries (visible strictly when coverage toggle is active)
    const demPoly = new Feature(new Polygon([[
      [jezeroExtent[0], jezeroExtent[1]],
      [jezeroExtent[2], jezeroExtent[1]],
      [jezeroExtent[2], jezeroExtent[3]],
      [jezeroExtent[0], jezeroExtent[3]],
      [jezeroExtent[0], jezeroExtent[1]],
    ]]));
    demPoly.setStyle((feature, resolution) => {
      if (!callbacks.current.props.coverage) return null;
      const resM = resolution * M_PER_DEG;
      return new Style({
        stroke: new Stroke({ color: '#5cffb088', width: 1.6, lineDash: [8, 6] }),
        fill: new Fill({ color: resM > 200 ? 'rgba(92,255,176,0.04)' : 'rgba(0,0,0,0)' }),
        text: new Text({
          text: resM > 400 ? 'Jezero Regional DEM (200 m MOLA-HRSC)' : 'USGS MOLA-HRSC Regional DEM Coverage (200 m/px · DOI: 10.5066/P907276M)',
          font: '600 11px Inter, sans-serif',
          offsetY: -12,
          fill: new Fill({ color: '#a3f4ca' }),
          stroke: new Stroke({ color: '#081210', width: 3 }),
        }),
      });
    });
    demBoundaryLayer.getSource().addFeature(demPoly);

    const map = new Map({
      target: node.current,
      layers: [
        wmtsVikingGlobal,
        wmtsMolaTerrain,
        wmtsCtxRegional,
        wmtsHiriseLocal,
        relief,
        hillshade,
        slopeLayer,
        roughnessLayer,
        hiriseBoundary,
        demBoundaryLayer,
        returnZoneLayer,
        rescueZoneLayer,
        themisLayer,
        footprintsLayer,
        groundTracksLayer,
        data,
        risk,
        historyLayer,
        curiosityLayer,
        historyPins,
        scienceTargetsLayer,
        routes,
        pins,
        turnaroundLayer,
        hoverLayer,
        roverReplayLayer,
        spacecraftLayer,
        playbackLayer,
      ],
      view: new View({
        projection: marsGeoProj,
        center: [77.425, 18.408],
        resolution: 18 / M_PER_DEG,
        constrainOnlyCenter: true,
        minResolution: 0.25 / M_PER_DEG,
        maxResolution: 28000 / M_PER_DEG,
        extent: globalExtent,
      }),
      controls: [new ScaleLine({ units: 'metric' })],
    });
    if (typeof window !== 'undefined') window.__ol_map = map;

    // Multi-resolution planetary GIS edge feathering: softly feather rectangular boundaries of high-res insets into basemap
    const applyEdgeFeathering = (layer, extent, featherPx = 54) => {
      layer.on('postrender', evt => {
        const ctx = evt.context;
        if (!ctx) return;
        const [minLon, minLat, maxLon, maxLat] = extent;
        const tl = map.getPixelFromCoordinate([minLon, maxLat]);
        const br = map.getPixelFromCoordinate([maxLon, minLat]);
        const grads = calculateEdgeFeatherGradients({ tl, br }, featherPx);
        if (!grads) return;

        ctx.save();
        ctx.globalCompositeOperation = 'destination-out';

        // Top feather
        const gradT = ctx.createLinearGradient(grads.top.x0, grads.top.y0, grads.top.x1, grads.top.y1);
        gradT.addColorStop(0, 'rgba(0,0,0,1)');
        gradT.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gradT;
        ctx.fillRect(...grads.top.fillRect);

        // Bottom feather
        const gradB = ctx.createLinearGradient(grads.bottom.x0, grads.bottom.y0, grads.bottom.x1, grads.bottom.y1);
        gradB.addColorStop(0, 'rgba(0,0,0,1)');
        gradB.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gradB;
        ctx.fillRect(...grads.bottom.fillRect);

        // Left feather
        const gradL = ctx.createLinearGradient(grads.left.x0, grads.left.y0, grads.left.x1, grads.left.y1);
        gradL.addColorStop(0, 'rgba(0,0,0,1)');
        gradL.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gradL;
        ctx.fillRect(...grads.left.fillRect);

        // Right feather
        const gradR = ctx.createLinearGradient(grads.right.x0, grads.right.y0, grads.right.x1, grads.right.y1);
        gradR.addColorStop(0, 'rgba(0,0,0,1)');
        gradR.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = gradR;
        ctx.fillRect(...grads.right.fillRect);

        ctx.restore();
      });
    };

    applyEdgeFeathering(wmtsCtxRegional, ctxExtent, 64);
    applyEdgeFeathering(wmtsHiriseLocal, hiriseOrthoExtent, 48);

    const element = document.createElement('div');
    element.className = 'route-midpoint glass';
    const label = new Overlay({ element, positioning: 'bottom-center', offset: [0, -20], stopEvent: false });
    map.addOverlay(label);
    midLabel.current = label;

    layers.current = {
      projection: marsGeoProj,
      extent: jezeroExtent,
      globalExtent,
      ctxExtent,
      hiriseOrthoExtent,
      wmtsVikingGlobal,
      wmtsMolaTerrain,
      wmtsCtxRegional,
      wmtsHiriseLocal,
      relief,
      hillshade,
      slopeLayer,
      roughnessLayer,
      hiriseBoundary,
      demBoundaryLayer,
      returnZoneLayer,
      rescueZoneLayer,
      themisLayer,
      footprintsLayer,
      groundTracksLayer,
      risk,
      data,
      historyLayer,
      curiosityLayer,
      historyPins,
      scienceTargetsLayer,
      routes,
      pins,
      turnaroundLayer,
      hoverLayer,
      roverReplayLayer,
      spacecraftLayer,
      playbackLayer,
      recordTileOk,
      recordTileErr,
    };
    mapRef.current = map;

    const syncViewState = () => {
      const v = map.getView();
      const resM = (v.getResolution() || (18 / M_PER_DEG)) * M_PER_DEG;
      const c = v.getCenter();
      setViewState({
        resolution: resM,
        centerLon: c ? c[0] : 77.425,
        centerLat: c ? c[1] : 18.408,
      });
    };
    map.getView().on('change:resolution', syncViewState);
    map.getView().on('change:center', syncViewState);
    syncViewState();

    map.on('pointermove', e => {
      if (e.dragging) return;
      const [lon, lat] = e.coordinate;
      if (Number.isFinite(lon) && Number.isFinite(lat)) {
        const b = terrainRef.current?.b || JEZERO_VALIDATED_DEM_BOUNDS;
        const hb = JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS;
        const ho = JEZERO_HIRISE_ORTHO_BOUNDS;
        const cb = JEZERO_CTX_ORTHO_BOUNDS;
        setCursorCoord({
          lon,
          lat,
          inJezeroDem: lon >= b[0] && lon <= b[2] && lat >= b[1] && lat <= b[3],
          inHiriseDtm: lon >= hb[0] && lon <= hb[2] && lat >= hb[1] && lat <= hb[3],
          inHiriseOrtho: lon >= ho[0] && lon <= ho[2] && lat >= ho[1] && lat <= ho[3],
          inCtxOrtho: lon >= cb[0] && lon <= cb[2] && lat >= cb[1] && lat <= cb[3],
        });
      }
    });

    map.on('singleclick', e => {
      interact();
      let routeId = null, recorded = null, obsId = null, scId = null;
      map.forEachFeatureAtPixel(e.pixel, f => {
        if (f.get('observationId')) { obsId = f.get('observationId'); return true; }
        if (f.get('spacecraftId')) { scId = f.get('spacecraftId'); return true; }
        if (f.get('waypoint')) { recorded = f.get('waypoint'); return true; }
        if (f.get('driveRecord')) { recorded = f.get('driveRecord'); return true; }
        if (f.get('routeId')) { routeId = f.get('routeId'); return true; }
      }, { hitTolerance: 6 });
      if (obsId) { callbacks.current.props.onSelectObservation?.(obsId); return; }
      if (scId) { callbacks.current.props.onSelectSpacecraft?.(scId); return; }
      if (recorded && !callbacks.current.pick) {
        if (recorded.geometry.type === 'Point') callbacks.current.props.onWaypoint?.(recorded);
        else callbacks.current.props.onWaypoint?.(callbacks.current.props.waypoints.findLast(w => w.properties.sol <= recorded.properties.sol));
        return;
      }
      if (routeId && !callbacks.current.pick) { callbacks.current.onSelectRoute(routeId); return; }
      const pt = { lon: e.coordinate[0], lat: e.coordinate[1] };
      if (callbacks.current.pick) {
        callbacks.current.onPin(pt);
        return;
      }

      // Click-to-inspect displays: Elevation at point, Active imagery layer, Terrain slope / hazard rating, Mars coordinates
      const t = terrainRef.current;
      const inDemBounds = Boolean(t && t.b && pt.lon >= t.b[0] && pt.lon <= t.b[2] && pt.lat >= t.b[1] && pt.lat <= t.b[3]);
      let elev = null, slope = null, hazard = inDemBounds ? 'Unobserved / NoData' : 'Outside local DEM bounds';
      let inspectError = null;
      if (inDemBounds) {
        try {
          const idx = toIndex(t, pt);
          const ev = t.e[idx];
          const sl = t.slope[idx];
          elev = Number.isFinite(ev) ? ev : null;
          slope = Number.isFinite(sl) ? sl : null;
          if (slope === null && elev === null) hazard = 'Unobserved / NoData';
          else if (slope === null) hazard = 'Slope Unavailable (DEM edge)';
          else if (slope > 20) hazard = 'Hazardous (>20° Steep)';
          else if (slope > 12) hazard = 'Moderate Slope (12°–20°)';
          else hazard = 'Nominal Terrain (<12°)';
        } catch (err) {
          console.error('Click-to-inspect DEM sample error:', err);
          inspectError = err?.message || 'DEM sampling error';
          hazard = 'Inspection error';
        }
      }

      const cp = callbacks.current.props;
      const baseMode = cp.base || 'auto';
      const isAutoMode = baseMode === 'auto' || baseMode === 'imagery';
      const isHiriseMode = baseMode === 'hirise';
      const isCtxMode = baseMode === 'ctx' || baseMode === 'ctx_global';
      const curResM = (map.getView().getResolution() || (18 / M_PER_DEG)) * M_PER_DEG;
      const inH = pt.lon >= JEZERO_HIRISE_ORTHO_BOUNDS[0] && pt.lon <= JEZERO_HIRISE_ORTHO_BOUNDS[2] && pt.lat >= JEZERO_HIRISE_ORTHO_BOUNDS[1] && pt.lat <= JEZERO_HIRISE_ORTHO_BOUNDS[3];
      const inC = pt.lon >= JEZERO_CTX_ORTHO_BOUNDS[0] && pt.lon <= JEZERO_CTX_ORTHO_BOUNDS[2] && pt.lat >= JEZERO_CTX_ORTHO_BOUNDS[1] && pt.lat <= JEZERO_CTX_ORTHO_BOUNDS[3];

      let imagery = 'NASA Viking MDIM 2.1 Global Mosaic (232 m/px)';
      if (cp.showHirise !== false && (isAutoMode || isHiriseMode) && inH && curResM <= (isHiriseMode ? 2500 : 35)) {
        imagery = 'USGS HiRISE Orthomosaic (0.25 m/px · DOI: 10.5066/P9QJDP48)';
      } else if (cp.showCtx !== false && (isAutoMode || isCtxMode || isHiriseMode) && inC && curResM <= (isCtxMode ? 8000 : 1800)) {
        imagery = 'USGS CTX Orthomosaic (6 m/px · DOI: 10.5066/P9GV1ND3)';
      } else if (cp.showMolaTerrain) {
        imagery = 'USGS MOLA-HRSC Color Hillshade (200 m/px · DOI: 10.5066/P9P7W018)';
      } else if (cp.showViking === false) {
        imagery = 'No basemap imagery enabled';
      }

      setInspectPopup({
        lon: pt.lon,
        lat: pt.lat,
        elev,
        slope,
        hazard,
        inDemBounds,
        inspectError,
        imagery,
      });
    });
    map.on('pointerdrag', () => {
      interact();
      if (followRoverRef.current) setFollowRover(false);
    });
    map.on('movestart', () => { if (map.getView().getInteracting()) interact(); });
    const observer = new ResizeObserver(() => map.updateSize());
    observer.observe(node.current);
    let frame, last = 0;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    function animate(t) {
      frame = requestAnimationFrame(animate);
      if (document.hidden || reduced || t - last < 42) return;
      last = t;
      if (callbacks.current.props.showRoute !== false) { routes.changed(); pins.changed(); }
    }
    frame = requestAnimationFrame(animate);
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      map.setTarget(null);
      mapRef.current = null;
    };
  }, []);

  // Multi-resolution satellite imagery & terrain analysis overlay synchronization
  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current;
    const isAuto = base === 'auto' || base === 'imagery';
    const isHirise = base === 'hirise';
    const isCtx = base === 'ctx' || base === 'ctx_global';
    const isViking = base === 'viking' || base === 'global';
    const isRelief = base === 'relief';

    // 1. Global Viking MDIM 2.1 (232 m/px)
    const vikingVisible = Boolean(showViking);
    l.wmtsVikingGlobal?.setVisible(vikingVisible);
    l.wmtsVikingGlobal?.setOpacity(effVikingOpacity);

    // 1b. Global MOLA-HRSC 200 m Color Hillshade
    const molaVisible = Boolean(showMolaTerrain || isRelief);
    l.wmtsMolaTerrain?.setVisible(molaVisible);
    l.wmtsMolaTerrain?.setOpacity(molaOpacity);

    // 2. Regional CTX (6 m/px)
    const ctxVisible = Boolean(showCtx && (isAuto || isCtx || isHirise || !isViking));
    l.wmtsCtxRegional?.setVisible(ctxVisible && !isViking);
    l.wmtsCtxRegional?.setMaxResolution((isCtx ? 8000 : 800) / M_PER_DEG);
    l.wmtsCtxRegional?.setOpacity(effCtxOpacity);

    // 3. Local HiRISE (0.25 m/px)
    const hiriseVisible = Boolean(showHirise && (isAuto || isHirise));
    l.wmtsHiriseLocal?.setVisible(hiriseVisible && !isViking && !isCtx);
    l.wmtsHiriseLocal?.setMaxResolution((isHirise ? 2500 : 25) / M_PER_DEG);
    l.wmtsHiriseLocal?.setOpacity(effHiriseOpacity);

    if (!effectiveTerrain) return;

    // 4. Separate Terrain Overlays derived from active DEM (1 m HiRISE DTM or 200 m MOLA-HRSC DEM)
    const demExtent = effectiveTerrain.b;
    l.relief.setVisible(isRelief);
    l.relief.setOpacity(terrainOpacity);
    if (isRelief) {
      l.relief.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'relief'), imageExtent: demExtent, projection: l.projection }));
    }

    const hillshadeVisible = Boolean(showHillshade || isRelief);
    l.hillshade.setVisible(hillshadeVisible);
    l.hillshade.setOpacity(terrainOpacity * 0.85);
    if (hillshadeVisible) {
      l.hillshade.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'hillshade'), imageExtent: demExtent, projection: l.projection }));
    }

    l.slopeLayer.setVisible(Boolean(showSlope));
    l.slopeLayer.setOpacity(terrainOpacity);
    if (showSlope) {
      l.slopeLayer.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'slope', maxSlope, maxRough), imageExtent: demExtent, projection: l.projection, interpolate: true }));
    }

    l.roughnessLayer.setVisible(Boolean(showRoughness));
    l.roughnessLayer.setOpacity(terrainOpacity);
    if (showRoughness) {
      l.roughnessLayer.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'roughness', maxSlope, maxRough), imageExtent: demExtent, projection: l.projection, interpolate: true }));
    }

    if (showThemisOverlay) {
      l.themisLayer?.setSource(new ImageStatic({ url: buildThemisThermalCanvas(effectiveTerrain), imageExtent: demExtent, projection: l.projection, interpolate: true }));
    }
    l.themisLayer?.setVisible(Boolean(showThemisOverlay));
    l.risk.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'hazards', maxSlope, maxRough), imageExtent: demExtent, projection: l.projection, interpolate: true }));
    l.data.setSource(new ImageStatic({ url: rasterImage(effectiveTerrain, 'coverage'), imageExtent: demExtent, projection: l.projection }));
    l.risk.setVisible(Boolean(hazards));
    l.risk.setOpacity(terrainOpacity);
    l.data.setVisible(Boolean(coverage));
    l.data.setOpacity(terrainOpacity);
    l.demBoundaryLayer?.changed();

    // Update HiRISE & CTX coverage boundary vectors
    if (l.hiriseBoundary) {
      const src = l.hiriseBoundary.getSource();
      src.clear();
      if (coverage || isHirise) {
        const orthoE = JEZERO_HIRISE_ORTHO_BOUNDS;
        const fOrtho = new Feature(new Polygon([[
          [orthoE[0], orthoE[1]], [orthoE[2], orthoE[1]], [orthoE[2], orthoE[3]], [orthoE[0], orthoE[3]], [orthoE[0], orthoE[1]],
        ]]));
        fOrtho.setStyle(new Style({
          stroke: new Stroke({ color: '#64dfdf88', width: 1.5, lineDash: [6, 6] }),
          text: new Text({
            text: 'USGS HiRISE 0.25 m/px Orthomosaic Footprint (DOI: 10.5066/P9QJDP48)',
            font: '600 11px Inter, sans-serif',
            offsetY: -10,
            fill: new Fill({ color: '#a0f0f0' }),
            stroke: new Stroke({ color: '#0a1412', width: 3 }),
          }),
        }));
        src.addFeature(fOrtho);

        const dtmE = JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS;
        const fDtm = new Feature(new Polygon([[
          [dtmE[0], dtmE[1]], [dtmE[2], dtmE[1]], [dtmE[2], dtmE[3]], [dtmE[0], dtmE[3]], [dtmE[0], dtmE[1]],
        ]]));
        fDtm.setStyle(new Style({
          stroke: new Stroke({ color: '#5cffb0cc', width: 2.0, lineDash: [4, 4] }),
          fill: new Fill({ color: coverage ? 'rgba(92,255,176,0.08)' : 'rgba(0,0,0,0)' }),
          text: new Text({
            text: 'USGS HiRISE 1 m/px Validated DTM Routing Corridor (DOI: 10.5066/P9REJ9JN)',
            font: '600 11px Inter, sans-serif',
            offsetY: 14,
            fill: new Fill({ color: '#9becbf' }),
            stroke: new Stroke({ color: '#081210', width: 3 }),
          }),
        }));
        src.addFeature(fDtm);
        l.hiriseBoundary.setVisible(true);
      } else {
        l.hiriseBoundary.setVisible(false);
      }
    }
  }, [
    effectiveTerrain, base, hazards, coverage, showHillshade, showSlope, showRoughness,
    showViking, showCtx, showHirise, showMolaTerrain,
    effVikingOpacity, effCtxOpacity, effHiriseOpacity, molaOpacity, terrainOpacity,
    maxSlope, maxRough, live, showThemisOverlay,
  ]);

  // Science Target markers
  useEffect(() => {
    if (!mapRef.current || !layers.current.scienceTargetsLayer) return;
    const l = layers.current, src = l.scienceTargetsLayer.getSource();
    src.clear();
    l.scienceTargetsLayer.setVisible(Boolean(showScienceTargets));
    if (!showScienceTargets || !scienceTargets?.length) return;
    scienceTargets.forEach(tgt => {
      if (!Number.isFinite(tgt.lon) || !Number.isFinite(tgt.lat)) return;
      const f = new Feature({ geometry: new Point([tgt.lon, tgt.lat]), scienceTarget: tgt });
      f.setStyle((feature, resolution) => {
        const resM = resolution * M_PER_DEG;
        return new Style({
          image: new CircleStyle({
            radius: resM > 400 ? 3.5 : 5.5,
            fill: new Fill({ color: '#ffd166' }),
            stroke: new Stroke({ color: '#141008', width: 1.8 }),
          }),
          text: resM > 400 ? undefined : new Text({
            text: `★ ${tgt.name} (${tgt.science_value_points} pts)`,
            font: '500 10px Inter, sans-serif',
            offsetY: 14,
            fill: new Fill({ color: '#ffe8a3' }),
            stroke: new Stroke({ color: '#0b1012', width: 3 }),
          }),
        });
      });
      src.addFeature(f);
    });
  }, [terrain, showScienceTargets, scienceTargets]);

  // Synchronized Rover Replay marker from Mars Time Machine
  useEffect(() => {
    if (!mapRef.current || !layers.current.roverReplayLayer) return;
    const l = layers.current, src = l.roverReplayLayer.getSource();
    src.clear();
    if (!roverReplayState || !roverReplayState.position_available || !roverReplayState.active_waypoint) return;
    const wp = roverReplayState.active_waypoint;
    if (!Number.isFinite(wp.lon) || !Number.isFinite(wp.lat)) return;
    const f = new Feature({ geometry: new Point([wp.lon, wp.lat]) });
    const statusLabel = roverReplayState.archive_status === 'EXACT_SOL_RECORD'
      ? `Sol ${wp.sol} (Exact)`
      : roverReplayState.archive_status === 'POST_ARCHIVE_CUTOFF'
        ? `Sol ${wp.sol} (Archive Cutoff)`
        : `Sol ${wp.sol} (Last Confirmed @ Sol ${roverReplayState.requested_sol})`;
    f.setStyle((feature, resolution) => {
      const resM = resolution * M_PER_DEG;
      return [
        new Style({ image: new CircleStyle({ radius: resM > 400 ? 10 : 16, stroke: new Stroke({ color: 'rgba(255,184,103,0.45)', width: 2, lineDash: [4, 4] }) }) }),
        new Style({
          image: new CircleStyle({ radius: resM > 400 ? 5 : 7.5, fill: new Fill({ color: '#ffb867' }), stroke: new Stroke({ color: '#181209', width: 2 }) }),
          text: resM > 400 ? undefined : new Text({
            text: `Perseverance Replay · ${statusLabel}`,
            font: '600 11px Inter, sans-serif',
            offsetY: -20,
            fill: new Fill({ color: '#ffe2b8' }),
            stroke: new Stroke({ color: '#0b1014', width: 3.5 }),
          }),
        }),
      ];
    });
    src.addFeature(f);
  }, [terrain, roverReplayState]);

  useEffect(() => {
    if (!mapRef.current) return;
    const src = layers.current.pins.getSource();
    src.clear();
    [[start, 'A'], [destination, 'B']].forEach(([p, label]) => {
      if (!Number.isFinite(Number(p.lon)) || !Number.isFinite(Number(p.lat))) return;
      const f = new Feature(new Point([Number(p.lon), Number(p.lat)]));
      f.setStyle(() => {
        if (!callbacks.current.props.showRoute && !callbacks.current.pick) return null;
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches, phase = reduced ? 0 : (performance.now() % 2600) / 2600;
        return [
          new Style({ image: new CircleStyle({ radius: 15 + phase * 15, stroke: new Stroke({ color: `rgba(92,255,176,${(1 - phase) * 0.25})`, width: 1 }) }) }),
          new Style({
            image: new CircleStyle({ radius: 12, fill: new Fill({ color: '#0a1b15ed' }), stroke: new Stroke({ color: '#9becbf', width: 1.5 }) }),
            text: new Text({ text: label, font: '600 12px Inter, sans-serif', fill: new Fill({ color: '#d7f6e5' }) }),
          }),
        ];
      });
      src.addFeature(f);
    });
  }, [terrain, start, destination]);

  useEffect(() => {
    if (!mapRef.current) return;
    const src = layers.current.routes.getSource();
    src.clear();
    if (!response) return;
    [...response.routes].reverse().forEach(r => {
      const primary = r.score_rank === 1, line = new LineString(r.geometry.coordinates.map(c => [c[0], c[1]])), f = new Feature({ geometry: line, routeId: r.route_id });
      const flow = new Stroke({ color: '#d6ffe7bb', width: 1.5, lineDash: [8, 22] });
      const styles = primary
        ? [new Style({ stroke: new Stroke({ color: '#000000aa', width: 10 }) }), new Style({ stroke: new Stroke({ color: '#5cffb04d', width: 8 }) }), new Style({ stroke: new Stroke({ color: '#5cffb0', width: 5 }) }), new Style({ stroke: flow })]
        : [new Style({ stroke: new Stroke({ color: '#0c171dcc', width: 4 }) }), new Style({ stroke: new Stroke({ color: '#b7c5c580', width: 2, lineDash: [6, 5] }) })];
      f.setStyle(() => {
        const p = callbacks.current.props;
        if (!p.showRoute) return null;
        if (!primary && !p.showAlternatives && r.route_id !== p.selected && r.route_id !== p.hoveredRoute) return null;
        flow.setLineDashOffset(matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : -performance.now() / 60);
        return styles;
      });
      src.addFeature(f);
      if (live && hazards) {
        for (const s of r.evidence_passport?.segments || []) {
          if (s.slope_deg > 12 || s.roughness > 0.5) {
            const a = new Feature(new LineString([[s.from_coord.lon, s.from_coord.lat], [s.to_coord.lon, s.to_coord.lat]]));
            a.setStyle(new Style({ stroke: new Stroke({ color: '#c38a6c77', width: 7 }) }));
            src.addFeature(a);
          }
        }
      }
    });
  }, [terrain, response, live, hazards, coverage, backendStatus]);

  useEffect(() => {
    if (!mapRef.current) return;
    layers.current.routes.changed();
    layers.current.pins.changed();
    const route = response?.routes.find(r => r.route_id === selected) || response?.routes[0];
    if (route && showRoute && !view3d) {
      const line = new LineString(route.geometry.coordinates.map(c => [c[0], c[1]]));
      midLabel.current.getElement().textContent = (route.summary.total_distance_meters / 1000).toFixed(2) + ' km · ' + (Number.isFinite(route.summary.estimated_duration_hours) ? route.summary.estimated_duration_hours.toFixed(1) + ' h' : 'ETA unavailable');
      midLabel.current.setPosition(line.getCoordinateAt(0.5));
    } else midLabel.current?.setPosition(undefined);
  }, [terrain, response, selected, showRoute, showAlternatives, hoveredRoute, view3d]);

  const activeRoute = response?.routes?.find(r => r.route_id === selected) || response?.routes?.[0] || (response?.geometry ? response : null);

  // Stage 1: Habitat Reachable Return-Time Zone, Rescue-Time Map & Hard Turnaround Marker
  useEffect(() => {
    const l = layers.current;
    if (!mapRef.current) return;

    const rz = response?.return_zone;
    if (showRoute && showReachableZone && rz?.minutes_grid?.length && rz?.bounds?.length === 4) {
      l.returnZoneLayer?.setSource(
        new ImageStatic({
          url: buildTimeOverlayCanvas(rz, 'return'),
          imageExtent: rz.bounds,
          projection: l.projection,
          interpolate: false,
        })
      );
      l.returnZoneLayer?.setVisible(true);
    } else {
      l.returnZoneLayer?.setVisible(false);
    }

    const rsz = response?.rescue_zone;
    if (showRoute && showRescueMap && rsz?.minutes_grid?.length && rsz?.bounds?.length === 4) {
      l.rescueZoneLayer?.setSource(
        new ImageStatic({
          url: buildTimeOverlayCanvas(rsz, 'rescue'),
          imageExtent: rsz.bounds,
          projection: l.projection,
          interpolate: false,
        })
      );
      l.rescueZoneLayer?.setVisible(true);
    } else {
      l.rescueZoneLayer?.setVisible(false);
    }

    const turnSrc = l.turnaroundLayer?.getSource();
    if (turnSrc) {
      turnSrc.clear();
      const ta = activeRoute?.turnaround;
      if (showRoute && ta?.turnaround_coord && Number.isFinite(ta.turnaround_coord[0]) && Number.isFinite(ta.turnaround_coord[1])) {
        const tf = new Feature({
          geometry: new Point([ta.turnaround_coord[0], ta.turnaround_coord[1]]),
          turnaround: ta,
        });
        const labelTxt = ta.feasible_before_sunset
          ? `Turnaround · ${ta.turnaround_ltst_hms || ta.turnaround_utc}`
          : `No Daylight Window · ${ta.limiting_constraint || 'dark'}`;
        tf.setStyle(
          new Style({
            image: new CircleStyle({
              radius: 9,
              fill: new Fill({ color: ta.feasible_before_sunset ? '#ffb867' : '#ff6b6b' }),
              stroke: new Stroke({ color: '#14110b', width: 2.5 }),
            }),
            text: new Text({
              text: labelTxt,
              font: '600 11px Inter, sans-serif',
              offsetY: 22,
              fill: new Fill({ color: ta.feasible_before_sunset ? '#ffe3b3' : '#ffb8b8' }),
              stroke: new Stroke({ color: '#090d11', width: 3.5 }),
            }),
          })
        );
        turnSrc.addFeature(tf);
      }
    }
  }, [response, activeRoute, showRoute, showReachableZone, showRescueMap]);

  const routeProfile = useMemo(() => {
    if (!activeRoute?.geometry?.coordinates || activeRoute.geometry.coordinates.length < 2) return null;
    const coords = activeRoute.geometry.coordinates;
    const cumDists = [0];
    for (let i = 1; i < coords.length; i++) {
      const p1 = coords[i - 1];
      const p2 = coords[i];
      const dLon = ((p2[0] - p1[0]) * Math.PI) / 180;
      const dLat = ((p2[1] - p1[1]) * Math.PI) / 180;
      const latM = (((p1[1] + p2[1]) / 2) * Math.PI) / 180;
      const dx = dLon * 3396190 * Math.cos(latM);
      const dy = dLat * 3396190;
      cumDists.push(cumDists[i - 1] + Math.hypot(dx, dy));
    }
    const totalDist = cumDists[cumDists.length - 1];
    return { coords, cumDists, totalDist: Math.max(1, totalDist) };
  }, [activeRoute]);

  const currentPlayback = useMemo(() => {
    if (!routeProfile) return null;
    const { coords, cumDists, totalDist } = routeProfile;
    const targetDist = Math.max(0, Math.min(totalDist, playbackProgress * totalDist));

    let k = 0;
    while (k < cumDists.length - 2 && cumDists[k + 1] < targetDist) {
      k++;
    }
    const segStartDist = cumDists[k];
    const segEndDist = cumDists[k + 1] || segStartDist + 1;
    const frac = Math.max(0, Math.min(1, (targetDist - segStartDist) / (segEndDist - segStartDist)));

    const p1 = coords[k];
    const p2 = coords[k + 1] || p1;
    const curLon = p1[0] + frac * (p2[0] - p1[0]);
    const curLat = p1[1] + frac * (p2[1] - p1[1]);
    const curEle = p1[2] !== undefined && p2[2] !== undefined ? p1[2] + frac * (p2[2] - p1[2]) : null;

    const dX = (p2[0] - p1[0]) * Math.cos((((p1[1] + p2[1]) / 2) * Math.PI) / 180);
    const dY = p2[1] - p1[1];
    const headingDeg = (Math.atan2(dX, dY) * (180 / Math.PI) + 360) % 360;

    const traveled = coords.slice(0, k + 1).map(c => [c[0], c[1]]);
    traveled.push([curLon, curLat]);

    const remaining = [[curLon, curLat], ...coords.slice(k + 1).map(c => [c[0], c[1]])];

    const segObj = activeRoute?.segments?.[k];
    const slope = segObj?.slope_deg ?? activeRoute?.summary?.average_slope_deg ?? 3.5;

    return {
      curLon,
      curLat,
      curEle,
      headingDeg,
      headingRad: (headingDeg * Math.PI) / 180,
      traveled,
      remaining,
      distTraveled: targetDist,
      distRemaining: Math.max(0, totalDist - targetDist),
      totalDist,
      slope,
      segmentIndex: k,
    };
  }, [routeProfile, playbackProgress, activeRoute]);

  // Playback animation step
  useEffect(() => {
    if (!isPlaying || !routeProfile || routeProfile.totalDist <= 0) return;
    let lastTime = performance.now();
    let animId;

    const step = now => {
      const dt = (now - lastTime) / 1000;
      lastTime = now;

      const baseDurationSec = 18;
      const progressDelta = (dt / baseDurationSec) * playbackSpeed;

      setPlaybackProgress(prev => {
        const next = prev + progressDelta;
        if (next >= 1.0) {
          setIsPlaying(false);
          return 1.0;
        }
        return next;
      });

      animId = requestAnimationFrame(step);
    };

    animId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(animId);
  }, [isPlaying, routeProfile, playbackSpeed]);

  // Update OpenLayers playbackLayer with animated progressive reveal & rover heading
  useEffect(() => {
    if (!mapRef.current || !layers.current.playbackLayer) return;
    const pl = layers.current.playbackLayer;
    const src = pl.getSource();
    src.clear();
    pl.setVisible(!historyMode && Boolean(currentPlayback));
    if (historyMode || !currentPlayback) return;

    // 1. Traveled progressive reveal path
    const traveledLine = new LineString(currentPlayback.traveled.map(c => [c[0], c[1]]));
    const traveledFeature = new Feature({ geometry: traveledLine });
    traveledFeature.setStyle([
      new Style({ stroke: new Stroke({ color: '#000000dd', width: 9, lineCap: 'round', lineJoin: 'round' }) }),
      new Style({ stroke: new Stroke({ color: '#5cffb044', width: 8, lineCap: 'round', lineJoin: 'round' }) }),
      new Style({ stroke: new Stroke({ color: '#5cffb0', width: 4.5, lineCap: 'round', lineJoin: 'round' }) }),
    ]);
    src.addFeature(traveledFeature);

    // 2. Remaining path (dashed)
    if (currentPlayback.remaining.length > 1) {
      const remainingLine = new LineString(currentPlayback.remaining.map(c => [c[0], c[1]]));
      const remainingFeature = new Feature({ geometry: remainingLine });
      remainingFeature.setStyle(
        new Style({
          stroke: new Stroke({ color: 'rgba(92, 255, 176, 0.35)', width: 2.2, lineDash: [6, 6] }),
        })
      );
      src.addFeature(remainingFeature);
    }

    // 3. Rover Marker with directional heading & animated pulse
    const roverPt = new Point([currentPlayback.curLon, currentPlayback.curLat]);
    const roverFeature = new Feature({ geometry: roverPt });
    roverFeature.setStyle(() => {
      const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
      const phase = reduced ? 0 : (performance.now() % 1600) / 1600;
      return [
        new Style({
          image: new CircleStyle({
            radius: 12 + phase * 16,
            stroke: new Stroke({ color: `rgba(92, 255, 176, ${(1 - phase) * 0.45})`, width: 1.8 }),
          }),
        }),
        new Style({
          image: new CircleStyle({
            radius: 11,
            fill: new Fill({ color: '#081713f0' }),
            stroke: new Stroke({ color: '#5cffb0', width: 2 }),
          }),
        }),
        new Style({
          image: new RegularShape({
            points: 3,
            radius: 7,
            rotation: currentPlayback.headingRad,
            rotateWithView: true,
            fill: new Fill({ color: '#5cffb0' }),
            stroke: new Stroke({ color: '#091512', width: 1 }),
          }),
        }),
        new Style({
          text: new Text({
            text: `Perseverance · ${Math.round(currentPlayback.distTraveled)} m (${Math.round(currentPlayback.headingDeg)}°)`,
            font: '600 11px Inter, sans-serif',
            offsetY: -22,
            fill: new Fill({ color: '#5cffb0' }),
            stroke: new Stroke({ color: '#060f0d', width: 3.5 }),
          }),
        }),
      ];
    });
    src.addFeature(roverFeature);

    if (followRoverRef.current && isPlaying) {
      mapRef.current.getView().setCenter([currentPlayback.curLon, currentPlayback.curLat]);
    }
  }, [currentPlayback, historyMode, isPlaying]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, source = l.historyLayer.getSource(), pins = l.historyPins.getSource();
    source.clear();
    pins.clear();
    l.historyLayer.setVisible(showHistory);
    l.historyPins.setVisible(showHistory && showWaypoints);
    for (const drive of drives) {
      const f = new Feature({ geometry: new LineString(drive.geometry.coordinates.map(c => [c[0], c[1]])), driveRecord: drive });
      f.setStyle([new Style({ stroke: new Stroke({ color: '#101318ed', width: 8, lineCap: 'round', lineJoin: 'round' }) }), new Style({ stroke: new Stroke({ color: '#ffb867', width: 4, lineCap: 'round', lineJoin: 'round' }) }), new Style({ stroke: new Stroke({ color: '#ffe1aa', width: 1 }) })]);
      source.addFeature(f);
    }
    waypoints.forEach((w, i) => {
      const latest = i === waypoints.length - 1, chosen = w === waypoint, c = w.geometry.coordinates, f = new Feature({ geometry: new Point([c[0], c[1]]), waypoint: w });
      f.setStyle((feature, resolution) => {
        const resM = resolution * M_PER_DEG;
        const ring = latest || chosen || i % 25 === 0 || resM < 2;
        return [
          new Style({ image: new CircleStyle({ radius: latest ? 7 : chosen ? 6 : 2.5, fill: new Fill({ color: latest ? '#87f1ee' : chosen ? '#f6a7f3' : '#c982d9' }), stroke: new Stroke({ color: '#18151e', width: 1.5 }) }) }),
          ...(ring ? [new Style({ image: new CircleStyle({ radius: latest ? 15 : chosen ? 20 : 10, stroke: new Stroke({ color: latest ? '#8bf3eeaa' : '#d38ce4aa', width: 1.5 }) }), text: latest || chosen ? new Text({ text: 'Sol ' + w.properties.sol, font: '500 12px Inter, sans-serif', offsetY: -24, fill: new Fill({ color: '#f7e5fd' }), stroke: new Stroke({ color: '#10151a', width: 4 }) }) : undefined })] : []),
        ];
      });
      pins.addFeature(f);
    });
  }, [terrain, drives, waypoints, showHistory, showWaypoints, waypoint]);

  function fitHistory() {
    if (view3d) { terrain3D.current?.fit(); return; }
    const coords = drives.flatMap(f => f.geometry.coordinates).map(c => [c[0], c[1]]);
    if (!coords.length || !mapRef.current) return;
    const xs = coords.map(p => p[0]), ys = coords.map(p => p[1]), mobile = innerWidth < 850;
    const padDeg = 250 / M_PER_DEG;
    mapRef.current.getView().fit(
      [Math.min(...xs) - padDeg, Math.min(...ys) - padDeg, Math.max(...xs) + padDeg, Math.max(...ys) + padDeg],
      { padding: mobile ? [200, 75, 150, 25] : [90, 125, 160, 395], duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450, minResolution: 0.8 / M_PER_DEG }
    );
  }
  useEffect(() => { if (historyMode) fitHistory(); }, [terrain, historyFit]);

  const fit = () => {
    if (historyMode) { fitHistory(); return; }
    if (view3d) { terrain3D.current?.fit(); return; }
    mapRef.current?.getView().fit(layers.current.extent, { padding: [60, 70, 110, 70], duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450 });
  };
  const zoom = delta => {
    interact();
    if (view3d) terrain3D.current?.zoom(delta > 0 ? 1.25 : 0.8);
    else mapRef.current?.getView().animate({ zoom: mapRef.current.getView().getZoom() + delta, duration: 180 });
  };
  const focus = coord => {
    if (!coord || !mapRef.current) return;
    interact();
    const view = mapRef.current.getView();
    view.cancelAnimations();
    view.setCenter([coord.lon, coord.lat]);
    if (coord.resolution) {
      view.setResolution(coord.resolution / M_PER_DEG);
    } else if (coord.zoom) {
      const approxMeters = 14500 / Math.pow(2, coord.zoom);
      view.setResolution(Math.max(0.5, approxMeters) / M_PER_DEG);
    } else {
      view.setResolution(12 / M_PER_DEG);
    }
  };
  useEffect(() => { if (actionsRef) actionsRef.current = { fit, zoom, focus }; }, [view3d, terrain, historyMode, drives]);

  useEffect(() => {
    if (historyMode || !response || !mapRef.current) return;
    const ps = response.routes.flatMap(r => r.geometry.coordinates).map(c => [c[0], c[1]]), xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
    if (!ps.length) return;
    const padDeg = 600 / M_PER_DEG;
    const ext = [Math.min(...xs) - padDeg, Math.min(...ys) - padDeg, Math.max(...xs) + padDeg, Math.max(...ys) + padDeg];
    const mobile = window.innerWidth < 850;
    mapRef.current.getView().fit(ext, { padding: mobile ? [100, 50, 140, 50] : [85, 340, 160, 380], duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500, minResolution: 1 / M_PER_DEG });
  }, [fitToken, historyMode]);

  useEffect(() => {
    if (!mapRef.current) return;
    const s = layers.current.hoverLayer.getSource();
    s.clear();
    if (hover) {
      const f = new Feature(new Point([hover[0], hover[1]]));
      f.setStyle(new Style({ image: new CircleStyle({ radius: 5, fill: new Fill({ color: '#f4d4a1' }), stroke: new Stroke({ color: '#202923', width: 2 }) }) }));
      s.addFeature(f);
    }
  }, [terrain, hover]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, src = l.spacecraftLayer.getSource();
    src.clear();
    l.spacecraftLayer.setVisible(showOrbiters);
    if (!showOrbiters || !spacecraftPositions.length) return;
    spacecraftPositions.forEach(ship => {
      if (!Number.isFinite(ship.lon) || !Number.isFinite(ship.lat)) return;
      const f = new Feature({ geometry: new Point([ship.lon, ship.lat]), spacecraftId: ship.spacecraft_id });
      const isSel = selectedSpacecraft === ship.spacecraft_id;
      f.setStyle(new Style({ image: new CircleStyle({ radius: isSel ? 9 : 7, fill: new Fill({ color: isSel ? '#5cffb0' : '#64dfdf' }), stroke: new Stroke({ color: '#091518', width: 2 }) }), text: new Text({ text: `${ship.spacecraft_id.toUpperCase()} (${Math.round(ship.altitude_km)} km)`, font: '600 11px Inter, sans-serif', offsetY: -16, fill: new Fill({ color: '#e6fbf2' }), stroke: new Stroke({ color: '#081013', width: 3 }) }) }));
      src.addFeature(f);
    });
  }, [terrain, showOrbiters, spacecraftPositions, selectedSpacecraft]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, src = l.groundTracksLayer.getSource();
    src.clear();
    l.groundTracksLayer.setVisible(showGroundTracks);
    if (!showGroundTracks || !groundTracks.length) return;
    groundTracks.forEach(gt => {
      if (!gt.points || gt.points.length < 2) return;
      let seg = [];
      for (let i = 0; i < gt.points.length; i++) {
        const pt = gt.points[i];
        if (seg.length > 0 && Math.abs(pt.lon - gt.points[i - 1].lon) > 180) {
          if (seg.length > 1) {
            const f = new Feature(new LineString(seg.map(c => [c[0], c[1]])));
            f.setStyle(new Style({ stroke: new Stroke({ color: '#64dfdf66', width: 1.5, lineDash: [6, 6] }) }));
            src.addFeature(f);
          }
          seg = [];
        }
        seg.push([pt.lon, pt.lat]);
      }
      if (seg.length > 1) {
        const f = new Feature(new LineString(seg.map(c => [c[0], c[1]])));
        f.setStyle(new Style({ stroke: new Stroke({ color: '#64dfdf66', width: 1.5, lineDash: [6, 6] }) }));
        src.addFeature(f);
      }
    });
  }, [terrain, showGroundTracks, groundTracks]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, src = l.footprintsLayer.getSource();
    src.clear();
    l.footprintsLayer.setVisible(showFootprints);
    if (!showFootprints || !orbitalObservations.length) return;
    orbitalObservations.forEach(obs => {
      const coords = obs.footprint_geojson?.geometry?.coordinates?.[0];
      if (!coords || coords.length < 4) return;
      const f = new Feature({ geometry: new Polygon([coords.map(c => [c[0], c[1]])]), observationId: obs.observation_id });
      const isSel = selectedObservation === obs.observation_id;
      f.setStyle(new Style({ stroke: new Stroke({ color: isSel ? '#5cffb0' : '#ffd16677', width: isSel ? 2.5 : 1.2, lineDash: isSel ? [] : [5, 5] }), fill: new Fill({ color: isSel ? '#5cffb022' : '#ffd16608' }), text: new Text({ text: `${obs.observation_id} (${obs.instrument})`, font: isSel ? '600 11px Inter, sans-serif' : '500 10px Inter, sans-serif', offsetY: -8, fill: new Fill({ color: isSel ? '#a3f4ca' : '#f5e3b8' }), stroke: new Stroke({ color: '#0a1412', width: 3 }) }) }));
      src.addFeature(f);
    });
  }, [terrain, showFootprints, orbitalObservations, selectedObservation]);

  useEffect(() => {
    if (!mapRef.current || !focusedProduct) return;
    const l = layers.current;
    if (!l.footprintsLayer) return;
    const src = l.footprintsLayer.getSource();
    let coords = null;
    if (focusedProduct.bounds) {
      const b = focusedProduct.bounds;
      coords = [[b.min_lon, b.min_lat], [b.max_lon, b.min_lat], [b.max_lon, b.max_lat], [b.min_lon, b.max_lat], [b.min_lon, b.min_lat]];
    } else if (focusedProduct.footprint_geojson?.geometry?.coordinates?.[0]) {
      coords = focusedProduct.footprint_geojson.geometry.coordinates[0];
    }
    if (coords && coords.length >= 4) {
      const poly = new Polygon([coords.map(c => [c[0], c[1]])]);
      const f = new Feature({ geometry: poly, observationId: focusedProduct.product_id });
      f.setStyle(new Style({ stroke: new Stroke({ color: '#64dfdf', width: 3 }), fill: new Fill({ color: 'rgba(100,223,223,0.2)' }), text: new Text({ text: `NASA: ${focusedProduct.product_id} (${focusedProduct.instrument})`, font: '600 11px Inter, sans-serif', offsetY: -12, fill: new Fill({ color: '#a0f0f0' }), stroke: new Stroke({ color: '#0a1412', width: 3 }) }) }));
      src.addFeature(f);
      mapRef.current.getView().fit(poly.getExtent(), { padding: [90, 90, 90, 90], duration: 450, minResolution: 15 / M_PER_DEG });
    }
  }, [focusedProduct]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, src = l.curiosityLayer.getSource();
    src.clear();
    l.curiosityLayer.setVisible(showCuriosity);
    if (!showCuriosity || !curiosityTraverse) return;
    for (const d of curiosityTraverse.features || []) {
      const f = new Feature({ geometry: new LineString(d.geometry.coordinates.map(c => [c[0], c[1]])), driveRecord: d });
      f.setStyle([new Style({ stroke: new Stroke({ color: '#101318ed', width: 6, lineCap: 'round' }) }), new Style({ stroke: new Stroke({ color: '#a78bfa', width: 3, lineCap: 'round' }) })]);
      src.addFeature(f);
    }
    if (curiosityWaypoints?.length) {
      const last = curiosityWaypoints[curiosityWaypoints.length - 1], c = last.geometry.coordinates, f = new Feature(new Point([c[0], c[1]]));
      f.setStyle(new Style({ image: new CircleStyle({ radius: 8, fill: new Fill({ color: '#a78bfa' }), stroke: new Stroke({ color: '#111827', width: 2 }) }), text: new Text({ text: 'Curiosity (MSL)', font: '600 11px Inter, sans-serif', offsetY: -16, fill: new Fill({ color: '#e9d5ff' }), stroke: new Stroke({ color: '#090e17', width: 3 }) }) }));
      src.addFeature(f);
    }
  }, [terrain, showCuriosity, curiosityTraverse, curiosityWaypoints]);

  // Determine exact validated imagery source label based on active visible layers & current view
  const inHiriseView =
    viewState.centerLon >= JEZERO_HIRISE_ORTHO_BOUNDS[0] &&
    viewState.centerLon <= JEZERO_HIRISE_ORTHO_BOUNDS[2] &&
    viewState.centerLat >= JEZERO_HIRISE_ORTHO_BOUNDS[1] &&
    viewState.centerLat <= JEZERO_HIRISE_ORTHO_BOUNDS[3];
  const inCtxView =
    viewState.centerLon >= JEZERO_CTX_ORTHO_BOUNDS[0] &&
    viewState.centerLon <= JEZERO_CTX_ORTHO_BOUNDS[2] &&
    viewState.centerLat >= JEZERO_CTX_ORTHO_BOUNDS[1] &&
    viewState.centerLat <= JEZERO_CTX_ORTHO_BOUNDS[3];

  const isAutoMode = base === 'auto' || base === 'imagery';
  const isHiriseMode = base === 'hirise';
  const isCtxMode = base === 'ctx' || base === 'ctx_global';
  const isVikingMode = base === 'viking' || base === 'global';
  const isReliefMode = base === 'relief';

  const hiriseVisuallyActive =
    showHirise && !isVikingMode && !isCtxMode && (isAutoMode || isHiriseMode) && inHiriseView && viewState.resolution <= (isHiriseMode ? 2500 : 35);
  const ctxVisuallyActive =
    showCtx && !isVikingMode && (isAutoMode || isCtxMode || isHiriseMode) && inCtxView && viewState.resolution <= (isCtxMode ? 8000 : 1800);
  const molaVisuallyActive = Boolean(showMolaTerrain || isReliefMode);

  let activeImageryLabel = 'No imagery layer active';
  if (hiriseVisuallyActive) {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.sourceLabel} (DOI: 10.5066/P9QJDP48)`;
  } else if (ctxVisuallyActive) {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.sourceLabel} (DOI: 10.5066/P9GV1ND3)`;
  } else if (molaVisuallyActive) {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.mola_hrsc_shaded_200m.sourceLabel} (DOI: 10.5066/P9P7W018)`;
  } else if (showViking) {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m.sourceLabel} (DOI: 10.5066/F71V5C67)`;
  }

  const activeTerrainOverlays = [
    isReliefMode && 'DEM Relief',
    (showHillshade || isReliefMode) && 'Hillshade',
    showSlope && 'Slope',
    showRoughness && 'Roughness',
  ].filter(Boolean);
  if (activeTerrainOverlays.length) {
    activeImageryLabel = `${activeImageryLabel} + ${activeTerrainOverlays.join('/')}`;
  }

  // Determine exact validated DEM source label driving routing
  const isHiriseDemActive = Boolean(
    response?.source_selection?.hirise_selected ||
    provenance?.productId === 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40' ||
    effectiveTerrain?.raw?.product_id === 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40'
  );
  const activeDemLabel = isHiriseDemActive
    ? `${AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.sourceLabel} (DOI: 10.5066/P9REJ9JN)`
    : `${AUTHORITATIVE_MARS_TERRAIN_CATALOG.mola_hrsc_dem_200m.sourceLabel} (DOI: 10.5066/P907276M)`;

  const wmtsBadge = wmtsStats.loaded > 0 ? `WMTS LIVE (${wmtsStats.loaded} tiles)` : 'WMTS CONNECTING';

  // Compute unobstructed horizontal map corridor between open side panels
  const leftInset = leftOpen ? 372 : 24;
  const rightInset = !historyMode ? (rightExpanded ? 452 : 392) : 76;
  const corridorCenterStyle = `calc(50% + ${(leftInset - rightInset) / 2}px)`;
  const corridorWidthStyle = `calc(100vw - ${leftInset + rightInset}px)`;
  const showPlaybackDeck = !historyMode && Boolean(currentPlayback);
  const inspectBottomOffset = profileExpanded
    ? undefined
    : showPlaybackDeck
      ? '224px'
      : historyMode
        ? '132px'
        : '112px';

  return (
    <div className={'map-surface ' + (view3d ? 'is-3d' : '')}>
      <div
        ref={node}
        className="ol-map"
        style={{ cursor: pick ? 'crosshair' : 'grab', visibility: view3d ? 'hidden' : 'visible' }}
        tabIndex={view3d ? -1 : 0}
        aria-hidden={view3d}
        aria-label="Interactive Global Mars & Jezero Crater geospatial map. Select a pin tool then click to place coordinates."
      />
      {view3d && <Terrain3D ref={terrain3D} {...props} hiriseMeta={hiriseMeta} onInteract={interact} />}
      <div className="atmosphere-vignette" />
      <div className={'location-label ' + (locationVisible ? 'visible' : '')}>
        <span />Jezero Crater <small>18.41°N · 77.42°E</small>
      </div>

      {/* Planetary Bookmark Bar */}
      <div
        className="planetary-bookmark-bar glass"
        role="region"
        aria-label="Planetary region bookmarks"
        style={{
          left: corridorCenterStyle,
          maxWidth: corridorWidthStyle,
        }}
      >
        {PLANETARY_BOOKMARKS.map(bm => (
          <button
            key={bm.id}
            type="button"
            className={activeBookmark === bm.id ? 'active' : ''}
            onClick={() => {
              interact();
              focus({ lon: bm.lon, lat: bm.lat, resolution: bm.resolution });
              onSelectBookmark?.(bm);
            }}
            title={bm.sub}
          >
            <span className="bm-dot" style={{ background: bm.hasDem ? '#5cffb0' : '#64dfdf' }} />
            {bm.label}
          </button>
        ))}
      </div>

      <div className="map-control-stack glass">
        <button aria-label="Zoom in" onClick={() => zoom(1)}><Icon name="plus" /></button>
        <button aria-label="Zoom out" onClick={() => zoom(-1)}><Icon name="minus" /></button>
        <button aria-label="Fit Jezero DEM region" title="Fit Jezero DEM region" onClick={() => { interact(); fit(); onSelectBookmark?.(PLANETARY_BOOKMARKS[1]); }}><Icon name="fit" /></button>
      </div>
      <button className={'map-layers-button glass icon-button ' + (layersOpen ? 'active' : '')} onClick={onLayersToggle} aria-label="Map layers" aria-expanded={layersOpen} title="Scientific Layer Manager"><Icon name="layers" /></button>
      <button className={'map-tilt-button glass icon-button ' + (view3d ? 'active' : '')} onClick={onTiltToggle} aria-label={view3d ? 'Switch to 2D map' : 'Switch to 3D terrain'} title={view3d ? '2D map' : '3D terrain'} aria-pressed={view3d}><Icon name="cube" /><small>{view3d ? '3D' : '2D'}</small></button>
      {(pick || hint) && (
        <div
          className="map-instruction glass"
          style={{ left: corridorCenterStyle, maxWidth: corridorWidthStyle }}
        >
          {pick ? `Click terrain to place ${pick === 'start' ? 'start A' : 'destination B'}` : 'Drag to explore Mars WMTS (Viking 232m → CTX 6m → HiRISE 0.25m). Scroll to zoom.'}
        </div>
      )}

      {/* Click-to-Inspect Display Card */}
      {inspectPopup && (
        <div
          className="map-inspect-popup glass"
          style={{
            left: corridorCenterStyle,
            ...(profileExpanded ? { top: '94px', bottom: 'auto' } : { bottom: inspectBottomOffset, top: 'auto' }),
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h4 style={{ margin: 0, fontSize: '12.5px', color: '#5cffb0', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>📍</span> Mars Surface Point Inspector
            </h4>
            <button
              onClick={() => setInspectPopup(null)}
              style={{ color: '#8fa398', cursor: 'pointer', fontSize: '16px', lineHeight: 1 }}
              aria-label="Close inspector"
            >
              ×
            </button>
          </div>
          <div style={{ display: 'grid', gap: '6px', fontSize: '11px', color: '#c7d6d1' }}>
            <div>
              <span style={{ color: '#8fa398', display: 'block', fontSize: '10px' }}>Coordinates:</span>
              <strong style={{ fontFamily: 'var(--mono)', color: '#fff', fontSize: '11.5px' }}>
                {inspectPopup.lat.toFixed(5)}°N, {inspectPopup.lon.toFixed(5)}°E
              </strong>
            </div>
            <div>
              <span style={{ color: '#8fa398', display: 'block', fontSize: '10px' }}>Active Imagery Layer:</span>
              <span style={{ color: '#a8e6cf' }}>{inspectPopup.imagery}</span>
            </div>
            <div style={{ display: 'flex', gap: '14px' }}>
              <div>
                <span style={{ color: '#8fa398', display: 'block', fontSize: '10px' }}>Elevation:</span>
                <strong style={{ fontFamily: 'var(--mono)', color: '#9becbf' }}>
                  {inspectPopup.elev !== null
                    ? `${inspectPopup.elev.toFixed(1)} m`
                    : inspectPopup.inDemBounds
                      ? 'Unobserved / NoData'
                      : 'Outside DEM'}
                </strong>
              </div>
              <div>
                <span style={{ color: '#8fa398', display: 'block', fontSize: '10px' }}>Slope / Rating:</span>
                <strong style={{ fontFamily: 'var(--mono)', color: inspectPopup.slope > 15 ? '#ff9885' : '#e6ebe9' }}>
                  {inspectPopup.slope !== null
                    ? `${inspectPopup.slope.toFixed(1)}° (${inspectPopup.hazard})`
                    : inspectPopup.hazard}
                </strong>
              </div>
            </div>
            {inspectPopup.inspectError && (
              <div style={{ fontSize: '10px', color: '#ff9885' }}>{inspectPopup.inspectError}</div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
            <button
              onClick={() => {
                onPin?.({ lon: inspectPopup.lon, lat: inspectPopup.lat });
                setInspectPopup(null);
              }}
              style={{
                flex: 1,
                background: 'rgba(92,255,176,0.18)',
                border: '1px solid #5cffb066',
                borderRadius: '8px',
                padding: '6px 8px',
                color: '#5cffb0',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Set Destination
            </button>
            {onOpenSurfacePov && (
              <button
                type="button"
                onClick={() => {
                  onOpenSurfacePov({ lat: inspectPopup.lat, lon: inspectPopup.lon });
                  setInspectPopup(null);
                }}
                style={{
                  background: 'rgba(56, 189, 248, 0.18)',
                  border: '1px solid #38bdf866',
                  borderRadius: '8px',
                  padding: '6px 8px',
                  color: '#38bdf8',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                📷 Surface POV
              </button>
            )}
            <button
              onClick={() => setInspectPopup(null)}
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '8px',
                padding: '6px 12px',
                color: '#8fa398',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Route Animation Playback Control Deck (Planner View only) */}
      {showPlaybackDeck && (
        <div
          className="route-playback-deck glass"
          role="region"
          aria-label="Route animation playback deck"
          style={{
            left: corridorCenterStyle,
            width: `min(620px, ${corridorWidthStyle})`,
            bottom: profileExpanded ? '320px' : '110px',
          }}
        >
          {/* Top Row: Play/Pause, Restart, Scrubber, Follow Toggle, Speed Multipliers */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <button
              onClick={() => {
                if (playbackProgress >= 1.0) setPlaybackProgress(0);
                setIsPlaying(!isPlaying);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '32px',
                height: '32px',
                borderRadius: '50%',
                background: isPlaying ? 'rgba(255, 184, 103, 0.22)' : 'rgba(92, 255, 176, 0.22)',
                color: isPlaying ? '#ffb867' : '#5cffb0',
                border: isPlaying ? '1px solid #ffb86766' : '1px solid #5cffb066',
                cursor: 'pointer',
                fontSize: '13px',
                flexShrink: 0,
              }}
              aria-label={isPlaying ? 'Pause rover animation' : 'Play rover animation'}
              title={isPlaying ? 'Pause animation' : 'Play animation'}
            >
              {isPlaying ? '⏸' : '▶'}
            </button>

            <button
              onClick={() => {
                setIsPlaying(false);
                setPlaybackProgress(0);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '28px',
                height: '28px',
                borderRadius: '50%',
                background: 'rgba(255, 255, 255, 0.05)',
                color: '#c5d6cf',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                cursor: 'pointer',
                fontSize: '12px',
                flexShrink: 0,
              }}
              aria-label="Restart rover animation from beginning"
              title="Restart route animation"
            >
              ↺
            </button>

            <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              <input
                type="range"
                min="0"
                max="100"
                step="0.1"
                value={(playbackProgress * 100).toFixed(1)}
                onChange={e => {
                  setIsPlaying(false);
                  setPlaybackProgress(Number(e.target.value) / 100);
                }}
                style={{
                  width: '100%',
                  accentColor: '#5cffb0',
                  cursor: 'pointer',
                  height: '5px',
                }}
                aria-label="Route scrubber"
              />
              <span style={{ fontSize: '11px', fontFamily: 'var(--mono)', color: '#5cffb0', minWidth: '36px', textAlign: 'right' }}>
                {(playbackProgress * 100).toFixed(0)}%
              </span>
            </div>

            <button
              type="button"
              onClick={() => setFollowRover(f => !f)}
              aria-pressed={followRover}
              style={{
                padding: '3px 8px',
                borderRadius: '7px',
                fontSize: '10px',
                fontWeight: 600,
                background: followRover ? 'rgba(92, 255, 176, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                color: followRover ? '#5cffb0' : '#9eb2a7',
                border: followRover ? '1px solid rgba(92, 255, 176, 0.45)' : '1px solid rgba(255, 255, 255, 0.1)',
                cursor: 'pointer',
                flexShrink: 0,
              }}
              title="Toggle optional camera tracking of animated rover"
            >
              Follow
            </button>

            <div style={{ display: 'flex', gap: '2px', background: 'rgba(255,255,255,0.04)', padding: '2px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)', flexShrink: 0 }}>
              {[1, 2, 5, 10].map(s => (
                <button
                  key={s}
                  onClick={() => setPlaybackSpeed(s)}
                  style={{
                    padding: '2px 6px',
                    borderRadius: '6px',
                    fontSize: '10px',
                    fontFamily: 'var(--mono)',
                    fontWeight: playbackSpeed === s ? 700 : 500,
                    background: playbackSpeed === s ? 'rgba(92, 255, 176, 0.22)' : 'transparent',
                    color: playbackSpeed === s ? '#5cffb0' : '#8da197',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                  title={`Set playback speed to ${s}x`}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>

          {/* Bottom Row: Real-time Telemetry Readout */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '10.5px',
              color: '#98ad9f',
              borderTop: '1px solid rgba(255, 255, 255, 0.07)',
              paddingTop: '5px',
              flexWrap: 'wrap',
              gap: '6px',
            }}
          >
            <div>
              <span style={{ color: '#5cffb0', marginRight: '4px' }}>📍 Rover:</span>
              <span style={{ fontFamily: 'var(--mono)', color: '#e6ebe9' }}>
                {currentPlayback.curLat.toFixed(5)}°N, {currentPlayback.curLon.toFixed(5)}°E
              </span>
            </div>

            <div>
              <span style={{ color: '#8da197', marginRight: '4px' }}>Traveled:</span>
              <span style={{ fontFamily: 'var(--mono)', color: '#d5e3dc' }}>
                {Math.round(currentPlayback.distTraveled)} m / {Math.round(currentPlayback.totalDist)} m
              </span>
            </div>

            <div>
              <span style={{ color: '#8da197', marginRight: '4px' }}>Terrain:</span>
              <span style={{ fontFamily: 'var(--mono)', color: '#d5e3dc' }}>
                {currentPlayback.curEle !== null ? `${Math.round(currentPlayback.curEle)} m` : '—'} (Slope: {currentPlayback.slope.toFixed(1)}°)
              </span>
            </div>

            <div>
              <span style={{ color: '#8da197', marginRight: '4px' }}>Heading:</span>
              <span style={{ fontFamily: 'var(--mono)', color: '#5cffb0' }}>
                {Math.round(currentPlayback.headingDeg)}°
              </span>
            </div>
          </div>
        </div>
      )}
      <div className="map-source" data-testid="map-active-source-banner">
        <strong>Imagery:</strong> {activeImageryLabel}
        {' · '}
        <strong>Routing Terrain:</strong> {activeDemLabel}
        {' · '}
        {wmtsBadge}
        {' · '}
        Cursor: {cursorCoord.lat.toFixed(4)}°N, {cursorCoord.lon.toFixed(4)}°E (
        {cursorCoord.inHiriseDtm
          ? 'HiRISE 1 m DTM + 200 m DEM'
          : cursorCoord.inJezeroDem
            ? 'Regional 200 m DEM Only'
            : 'Global Imagery Only'}
        )
      </div>
    </div>
  );
}
