import React, { useEffect, useRef, useState } from 'react';
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
import { Style, Stroke, Fill, Circle as CircleStyle, Text } from 'ol/style.js';
import { ScaleLine } from 'ol/control.js';
import { M_PER_DEG, project, unproject, extentFor, rasterImage } from './terrain.js';
import {
  AUTHORITATIVE_MARS_IMAGERY_CATALOG,
  AUTHORITATIVE_MARS_TERRAIN_CATALOG,
  buildCapabilitiesFromCatalogEntry,
  createOpenLayersWMTSSource,
  fetchAndParseWMTSCapabilities,
} from './wmts_capabilities.js';
import Icon from './Icons.jsx';
import Terrain3D from './Terrain3D.jsx';

export const GLOBAL_MARS_BOUNDS = [-180, -85, 180, 85];
export const JEZERO_VALIDATED_DEM_BOUNDS = [77.2008333, 18.1491667, 77.9491667, 18.6508333];
export const JEZERO_HIRISE_ORTHO_BOUNDS = [77.2229331, 18.3067994, 77.583964, 18.669315];
export const JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS = [77.3819891, 18.3719875, 77.4580081, 18.4400097];
export const JEZERO_CTX_ORTHO_BOUNDS = [77.1604655, 18.2110274, 77.6991776, 18.7211945];

export const MARS_WMTS_LAYERS = {
  viking: AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m,
  ctx_global: AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m,
  jezero_hirise_wmts: AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm,
  mola_hrsc: AUTHORITATIVE_MARS_IMAGERY_CATALOG.mola_hrsc_hillshade_200m,
};

export const PLANETARY_BOOKMARKS = [
  { id: 'jezero_landing', label: 'Jezero Landing & Delta (HiRISE 0.25m)', sub: 'USGS HiRISE 0.25 m Ortho + 1 m DTM Routing', lon: 77.425, lat: 18.41, resolution: 6, hasDem: true },
  { id: 'jezero', label: 'Jezero Regional (CTX 6m)', sub: 'USGS CTX 6 m Ortho + Jezero Crater Basin', lon: 77.4508, lat: 18.4447, resolution: 75, hasDem: true },
  { id: 'gale', label: 'Gale Crater', sub: 'Curiosity (MSL) · Global Imagery Only', lon: 137.4417, lat: -4.5895, resolution: 320, hasDem: false },
  { id: 'olympus', label: 'Olympus Mons', sub: 'Shield Volcano · Global Imagery Only', lon: -133.8, lat: 18.65, resolution: 2200, hasDem: false },
  { id: 'valles', label: 'Valles Marineris', sub: 'Tectonic Canyon · Global Imagery Only', lon: -70.0, lat: -10.0, resolution: 3500, hasDem: false },
  { id: 'global', label: 'Global Mars (232m)', sub: 'NASA Viking MDIM 2.1 Global Mosaic (180°W–180°E)', lon: 0.0, lat: 0.0, resolution: 14000, hasDem: false },
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
    imageryOpacity = 1.0, terrainOpacity = 0.72,
    maxSlope = 20, maxRough = 0.85, response, selected, onSelectRoute,
    hover, fitToken, live, backendStatus, provenance, showRoute = true, showAlternatives = false, hoveredRoute = null,
    view3d = false, layersOpen, onLayersToggle, onTiltToggle, actionsRef,
    showOrbiters = true, showGroundTracks = true, showFootprints = true, showCuriosity = false,
    spacecraftPositions = [], groundTracks = [], orbitalObservations = [], selectedObservation = null, selectedSpacecraft = null,
    onSelectObservation, onSelectSpacecraft, curiosityTraverse = null, curiosityWaypoints = [], focusedProduct = null,
    showThemisOverlay = false, showScienceTargets = true, scienceTargets = [], roverReplayState = null,
    activeBookmark = 'jezero_landing', onSelectBookmark, onWmtsStatusChange,
  } = props;

  const effectiveTerrain = activeDemTerrain || terrain;

  useEffect(() => {
    fetch('/mission-data/jezero-hirise.json')
      .then(r => (r.ok ? r.json() : null))
      .then(setHiriseMeta)
      .catch(() => {});
  }, []);

  const node = useRef(), mapRef = useRef(), layers = useRef({}), callbacks = useRef({}), terrain3D = useRef(), midLabel = useRef();
  const [locationVisible, setLocationVisible] = useState(true);
  const [hiriseMeta, setHiriseMeta] = useState(null);
  const [viewState, setViewState] = useState({ resolution: 16, centerLon: 77.425, centerLat: 18.408 });
  const [wmtsStats, setWmtsStats] = useState({
    loaded: 0,
    errors: 0,
    byLayer: {
      viking: { loaded: 0, errors: 0, capabilitiesVerified: false },
      ctx: { loaded: 0, errors: 0, capabilitiesVerified: false },
      hirise: { loaded: 0, errors: 0, capabilitiesVerified: false },
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
    if (!terrain || !node.current) return;
    const jezeroExtent = extentFor(terrain.b);
    const globalExtent = extentFor(GLOBAL_MARS_BOUNDS);
    const ctxExtent = extentFor(JEZERO_CTX_ORTHO_BOUNDS);
    const hiriseOrthoExtent = extentFor(JEZERO_HIRISE_ORTHO_BOUNDS);

    const marsGeoProj = new Projection({
      code: 'IAU2000:49900',
      units: 'degrees',
      extent: [-180, -90, 180, 90],
      global: false,
      metersPerUnit: M_PER_DEG,
      getPointResolution: r => r,
    });
    addProjection(marsGeoProj);
    const projection = new Projection({
      code: 'MARSPATH:JEZERO_METERS',
      units: 'm',
      extent: globalExtent,
      global: false,
      metersPerUnit: 1,
      getPointResolution: r => r,
    });
    addProjection(projection);
    addCoordinateTransforms(
      marsGeoProj,
      projection,
      ([lon, lat]) => project(lon, lat),
      ([x, y]) => {
        const p = unproject(x, y);
        return [p.lon, p.lat];
      }
    );

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

    // 1. Global Mars Basemap: NASA Mars Trek Viking MDIM 2.1 Color Mosaic (232 m/px)
    const wmtsVikingGlobal = new TileLayer({
      source: createOpenLayersWMTSSource(vikingCap, recordTileOk('viking'), recordTileErr('viking')),
      zIndex: 0,
      opacity: 1.0,
      preload: 2,
    });

    // 2. Regional Jezero Basemap: USGS Mars 2020 TRN CTX Orthomosaic (6 m/px, DOI: 10.5066/P9GV1ND3)
    const wmtsCtxRegional = new TileLayer({
      source: createOpenLayersWMTSSource(ctxCap, recordTileOk('ctx'), recordTileErr('ctx')),
      extent: ctxExtent,
      maxResolution: 1200,
      zIndex: 1,
      opacity: 1.0,
      preload: 2,
    });

    // 3. High-Resolution Jezero Basemap: USGS Mars 2020 TRN HiRISE Orthomosaic (0.25 m/px, DOI: 10.5066/P9QJDP48)
    const wmtsHiriseLocal = new TileLayer({
      source: createOpenLayersWMTSSource(hiriseCap, recordTileOk('hirise'), recordTileErr('hirise')),
      extent: hiriseOrthoExtent,
      maxResolution: 180,
      zIndex: 2,
      opacity: 1.0,
      preload: 1,
    });

    // Async verify live GetCapabilities XML documents and bind verified WMTS sources
    let cancelled = false;
    Promise.all([
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m),
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m),
      fetchAndParseWMTSCapabilities(AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm),
    ]).then(([vParsed, cParsed, hParsed]) => {
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
      setWmtsStats(s => ({
        ...s,
        byLayer: {
          viking: { ...s.byLayer.viking, capabilitiesVerified: Boolean(vParsed?.tileMatrices?.length) },
          ctx: { ...s.byLayer.ctx, capabilitiesVerified: Boolean(cParsed?.tileMatrices?.length) },
          hirise: { ...s.byLayer.hirise, capabilitiesVerified: Boolean(hParsed?.tileMatrices?.length) },
        },
      }));
    }).catch(() => {});

    // Separate Terrain Analysis Overlays (never mixed with satellite imagery)
    const relief = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(effectiveTerrain, 'relief'), imageExtent: extentFor(effectiveTerrain.b), projection }),
      zIndex: 3,
      visible: false,
      opacity: 0.85,
    });
    const hillshade = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(effectiveTerrain, 'hillshade'), imageExtent: extentFor(effectiveTerrain.b), projection }),
      opacity: 0.65,
      zIndex: 4,
      visible: false,
    });
    const slopeLayer = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(effectiveTerrain, 'slope', maxSlope, maxRough), imageExtent: extentFor(effectiveTerrain.b), projection }),
      opacity: 0.72,
      zIndex: 5,
      visible: false,
    });
    const roughnessLayer = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(effectiveTerrain, 'roughness', maxSlope, maxRough), imageExtent: extentFor(effectiveTerrain.b), projection }),
      opacity: 0.72,
      zIndex: 6,
      visible: false,
    });
    const themisLayer = new ImageLayer({
      source: new ImageStatic({ url: buildThemisThermalCanvas(effectiveTerrain), imageExtent: extentFor(effectiveTerrain.b), projection, interpolate: true }),
      zIndex: 10,
      visible: false,
    });
    const footprintsLayer = new VectorLayer({ source: new VectorSource(), zIndex: 11 });
    const groundTracksLayer = new VectorLayer({ source: new VectorSource(), zIndex: 12 });
    const hiriseBoundary = new VectorLayer({ source: new VectorSource(), zIndex: 13 });
    const demBoundaryLayer = new VectorLayer({ source: new VectorSource(), zIndex: 13.5 });
    const risk = new ImageLayer({ zIndex: 14, visible: false });
    const data = new ImageLayer({ zIndex: 14.5, visible: false });
    const historyLayer = new VectorLayer({ source: new VectorSource(), zIndex: 15 });
    const curiosityLayer = new VectorLayer({ source: new VectorSource(), zIndex: 16 });
    const historyPins = new VectorLayer({ source: new VectorSource(), zIndex: 17 });
    const scienceTargetsLayer = new VectorLayer({ source: new VectorSource(), zIndex: 19 });
    const routes = new VectorLayer({ source: new VectorSource(), zIndex: 20 });
    const pins = new VectorLayer({ source: new VectorSource(), zIndex: 22 });
    const hoverLayer = new VectorLayer({ source: new VectorSource(), zIndex: 24 });
    const roverReplayLayer = new VectorLayer({ source: new VectorSource(), zIndex: 25 });
    const spacecraftLayer = new VectorLayer({ source: new VectorSource(), zIndex: 26 });

    // Populate DEM & Imagery Coverage Boundaries
    const demPoly = new Feature(new Polygon([[
      [jezeroExtent[0], jezeroExtent[1]],
      [jezeroExtent[2], jezeroExtent[1]],
      [jezeroExtent[2], jezeroExtent[3]],
      [jezeroExtent[0], jezeroExtent[3]],
      [jezeroExtent[0], jezeroExtent[1]],
    ]]));
    demPoly.setStyle((feature, resolution) => {
      if (resolution < 90 && !callbacks.current.props.coverage) return null;
      return new Style({
        stroke: new Stroke({ color: '#5cffb088', width: 1.6, lineDash: [8, 6] }),
        fill: new Fill({ color: resolution > 200 ? 'rgba(92,255,176,0.04)' : 'rgba(0,0,0,0)' }),
        text: new Text({
          text: resolution > 400 ? 'Jezero Regional DEM (200 m MOLA-HRSC)' : 'USGS MOLA-HRSC Regional DEM Coverage (200 m/px · DOI: 10.5066/P907276M)',
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
        wmtsCtxRegional,
        wmtsHiriseLocal,
        relief,
        hillshade,
        slopeLayer,
        roughnessLayer,
        hiriseBoundary,
        demBoundaryLayer,
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
        hoverLayer,
        roverReplayLayer,
        spacecraftLayer,
      ],
      view: new View({
        projection,
        center: project(77.425, 18.408),
        resolution: 18,
        constrainOnlyCenter: true,
        minResolution: 0.25,
        maxResolution: 24000,
        extent: globalExtent,
      }),
      controls: [new ScaleLine({ units: 'metric' })],
    });

    const element = document.createElement('div');
    element.className = 'route-midpoint glass';
    const label = new Overlay({ element, positioning: 'bottom-center', offset: [0, -20], stopEvent: false });
    map.addOverlay(label);
    midLabel.current = label;

    layers.current = {
      projection,
      extent: jezeroExtent,
      globalExtent,
      ctxExtent,
      hiriseOrthoExtent,
      wmtsVikingGlobal,
      wmtsCtxRegional,
      wmtsHiriseLocal,
      relief,
      hillshade,
      slopeLayer,
      roughnessLayer,
      hiriseBoundary,
      demBoundaryLayer,
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
      hoverLayer,
      roverReplayLayer,
      spacecraftLayer,
      recordTileOk,
      recordTileErr,
    };
    mapRef.current = map;

    const syncViewState = () => {
      const v = map.getView();
      const res = v.getResolution() || 18;
      const c = v.getCenter();
      const pt = c ? unproject(c[0], c[1]) : { lon: 77.425, lat: 18.408 };
      setViewState({ resolution: res, centerLon: pt.lon, centerLat: pt.lat });
    };
    map.getView().on('change:resolution', syncViewState);
    map.getView().on('change:center', syncViewState);
    syncViewState();

    map.on('pointermove', e => {
      if (e.dragging) return;
      const pt = unproject(...e.coordinate);
      if (Number.isFinite(pt.lon) && Number.isFinite(pt.lat)) {
        const b = terrain.b;
        const hb = JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS;
        const ho = JEZERO_HIRISE_ORTHO_BOUNDS;
        const cb = JEZERO_CTX_ORTHO_BOUNDS;
        setCursorCoord({
          lon: pt.lon,
          lat: pt.lat,
          inJezeroDem: pt.lon >= b[0] && pt.lon <= b[2] && pt.lat >= b[1] && pt.lat <= b[3],
          inHiriseDtm: pt.lon >= hb[0] && pt.lon <= hb[2] && pt.lat >= hb[1] && pt.lat <= hb[3],
          inHiriseOrtho: pt.lon >= ho[0] && pt.lon <= ho[2] && pt.lat >= ho[1] && pt.lat <= ho[3],
          inCtxOrtho: pt.lon >= cb[0] && pt.lon <= cb[2] && pt.lat >= cb[1] && pt.lat <= cb[3],
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
      callbacks.current.onPin(unproject(...e.coordinate));
    });
    map.on('pointerdrag', interact);
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
  }, [terrain]);

  // Multi-resolution satellite imagery & terrain analysis overlay synchronization
  useEffect(() => {
    if (!effectiveTerrain || !mapRef.current) return;
    const l = layers.current;
    const isAuto = base === 'auto' || base === 'imagery';
    const isHirise = base === 'hirise';
    const isCtx = base === 'ctx' || base === 'ctx_global';
    const isViking = base === 'viking' || base === 'global';
    const isRelief = base === 'relief';

    // 1. Global Viking MDIM 2.1 (232 m/px) is ALWAYS visible underneath so no blank grey regions ever appear
    l.wmtsVikingGlobal?.setVisible(true);
    l.wmtsVikingGlobal?.setOpacity(imageryOpacity);

    // 2. Regional CTX (6 m/px) is visible in Auto, CTX, and HiRISE modes (acting as seamless fallback outside HiRISE)
    const showCtx = isAuto || isCtx || isHirise;
    l.wmtsCtxRegional?.setVisible(showCtx);
    l.wmtsCtxRegional?.setOpacity(imageryOpacity);

    // 3. Local HiRISE (0.25 m/px) is visible in Auto and HiRISE modes
    const showHirise = isAuto || isHirise;
    l.wmtsHiriseLocal?.setVisible(showHirise);
    l.wmtsHiriseLocal?.setMaxResolution(isHirise ? 1200 : 180);
    l.wmtsHiriseLocal?.setOpacity(imageryOpacity);

    // 4. Separate Terrain Overlays derived from active DEM (1 m HiRISE DTM or 200 m MOLA-HRSC DEM)
    const demExtent = extentFor(effectiveTerrain.b);
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
        const orthoE = extentFor(JEZERO_HIRISE_ORTHO_BOUNDS);
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

        const dtmE = extentFor(JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS);
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
  }, [effectiveTerrain, base, hazards, coverage, showHillshade, showSlope, showRoughness, imageryOpacity, terrainOpacity, maxSlope, maxRough, live, showThemisOverlay]);

  // Science Target markers
  useEffect(() => {
    if (!mapRef.current || !layers.current.scienceTargetsLayer) return;
    const l = layers.current, src = l.scienceTargetsLayer.getSource();
    src.clear();
    l.scienceTargetsLayer.setVisible(Boolean(showScienceTargets));
    if (!showScienceTargets || !scienceTargets?.length) return;
    scienceTargets.forEach(tgt => {
      if (!Number.isFinite(tgt.lon) || !Number.isFinite(tgt.lat)) return;
      const f = new Feature({ geometry: new Point(project(tgt.lon, tgt.lat)), scienceTarget: tgt });
      f.setStyle((feature, resolution) => new Style({
        image: new CircleStyle({
          radius: resolution > 400 ? 3.5 : 5.5,
          fill: new Fill({ color: '#ffd166' }),
          stroke: new Stroke({ color: '#141008', width: 1.8 }),
        }),
        text: resolution > 400 ? undefined : new Text({
          text: `★ ${tgt.name} (${tgt.science_value_points} pts)`,
          font: '500 10px Inter, sans-serif',
          offsetY: 14,
          fill: new Fill({ color: '#ffe8a3' }),
          stroke: new Stroke({ color: '#0b1012', width: 3 }),
        }),
      }));
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
    const f = new Feature({ geometry: new Point(project(wp.lon, wp.lat)) });
    const statusLabel = roverReplayState.archive_status === 'EXACT_SOL_RECORD'
      ? `Sol ${wp.sol} (Exact)`
      : roverReplayState.archive_status === 'POST_ARCHIVE_CUTOFF'
        ? `Sol ${wp.sol} (Archive Cutoff)`
        : `Sol ${wp.sol} (Last Confirmed @ Sol ${roverReplayState.requested_sol})`;
    f.setStyle((feature, resolution) => [
      new Style({ image: new CircleStyle({ radius: resolution > 400 ? 10 : 16, stroke: new Stroke({ color: 'rgba(255,184,103,0.45)', width: 2, lineDash: [4, 4] }) }) }),
      new Style({
        image: new CircleStyle({ radius: resolution > 400 ? 5 : 7.5, fill: new Fill({ color: '#ffb867' }), stroke: new Stroke({ color: '#181209', width: 2 }) }),
        text: resolution > 400 ? undefined : new Text({
          text: `Perseverance Replay · ${statusLabel}`,
          font: '600 11px Inter, sans-serif',
          offsetY: -20,
          fill: new Fill({ color: '#ffe2b8' }),
          stroke: new Stroke({ color: '#0b1014', width: 3.5 }),
        }),
      }),
    ]);
    src.addFeature(f);
  }, [terrain, roverReplayState]);

  useEffect(() => {
    if (!mapRef.current) return;
    const src = layers.current.pins.getSource();
    src.clear();
    [[start, 'A'], [destination, 'B']].forEach(([p, label]) => {
      if (!Number.isFinite(Number(p.lon)) || !Number.isFinite(Number(p.lat))) return;
      const f = new Feature(new Point(project(Number(p.lon), Number(p.lat))));
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
      const primary = r.score_rank === 1, line = new LineString(r.geometry.coordinates.map(c => project(c[0], c[1]))), f = new Feature({ geometry: line, routeId: r.route_id });
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
            const a = new Feature(new LineString([project(s.from_coord.lon, s.from_coord.lat), project(s.to_coord.lon, s.to_coord.lat)]));
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
      const line = new LineString(route.geometry.coordinates.map(c => project(c[0], c[1])));
      midLabel.current.getElement().textContent = (route.summary.total_distance_meters / 1000).toFixed(2) + ' km · ' + (Number.isFinite(route.summary.estimated_duration_hours) ? route.summary.estimated_duration_hours.toFixed(1) + ' h' : 'ETA unavailable');
      midLabel.current.setPosition(line.getCoordinateAt(0.5));
    } else midLabel.current?.setPosition(undefined);
  }, [terrain, response, selected, showRoute, showAlternatives, hoveredRoute, view3d]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, source = l.historyLayer.getSource(), pins = l.historyPins.getSource();
    source.clear();
    pins.clear();
    l.historyLayer.setVisible(showHistory);
    l.historyPins.setVisible(showHistory && showWaypoints);
    for (const drive of drives) {
      const f = new Feature({ geometry: new LineString(drive.geometry.coordinates.map(c => project(c[0], c[1]))), driveRecord: drive });
      f.setStyle([new Style({ stroke: new Stroke({ color: '#101318ed', width: 8, lineCap: 'round', lineJoin: 'round' }) }), new Style({ stroke: new Stroke({ color: '#ffb867', width: 4, lineCap: 'round', lineJoin: 'round' }) }), new Style({ stroke: new Stroke({ color: '#ffe1aa', width: 1 }) })]);
      source.addFeature(f);
    }
    waypoints.forEach((w, i) => {
      const latest = i === waypoints.length - 1, chosen = w === waypoint, c = w.geometry.coordinates, f = new Feature({ geometry: new Point(project(c[0], c[1])), waypoint: w });
      f.setStyle((feature, resolution) => {
        const ring = latest || chosen || i % 25 === 0 || resolution < 2;
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
    const coords = drives.flatMap(f => f.geometry.coordinates).map(c => project(c[0], c[1]));
    if (!coords.length || !mapRef.current) return;
    const xs = coords.map(p => p[0]), ys = coords.map(p => p[1]), mobile = innerWidth < 850;
    mapRef.current.getView().fit([Math.min(...xs) - 250, Math.min(...ys) - 250, Math.max(...xs) + 250, Math.max(...ys) + 250], { padding: mobile ? [200, 75, 150, 25] : [90, 125, 160, 395], duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450, minResolution: 0.8 });
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
    view.setCenter(project(coord.lon, coord.lat));
    if (coord.resolution) {
      view.setResolution(coord.resolution);
    } else {
      view.setZoom(coord.zoom || 11);
    }
  };
  useEffect(() => { if (actionsRef) actionsRef.current = { fit, zoom, focus }; }, [view3d, terrain, historyMode, drives]);

  useEffect(() => {
    if (historyMode || !response || !mapRef.current) return;
    const ps = response.routes.flatMap(r => r.geometry.coordinates).map(c => project(c[0], c[1])), xs = ps.map(p => p[0]), ys = ps.map(p => p[1]);
    if (!ps.length) return;
    const ext = [Math.min(...xs) - 600, Math.min(...ys) - 600, Math.max(...xs) + 600, Math.max(...ys) + 600];
    const mobile = window.innerWidth < 850;
    mapRef.current.getView().fit(ext, { padding: mobile ? [100, 50, 140, 50] : [85, 320, 140, 370], duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500, minResolution: 1 });
  }, [fitToken, historyMode]);

  useEffect(() => {
    if (!mapRef.current) return;
    const s = layers.current.hoverLayer.getSource();
    s.clear();
    if (hover) {
      const f = new Feature(new Point(project(hover[0], hover[1])));
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
      const f = new Feature({ geometry: new Point(project(ship.lon, ship.lat)), spacecraftId: ship.spacecraft_id });
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
            const f = new Feature(new LineString(seg.map(c => project(c[0], c[1]))));
            f.setStyle(new Style({ stroke: new Stroke({ color: '#64dfdf66', width: 1.5, lineDash: [6, 6] }) }));
            src.addFeature(f);
          }
          seg = [];
        }
        seg.push([pt.lon, pt.lat]);
      }
      if (seg.length > 1) {
        const f = new Feature(new LineString(seg.map(c => project(c[0], c[1]))));
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
      const f = new Feature({ geometry: new Polygon([coords.map(c => project(c[0], c[1]))]), observationId: obs.observation_id });
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
      const poly = new Polygon([coords.map(c => project(c[0], c[1]))]);
      const f = new Feature({ geometry: poly, observationId: focusedProduct.product_id });
      f.setStyle(new Style({ stroke: new Stroke({ color: '#64dfdf', width: 3 }), fill: new Fill({ color: 'rgba(100,223,223,0.2)' }), text: new Text({ text: `NASA: ${focusedProduct.product_id} (${focusedProduct.instrument})`, font: '600 11px Inter, sans-serif', offsetY: -12, fill: new Fill({ color: '#a0f0f0' }), stroke: new Stroke({ color: '#0a1412', width: 3 }) }) }));
      src.addFeature(f);
      mapRef.current.getView().animate({ center: poly.getInteriorPoint().getCoordinates(), zoom: 10, duration: 450 });
    }
  }, [focusedProduct]);

  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current, src = l.curiosityLayer.getSource();
    src.clear();
    l.curiosityLayer.setVisible(showCuriosity);
    if (!showCuriosity || !curiosityTraverse) return;
    for (const d of curiosityTraverse.features || []) {
      const f = new Feature({ geometry: new LineString(d.geometry.coordinates.map(c => project(c[0], c[1]))), driveRecord: d });
      f.setStyle([new Style({ stroke: new Stroke({ color: '#101318ed', width: 6, lineCap: 'round' }) }), new Style({ stroke: new Stroke({ color: '#a78bfa', width: 3, lineCap: 'round' }) })]);
      src.addFeature(f);
    }
    if (curiosityWaypoints?.length) {
      const last = curiosityWaypoints[curiosityWaypoints.length - 1], c = last.geometry.coordinates, f = new Feature(new Point(project(c[0], c[1])));
      f.setStyle(new Style({ image: new CircleStyle({ radius: 8, fill: new Fill({ color: '#a78bfa' }), stroke: new Stroke({ color: '#111827', width: 2 }) }), text: new Text({ text: 'Curiosity (MSL)', font: '600 11px Inter, sans-serif', offsetY: -16, fill: new Fill({ color: '#e9d5ff' }), stroke: new Stroke({ color: '#090e17', width: 3 }) }) }));
      src.addFeature(f);
    }
  }, [terrain, showCuriosity, curiosityTraverse, curiosityWaypoints]);

  // Determine exact validated imagery source label based on loaded tiles & current view
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

  const hiriseTilesOk = wmtsStats.byLayer.hirise.loaded > 0;
  const ctxTilesOk = wmtsStats.byLayer.ctx.loaded > 0;
  const vikingTilesOk = wmtsStats.byLayer.viking.loaded > 0;

  let activeImageryLabel = 'NASA Viking global imagery · 232 m/px';
  if (base === 'relief') {
    activeImageryLabel = 'DEM Shaded Relief + NASA Viking global imagery · 232 m/px';
  } else if (base === 'viking' || base === 'global') {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m.sourceLabel} (DOI: 10.5066/F71V5C67)`;
  } else if (base === 'ctx' || base === 'ctx_global') {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.sourceLabel} (DOI: 10.5066/P9GV1ND3)`;
  } else if (base === 'hirise') {
    activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.sourceLabel} (DOI: 10.5066/P9QJDP48)`;
  } else {
    // Automatic multi-resolution mode
    if (inHiriseView && viewState.resolution <= 250) {
      activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.hirise_jezero_25cm.sourceLabel} (DOI: 10.5066/P9QJDP48)`;
    } else if (inCtxView && viewState.resolution <= 2500) {
      activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.ctx_jezero_6m.sourceLabel} (DOI: 10.5066/P9GV1ND3)`;
    } else {
      activeImageryLabel = `${AUTHORITATIVE_MARS_IMAGERY_CATALOG.viking_global_232m.sourceLabel} (DOI: 10.5066/F71V5C67)`;
    }
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
          position: 'absolute',
          top: '54px',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 28,
          display: 'flex',
          gap: '6px',
          padding: '5px 8px',
          borderRadius: '999px',
          background: 'rgba(10,16,20,0.84)',
          border: '1px solid rgba(255,255,255,0.1)',
          backdropFilter: 'blur(12px)',
          flexWrap: 'wrap',
          maxWidth: 'calc(100vw - 140px)',
        }}
      >
        {PLANETARY_BOOKMARKS.map(bm => (
          <button
            key={bm.id}
            type="button"
            onClick={() => {
              interact();
              focus({ lon: bm.lon, lat: bm.lat, resolution: bm.resolution });
              onSelectBookmark?.(bm);
            }}
            style={{
              background: activeBookmark === bm.id ? 'rgba(92,255,176,0.18)' : 'transparent',
              color: activeBookmark === bm.id ? '#9becbf' : '#c6d4d1',
              border: activeBookmark === bm.id ? '1px solid rgba(92,255,176,0.45)' : '1px solid transparent',
              borderRadius: '999px',
              padding: '3px 9px',
              fontSize: '11px',
              fontWeight: activeBookmark === bm.id ? 600 : 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
            }}
            title={bm.sub}
          >
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: bm.hasDem ? '#5cffb0' : '#64dfdf' }} />
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
      {(pick || hint) && <div className="map-instruction glass">{pick ? `Click terrain to place ${pick === 'start' ? 'start A' : 'destination B'}` : 'Drag to explore Mars WMTS (Viking 232m → CTX 6m → HiRISE 0.25m). Scroll to zoom.'}</div>}
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
