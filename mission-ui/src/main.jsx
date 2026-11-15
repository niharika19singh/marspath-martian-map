import {
  validateTraverse,
  visibleDrives,
  visibleWaypoints,
  windowedDrives,
  windowedWaypoints,
  latestWaypointThroughSol,
  traverseStats,
  exportTraverse,
} from './traverse.js';
import { TraversePanel, TraverseTimeline } from './TraversePanel.jsx';
import { ConditionsPanel } from './ConditionsPanel.jsx';
import { computeClientMars24 } from './conditions.js';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import 'ol/ol.css';
import './style.css';
import MapView from './MapView.jsx';
import Profile from './Profile.jsx';
import { exportGeoJSON, exportCSV, exportJSON, exportMissionBriefMarkdown, exportMissionConfigJSON, exportPDF } from './export.js';
import { buildTerrain } from './terrain.js';
import Icon from './Icons.jsx';
import {
  resolveInitialApiUrl,
  resolveTerrainProvenance,
  resolveAlternativeShortfall,
  canSubmitRoute,
  validateRouteExecutionPreconditions,
  getAssetUrl
} from './integration.js';
import IntelligencePanel from './IntelligencePanel.jsx';
import MissionIntelligencePanel from './MissionIntelligencePanel.jsx';
import NasaDataPanel from './NasaDataPanel.jsx';
import CloudAiPanel from './CloudAiPanel.jsx';
import VisorHUD from './VisorHUD.jsx';
import {
  HABITAT_BASE_COORD,
  SPE_SEVERITY_LEVELS,
  JEZERO_RADIATION_SHELTERS,
  PLANETARY_PROTECTION_ZONES,
  AUTHENTIC_NASA_SURFACE_IMAGERY,
  computeMarswalkSurvivabilityScore,
  assessWalkBackSafety,
  evaluateRoutePlanetaryProtection,
  evaluateRFCommunications,
  evaluateCompoundRisk,
  findNearestShelter,
} from './survivability.js';
import { verifyCoordinateDatasetCoverage } from './wmts_capabilities.js';
import {
  JEZERO_SCIENCE_TARGETS_CLIENT,
  MISSION_PRESETS_CLIENT,
  enrichResponseWithMasterSpec
} from './planning_enrichment.js';
import {
  fetchSpacecraftList,
  fetchGroundTrack,
  fetchOrbitalObservations,
  fetchRoversList,
  fetchIntelligenceTimeline,
  propagateKeplerian
} from './intelligence.js';

const INITIAL = { start: { lon: 77.40, lat: 18.39 }, destination: { lon: 77.44, lat: 18.42 } };
const fmt = (n, d = 1) => (Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—');
const pct = (n, d = 0) => (Number.isFinite(n) ? (n * 100).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) + '%' : '—');

const initialRequest = {
  ...INITIAL,
  algorithm: 'astar',
  mode: 'balanced',
  constraints: { max_slope_deg: 20, max_roughness: 0.85, avoid_unobserved_terrain: true },
  science_waypoints: [],
  num_alternatives: 3,
  crs_identifier: 'IAU2000:49900',
  cost_mode: 'directional',
  effort_model: 'slope_penalty',
  suit_load_factor: 1.0,
  max_eva_hours: 8.0,
  return_constraint_mode: 'flag',
  departure_utc: '2026-06-15T08:00:00Z',
  daylight_buffer_minutes: 0,
  rescue_enabled: true,
  rescue_threshold_minutes: 30,
};

function Dialog({ onClose, children, label = 'Close dialog' }) {
  const ref = useRef();
  useEffect(() => {
    ref.current?.showModal();
    ref.current?.querySelector('input[autofocus]')?.focus();
  }, []);
  return (
    <dialog
      ref={ref}
      className="settings-dialog"
      onCancel={e => {
        e.preventDefault();
        onClose();
      }}
    >
      <button className="close-dialog" onClick={onClose} aria-label={label}>
        ×
      </button>
      {children}
    </dialog>
  );
}

function App() {
  const [missionView, setMissionView] = useState(() => {
    const v = new URLSearchParams(location.search).get('view');
    return v === 'planner' || v === 'conditions' || v === 'intelligence' || v === 'nasa-data' || v === 'cloud-ai' ? v : 'history';
  });
  const [traverse, setTraverse] = useState(null);
  const [waypointData, setWaypointData] = useState(null);
  const [traverseError, setTraverseError] = useState('');
  const [solCut, setSolCut] = useState(2022);
  const [showHistory, setShowHistory] = useState(true);
  const [showWaypoints, setShowWaypoints] = useState(true);
  const [historyFit, setHistoryFit] = useState(0);
  const [waypoint, setWaypoint] = useState(null);
  const [focusedProduct, setFocusedProduct] = useState(null);

  // Live Intelligence, Curiosity & Orbiter State
  const [spacecraftList, setSpacecraftList] = useState([]);
  const [selectedSpacecraft, setSelectedSpacecraft] = useState('mro');
  const [spacecraftPositions, setSpacecraftPositions] = useState([]);
  const [groundTracks, setGroundTracks] = useState([]);
  const [orbitalObservations, setOrbitalObservations] = useState([]);
  const [selectedObservation, setSelectedObservation] = useState(null);
  const [roversList, setRoversList] = useState([]);
  const [selectedRover, setSelectedRover] = useState('perseverance');
  const [curiosityTraverse, setCuriosityTraverse] = useState(null);
  const [curiosityWaypoints, setCuriosityWaypoints] = useState(null);
  const [timelineEvents, setTimelineEvents] = useState([]);
  const [showOrbiters, setShowOrbiters] = useState(false);
  const [showGroundTracks, setShowGroundTracks] = useState(false);
  const [showFootprints, setShowFootprints] = useState(false);
  const [showCuriosity, setShowCuriosity] = useState(false);
  const [showThemisOverlay, setShowThemisOverlay] = useState(false);
  const [showScienceTargets, setShowScienceTargets] = useState(true);
  const [selectedPresetId, setSelectedPresetId] = useState('flagship_jezero_expedition');
  const [activeProfileTab, setActiveProfileTab] = useState('elevation');

  // Mars Now & Conditions state
  const [inspectCoord, setInspectCoord] = useState({ lon: 77.40, lat: 18.39 });
  const [timeMode, setTimeMode] = useState('now');
  const [customUtc, setCustomUtc] = useState(() => new Date().toISOString());
  const [customSol, setCustomSol] = useState(2022);
  const [vikingOpacity, setVikingOpacity] = useState(1.0);
  const [ctxOpacity, setCtxOpacity] = useState(1.0);
  const [hiriseOpacity, setHiriseOpacity] = useState(1.0);
  const [molaOpacity, setMolaOpacity] = useState(0.78);
  const [terrainOpacity, setTerrainOpacity] = useState(0.75);

  // Astronaut EVA & Survivability System State
  const [visorActive, setVisorActive] = useState(false);
  const [speActive, setSpeActive] = useState(false);
  const [speSeverity, setSpeSeverity] = useState('S2');
  const [selectedProtectionZone, setSelectedProtectionZone] = useState(null);
  const [scoutRoverModalOpen, setScoutRoverModalOpen] = useState(false);
  const [scoutRoverDispatched, setScoutRoverDispatched] = useState(false);
  const [selectedNasaPhoto, setSelectedNasaPhoto] = useState(null);
  const [showWalkBackEnvelopes, setShowWalkBackEnvelopes] = useState(true);
  const [showPlanetaryProtection, setShowPlanetaryProtection] = useState(true);
  const [showAuthenticPhotos, setShowAuthenticPhotos] = useState(true);

  function handleSelectWaypoint(w) {
    setWaypoint(w);
    if (w && w.geometry?.coordinates) {
      setInspectCoord({
        lon: Number(w.geometry.coordinates[0].toFixed(5)),
        lat: Number(w.geometry.coordinates[1].toFixed(5)),
      });
    }
  }

  function inspectRoverPosition() {
    const wp = waypoint || (waypointData && waypointData.length ? waypointData[waypointData.length - 1] : null);
    if (wp && wp.geometry?.coordinates) {
      const [lon, lat] = wp.geometry.coordinates;
      setInspectCoord({ lon: Number(lon.toFixed(5)), lat: Number(lat.toFixed(5)) });
      mapActions.current?.focus?.({ lon, lat, zoom: 14 });
    }
  }

  useEffect(() => {
    if (typeof window !== 'undefined') {
      window.__openScoutRoverModal = () => setScoutRoverModalOpen(true);
      window.__selectProtectionZone = (z) => setSelectedProtectionZone(z || PLANETARY_PROTECTION_ZONES[0]);
      window.__selectNasaPhoto = (p) => setSelectedNasaPhoto(p || Object.values(AUTHENTIC_NASA_SURFACE_IMAGERY)[0]);
    }
  }, []);

  const clientMars24Quick = useMemo(() => {
    try {
      return computeClientMars24(inspectCoord.lat, inspectCoord.lon, new Date());
    } catch {
      return { ltst_hms: '12:00:00', daylight_state: 'DAYLIGHT' };
    }
  }, [inspectCoord.lat, inspectCoord.lon]);

  const historyMode = missionView === 'history';
  const intelligenceMode = missionView === 'intelligence';
  const fusionMode = missionView === 'fusion';
  const nasaDataMode = missionView === 'nasa-data';
  const cloudAiMode = missionView === 'cloud-ai';
  const plannerMode = missionView === 'planner';
  const maxSol = useMemo(() => (traverse?.features ? Math.max(...traverse.features.map(f => f.properties.sol)) : 2022), [traverse]);
  const minSol = useMemo(() => (traverse?.features ? Math.min(...traverse.features.map(f => f.properties.sol)) : 14), [traverse]);

  // Windowed 15-sol trailing window drives & waypoints: [solCut - 14, solCut]
  const highlightedDrives = useMemo(() => windowedDrives(traverse, solCut, 15), [traverse, solCut]);
  const highlightedWaypoints = useMemo(() => windowedWaypoints(waypointData, solCut, 15), [waypointData, solCut]);
  const activeRoverWp = useMemo(() => latestWaypointThroughSol(waypointData, solCut), [waypointData, solCut]);
  const windowStats = useMemo(() => traverseStats(highlightedDrives, highlightedWaypoints), [highlightedDrives, highlightedWaypoints]);
  const totalArchiveStats = useMemo(() => traverseStats(traverse?.features || [], waypointData || []), [traverse, waypointData]);
  const drivesThroughSol = useMemo(() => visibleDrives(traverse, solCut), [traverse, solCut]);
  const historyStats = useMemo(() => traverseStats(drivesThroughSol, visibleWaypoints(waypointData, solCut)), [drivesThroughSol, waypointData, solCut]);

  useEffect(() => {
    let cancelled = false;
    async function loadTraverseData() {
      let t = null;
      let w = null;
      // Gracefully attempt to refresh from official NASA/JPL MMGIS feed if accessible
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3500);
        const [onlineT, onlineW] = await Promise.all([
          fetch('https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json', { signal: controller.signal }),
          fetch('https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json', { signal: controller.signal }),
        ]);
        clearTimeout(timeout);
        if (onlineT.ok && onlineW.ok) {
          const [parsedT, parsedW] = await Promise.all([onlineT.json(), onlineW.json()]);
          validateTraverse(parsedT);
          t = parsedT;
          w = parsedW;
        }
      } catch (err) {
        // Upstream unavailable or blocked; fall back to verified bundled snapshot
      }

      // If upstream failed or returned empty, load validated local snapshot
      if (!t || !w) {
        try {
          const rs = await Promise.all([
            fetch(getAssetUrl('/mission-data/perseverance-traverse.geojson')),
            fetch(getAssetUrl('/mission-data/perseverance-waypoints.geojson')),
          ]);
          if (rs.some(r => !r.ok)) throw Error('The recorded traverse could not load.');
          const [parsedT, parsedW] = await Promise.all(rs.map(r => r.json()));
          validateTraverse(parsedT);
          t = parsedT;
          w = parsedW;
        } catch (err) {
          if (!cancelled) setTraverseError(err.message);
          return;
        }
      }

      if (cancelled) return;
      setTraverse(t);
      setWaypointData(w);
      const maxS = Math.max(...t.features.map(f => f.properties.sol));
      setSolCut(maxS);
      setHistoryFit(n => n + 1);
    }

    loadTraverseData();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch(getAssetUrl('/mission-data/curiosity-traverse.geojson')),
      fetch(getAssetUrl('/mission-data/curiosity-waypoints.geojson'))
    ])
      .then(async rs => {
        if (rs.some(r => !r.ok)) return;
        const [t, w] = await Promise.all(rs.map(r => r.json()));
        if (!cancelled) {
          setCuriosityTraverse(t);
          setCuriosityWaypoints(w.features || w);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  function switchMission(mode) {
    setMissionView(mode);
    setLeftOpen(true);
    setShowRoute(mode === 'planner');
    setProfileExpanded(false);
    setLayersOpen(false);
    setPick(null);
    const url = new URL(window.location);
    if (mode === 'history') url.searchParams.delete('view');
    else url.searchParams.set('view', mode);
    window.history.replaceState({}, '', url);
    if (mode === 'history') setHistoryFit(n => n + 1);
    else setFitToken(n => n + 1);
  }

  function exportHistory() {
    if (!traverse) return;
    const blob = new Blob([JSON.stringify(exportTraverse(traverse, solCut), null, 2)], { type: 'application/geo+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'perseverance-recorded-through-sol-' + solCut + '.geojson';
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Recorded traverse exported with source and snapshot metadata.');
  }

  function planFromWaypoint(w) {
    invalidate();
    const c = w.geometry.coordinates;
    setStart({ lon: c[0], lat: c[1] });
    switchMission('planner');
  }

  function showAllHistory() {
    setSolCut(maxSol);
    setWaypoint(null);
    setHistoryFit(n => n + 1);
  }

  // Planner inputs & options
  const [raw, setRaw] = useState(null);
  const [hiriseRaw, setHiriseRaw] = useState(null);
  const [hiriseLoadStatus, setHiriseLoadStatus] = useState('loading');
  const [hiriseLoadReason, setHiriseLoadReason] = useState('Verifying USGS HiRISE 1 m DTM (10.5066/P9REJ9JN)…');
  const [demSourcePreference, setDemSourcePreference] = useState('auto');
  const [loadError, setLoadError] = useState('');
  const [start, setStart] = useState(INITIAL.start);
  const [destination, setDestination] = useState(INITIAL.destination);
  const [scienceWaypoints, setScienceWaypoints] = useState([]);
  const [pick, setPick] = useState(null);
  const [algorithm, setAlgorithm] = useState('astar');
  const [mode, setMode] = useState('balanced');
  const [maxSlope, setMaxSlope] = useState(20);
  const [maxRough, setMaxRough] = useState(0.85);
  const [avoidUnobserved, setAvoidUnobserved] = useState(true);
  const [numAlternatives, setNumAlternatives] = useState(3);
  const [robustnessEnabled, setRobustnessEnabled] = useState(false);
  const [robustnessConfig, setRobustnessConfig] = useState({
    vertical_sigma_m: 1.5,
    correlation_length_m: 400.0,
    scenario_count: 5,
    seed: 42,
    cost_regret_threshold_fraction: 0.05
  });

  // Layer & Stage 1 safety controls
  const [base, setBase] = useState('auto');
  const [activeBookmark, setActiveBookmark] = useState('jezero');
  const [showViking, setShowViking] = useState(true);
  const [showCtx, setShowCtx] = useState(false);
  const [showHirise, setShowHirise] = useState(false);
  const [showMolaTerrain, setShowMolaTerrain] = useState(false);
  const [showHillshade, setShowHillshade] = useState(false);
  const [showSlope, setShowSlope] = useState(false);
  const [showRoughness, setShowRoughness] = useState(false);
  const [hazards, setHazards] = useState(false);
  const [coverage, setCoverage] = useState(false);
  const [costMode, setCostMode] = useState('directional');
  const [effortModel, setEffortModel] = useState('slope_penalty');
  const [suitLoadFactor, setSuitLoadFactor] = useState(1.0);
  const [evaBudgetHours, setEvaBudgetHours] = useState(8.0);
  const [returnConstraintMode, setReturnConstraintMode] = useState('flag');
  const [departureUtc, setDepartureUtc] = useState('2026-06-15T08:00:00Z');
  const [daylightBufferMinutes, setDaylightBufferMinutes] = useState(0);
  const [rescueThresholdMinutes, setRescueThresholdMinutes] = useState(30);
  const [showReachableZone, setShowReachableZone] = useState(false);
  const [showRescueMap, setShowRescueMap] = useState(false);

  // Results & analysis state
  const [result, setResult] = useState(null);
  const [previousResult, setPreviousResult] = useState(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [hover, setHover] = useState(null);
  const [fitToken, setFitToken] = useState(0);
  const [sourceMode, setSourceMode] = useState('browser');
  const [api, setApi] = useState(null);
  const [apiConnectionState, setApiConnectionState] = useState('disconnected');
  const [analysisTab, setAnalysisTab] = useState('overview');

  // Settings & dialogs
  const [showSettings, setShowSettings] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => {
    const saved = resolveInitialApiUrl();
    if (saved) return saved;
    if (typeof window !== 'undefined' && !['localhost', '127.0.0.1'].includes(window.location.hostname)) {
      return window.location.origin;
    }
    return 'http://localhost:8000';
  });
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [exportFormat, setExportFormat] = useState('json');
  const [notice, setNotice] = useState('');

  // UI Panels
  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth > 760);
  const [rightExpanded, setRightExpanded] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [robustnessSettingsOpen, setRobustnessSettingsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(true);
  const [profileExpanded, setProfileExpanded] = useState(false);
  const [layersOpen, setLayersOpen] = useState(false);
  const [showRoute, setShowRoute] = useState(() => new URLSearchParams(location.search).get('view') === 'planner');
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [hoveredRoute, setHoveredRoute] = useState(null);
  const [view3d, setView3d] = useState(false);
  const [exaggeration, setExaggeration] = useState(6);
  const [commandsOpen, setCommandsOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState('');
  const [commandIndex, setCommandIndex] = useState(0);

  const mapActions = useRef(null);
  const routeForm = useRef(null);
  const worker = useRef(null);
  const sequence = useRef(0);
  const abort = useRef(null);
  const lastRequest = useRef(initialRequest);

  const terrain = useMemo(() => (raw ? buildTerrain(raw) : null), [raw]);
  const hiriseTerrain = useMemo(() => (hiriseRaw ? buildTerrain(hiriseRaw) : null), [hiriseRaw]);
  const coordCoverage = useMemo(() => verifyCoordinateDatasetCoverage(start, destination), [start, destination]);
  const activeDemTerrain = useMemo(() => {
    if (demSourcePreference === 'mola_hrsc_200m') return terrain;
    if (hiriseTerrain && coordCoverage.bothInLocalHiriseDtmCorridor) return hiriseTerrain;
    return terrain;
  }, [demSourcePreference, hiriseTerrain, terrain, coordCoverage.bothInLocalHiriseDtmCorridor]);
  const active = result?.routes.find(r => r.route_id === selected) || result?.routes[0];
  const live = sourceMode === 'api';

  // Astronaut EVA & Survivability Engine Calculations
  const survivabilityScore = useMemo(() => computeMarswalkSurvivabilityScore(active, {
    speActive,
    speSeverity,
    evaBudgetHours,
  }), [active, speActive, speSeverity, evaBudgetHours]);

  const baselineSurvivabilityScore = useMemo(() => computeMarswalkSurvivabilityScore(active, {
    speActive: false,
    evaBudgetHours,
  }), [active, evaBudgetHours]);

  const walkBackSafety = useMemo(() => assessWalkBackSafety(destination, HABITAT_BASE_COORD, {
    evaBudgetHours,
  }), [destination, evaBudgetHours]);

  const protectionCheck = useMemo(() => evaluateRoutePlanetaryProtection(active?.coordinates || []), [active]);

  const rfComms = useMemo(() => evaluateRFCommunications(active?.summary || {}), [active]);

  const compoundRisk = useMemo(() => evaluateCompoundRisk(active?.summary || {}, { speActive, speSeverity }), [active, speActive, speSeverity]);

  const nearestShelter = useMemo(() => findNearestShelter(destination || HABITAT_BASE_COORD), [destination]);

  // Load Live Mars Intelligence datasets (orbiters, tracks, footprints, timeline)
  useEffect(() => {
    let cancelled = false;
    const backend = api?.url || '';
    fetchSpacecraftList(backend).then(scs => {
      if (!cancelled && scs?.length) {
        setSpacecraftList(scs);
        setSelectedSpacecraft(prev => prev || scs[0]?.spacecraft_id || 'mro');
      }
    }).catch(() => {});

    fetchRoversList(backend).then(rl => {
      if (!cancelled && rl?.length) {
        setRoversList(rl);
        setSelectedRover(prev => prev || rl[0]?.rover_id || 'perseverance');
      }
    }).catch(() => {});

    fetchOrbitalObservations(backend).then(obs => {
      if (!cancelled && obs?.length) setOrbitalObservations(obs);
    }).catch(() => {});

    fetchIntelligenceTimeline(25, backend).then(tl => {
      if (!cancelled && tl?.length) setTimelineEvents(tl);
    }).catch(() => {});

    Promise.all(['mro', 'ody', 'mex', 'tgo', 'maven'].map(id => fetchGroundTrack(id, 120, 60, backend)))
      .then(tracks => {
        if (!cancelled) setGroundTracks(tracks.filter(Boolean));
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [api]);

  // Real-time orbiter propagation ticker
  useEffect(() => {
    const updateOrbiterPositions = () => {
      const now = new Date();
      setSpacecraftPositions(['mro', 'ody', 'mex', 'tgo', 'maven'].map(id => propagateKeplerian(id, now)));
    };
    updateOrbiterPositions();
    const timer = setInterval(updateOrbiterPositions, 3500);
    return () => clearInterval(timer);
  }, []);

  const provenance = useMemo(
    () => resolveTerrainProvenance({ live, raw, loadError, api, result, active }),
    [live, raw, loadError, api, result, active]
  );

  const shortfall = useMemo(
    () => resolveAlternativeShortfall(result, lastRequest.current?.num_alternatives),
    [result]
  );

  function accept(response, request) {
    if (!Array.isArray(response.routes) || !response.routes.length || response.routes.some(r => !Array.isArray(r.geometry?.coordinates))) {
      throw new Error('The server returned no usable route geometry.');
    }
    const enriched = enrichResponseWithMasterSpec(response, activeDemTerrain || terrain, request);
    setResult(enriched);
    setPreviousResult(null);
    setSelected(enriched.routes[0].route_id);
    lastRequest.current = request;
    setFitToken(n => n + 1);
    setBusy(false);
    setError('');
  }

  // Load bundled terrain rasters (MOLA-HRSC 200 m + USGS HiRISE 1 m corridor DTM) for local worker & client analytics
  useEffect(() => {
    let disposed = false;
    Promise.all([
      fetch(getAssetUrl('/mission-data/jezero-dem.json')),
      fetch(getAssetUrl('/mission-data/jezero-dem.sha256')),
      fetch(getAssetUrl('/mission-data/jezero-hirise-dtm.json')).catch(() => null),
      fetch(getAssetUrl('/mission-data/jezero-hirise-dtm.sha256')).catch(() => null)
    ])
      .then(async ([r, h, hr, hh]) => {
        if (!r.ok || !h.ok) throw new Error('The terrain dataset could not be loaded. Refresh this page to retry.');
        const text = await r.text();
        const expected = (await h.text()).trim();
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        const actual = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
        if (actual !== expected) throw new Error('Terrain file integrity check failed. No routes were computed.');
        const data = { ...JSON.parse(text), local_integrity_verified: true, file_sha256: actual };

        let hiData = null;
        if (hr?.ok && hh?.ok) {
          try {
            const hiText = await hr.text();
            const hiExpected = (await hh.text()).trim();
            const hiDigest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(hiText));
            const hiActual = Array.from(new Uint8Array(hiDigest), b => b.toString(16).padStart(2, '0')).join('');
            if (hiActual === hiExpected) {
              hiData = { ...JSON.parse(hiText), local_integrity_verified: true, file_sha256: hiActual };
              if (!disposed) {
                setHiriseRaw(hiData);
                setHiriseLoadStatus('ready');
                setHiriseLoadReason('USGS HiRISE 1 m DTM (DOI: 10.5066/P9REJ9JN) validated and ready.');
              }
            } else if (!disposed) {
              setHiriseLoadStatus('invalid_metadata');
              setHiriseLoadReason('HiRISE DTM SHA-256 checksum mismatch.');
            }
          } catch (err) {
            if (!disposed) {
              setHiriseLoadStatus('processing_failure');
              setHiriseLoadReason(`Failed to parse HiRISE DTM: ${err.message}`);
            }
          }
        } else if (!disposed) {
          setHiriseLoadStatus('missing_file');
          setHiriseLoadReason('USGS HiRISE 1 m DTM asset (/mission-data/jezero-hirise-dtm.json) not found.');
        }

        if (disposed) return;
        setRaw(data);

        const w = new Worker(new URL('./routing.worker.js', import.meta.url), { type: 'module' });
        worker.current = w;
        w.onmessage = e => {
          if (e.data.id !== sequence.current) return;
          if (e.data.error) {
            setError(e.data.error);
            setBusy(false);
            return;
          }
          try {
            accept(e.data.result, lastRequest.current);
          } catch (error) {
            setError(error.message);
            setBusy(false);
          }
        };
        w.onerror = () => {
          setError('The route worker could not run. Refresh the page or connect a Python backend.');
          setBusy(false);
        };
        setBusy(true);
        const initDem = data;
        const initReq = { ...initialRequest, preferred_dem_source: hiData ? 'hirise_1m' : 'mola_hrsc_200m' };
        lastRequest.current = initReq;
        w.postMessage({ id: ++sequence.current, raw: initDem, request: initReq });
      })
      .catch(e => {
        if (!disposed) setLoadError(e.message);
      });

    return () => {
      disposed = true;
      worker.current?.terminate();
      abort.current?.abort();
    };
  }, []);

  // Silently probe same-origin proxied Python backend when running on a deployed host
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const isLocalHost = ['localhost', '127.0.0.1'].includes(window.location.hostname);
    if (isLocalHost && !resolveInitialApiUrl()) return;
    connect({ silent: true });
  }, []);

  function invalidate() {
    sequence.current++;
    abort.current?.abort();
    setBusy(false);
    setError('');
    setNotice('');
  }

  function mapPin(p) {
    if (!pick) {
      setInspectCoord({ lon: Number(p.lon.toFixed(5)), lat: Number(p.lat.toFixed(5)) });
      return;
    }
    invalidate();
    const v = { lon: Number(p.lon.toFixed(5)), lat: Number(p.lat.toFixed(5)) };
    if (pick === 'start') {
      setStart(v);
      setPick('destination');
    } else if (pick === 'destination') {
      setDestination(v);
      setPick(null);
    } else if (pick === 'waypoint') {
      setScienceWaypoints(wps => [...wps, v]);
      setPick(null);
    } else if (pick.startsWith('waypoint-')) {
      const idx = Number(pick.replace('waypoint-', ''));
      setScienceWaypoints(wps => wps.map((w, i) => (i === idx ? v : w)));
      setPick(null);
    }
  }

  function addWaypoint() {
    invalidate();
    const nextLon = Number((Number(destination.lon) + Number(start.lon)) / 2).toFixed(5);
    const nextLat = Number((Number(destination.lat) + Number(start.lat)) / 2).toFixed(5);
    setScienceWaypoints(wps => [...wps, { lon: Number(nextLon), lat: Number(nextLat) }]);
  }

  function removeWaypoint(idx) {
    invalidate();
    setScienceWaypoints(wps => wps.filter((_, i) => i !== idx));
    if (pick === `waypoint-${idx}`) setPick(null);
  }

  function updateWaypoint(idx, key, val) {
    invalidate();
    setScienceWaypoints(wps => wps.map((w, i) => (i === idx ? { ...w, [key]: val } : w)));
  }

  function selectBrowserDemForRequest(req, prefOverride) {
    const pref = prefOverride || req.preferred_dem_source || demSourcePreference;
    if (pref === 'mola_hrsc_200m') return { dem: raw, fallbackNote: null };
    const cov = verifyCoordinateDatasetCoverage(req.start, req.destination);
    if (pref === 'hirise_1m' && hiriseRaw && cov.bothInLocalHiriseDtmCorridor) {
      return { dem: hiriseRaw, fallbackNote: null };
    }
    if (pref === 'auto' && hiriseRaw && cov.bothInLocalHiriseDtmCorridor) {
      return { dem: hiriseRaw, fallbackNote: null };
    }
    if (pref === 'hirise_1m') {
      const reason = !hiriseRaw
        ? `HiRISE 1 m DTM unavailable (${hiriseLoadStatus}: ${hiriseLoadReason}). Falling back to USGS MOLA-HRSC 200 m DEM.`
        : 'Selected corridor extends outside bundled HiRISE 1 m preview window; using USGS MOLA-HRSC 200 m DEM.';
      return { dem: raw, fallbackNote: reason };
    }
    return { dem: raw, fallbackNote: null };
  }

  function buildRequest(overrides = {}) {
    const req = {
      start: overrides.start || { lon: Number(start.lon), lat: Number(start.lat) },
      destination: overrides.destination || { lon: Number(destination.lon), lat: Number(destination.lat) },
      crs_identifier: 'IAU2000:49900',
      mode: overrides.mode || mode,
      constraints: {
        max_slope_deg: Number(maxSlope),
        max_roughness: Number(maxRough),
        avoid_unobserved_terrain: avoidUnobserved
      },
      science_waypoints: (overrides.science_waypoints ?? scienceWaypoints).map(w => ({
        lon: Number(w.lon),
        lat: Number(w.lat)
      })),
      num_alternatives: Math.max(1, Math.min(3, Number(numAlternatives))),
      cost_mode: costMode,
      effort_model: effortModel,
      suit_load_factor: Number(suitLoadFactor),
      max_eva_hours: Number(overrides.max_eva_hours ?? evaBudgetHours),
      return_constraint_mode: returnConstraintMode,
      departure_utc: overrides.departure_utc || departureUtc,
      daylight_buffer_minutes: Number(daylightBufferMinutes),
      rescue_enabled: true,
      rescue_threshold_minutes: Number(rescueThresholdMinutes),
      preferred_dem_source: overrides.demSourceOverride || overrides.preferred_dem_source || demSourcePreference
    };

    if (robustnessEnabled) {
      req.robustness_config = {
        enabled: true,
        vertical_sigma_m: Number(robustnessConfig.vertical_sigma_m),
        correlation_length_m: Number(robustnessConfig.correlation_length_m),
        scenario_count: Math.max(3, Math.min(200, Number(robustnessConfig.scenario_count))),
        seed: Number(robustnessConfig.seed),
        cost_regret_threshold_fraction: Number(robustnessConfig.cost_regret_threshold_fraction)
      };
    }

    if (!live || api?.algorithmSupported) {
      req.algorithm = overrides.algorithm || algorithm;
    }

    return req;
  }

  function applyPreset(presetId) {
    const preset = MISSION_PRESETS_CLIENT.find(p => p.preset_id === presetId) || MISSION_PRESETS_CLIENT[0];
    setSelectedPresetId(preset.preset_id);
    invalidate();
    setStart(preset.start);
    setDestination(preset.destination);
    setScienceWaypoints(preset.waypoints || []);
    const uiMode =
      preset.profile === 'safest' ? 'safety_first' : preset.profile === 'direct' ? 'science_first' : 'balanced';
    setMode(uiMode);
    setMaxSlope(uiMode === 'safety_first' ? 14 : uiMode === 'science_first' ? 22 : 20);
    setDepartureUtc(preset.departure_utc || '2026-06-15T08:00:00Z');
    setCustomUtc(preset.departure_utc || '2026-06-15T08:00:00Z');
    setEvaBudgetHours(preset.max_eva_hours || 8.0);
    setMissionView('planner');
    setShowRoute(true);
    setRightExpanded(true);
    setNotice(
      preset.preset_id === 'flagship_jezero_expedition'
        ? 'Loaded Flagship Integrated Jezero Expedition (Landing -> Three Forks -> Hawksbill Gap).'
        : `Loaded Mission Preset: ${preset.title}`
    );
    const req = buildRequest({
      start: preset.start,
      destination: preset.destination,
      science_waypoints: preset.waypoints || [],
      mode: uiMode,
      departure_utc: preset.departure_utc || departureUtc,
      max_eva_hours: preset.max_eva_hours || evaBudgetHours
    });
    if (!live && raw) {
      const { dem, fallbackNote } = selectBrowserDemForRequest(req);
      if (fallbackNote) setNotice(fallbackNote);
      setBusy(true);
      lastRequest.current = req;
      worker.current?.postMessage({ id: ++sequence.current, raw: dem, request: req });
    } else if (live && api) {
      run(req);
    }
  }

  async function run(overrides = {}) {
    const preconditions = validateRouteExecutionPreconditions({ live, raw, loadError, api, algorithm });
    if (!preconditions.ok) {
      setError(preconditions.error);
      setLeftOpen(true);
      return;
    }

    if (routeForm.current && !routeForm.current.checkValidity()) {
      setError('Enter valid latitude, longitude coordinates.');
      setLeftOpen(true);
      return;
    }

    const req = overrides?.start && overrides?.destination ? overrides : buildRequest(overrides);
    if ([req.start.lon, req.start.lat, req.destination.lon, req.destination.lat].some(n => !Number.isFinite(n))) {
      setError('Enter valid numeric latitude and longitude coordinates.');
      return;
    }

    setPreviousResult(result);
    setError('');
    setNotice('');
    setHover(null);
    lastRequest.current = req;
    setBusy(true);

    const id = ++sequence.current;

    if (!live) {
      const { dem, fallbackNote } = selectBrowserDemForRequest(req, overrides?.demSourceOverride);
      if (fallbackNote) setNotice(fallbackNote);
      worker.current?.postMessage({ id, raw: dem, request: req });
      return;
    }

    if ((algorithm === 'dijkstra' || algorithm === 'compare') && !api.algorithmSupported) {
      setError('This backend only exposes A* through its API. Select A*, or use the bundled-grid planner for Dijkstra and Comparison mode.');
      setBusy(false);
      return;
    }

    const payload = { ...req };
    if (!api.algorithmSupported) {
      delete payload.algorithm;
    }

    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    let timedOut = false;
    const timeout = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, 60000);

    try {
      const response = await fetch(api.url + '/api/v1/routes/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });

      let json;
      try {
        json = await response.json();
      } catch {
        throw new Error(`The backend returned an unparseable response (${response.status}).`);
      }

      if (!response.ok) {
        let msg = 'Route request failed (' + response.status + ').';
        if (json.detail) {
          if (typeof json.detail === 'string') msg = json.detail;
          else if (Array.isArray(json.detail)) msg = json.detail.map(d => d.msg || d.error || JSON.stringify(d)).join('; ');
          else if (json.detail.error) msg = json.detail.error;
        } else if (json.error) {
          msg = json.error;
        } else if (Array.isArray(json.blocking_errors) && json.blocking_errors.length) {
          msg = json.blocking_errors.join('; ');
        }
        throw new Error(msg);
      }

      if (id === sequence.current) {
        accept(json, req);
      }
    } catch (e) {
      if (e.name === 'AbortError' && !timedOut) return;
      if (id === sequence.current) {
        if (e.name === 'AbortError') {
          setError('The backend route calculation timed out. Consider reducing the corridor length or scenario count.');
        } else {
          setError(e.message + ' Check backend service status and CORS origins.');
        }
        setBusy(false);
      }
    } finally {
      clearTimeout(timeout);
    }
  }

  async function connect(opts = {}) {
    const silent = Boolean(opts?.silent);
    if (!silent) {
      setConnecting(true);
      setConnectionError('');
    }
    try {
      const targetInput = (apiUrl || '').trim() || (typeof window !== 'undefined' ? window.location.origin : '');
      const u = new URL(targetInput);
      if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password || u.search || u.hash) {
        throw new Error('Enter a plain HTTP(S) backend URL without credentials, query parameters, or fragments.');
      }
      if (u.protocol === 'http:' && !['localhost', '127.0.0.1'].includes(u.hostname)) {
        throw new Error('Use HTTPS for a remote backend.');
      }
      const url = u.href.replace(/\/$/, '');

      const fetchEndpoint = async path => {
        try {
          const r = await fetch(url + path, { signal: AbortSignal.timeout(silent ? 8000 : 30000) });
          const data = await r.json().catch(() => null);
          return { ok: r.ok, status: r.status, data };
        } catch (err) {
          return { ok: false, status: 0, error: err.message };
        }
      };

      const [healthRes, statusRes, layersRes, openapiRes] = await Promise.all([
        fetchEndpoint('/health'),
        fetchEndpoint('/api/v1/data/status'),
        fetchEndpoint('/api/v1/layers'),
        fetchEndpoint('/openapi.json')
      ]);

      if (!openapiRes.ok || !openapiRes.data) {
        throw new Error(`Cannot reach /openapi.json (${openapiRes.error || 'HTTP ' + openapiRes.status}). Verify the server is running.`);
      }

      const openapi = openapiRes.data;
      if (!openapi.paths?.['/api/v1/routes/plan']) {
        throw new Error('This server does not expose the /api/v1/routes/plan route-planning endpoint.');
      }

      const props = openapi.components?.schemas?.RoutePlanRequest?.properties || {};
      const algorithmSupported = Boolean(props.algorithm);

      const health = healthRes.data || {};
      const status = statusRes.data || {};
      const layers = layersRes.data || {};

      const isDegraded = health.status === 'degraded' || (status.blocking_errors && status.blocking_errors.length > 0) || !status.dem_loaded;
      const connectionState = isDegraded ? 'connected_degraded' : 'connected';

      setApi({
        url,
        health,
        status,
        layers,
        openapi,
        algorithmSupported
      });
      setApiConnectionState(connectionState);
      if (!silent) {
        localStorage.setItem('marspath-api-url', url);
      }
      setApiUrl(url);

      invalidate();
      setSourceMode('api');
      setAlgorithm('astar');
      if (!silent) setShowSettings(false);

      if (isDegraded) {
        const blockerMsg = status.blocking_errors?.join(', ') || health.data_readiness?.fallback_reason || 'Real DEM not fully provisioned';
        setNotice(`Connected to Python API (Degraded mode: ${blockerMsg}).`);
      } else if (!silent) {
        setNotice('Python API connected. Planetary routing and evidence pipelines ready.');
      }
    } catch (e) {
      if (!silent) {
        setConnectionError(
          `${e.message} If browser-blocked, confirm ${location.origin} is included in backend MARSPATH_CORS_ORIGINS.`
        );
      }
    } finally {
      if (!silent) setConnecting(false);
    }
  }

  function disconnectApi() {
    setApi(null);
    setApiConnectionState('disconnected');
    setSourceMode('browser');
    invalidate();
    setNotice('Disconnected from Python backend. Switched to bundled local planner.');
  }

  async function download() {
    if (!result) return;
    const missionId = result.mission_id || 'jezero-mission';
    let fileContent;
    let mimeType;
    let ext;

    if (exportFormat === 'pdf') {
      setNotice('Generating PDF Mission Dossier...');
      try {
        const blob = await exportPDF(result, active.route_id, lastRequest.current, api?.url || apiUrl || '');
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `marspath-${missionId}-${active.route_id}.pdf`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice(`Route ${active.name || active.route_id} exported as PDF Mission Dossier.`);
      } catch (err) {
        console.error('PDF export failed:', err);
        setNotice(`PDF export error: ${err.message}`);
      }
      return;
    }

    if (exportFormat === 'geojson') {
      fileContent = JSON.stringify(exportGeoJSON(result, active.route_id, lastRequest.current), null, 2);
      mimeType = 'application/geo+json';
      ext = 'geojson';
    } else if (exportFormat === 'csv') {
      fileContent = exportCSV(result, active.route_id);
      mimeType = 'text/csv';
      ext = 'csv';
    } else if (exportFormat === 'brief') {
      fileContent = exportMissionBriefMarkdown(result, active?.route_id, lastRequest.current);
      mimeType = 'text/markdown';
      ext = 'md';
    } else if (exportFormat === 'config') {
      fileContent = exportMissionConfigJSON({
        start,
        destination,
        science_waypoints: scienceWaypoints,
        algorithm,
        mode,
        max_slope_deg: maxSlope,
        max_roughness: maxRough,
        departure_utc: departureUtc,
        eva_budget_hours: evaBudgetHours
      });
      mimeType = 'application/json';
      ext = 'json';
    } else {
      fileContent = JSON.stringify(exportJSON(result, active.route_id, lastRequest.current), null, 2);
      mimeType = 'application/json';
      ext = 'json';
    }

    const blob = new Blob([fileContent], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `marspath-${missionId}-${active.route_id}.${ext}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(`Route ${active.name || active.route_id} exported as ${ext.toUpperCase()}.`);
  }

  const penalty = active
    ? ['slope_penalty', 'roughness_penalty', 'hazard_penalty', 'extra_penalty'].reduce(
        (s, k) => s + (active.cost_breakdown?.[k] || 0),
        0
      )
    : null;

  const penaltyShare = active && active.total_cost > 0 ? Math.min(100, ((penalty || 0) / active.total_cost) * 100) : 0;

  const effectiveGrid = live
    ? result?.source_selection?.effective_resolution_meters ||
      active?.evidence_passport?.resolution_assessment?.effective_resolution_meters ||
      api?.status?.dem_resolution_meters
    : terrain
    ? Math.max(terrain.dx, terrain.dy)
    : null;

  function swap() {
    invalidate();
    setStart(destination);
    setDestination(start);
    setPick(null);
  }

  function toggleLayers() {
    setLayersOpen(v => !v);
    setRightExpanded(false);
  }

  function toggleAnalysis() {
    setRightExpanded(v => !v);
    setLayersOpen(false);
  }

  const canSubmit = canSubmitRoute({ live, raw, api, busy });

  const commands = [
    { name: 'Swap start and destination', hint: 'Reverse A / B', icon: 'swap', run: swap },
    {
      name: 'Generate route',
      hint: busy ? 'Computing…' : algorithm === 'astar' ? 'A* search' : 'Dijkstra search',
      icon: 'arrow',
      run: () => {
        switchMission('planner');
        run();
      },
      disabled: !canSubmit
    },
    { name: 'Add science waypoint', hint: 'Intermediate Mars coordinate', icon: 'plus', run: addWaypoint },
    { name: 'Toggle hazards', hint: hazards ? 'Hide overlay' : 'Show terrain heatmap', icon: 'layers', run: () => setHazards(v => !v) },
    { name: 'Routing settings', hint: 'Algorithm, constraints & robustness', icon: 'sliders', run: () => { setLeftOpen(true); setSettingsOpen(true); } },
    { name: 'Toggle terrain profile', hint: profileExpanded ? 'Collapse drawer' : 'Expand drawer', icon: 'chevron', run: () => { if (historyMode) { switchMission('planner'); setProfileExpanded(true); } else setProfileExpanded(v => !v); } },
    { name: 'Toggle route analysis', hint: rightExpanded ? 'Collapse analysis' : 'Expand analysis', icon: 'sliders', run: toggleAnalysis },
    { name: 'Fit region', hint: 'Reset map extent', icon: 'fit', run: () => mapActions.current?.fit() },
    { name: 'Toggle 2D / 3D terrain', hint: 'DEM elevation view', icon: 'cube', run: () => setView3d(v => !v) },
    { name: 'Export selected route', hint: 'Download ' + exportFormat.toUpperCase(), icon: 'download', run: download, disabled: !result },
    { name: 'Connect Python API', hint: 'Backend connection settings', icon: 'command', run: () => setShowSettings(true) }
  ];

  const matches = commands.filter(c => (c.name + ' ' + c.hint).toLowerCase().includes(commandQuery.toLowerCase()));

  function execute(command) {
    if (!command || command.disabled) return;
    setCommandsOpen(false);
    command.run();
  }

  useEffect(() => {
    const handler = e => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setShowSettings(false);
        setCommandsOpen(v => !v);
        setCommandQuery('');
        setCommandIndex(0);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  useEffect(() => {
    if (error) setLeftOpen(true);
  }, [error]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 4000);
    return () => clearTimeout(timer);
  }, [notice]);

  const activeEvidence = active?.evidence_passport;
  const activeSource = activeEvidence?.source || activeEvidence?.source_evidence;
  const activeRobustness = result?.robustness_assessment;
  const activeSourceSelection = result?.source_selection;

  const activeRouteRobustness = activeRobustness?.baseline_route_assessments?.find(
    b => b.route_id === (active?.route_id || selected)
  ) || activeRobustness?.baseline_route_assessments?.[0];

  return (
    <div
      className={
        'mission-app ' +
        (historyMode ? 'history-view ' : '') +
        (profileExpanded ? 'profile-expanded ' : '') +
        (!leftOpen ? 'left-collapsed' : '') +
        (rightExpanded ? ' right-expanded' : '')
      }
    >
      <header className="mission-header">
        <div className="brand-group">
          <a className="brand" href="/#home" aria-label="Return to MarsPath home">
            MarsPath<span><Icon name="arrow" /></span>
          </a>
          <span className="brand-rule" />
          <span className="project-brand">Mission Control</span>
        </div>
        <nav className="mission-breadcrumb" aria-label="Breadcrumb">
          <a href="/#missions/planets/mars">Mars</a>
          <span>/</span>
          <span>Jezero Crater</span>
          {missionView === 'conditions' && <span> / Mars Now</span>}
          {intelligenceMode && <span> / Live Intelligence</span>}
          {fusionMode && <span> / Risk Fusion Engine</span>}
          {nasaDataMode && <span> / NASA Data</span>}
          {cloudAiMode && <span> / Cloud & AI</span>}
        </nav>
        <div className="header-actions">
          <span className={'status-chip ' + (provenance.isSynthetic ? 'synthetic' : '')} title="Data readiness and active compute source">
            <i
              className={
                provenance.headerReady
                  ? 'ready'
                  : provenance.isSynthetic
                  ? 'synthetic'
                  : apiConnectionState === 'connected_degraded'
                  ? 'degraded'
                  : ''
              }
            />
            {provenance.headerStatusText}
            <b>{provenance.headerEngineLabel}</b>
          </span>
          <button
            className={'visor-hud-trigger ' + (visorActive ? 'is-active' : '')}
            onClick={() => setVisorActive(v => !v)}
            aria-label="Toggle Astronaut Visor Tactical HUD"
            title="Switch to Astronaut Field Tactical Visor Mode [ESC to exit]"
          >
            <span className="visor-hud-badge">HUD</span>
            <span>ASTRONAUT VISOR HUD</span>
          </button>
          <button
            className="command-trigger"
            onClick={() => {
              setCommandsOpen(true);
              setCommandQuery('');
              setCommandIndex(0);
            }}
            aria-label="Open command bar"
          >
            <Icon name="search" />
            <kbd>Ctrl K</kbd>
          </button>
          <button
            className={'api-connect ' + (api ? 'is-connected' : '')}
            onClick={() => setShowSettings(true)}
            aria-label="Configure API connection"
          >
            <i className={apiConnectionState === 'connected' ? 'connected' : apiConnectionState === 'connected_degraded' ? 'degraded' : ''} />
            <span>{api ? 'API settings' : 'Connect Python API'}</span>
          </button>
        </div>
      </header>

      {visorActive && (
        <VisorHUD
          activeRoute={active}
          destination={destination}
          start={start}
          speActive={speActive}
          speSeverity={speSeverity}
          evaBudgetHours={evaBudgetHours}
          onClose={() => setVisorActive(false)}
          onToggleSpe={() => setSpeActive(v => !v)}
          onSelectSpeSeverity={setSpeSeverity}
          onTargetShelter={(shelter) => {
            setDestination({ lon: shelter.coordinates[0], lat: shelter.coordinates[1], name: shelter.name });
            setNotice(`Navigating to radiation shelter: ${shelter.name}`);
            setVisorActive(false);
          }}
        />
      )}

      <main className="map-stage" aria-label="MarsPath mission planner">
        <MapView
          showWalkBackEnvelopes={showWalkBackEnvelopes}
          showPlanetaryProtection={showPlanetaryProtection}
          showAuthenticPhotos={showAuthenticPhotos}
          onSelectProtectionZone={(zone) => setSelectedProtectionZone(zone)}
          onSelectNasaPhoto={(photo) => setSelectedNasaPhoto(photo)}
          historyMode={historyMode}
          drives={highlightedDrives}
          waypoints={highlightedWaypoints}
          fullTraverse={traverse}
          fullWaypoints={waypointData}
          roverWaypoint={activeRoverWp}
          windowStats={windowStats}
          solCut={solCut}
          maxSol={maxSol}
          minSol={minSol}
          onSolChange={setSolCut}
          showHistory={showHistory}
          showWaypoints={showWaypoints}
          historyFit={historyFit}
          waypoint={waypoint}
          onWaypoint={handleSelectWaypoint}
          terrain={terrain}
          activeDemTerrain={activeDemTerrain}
          start={start}
          destination={destination}
          scienceWaypoints={scienceWaypoints}
          pick={pick}
          onPin={mapPin}
          base={base}
          activeBookmark={activeBookmark}
          onSelectBookmark={bm => {
            setActiveBookmark(bm.id);
            if (bm.id === 'gale') setShowCuriosity(true);
            if (bm.hasDem === false) {
              setError('Global imagery available. High-resolution elevation and route optimization are not currently supported in this region.');
            } else {
              setError('');
            }
          }}
          showViking={showViking}
          showCtx={showCtx}
          showHirise={showHirise}
          showMolaTerrain={showMolaTerrain}
          showHillshade={showHillshade}
          showSlope={showSlope}
          showRoughness={showRoughness}
          vikingOpacity={vikingOpacity}
          ctxOpacity={ctxOpacity}
          hiriseOpacity={hiriseOpacity}
          molaOpacity={molaOpacity}
          hazards={hazards}
          coverage={coverage}
          maxSlope={mode === 'safety_first' ? Math.min(maxSlope, 14) : maxSlope}
          maxRough={maxRough}
          response={result || previousResult}
          selected={selected}
          onSelectRoute={setSelected}
          hover={hover}
          fitToken={fitToken}
          live={live}
          backendStatus={api?.status}
          provenance={provenance}
          showRoute={showRoute}
          showAlternatives={showAlternatives}
          hoveredRoute={hoveredRoute}
          view3d={view3d}
          exaggeration={exaggeration}
          layersOpen={layersOpen}
          onLayersToggle={toggleLayers}
          onTiltToggle={() => setView3d(v => !v)}
          leftOpen={leftOpen}
          rightExpanded={rightExpanded}
          profileExpanded={profileExpanded}
          actionsRef={mapActions}
          customSol={customSol}
          terrainOpacity={terrainOpacity}
          showReachableZone={showReachableZone}
          showRescueMap={showRescueMap}
          showOrbiters={showOrbiters}
          showGroundTracks={showGroundTracks}
          showFootprints={showFootprints}
          showCuriosity={showCuriosity}
          spacecraftPositions={spacecraftPositions}
          groundTracks={groundTracks}
          orbitalObservations={orbitalObservations}
          selectedObservation={selectedObservation}
          selectedSpacecraft={selectedSpacecraft}
          onSelectObservation={obsId => {
            setSelectedObservation(obsId);
            if (!leftOpen) setLeftOpen(true);
          }}
          onSelectSpacecraft={scId => {
            setSelectedSpacecraft(scId);
            if (!leftOpen) setLeftOpen(true);
          }}
          curiosityTraverse={curiosityTraverse}
          curiosityWaypoints={curiosityWaypoints}
          focusedProduct={focusedProduct}
          showThemisOverlay={showThemisOverlay}
          showScienceTargets={showScienceTargets}
          scienceTargets={JEZERO_SCIENCE_TARGETS_CLIENT}
        />

        {loadError && !live && (
          <div className="load-error-banner glass" role="alert">
            <div className="load-error-content">
              <strong>Local terrain notice:</strong> {loadError}
            </div>
            <div className="fallback-actions">
              <button onClick={() => location.reload()}>Retry DEM</button>
              <button onClick={() => setShowSettings(true)}>Connect API</button>
            </div>
          </div>
        )}

        {!terrain && !live && !loadError && (
          <div className="loading-map glass">
            <span className="spinner" />
            <span>Verifying Jezero terrain…</span>
          </div>
        )}

        <div
          className="mars-now-quick-badge glass"
          style={{
            left: `calc(50% + ${((leftOpen ? 372 : 24) - (plannerMode ? (rightExpanded ? 452 : 392) : 24)) / 2}px)`,
          }}
          onClick={() => {
            switchMission('conditions');
            setLeftOpen(true);
          }}
          title="Open Mars Now & Conditions Panel"
        >
          <span className="quick-badge-icon">☀️</span>
          <span className="quick-badge-text">
            Mars Now · {clientMars24Quick.ltst_hms} LTST ({clientMars24Quick.daylight_state})
          </span>
          <span className="quick-badge-arrow">›</span>
        </div>

        {!leftOpen && (
          <button className="route-reopen glass" onClick={() => setLeftOpen(true)} aria-label="Open mission control panel">
            <Icon name="sliders" />
            {missionView === 'conditions'
              ? 'Mars Now'
              : historyMode
              ? 'Rover traverse'
              : intelligenceMode
              ? 'Live Intel'
              : fusionMode
              ? 'Risk Fusion'
              : nasaDataMode
              ? 'NASA Data'
              : cloudAiMode
              ? 'Cloud & AI'
              : 'Route design'}
          </button>
        )}

        <aside className={'floating-left glass ' + (leftOpen ? '' : 'collapsed') + (nasaDataMode || fusionMode ? ' nasa-mode' : '')} inert={!leftOpen} aria-label="Mission control panel">
          <div className="panel-heading">
            <h1>
              {missionView === 'conditions'
                ? 'Mars Now & Conditions'
                : historyMode
                ? 'Rover traverse'
                : intelligenceMode
                ? 'Live Mars Intelligence'
                : fusionMode
                ? 'Mission Intelligence & Risk Fusion'
                : nasaDataMode
                ? 'NASA Data & Intelligence'
                : cloudAiMode
                ? 'Cloud & AI Center'
                : 'Route design'}
            </h1>
            <button className="icon-button" onClick={() => setLeftOpen(false)} aria-label="Collapse panel">
              <Icon name="left" />
            </button>
          </div>

          <div className="mission-mode unified-modes" role="group" aria-label="Mission view">
            <button
              className={missionView === 'conditions' ? 'active' : ''}
              aria-pressed={missionView === 'conditions'}
              onClick={() => switchMission('conditions')}
            >
              Mars Now
            </button>
            <button
              className={historyMode ? 'active' : ''}
              aria-pressed={historyMode}
              onClick={() => switchMission('history')}
            >
              Rover history
            </button>
            <button
              className={plannerMode ? 'active' : ''}
              aria-pressed={plannerMode}
              onClick={() => switchMission('planner')}
            >
              Route planner
            </button>
            <button
              className={intelligenceMode ? 'active' : ''}
              aria-pressed={intelligenceMode}
              onClick={() => switchMission('intelligence')}
            >
              Live Intel
            </button>
            <button
              className={fusionMode ? 'active' : ''}
              aria-pressed={fusionMode}
              onClick={() => switchMission('fusion')}
            >
              Risk Fusion
            </button>
            <button
              className={nasaDataMode ? 'active' : ''}
              aria-pressed={nasaDataMode}
              onClick={() => switchMission('nasa-data')}
            >
              NASA Data
            </button>
            <button
              className={cloudAiMode ? 'active' : ''}
              aria-pressed={cloudAiMode}
              onClick={() => switchMission('cloud-ai')}
            >
              Cloud &amp; AI
            </button>
          </div>

          {fusionMode ? (
            <MissionIntelligencePanel
              apiUrl={api?.url || apiUrl || ''}
              onClose={() => setLeftOpen(false)}
              activeRoute={active}
              onFocusCoordinates={coords => {
                mapActions.current?.focus({ lon: coords[0], lat: coords[1], zoom: 11 });
              }}
              onHighlightSegment={idx => {}}
            />
          ) : cloudAiMode ? (
            <CloudAiPanel
              activeRoute={active}
              currentCoords={start}
              survivabilityScore={survivabilityScore}
              speActive={speActive}
              speSeverity={speSeverity}
              walkBackSafety={walkBackSafety}
              protectionCheck={protectionCheck}
              evaBudgetHours={evaBudgetHours}
            />
          ) : nasaDataMode ? (
            <NasaDataPanel
              apiUrl={api?.url || apiUrl || ''}
              onFocusProduct={prod => {
                setFocusedProduct(prod);
                if (prod.bounds) {
                  const centerLon = (prod.bounds.min_lon + prod.bounds.max_lon) / 2;
                  const centerLat = (prod.bounds.min_lat + prod.bounds.max_lat) / 2;
                  mapActions.current?.focus({ lon: centerLon, lat: centerLat, zoom: 10 });
                } else if (prod.footprint_geojson?.geometry?.coordinates) {
                  const c = prod.footprint_geojson.geometry.coordinates;
                  const pt = Array.isArray(c[0]) ? c[0][0] : c;
                  if (pt) mapActions.current?.focus({ lon: pt[0], lat: pt[1], zoom: 10 });
                }
              }}
              onClose={() => setLeftOpen(false)}
            />
          ) : intelligenceMode ? (
            <IntelligencePanel
              spacecraftList={spacecraftList}
              selectedSpacecraft={selectedSpacecraft}
              onSelectSpacecraft={sc => {
                setSelectedSpacecraft(sc.spacecraft_id);
                const pos = spacecraftPositions.find(p => p.spacecraft_id === sc.spacecraft_id) || sc.current_position;
                if (pos) mapActions.current?.focus({ lon: pos.lon, lat: pos.lat, zoom: 6 });
              }}
              spacecraftPositions={spacecraftPositions}
              groundTracks={groundTracks}
              orbitalObservations={orbitalObservations}
              selectedObservation={selectedObservation}
              onSelectObservation={obs => {
                setSelectedObservation(obs.observation_id);
                const c = obs.footprint_geojson?.geometry?.coordinates?.[0]?.[0] || [obs.center_lon, obs.center_lat];
                if (c) mapActions.current?.focus({ lon: c[0], lat: c[1], zoom: 9 });
              }}
              roversList={roversList}
              selectedRover={selectedRover}
              onSelectRover={r => {
                setSelectedRover(r.rover_id);
                if (r.rover_id === 'curiosity') {
                  setShowCuriosity(true);
                  mapActions.current?.focus({ lon: 137.3582, lat: -4.6881, zoom: 6 });
                } else {
                  mapActions.current?.focus({ lon: 77.2332, lat: 18.4356, zoom: 11 });
                }
              }}
              timelineEvents={timelineEvents}
              apiUrl={api?.url || apiUrl || ''}
            />
          ) : missionView === 'conditions' ? (
            <ConditionsPanel
              inspectCoord={inspectCoord}
              onInspectCoordChange={setInspectCoord}
              timeMode={timeMode}
              setTimeMode={setTimeMode}
              customUtc={customUtc}
              setCustomUtc={setCustomUtc}
              customSol={customSol}
              setCustomSol={s => {
                setCustomSol(s);
                setSolCut(s);
              }}
              onInspectRover={inspectRoverPosition}
              roverWaypoint={waypoint || (waypointData && waypointData.length ? waypointData[waypointData.length - 1] : null)}
              maxSol={maxSol}
              apiUrl={apiUrl}
              terrain={terrain}
            />
          ) : historyMode ? (
            <TraversePanel
              data={traverse}
              waypoints={highlightedWaypoints}
              stats={totalArchiveStats}
              windowStats={windowStats}
              selected={waypoint}
              onFit={() => mapActions.current?.fitFullTraverse?.()}
              onExport={exportHistory}
              onPlan={planFromWaypoint}
              error={traverseError}
              solCut={solCut}
              windowSize={15}
            />
          ) : (
            <>
              {error && (
                <div className="error-message" role="alert">
                  {error}
                </div>
              )}

              <div
                className="mission-presets-box"
                style={{
                  marginBottom: '10px',
                  padding: '8px 10px',
                  borderRadius: '10px',
                  background: 'rgba(92,255,176,0.06)',
                  border: '1px solid rgba(92,255,176,0.22)'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontSize: '10.5px', fontWeight: 600, color: '#9becbf', letterSpacing: '0.03em' }}>
                    CURATED MISSION PRESETS
                  </span>
                  <button
                    type="button"
                    onClick={() => applyPreset('flagship_jezero_expedition')}
                    style={{
                      background: 'rgba(92,255,176,0.2)',
                      color: '#d7f6e5',
                      border: '1px solid rgba(92,255,176,0.5)',
                      borderRadius: '6px',
                      padding: '2px 7px',
                      fontSize: '10.5px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    ★ Flagship
                  </button>
                </div>
                <select
                  aria-label="Mission preset selector"
                  value={selectedPresetId}
                  onChange={e => applyPreset(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '6px 8px',
                    borderRadius: '7px',
                    background: 'rgba(8,14,18,0.85)',
                    color: '#e2f1ec',
                    border: '1px solid rgba(255,255,255,0.14)',
                    fontSize: '12px'
                  }}
                >
                  {MISSION_PRESETS_CLIENT.map(p => (
                    <option key={p.preset_id} value={p.preset_id}>
                      {p.title}
                    </option>
                  ))}
                </select>
              </div>

              <form
                ref={routeForm}
                onSubmit={e => {
                  e.preventDefault();
                  run();
                }}
              >
                <div className="route-card">
                  <CoordinateRow
                    point={start}
                    label="Start"
                    marker="A"
                    active={pick === 'start'}
                    onDraft={invalidate}
                    onCommit={p => {
                      invalidate();
                      setStart(p);
                    }}
                    onPick={() => {
                      setShowRoute(true);
                      setPick(pick === 'start' ? null : 'start');
                    }}
                  />

                  {scienceWaypoints.map((wp, idx) => (
                    <div key={idx} className="waypoint-row-container">
                      <div className="swap-divider small" />
                      <CoordinateRow
                        point={wp}
                        label={`Science stop ${idx + 1}`}
                        marker={`W${idx + 1}`}
                        active={pick === `waypoint-${idx}`}
                        onDraft={invalidate}
                        onCommit={p => updateWaypoint(idx, 'lon', p.lon) || updateWaypoint(idx, 'lat', p.lat)}
                        onPick={() => {
                          setShowRoute(true);
                          setPick(pick === `waypoint-${idx}` ? null : `waypoint-${idx}`);
                        }}
                        onRemove={() => removeWaypoint(idx)}
                      />
                    </div>
                  ))}

                  <div className="waypoint-action-row">
                    <button
                      type="button"
                      className="text-btn add-stop-btn"
                      onClick={() => {
                        setShowRoute(true);
                        setPick('waypoint');
                      }}
                      title="Pick a science stop directly on the map"
                    >
                      <Icon name="plus" />
                      <span>{pick === 'waypoint' ? 'Click map for stop…' : '+ Add science stop'}</span>
                    </button>
                  </div>

                  <div className="swap-divider">
                    <button type="button" onClick={swap} aria-label="Swap start and destination" title="Swap A / B">
                      <Icon name="swap" />
                    </button>
                  </div>

                  <CoordinateRow
                    point={destination}
                    label="Destination"
                    marker="B"
                    active={pick === 'destination'}
                    onDraft={invalidate}
                    onCommit={p => {
                      invalidate();
                      setDestination(p);
                    }}
                    onPick={() => {
                      setShowRoute(true);
                      setPick(pick === 'destination' ? null : 'destination');
                    }}
                  />
                </div>

                <details className="routing-settings" open={settingsOpen} onToggle={e => setSettingsOpen(e.currentTarget.open)}>
                  <summary>
                    <Icon name="sliders" />
                    <span>Settings & Constraints</span>
                    <small>{mode.replace('_first', ' first')} · {numAlternatives} alt</small>
                    <Icon name="chevron" />
                  </summary>

                  <div className="settings-body">
                    <label>
                      Compute source
                      <select
                        value={sourceMode}
                        onChange={e => {
                          invalidate();
                          setSourceMode(e.target.value);
                          if (e.target.value === 'api') setAlgorithm('astar');
                        }}
                      >
                        <option value="browser">Bundled USGS terrain</option>
                        <option value="api" disabled={!api}>
                          Python backend{!api ? ' · connect first' : ''}
                        </option>
                      </select>
                    </label>

                    <label>
                      Routing terrain (DEM)
                      <select
                        aria-label="Routing terrain DEM source"
                        value={demSourcePreference}
                        onChange={e => {
                          const nextPref = e.target.value;
                          invalidate();
                          setDemSourcePreference(nextPref);
                          run({ demSourceOverride: nextPref });
                        }}
                      >
                        <option value="auto">Auto (HiRISE 1 m where covered, else 200 m)</option>
                        <option value="hirise_1m">USGS HiRISE 1 m DTM (DOI: 10.5066/P9REJ9JN)</option>
                        <option value="mola_hrsc_200m">USGS MOLA-HRSC 200 m DEM (DOI: 10.5066/P907276M)</option>
                      </select>
                    </label>

                    <div className="two-fields">
                      <label>
                        Algorithm
                        <select
                          value={algorithm}
                          onChange={e => {
                            invalidate();
                            setAlgorithm(e.target.value);
                          }}
                          aria-label="Routing algorithm"
                        >
                          <option value="astar">A* search</option>
                          <option value="dijkstra" disabled={live && !api?.algorithmSupported}>
                            Dijkstra
                          </option>
                          <option value="compare" disabled={live && !api?.algorithmSupported}>
                            Benchmark (A* vs Dijkstra)
                          </option>
                        </select>
                      </label>
                      <label>
                        Candidates
                        <select
                          value={numAlternatives}
                          onChange={e => {
                            invalidate();
                            setNumAlternatives(Number(e.target.value));
                          }}
                          aria-label="Number of route candidates"
                        >
                          <option value="1">1 route</option>
                          <option value="2">2 routes</option>
                          <option value="3">3 routes</option>
                        </select>
                      </label>
                    </div>

                    <label>
                      Optimization mode
                      <select
                        value={mode}
                        onChange={e => {
                          invalidate();
                          setMode(e.target.value);
                          setMaxSlope(e.target.value === 'safety_first' ? 14 : e.target.value === 'science_first' ? 22 : 20);
                        }}
                        aria-label="Optimization mode"
                      >
                        <option value="safety_first">Safety first (≤14°)</option>
                        <option value="balanced">Balanced (≤20°)</option>
                        <option value="science_first">Science first (≤22°)</option>
                      </select>
                    </label>

                    <div className="slider-field">
                      <label htmlFor="max-slope">
                        Slope ceiling <strong>{maxSlope}°</strong>
                      </label>
                      <input
                        id="max-slope"
                        type="range"
                        min="5"
                        max="35"
                        step="1"
                        value={maxSlope}
                        onChange={e => {
                          invalidate();
                          setMaxSlope(Number(e.target.value));
                        }}
                      />
                    </div>

                    <div className="slider-field">
                      <label htmlFor="max-rough">
                        Roughness limit <strong>{maxRough.toFixed(2)}</strong>
                      </label>
                      <input
                        id="max-rough"
                        type="range"
                        min="0.1"
                        max="1"
                        step="0.05"
                        value={maxRough}
                        onChange={e => {
                          invalidate();
                          setMaxRough(Number(e.target.value));
                        }}
                      />
                    </div>

                    <label className="toggle-checkbox-row">
                      <span>Avoid unobserved terrain (strict NoData mask)</span>
                      <input
                        type="checkbox"
                        checked={avoidUnobserved}
                        onChange={e => {
                          invalidate();
                          setAvoidUnobserved(e.target.checked);
                        }}
                      />
                    </label>

                    <div className="two-fields">
                      <label>
                        Slope cost model
                        <select
                          value={costMode}
                          onChange={e => {
                            invalidate();
                            setCostMode(e.target.value);
                          }}
                          aria-label="Slope cost model"
                        >
                          <option value="directional">Directional + X-Slope</option>
                          <option value="legacy_magnitude">Legacy magnitude</option>
                        </select>
                      </label>
                      <label>
                        Effort curve
                        <select
                          value={effortModel}
                          onChange={e => {
                            invalidate();
                            setEffortModel(e.target.value);
                          }}
                          aria-label="Effort curve model"
                        >
                          <option value="slope_penalty">Slope penalty</option>
                          <option value="minetti_effort">Minetti Mars effort</option>
                        </select>
                      </label>
                    </div>

                    <div className="two-fields">
                      <label>
                        Return mode
                        <select
                          value={returnConstraintMode}
                          onChange={e => {
                            invalidate();
                            setReturnConstraintMode(e.target.value);
                          }}
                          aria-label="Habitat return-time constraint"
                        >
                          <option value="flag">Flag over-budget</option>
                          <option value="block">Block unreachable</option>
                          <option value="off">Off</option>
                        </select>
                      </label>
                      <label>
                        EVA budget (h)
                        <input
                          type="number"
                          min="0.5"
                          max="48"
                          step="0.5"
                          value={evaBudgetHours}
                          onChange={e => {
                            invalidate();
                            setEvaBudgetHours(Number(e.target.value));
                          }}
                        />
                      </label>
                    </div>

                    <div className="two-fields">
                      <label>
                        Sunset buffer (min)
                        <input
                          type="number"
                          min="0"
                          max="120"
                          step="5"
                          value={daylightBufferMinutes}
                          onChange={e => {
                            invalidate();
                            setDaylightBufferMinutes(Number(e.target.value));
                          }}
                        />
                      </label>
                      <label>
                        Rescue limit (min)
                        <input
                          type="number"
                          min="5"
                          max="240"
                          step="5"
                          value={rescueThresholdMinutes}
                          onChange={e => {
                            invalidate();
                            setRescueThresholdMinutes(Number(e.target.value));
                          }}
                        />
                      </label>
                    </div>

                    <label>
                      Departure UTC
                      <input
                        type="text"
                        value={departureUtc}
                        onChange={e => {
                          invalidate();
                          setDepartureUtc(e.target.value);
                        }}
                        aria-label="EVA departure UTC timestamp"
                      />
                    </label>

                    <details
                      className="robustness-settings-block"
                      open={robustnessSettingsOpen}
                      onToggle={e => setRobustnessSettingsOpen(e.currentTarget.open)}
                    >
                      <summary>
                        <span>Robustness Stress Testing</span>
                        <small>{robustnessEnabled ? 'Enabled' : 'Off'}</small>
                        <Icon name="chevron" />
                      </summary>

                      <div className="robustness-settings-fields">
                        <label className="toggle-checkbox-row">
                          <span>Enable elevation perturbation testing</span>
                          <input
                            type="checkbox"
                            checked={robustnessEnabled}
                            onChange={e => {
                              invalidate();
                              setRobustnessEnabled(e.target.checked);
                            }}
                          />
                        </label>

                        {robustnessEnabled && (
                          <>
                            <div className="two-fields">
                              <label>
                                Vertical sigma (m)
                                <input
                                  type="number"
                                  min="0.1"
                                  step="0.1"
                                  value={robustnessConfig.vertical_sigma_m}
                                  onChange={e =>
                                    setRobustnessConfig(c => ({ ...c, vertical_sigma_m: Number(e.target.value) }))
                                  }
                                />
                              </label>
                              <label>
                                Correlation length (m)
                                <input
                                  type="number"
                                  min="50"
                                  step="50"
                                  value={robustnessConfig.correlation_length_m}
                                  onChange={e =>
                                    setRobustnessConfig(c => ({ ...c, correlation_length_m: Number(e.target.value) }))
                                  }
                                />
                              </label>
                            </div>

                            <div className="two-fields">
                              <label>
                                Scenarios (3–200)
                                <input
                                  type="number"
                                  min="3"
                                  max="200"
                                  step="1"
                                  value={robustnessConfig.scenario_count}
                                  onChange={e =>
                                    setRobustnessConfig(c => ({ ...c, scenario_count: Number(e.target.value) }))
                                  }
                                />
                                <div className="scenario-presets" style={{ display: 'flex', gap: '4px', marginTop: '4px' }}>
                                  {[5, 20, 50, 100, 200].map(cnt => (
                                    <button
                                      key={cnt}
                                      type="button"
                                      className={`chip-button ${robustnessConfig.scenario_count === cnt ? 'active' : ''}`}
                                      style={{
                                        fontSize: '10px',
                                        padding: '2px 6px',
                                        background: robustnessConfig.scenario_count === cnt ? 'var(--accent, #e55)' : 'rgba(255,255,255,0.08)',
                                        color: '#fff',
                                        border: '1px solid rgba(255,255,255,0.2)',
                                        borderRadius: '3px',
                                        cursor: 'pointer'
                                      }}
                                      onClick={() => setRobustnessConfig(c => ({ ...c, scenario_count: cnt }))}
                                    >
                                      {cnt}
                                    </button>
                                  ))}
                                </div>
                              </label>
                              <label>
                                Random seed
                                <input
                                  type="number"
                                  step="1"
                                  value={robustnessConfig.seed}
                                  onChange={e =>
                                    setRobustnessConfig(c => ({ ...c, seed: Number(e.target.value) }))
                                  }
                                />
                              </label>
                            </div>

                            <label>
                              Cost regret threshold
                              <input
                                type="number"
                                min="0"
                                max="1"
                                step="0.01"
                                value={robustnessConfig.cost_regret_threshold_fraction}
                                onChange={e =>
                                  setRobustnessConfig(c => ({
                                    ...c,
                                    cost_regret_threshold_fraction: Number(e.target.value)
                                  }))
                                }
                              />
                            </label>
                            <p className="disclaimer-text">
                              Assumed perturbations are user hypotheses. They do not represent empirical MOLA DEM errors.
                            </p>
                          </>
                        )}
                      </div>
                    </details>

                    <p className="field-note">
                      {live && !api?.algorithmSupported
                        ? 'This API exposes A* only. Use the bundled planner for Dijkstra.'
                        : 'Both searches optimize weighted Martian terrain cost.'}
                    </p>
                  </div>
                </details>

                <button className="plan-button" type="submit" disabled={!canSubmit}>
                  {busy ? (
                    <>
                      <span className="spinner" />
                      Computing route…
                    </>
                  ) : (
                    <>
                      Generate route
                      <Icon name="arrow" />
                    </>
                  )}
                </button>
              </form>
              <p className="route-caption">Jezero pilot region · IAU2000:49900</p>
            </>
          )}
        </aside>

        {plannerMode && (
          <aside className={'floating-analysis glass ' + (rightExpanded ? 'expanded' : '')} aria-label="Route analysis">
            <div className="analysis-heading">
              <button
                className="analysis-toggle"
                onClick={toggleAnalysis}
                aria-expanded={rightExpanded}
                aria-label={rightExpanded ? 'Collapse route analysis' : 'Expand route analysis'}
              >
                <span>Route analysis</span>
                <Icon name="chevron" />
              </button>
              <button
                className="icon-button quick-export"
                onClick={download}
                disabled={!result}
                aria-label="Export selected route"
                title="Export selected route"
              >
                <Icon name="download" />
              </button>
            </div>

            <div className={'analysis-content ' + (busy ? 'calculating' : '')}>
              {shortfall.hasShortfall && (
                <div className="shortfall-banner" role="status">
                  <strong>
                    {shortfall.returnedCount} of {shortfall.requestedCount} alternatives found
                  </strong>
                  <span>{shortfall.message}</span>
                </div>
              )}

              {busy && previousResult && (
                <div className="recomputing-notice">
                  <span className="spinner small" />
                  <span>Showing previous plan · Computing new route…</span>
                </div>
              )}

              <div className="key-metrics">
                <Metric
                  label="Distance"
                  value={active?.summary?.total_distance_meters ? active.summary.total_distance_meters / 1000 : null}
                  digits={2}
                  unit="km"
                  primary
                />
                <Metric
                  label="Estimated time"
                  value={active?.summary?.estimated_duration_hours}
                  digits={1}
                  unit={Number.isFinite(active?.summary?.estimated_duration_hours) ? 'hrs' : 'ETA unavail'}
                  primary
                />
                <Metric
                  label="Energy Index / Effort"
                  value={active?.summary?.energy_index ?? active?.summary?.observed_energy_index_partial ?? 1.0}
                  digits={2}
                  unit="× flat"
                />

                {rightExpanded && (
                  <>
                    <Metric label="Weighted cost" value={active?.total_cost} digits={0} unit="units" />
                    <Metric
                      label="Observed terrain"
                      value={active?.summary?.data_coverage_fraction ? active.summary.data_coverage_fraction * 100 : null}
                      digits={0}
                      unit="%"
                    />
                  </>
                )}
              </div>

              {active?.summary?.provenance && (
                <div className="provenance-strip" data-testid="route-provenance-strip">
                  <span className="prov-kind">{active.summary.provenance.kind}</span>
                  <span>{active.summary.provenance.source}</span>
                  <strong className="prov-res">{active.summary.provenance.resolution}</strong>
                </div>
              )}

              {rightExpanded && (
                <>
                  <nav className="analysis-tabs" role="tablist" aria-label="Analysis perspectives">
                    <button
                      className={'tab-button ' + (analysisTab === 'overview' ? 'active' : '')}
                      role="tab"
                      aria-selected={analysisTab === 'overview'}
                      onClick={() => setAnalysisTab('overview')}
                    >
                      Overview
                    </button>
                    <button
                      className={'tab-button ' + (analysisTab === 'evidence' ? 'active' : '')}
                      role="tab"
                      aria-selected={analysisTab === 'evidence'}
                      onClick={() => setAnalysisTab('evidence')}
                    >
                      Terrain Evidence
                    </button>
                    <button
                      className={'tab-button ' + (analysisTab === 'science' ? 'active' : '')}
                      role="tab"
                      aria-selected={analysisTab === 'science'}
                      onClick={() => setAnalysisTab('science')}
                    >
                      Source & Science
                    </button>
                    <button
                      className={'tab-button ' + (analysisTab === 'robustness' ? 'active' : '')}
                      role="tab"
                      aria-selected={analysisTab === 'robustness'}
                      onClick={() => setAnalysisTab('robustness')}
                    >
                      Robustness
                    </button>
                    <button
                      className={'tab-button ' + (analysisTab === 'eva' ? 'active' : '')}
                      role="tab"
                      aria-selected={analysisTab === 'eva'}
                      onClick={() => setAnalysisTab('eva')}
                    >
                      EVA Safety &amp; Survival
                    </button>
                  </nav>

                  {/* TAB 1: OVERVIEW */}
                  {analysisTab === 'overview' && (
                    <div className="tab-pane overview-pane" role="tabpanel">
                      {/* Phase 5.E: Advanced Mission Intelligence Deep-Link Entry Points */}
                      <div className="advanced-intel-bar" data-testid="advanced-intel-navigation">
                        <div style={{ width: '100%', fontSize: '10.5px', color: '#8ba295', textTransform: 'uppercase', letterSpacing: '0.4px', marginBottom: '4px', fontWeight: 600 }}>
                          Advanced Mission Intelligence Entry Points:
                        </div>
                        <button
                          type="button"
                          className="intel-pill-btn"
                          onClick={() => {
                            setRightExpanded(true);
                            setAnalysisTab('robustness');
                          }}
                          title="Open Monte Carlo terrain uncertainty perturbation and reliability assessment"
                        >
                          🛡️ Uncertainty &amp; Robustness
                        </button>
                        <button
                          type="button"
                          className="intel-pill-btn"
                          onClick={() => {
                            setProfileExpanded(true);
                            setActiveProfileTab('science');
                          }}
                          title="Open Pareto multi-objective trade-off explorer"
                        >
                          ⚖️ Pareto Trade-off Explorer
                        </button>
                        <button
                          type="button"
                          className="intel-pill-btn"
                          onClick={() => {
                            setProfileExpanded(true);
                            setActiveProfileTab('uncertainty');
                          }}
                          title="Open Next-Best-Reconnaissance observation targets"
                        >
                          🛰️ Next-Best-Reconnaissance
                        </button>
                        <button
                          type="button"
                          className="intel-pill-btn"
                          onClick={() => {
                            setProfileExpanded(true);
                            setActiveProfileTab('science');
                          }}
                          title="Inspect Scientific Return per EVA Hour and Geological Targets"
                        >
                          🔬 Science Return per EVA Hour
                        </button>
                        <button
                          type="button"
                          className="intel-pill-btn"
                          onClick={() => {
                            setProfileExpanded(true);
                            setActiveProfileTab('stress');
                          }}
                          title="Run 7-Scenario Operational Mission Stress Testing"
                        >
                          ⚡ Mission Stress Testing
                        </button>
                      </div>

                      <div className="route-candidates" role="group" aria-label="Route candidates">
                        {result?.routes.map((r, i) => {
                          const rSurv = computeMarswalkSurvivabilityScore(r, { speActive, speSeverity, evaBudgetHours });
                          return (
                            <button
                              key={r.route_id}
                              className={'candidate ' + (r.route_id === selected ? 'selected' : '')}
                              onClick={() => {
                                setSelected(r.route_id);
                                setHover(null);
                              }}
                              onPointerEnter={() => setHoveredRoute(r.route_id)}
                              onPointerLeave={() => setHoveredRoute(null)}
                              onFocus={() => setHoveredRoute(r.route_id)}
                              onBlur={() => setHoveredRoute(null)}
                              aria-pressed={r.route_id === selected}
                            >
                              <div className="candidate-main">
                                <span className="radio-dot" />
                                <span>{i === 0 ? 'Primary' : 'Alternative ' + i}</span>
                                <span
                                  className="survivability-score-pill"
                                  style={{ borderColor: rSurv.color, color: rSurv.color }}
                                  title={`Marswalk Survivability Score: ${rSurv.score}/100 (${rSurv.tier})`}
                                >
                                  🛡️ {rSurv.score}/100
                                </span>
                              </div>
                              <small>
                                {fmt(r.summary?.total_distance_meters / 1000, 2)} km <b>·</b>{' '}
                                {Number.isFinite(r.summary?.estimated_duration_hours)
                                  ? fmt(r.summary.estimated_duration_hours, 1) + ' h'
                                  : 'ETA unavail'}
                              </small>
                            </button>
                          );
                        })}
                        {!result && (
                          <p className={'empty-routes ' + (busy ? 'shimmer' : '')}>
                            {busy ? 'Analyzing corridors…' : 'Generate a route to compare candidates.'}
                          </p>
                        )}
                      </div>

                      {/* Phase 5.D: Dedicated Mission Resource Summary Card */}
                      {active && (
                        <section className="mission-resource-card" data-testid="mission-resource-summary">
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                            <strong style={{ fontSize: '11.5px', color: '#5cffb0', letterSpacing: '0.4px', textTransform: 'uppercase' }}>
                              Mission Resource Summary
                            </strong>
                            <span className="badge-tag">Actual Backend Telemetry</span>
                          </div>
                          <div className="resource-grid">
                            <div className="resource-item">
                              <span>Total Distance</span>
                              <strong>{fmt(active.summary?.total_distance_meters / 1000, 2)} km</strong>
                              <small>{fmt(active.summary?.surface_3d_distance_meters || active.summary?.total_distance_meters, 0)} m (3D surface)</small>
                            </div>
                            <div className="resource-item">
                              <span>Estimated Travel Time</span>
                              <strong>{Number.isFinite(active.summary?.estimated_duration_hours) ? fmt(active.summary.estimated_duration_hours, 1) + ' hrs' : '—'}</strong>
                              <small>{active.summary?.motion_profile || 'Nominal 0.15 m/s'}</small>
                            </div>
                            <div className="resource-item">
                              <span>Outbound Leg</span>
                              <strong>{fmt(active.mission_clock?.outbound_leg?.total_duration_hours ?? active.summary?.estimated_duration_hours, 1)} hrs</strong>
                              <small>{fmt((active.mission_clock?.outbound_leg?.distance_m ?? active.summary?.total_distance_meters) / 1000, 2)} km</small>
                            </div>
                            <div className="resource-item">
                              <span>Return Leg</span>
                              <strong>{fmt(active.mission_clock?.return_leg?.walking_duration_hours ?? active.summary?.estimated_duration_hours, 1)} hrs</strong>
                              <small>{fmt((active.mission_clock?.return_leg?.distance_m ?? active.summary?.total_distance_meters) / 1000, 2)} km</small>
                            </div>
                            <div className="resource-item">
                              <span>Total Mission Duration</span>
                              <strong>{fmt(active.mission_clock?.total_duration_hours ?? active.science_eva_plan?.total_eva_duration_hours ?? (active.summary?.estimated_duration_hours ? active.summary.estimated_duration_hours * 2 : null), 1)} hrs</strong>
                              <small>Outbound + Science + Return</small>
                            </div>
                            <div className="resource-item">
                              <span>EVA Budget</span>
                              <strong>{fmt(active.science_eva_plan?.max_eva_budget_hours ?? active.mission_clock?.max_eva_duration_hours ?? 8.0, 1)} hrs</strong>
                              <small>Hard Physiological Limit</small>
                            </div>
                            <div className="resource-item">
                              <span>Used EVA Time</span>
                              <strong>{fmt(active.science_eva_plan?.total_eva_duration_hours ?? active.mission_clock?.total_duration_hours ?? active.summary?.estimated_duration_hours, 1)} hrs</strong>
                              <small>Walking + Sample Stops</small>
                            </div>
                            <div className="resource-item">
                              <span>Remaining EVA Margin</span>
                              <strong style={{ color: ((active.science_eva_plan?.max_eva_budget_hours ?? 8.0) - (active.science_eva_plan?.total_eva_duration_hours ?? active.summary?.estimated_duration_hours ?? 0)) > 1 ? '#5cffb0' : '#e56858' }}>
                                {fmt(Math.max(0, (active.science_eva_plan?.max_eva_budget_hours ?? 8.0) - (active.science_eva_plan?.total_eva_duration_hours ?? active.summary?.estimated_duration_hours ?? 0)), 1)} hrs
                              </strong>
                              <small>Contingency buffer</small>
                            </div>
                            <div className="resource-item">
                              <span>Return Feasibility</span>
                              <strong style={{ color: active.turnaround?.feasible_before_sunset && !active.summary?.exceeds_return_budget ? '#5cffb0' : '#e56858' }}>
                                {active.turnaround?.feasible_before_sunset && !active.summary?.exceeds_return_budget ? 'FEASIBLE' : (active.turnaround?.limiting_constraint ? active.turnaround.limiting_constraint.replace(/_/g, ' ').toUpperCase() : 'EXCEEDS BUDGET')}
                              </strong>
                              <small>{active.turnaround?.feasible_before_sunset ? 'Returns before sunset' : 'Daylight / EVA restricted'}</small>
                            </div>
                            <div className="resource-item">
                              <span>Solar Turnaround Time</span>
                              <strong>{active.turnaround?.turnaround_ltst_hms ? `${active.turnaround.turnaround_ltst_hms} LTST` : (active.turnaround?.turnaround_utc || 'N/A')}</strong>
                              <small>Sunset: {active.turnaround?.sunset_ltst_hms || '17:30 LTST'}</small>
                            </div>
                            <div className="resource-item" style={{ gridColumn: 'span 2' }}>
                              <span>Energy Index / Mechanical Effort</span>
                              <strong style={{ color: '#5cffb0' }}>
                                {active.summary?.energy_index ? `${fmt(active.summary.energy_index, 2)}× flat baseline` : '1.00×'}
                              </strong>
                              <small>Minetti cost of transport model factoring uphill gradient and Mars gravity (dimensionless index, not kWh)</small>
                            </div>
                          </div>
                        </section>
                      )}

                      {result?.algorithm_comparison && (
                        <div className="algorithm-benchmark-card">
                          <div className="benchmark-header">
                            <span>Algorithm Benchmark</span>
                            <span className="benchmark-tag">A* vs Dijkstra</span>
                          </div>
                          <table className="benchmark-table">
                            <thead>
                              <tr>
                                <th>Metric</th>
                                <th>A* (Heuristic)</th>
                                <th>Dijkstra (Uniform)</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr>
                                <td>Distance</td>
                                <td>{fmt(result.algorithm_comparison.astar.path_length_km, 2)} km</td>
                                <td>{fmt(result.algorithm_comparison.dijkstra.path_length_km, 2)} km</td>
                              </tr>
                              <tr>
                                <td>Weighted cost</td>
                                <td>{fmt(result.algorithm_comparison.astar.total_cost, 1)}</td>
                                <td>{fmt(result.algorithm_comparison.dijkstra.total_cost, 1)}</td>
                              </tr>
                              <tr>
                                <td>Compute time</td>
                                <td>{fmt(result.algorithm_comparison.astar.execution_time_seconds * 1000, 1)} ms</td>
                                <td>{fmt(result.algorithm_comparison.dijkstra.execution_time_seconds * 1000, 1)} ms</td>
                              </tr>
                              <tr>
                                <td>States expanded</td>
                                <td>{result.algorithm_comparison.astar.nodes_expanded.toLocaleString()}</td>
                                <td>{result.algorithm_comparison.dijkstra.nodes_expanded.toLocaleString()}</td>
                              </tr>
                            </tbody>
                          </table>
                          <div className="benchmark-verification">
                            <span className={'verification-pill ' + (result.algorithm_comparison.optimality_verified ? 'verified' : 'divergent')}>
                              {result.algorithm_comparison.optimality_verified ? 'Optimal Cost Equivalence Confirmed' : 'Cost Divergence'}
                            </span>
                            <small>{result.algorithm_comparison.comparison_statement}</small>
                          </div>
                        </div>
                      )}

                      {result?.routes?.length > 0 && (
                        <div className="route-comparison-wrap">
                          <div className="box-header">
                            <span>Candidate Comparison</span>
                            <small>
                              {activeSourceSelection?.effective_resolution_meters
                                ? `${fmt(activeSourceSelection.effective_resolution_meters, 1)} m/px grid`
                                : `${fmt(effectiveGrid, 0)} m/px`}
                            </small>
                          </div>
                          <table className="route-compare-table">
                            <thead>
                              <tr>
                                <th>Route</th>
                                <th>Dist</th>
                                <th>Est. Effort</th>
                                <th>Max/X-Slp</th>
                                <th>Unk %</th>
                                <th>Return</th>
                                <th>Turnaround</th>
                              </tr>
                            </thead>
                            <tbody>
                              {result.routes.map((r, i) => {
                                const covFrac = r.summary?.data_coverage_fraction;
                                const unkPct = Number.isFinite(covFrac) ? (1 - covFrac) * 100 : null;
                                return (
                                  <tr
                                    key={r.route_id}
                                    className={r.route_id === selected ? 'is-selected' : ''}
                                    onClick={() => {
                                      setSelected(r.route_id);
                                      setHover(null);
                                    }}
                                  >
                                    <td>{i === 0 ? 'Primary' : `Alt ${i}`}</td>
                                    <td>{fmt((r.summary?.total_distance_meters || 0) / 1000, 2)} km</td>
                                    <td>{fmt(r.summary?.estimated_relative_effort, 0)}</td>
                                    <td>
                                      {fmt(r.summary?.max_slope_deg, 1)}° / {fmt(r.summary?.max_cross_slope_deg, 1)}°
                                    </td>
                                    <td>{unkPct !== null ? `${fmt(unkPct, 0)}%` : '—'}</td>
                                    <td className={r.summary?.exceeds_return_budget ? 'text-warn' : ''}>
                                      {Number.isFinite(r.summary?.max_return_time_minutes)
                                        ? `${fmt(r.summary.max_return_time_minutes, 0)}m`
                                        : '—'}
                                    </td>
                                    <td>{r.turnaround?.turnaround_ltst_hms || '—'}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {active?.turnaround && (
                        <div className="metric-box turnaround-box">
                          <div className="box-header">
                            <span>Hard Turnaround & Rescue Margin</span>
                            <span className={'badge ' + (active.turnaround.feasible_before_sunset ? 'nominal' : 'high')}>
                              {active.turnaround.feasible_before_sunset ? active.turnaround.limiting_constraint : 'NO WINDOW'}
                            </span>
                          </div>
                          <dl className="compact-dl">
                            <dt>Latest Turnaround</dt>
                            <dd>
                              {active.turnaround.turnaround_ltst_hms} LTST ({active.turnaround.turnaround_utc?.slice(11, 19)}Z)
                            </dd>
                            <dt>Local Sunset</dt>
                            <dd>{active.turnaround.sunset_ltst_hms ? `${active.turnaround.sunset_ltst_hms} LTST` : '—'}</dd>
                            <dt>Est. Relative Effort</dt>
                            <dd>
                              {Number.isFinite(active.summary?.estimated_relative_effort)
                                ? `${fmt(active.summary.estimated_relative_effort, 0)} eq-m (${active.summary?.effort_model || 'slope_penalty'})`
                                : 'Unavailable'}
                            </dd>
                            <dt>Max Rescue Time</dt>
                            <dd>
                              {Number.isFinite(active.summary?.max_rescue_time_minutes)
                                ? `${fmt(active.summary.max_rescue_time_minutes, 1)} min (${fmt(active.summary?.rescue_flagged_distance_meters || 0, 0)} m > ${rescueThresholdMinutes}m)`
                                : 'Unavailable'}
                            </dd>
                          </dl>
                          {active.turnaround.provenance && (
                            <p className="field-note">
                              Provenance: {active.turnaround.provenance.kind} · {active.turnaround.provenance.source} · {active.turnaround.provenance.resolution} · {active.turnaround.provenance.as_of}
                            </p>
                          )}
                        </div>
                      )}

                      <div className="scientific-disclaimer-box">
                        <strong>Planning Indicator & Limitations</strong>
                        Relative route scores and estimated relative effort are planning indicators on finite DEMs ({active?.summary?.provenance?.resolution || 'DEM'}); they are not survival probabilities or certified flight routes. No-data cells are never assumed safe.
                      </div>

                      <section className="penalty-gauge">
                        <div>
                          <span>Terrain penalty share</span>
                          <span className={'risk-badge ' + (active?.summary?.risk_category || '')}>
                            {active?.summary?.risk_category?.replaceAll('_', ' ') || 'Unassessed'}
                          </span>
                        </div>
                        <div
                          className="gauge-track"
                          role="meter"
                          aria-label="Terrain penalty share of weighted route cost"
                          aria-valuemin="0"
                          aria-valuemax="100"
                          aria-valuenow={Math.round(penaltyShare)}
                        >
                          <span style={{ width: penaltyShare + '%' }} />
                        </div>
                        <small>
                          {active ? Math.round(penaltyShare) + '% of weighted cost' : 'Awaiting a route'} · Deterministic terrain
                          heuristic, not a failure probability
                        </small>
                      </section>

                      <div className="metric-box physical-risk-box">
                        <div className="box-header">
                          <span>Physical Traversal Risk</span>
                          <span className={'badge ' + (active?.summary?.risk_category || 'unassessed')}>
                            {active?.summary?.risk_category || 'Unassessed'}
                          </span>
                        </div>
                        <dl className="compact-dl">
                          <dt>Assessment Status</dt>
                          <dd>{active?.summary?.risk_assessment_status || 'Complete'}</dd>
                          <dt>Hazard Exposure</dt>
                          <dd>
                            {Number.isFinite(active?.summary?.hazard_exposure_meters)
                              ? `${fmt(active.summary.hazard_exposure_meters, 0)} m`
                              : 'None observed'}
                          </dd>
                          <dt>Motion Profile</dt>
                          <dd>{active?.summary?.motion_profile || 'Slope-derated 0.15 m/s'}</dd>
                        </dl>
                      </div>

                      {/* Phase 5.B: Cost & Terrain Breakdown (visible by default, collapsible, not labeled as currency) */}
                      <details className="analysis-details" open={detailsOpen} onToggle={e => setDetailsOpen(e.currentTarget.open)}>
                        <summary>
                          <span>Cost &amp; Terrain Breakdown</span>
                          <Icon name="chevron" />
                        </summary>
                        <div className="details-body">
                          <div style={{ marginBottom: '10px', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.08)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                              <strong style={{ fontSize: '11px', color: '#5cffb0' }}>Total Weighted Route Cost</strong>
                              <strong style={{ fontSize: '15px', fontFamily: 'var(--mono)', color: '#5cffb0' }}>{fmt(active?.total_cost, 1)}</strong>
                            </div>
                            <small style={{ display: 'block', color: '#8fa498', fontSize: '10px', marginTop: '3px' }}>
                              Dimensionless weighted traversal cost (3D distance + slope + roughness + hazard penalties; NOT monetary expenditure).
                            </small>
                          </div>
                          <dl>
                            <dt>Max slope</dt>
                            <dd>{fmt(active?.summary?.max_slope_deg, 1)}°</dd>
                            <dt>Average slope</dt>
                            <dd>{fmt(active?.summary?.average_slope_deg, 1)}°</dd>
                            <dt>Average roughness</dt>
                            <dd>{fmt(active?.summary?.average_roughness, 2)}</dd>
                            <dt>Ascent / descent</dt>
                            <dd>
                              {fmt(active?.summary?.elevation_gain_meters, 0)} / {fmt(active?.summary?.elevation_loss_meters, 0)} m
                            </dd>
                            {[
                              ['Base distance cost', 'base_distance_cost'],
                              ['Slope penalty', 'slope_penalty'],
                              ['Roughness penalty', 'roughness_penalty'],
                              ['Hazard penalty', 'hazard_penalty'],
                              ['Extra detour penalty', 'extra_penalty']
                            ].map(([label, key]) => (
                              <React.Fragment key={key}>
                                <dt>{label}</dt>
                                <dd>{fmt(active?.cost_breakdown?.[key], 1)}</dd>
                              </React.Fragment>
                            ))}
                          </dl>
                          {result && (
                            <p className="computation-stats">
                              {result.stats?.algorithm_used} · {fmt(result.stats?.nodes_expanded, 0)} nodes ·{' '}
                              {fmt(result.stats?.search_duration_seconds, 3)} s
                            </p>
                          )}
                        </div>
                      </details>
                    </div>
                  )}

                  {/* TAB 2: TERRAIN EVIDENCE */}
                  {analysisTab === 'evidence' && (
                    <div className="tab-pane evidence-pane" role="tabpanel">
                      <div className="evidence-header-card">
                        <div className="tier-line">
                          <span>Evidence Quality Tier</span>
                          <span className={'tier-badge ' + (activeEvidence?.quality_tier || 'unverified')}>
                            {activeEvidence?.quality_tier?.toUpperCase() || 'UNVERIFIED'}
                          </span>
                        </div>
                        <p className="tier-explanation">
                          {activeEvidence?.tier_explanation ||
                            'Evidence tier quantifies source integrity, pixel resolution, and observation coverage across the mission corridor.'}
                        </p>
                      </div>

                      {Array.isArray(activeEvidence?.quality_flags) && activeEvidence.quality_flags.length > 0 && (
                        <div className="quality-flags-list">
                          <span>Quality flags:</span>
                          <div className="tags">
                            {activeEvidence.quality_flags.map((flag, idx) => (
                              <span key={idx} className="tag-flag">
                                {flag.replaceAll('_', ' ')}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="coverage-block">
                        <div className="coverage-row">
                          <div className="coverage-labels">
                            <span>Route Path Coverage</span>
                            <strong>
                              {activeEvidence?.coverage?.route_data_coverage_fraction
                                ? pct(activeEvidence.coverage.route_data_coverage_fraction, 0)
                                : pct(active?.summary?.data_coverage_fraction, 0)}
                            </strong>
                          </div>
                          <div className="bar-track">
                            <span
                              style={{
                                width:
                                  (activeEvidence?.coverage?.route_data_coverage_fraction ||
                                    active?.summary?.data_coverage_fraction ||
                                    0) *
                                    100 +
                                  '%'
                              }}
                            />
                          </div>
                        </div>

                        <div className="coverage-row">
                          <div className="coverage-labels">
                            <span>Corridor Area Coverage</span>
                            <strong>
                              {activeEvidence?.coverage?.corridor_data_coverage_fraction
                                ? pct(activeEvidence.coverage.corridor_data_coverage_fraction, 0)
                                : '100%'}
                            </strong>
                          </div>
                          <div className="bar-track">
                            <span
                              style={{
                                width: (activeEvidence?.coverage?.corridor_data_coverage_fraction ?? 1) * 100 + '%'
                              }}
                            />
                          </div>
                        </div>

                        {activeEvidence?.coverage?.near_nodata_segment_count > 0 && (
                          <p className="warning-note">
                            ⚠️ {activeEvidence.coverage.near_nodata_segment_count} segments pass within 5 cells of unobserved terrain.
                          </p>
                        )}
                      </div>

                      <dl className="compact-dl">
                        <dt>Active Dataset</dt>
                        <dd>{provenance.datasetName}</dd>
                        <dt>Product ID</dt>
                        <dd>{activeSource?.product_id || (provenance.isSynthetic ? 'Synthetic Fixture' : 'USGS Regional DEM')}</dd>
                        <dt>Source Verification</dt>
                        <dd>{provenance.sourceVerificationText}</dd>
                        <dt>Local File Integrity</dt>
                        <dd className={provenance.localIntegrityVerified ? 'text-ok' : ''}>
                          {provenance.fileIntegrityText}
                        </dd>
                        <dt>Upstream Checksum</dt>
                        <dd className={provenance.sourceChecksumVerified ? 'text-ok' : 'text-muted'}>
                          {provenance.upstreamChecksumText}
                        </dd>
                        <dt>Resolution (dx / dy)</dt>
                        <dd>
                          {activeSource?.pixel_resolution_x_meters
                            ? `${fmt(activeSource.pixel_resolution_x_meters, 0)} × ${fmt(
                                activeSource.pixel_resolution_y_meters,
                                0
                              )} m`
                            : `${fmt(effectiveGrid, 0)} m`}
                        </dd>
                        <dt>Vertical Datum</dt>
                        <dd>{activeSource?.vertical_datum || 'Mars Areoid (MOLA)'}</dd>
                      </dl>

                      {provenance.officialSourceUrl ? (
                        <p>
                          <a href={provenance.officialSourceUrl} target="_blank" rel="noopener">
                            Official planetary dataset source ↗
                          </a>
                        </p>
                      ) : (
                        <p className="no-source-link">
                          {provenance.isSynthetic ? 'Synthetic model — no external planetary archive.' : 'No upstream planetary archive link available.'}
                        </p>
                      )}

                      <p className="regional-disclaimer">
                        Regional corridor assessment only (~200 m). Does not resolve rover-scale rocks, ripples, or scarps.
                      </p>

                      {(activeEvidence?.known_limitations?.length > 0 || activeSource?.source_limitations?.length > 0) && (
                        <details className="sub-details">
                          <summary>Known evidence limitations ({activeEvidence?.known_limitations?.length || 0})</summary>
                          <ul>
                            {(activeEvidence?.known_limitations || activeSource?.source_limitations || []).map((lim, i) => (
                              <li key={i}>{lim}</li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </div>
                  )}

                  {/* TAB 3: SOURCE & SCIENCE */}
                  {analysisTab === 'science' && (
                    <div className="tab-pane science-pane" role="tabpanel">
                      <div className="metric-box">
                        <div className="box-header">
                          <span>Multi-Resolution Source Selection</span>
                          <span className="badge-tag">Single Source Invariant</span>
                        </div>
                        <dl className="compact-dl">
                          <dt>Selected DEM</dt>
                          <dd>{activeSourceSelection?.selected_dataset_name || provenance.datasetName}</dd>
                          <dt>Source ID</dt>
                          <dd>{activeSourceSelection?.selected_source_id || 'dem_mola_hrsc_jezero_200m'}</dd>
                          <dt>Selection Reason</dt>
                          <dd className="wrap-dd">
                            {activeSourceSelection?.selection_reason || 'Regional MOLA-HRSC DEM covers mission corridor'}
                          </dd>
                          <dt>HiRISE Evaluated</dt>
                          <dd>{activeSourceSelection?.hirise_evaluated ? 'Yes' : 'No'}</dd>
                          <dt>HiRISE Status</dt>
                          <dd>{activeSourceSelection?.hirise_status || api?.status?.hirise_status || 'Disabled'}</dd>
                          {activeSourceSelection?.hirise_rejection_reason && (
                            <>
                              <dt>Rejection Reason</dt>
                              <dd className="wrap-dd">{activeSourceSelection.hirise_rejection_reason}</dd>
                            </>
                          )}
                          <dt>Analysis Grid Resolution</dt>
                          <dd>
                            {activeSourceSelection?.effective_resolution_meters
                              ? `${fmt(activeSourceSelection.effective_resolution_meters, 1)} m/px`
                              : `${fmt(effectiveGrid, 0)} m`}
                          </dd>
                          <dt>Aggregation Mode</dt>
                          <dd>
                            {activeSourceSelection?.aggregation_applied
                              ? `Factor ${activeSourceSelection.aggregation_factor} (${activeSourceSelection.aggregation_method})`
                              : 'Native resolution'}
                          </dd>
                        </dl>
                      </div>

                      <div className="metric-box science-box">
                        <div className="box-header">
                          <span>Science Exploration Score</span>
                          <strong className="science-score-val">
                            {Number.isFinite(active?.summary?.science_score) ? fmt(active.summary.science_score, 1) : '—'}
                          </strong>
                        </div>
                        <dl className="compact-dl">
                          <dt>Intermediate Waypoints</dt>
                          <dd>
                            {active?.waypoints_visited?.length || 0} of {scienceWaypoints.length} visited
                          </dd>
                          <dt>Science POIs Visited</dt>
                          <dd>
                            {Array.isArray(active?.science_targets_visited) && active.science_targets_visited.length
                              ? active.science_targets_visited.join(', ')
                              : 'None directly on path'}
                          </dd>
                          <dt>Nearby Science POIs</dt>
                          <dd>
                            {Array.isArray(active?.science_targets_nearby) && active.science_targets_nearby.length
                              ? active.science_targets_nearby.join(', ')
                              : 'None within corridor'}
                          </dd>
                        </dl>
                      </div>

                      {active?.warnings && active.warnings.length > 0 && (
                        <div className="route-warnings-list">
                          <span>Mission & Detour Notes:</span>
                          <ul>
                            {active.warnings.map((w, idx) => (
                              <li key={idx}>{w}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 4: ROBUSTNESS */}
                  {analysisTab === 'robustness' && (
                    <div className="tab-pane robustness-pane" role="tabpanel">
                      {activeRobustness ? (
                        <>
                          <div className="robustness-summary-card">
                            <div className="model-name">
                              <span>Perturbation Model</span>
                              <strong>Spatially Correlated Gaussian</strong>
                            </div>
                            <div className="assumptions-grid">
                              <div>
                                <small>Sigma (m)</small>
                                <b>{fmt(activeRobustness.uncertainty_assumptions?.vertical_sigma_m, 1)}</b>
                              </div>
                              <div>
                                <small>Correlation (m)</small>
                                <b>{fmt(activeRobustness.uncertainty_assumptions?.correlation_length_m, 0)}</b>
                              </div>
                              <div>
                                <small>Scenarios</small>
                                <b>
                                  {activeRobustness.completed_scenario_count} / {activeRobustness.requested_scenario_count}
                                </b>
                              </div>
                              <div>
                                <small>Seed</small>
                                <b>{activeRobustness.seed}</b>
                              </div>
                            </div>
                          </div>

                          {activeRouteRobustness?.reliability_classification && (
                            <div className="metric-box reliability-box" style={{
                              borderLeft: `4px solid ${
                                activeRouteRobustness.reliability_classification === 'HIGH' ? '#5cffb0' :
                                activeRouteRobustness.reliability_classification === 'MEDIUM' ? '#ffb867' : '#ff6b6b'
                              }`,
                              marginBottom: '12px'
                            }}>
                              <div className="box-header">
                                <span>Reliability Classification</span>
                                <span className={`badge-tag ${activeRouteRobustness.reliability_classification.toLowerCase()}`} style={{
                                  fontWeight: 'bold',
                                  padding: '2px 8px',
                                  borderRadius: '4px',
                                  backgroundColor: activeRouteRobustness.reliability_classification === 'HIGH' ? 'rgba(92,255,176,0.15)' :
                                    activeRouteRobustness.reliability_classification === 'MEDIUM' ? 'rgba(255,184,103,0.15)' : 'rgba(255,107,107,0.15)',
                                  color: activeRouteRobustness.reliability_classification === 'HIGH' ? '#5cffb0' :
                                    activeRouteRobustness.reliability_classification === 'MEDIUM' ? '#ffb867' : '#ff6b6b'
                                }}>
                                  {activeRouteRobustness.reliability_classification} ({fmt(activeRouteRobustness.reliability_score, 1)} / 100)
                                </span>
                              </div>
                              <div style={{ fontSize: '11px', color: '#aaa', margin: '4px 0 8px 0', fontFamily: 'monospace' }}>
                                {activeRouteRobustness.reliability_formula}
                              </div>
                              {activeRouteRobustness.reliability_factors && (
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '6px', fontSize: '11px', marginBottom: '8px' }}>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>M_data (Trust):</span> <b>{fmt(activeRouteRobustness.reliability_factors.M_data, 2)}</b>
                                  </div>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>M_slope (Safety):</span> <b>{fmt(activeRouteRobustness.reliability_factors.M_slope, 2)}</b>
                                  </div>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>S_ret (Regret):</span> <b>{fmt(activeRouteRobustness.reliability_factors.S_ret, 1)}%</b>
                                  </div>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>S_feas (Feasibility):</span> <b>{fmt(activeRouteRobustness.reliability_factors.S_feas, 1)}%</b>
                                  </div>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>S_cov (Spatial):</span> <b>{fmt(activeRouteRobustness.reliability_factors.S_cov, 1)}%</b>
                                  </div>
                                  <div style={{ background: 'rgba(255,255,255,0.04)', padding: '4px 6px', borderRadius: '4px' }}>
                                    <span style={{ color: '#888' }}>Duration:</span> <b>{fmt(activeRobustness.execution_duration_seconds, 2)}s</b>
                                  </div>
                                </div>
                              )}
                              {activeRouteRobustness.reliability_explanation && (
                                <div style={{ fontSize: '11px', color: '#ffb867', fontStyle: 'italic', background: 'rgba(255,184,103,0.08)', padding: '6px 8px', borderRadius: '4px' }}>
                                  ℹ️ {activeRouteRobustness.reliability_explanation}
                                </div>
                              )}
                            </div>
                          )}

                          {activeRouteRobustness ? (
                            <div className="metric-box">
                              <div className="box-header">
                                <span>Baseline Route Stability</span>
                                <span className="badge-tag">Candidate {active?.name || active?.route_id}</span>
                              </div>
                              <dl className="compact-dl">
                                <dt>Feasibility Fraction</dt>
                                <dd className="text-ok">
                                  {pct(activeRouteRobustness.baseline_route_feasibility_fraction, 0)}
                                </dd>
                                <dt>Route Retention</dt>
                                <dd>{pct(activeRouteRobustness.baseline_route_retention_fraction, 0)}</dd>
                                <dt>Mean Route Overlap</dt>
                                <dd>{pct(activeRouteRobustness.mean_route_overlap_fraction, 0)}</dd>
                                <dt>Min Route Overlap</dt>
                                <dd>{pct(activeRouteRobustness.minimum_route_overlap_fraction, 0)}</dd>
                                <dt>Mean Cost Regret</dt>
                                <dd>{pct(activeRouteRobustness.mean_cost_regret_fraction, 1)}</dd>
                                <dt>Max Cost Regret</dt>
                                <dd>{pct(activeRouteRobustness.maximum_cost_regret_fraction, 1)}</dd>
                                <dt>Within Regret Threshold</dt>
                                <dd>
                                  {activeRouteRobustness.within_regret_threshold_count} /{' '}
                                  {activeRouteRobustness.evaluated_scenario_count} scenarios
                                </dd>
                              </dl>
                            </div>
                          ) : (
                            <p className="empty-routes">Robustness assessment generated for other candidates.</p>
                          )}

                          {activeRobustness.failed_scenario_count > 0 && (
                            <p className="warning-note">
                              ⚠️ {activeRobustness.failed_scenario_count} scenario search(es) failed due to corridor boundaries or
                              severe untraversable terrain perturbations.
                            </p>
                          )}

                          <div className="scientific-disclaimer-box">
                            <strong>Scientific Disclaimer</strong>
                            <p>
                              Results describe route stability under the specified hypothetical terrain perturbation model.
                              They do not establish the actual probability of rover failure or mission success.
                            </p>
                          </div>
                        </>
                      ) : (
                        <div className="empty-robustness">
                          <p>
                            Deterministic terrain perturbation stress testing was not evaluated for this route plan.
                          </p>
                          <p>
                            To evaluate route stability under hypothetical terrain uncertainty, open <strong>Settings & Constraints</strong>,
                            expand <strong>Robustness Stress Testing</strong>, toggle it on, and generate the route.
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* TAB 5: EVA SAFETY & SURVIVABILITY */}
                  {analysisTab === 'eva' && (
                    <div className="tab-pane eva-pane" role="tabpanel" aria-label="EVA Safety & Survivability">
                      {/* 1. Marswalk Survivability Score */}
                      <div className="eva-metric-card">
                        <div className="eva-card-title-row">
                          <h4>MARSWALK SURVIVABILITY SCORE</h4>
                          <span
                            className="status-pill"
                            style={{ borderColor: survivabilityScore.color, color: survivabilityScore.color }}
                          >
                            {survivabilityScore.score}/100 · {survivabilityScore.tier}
                          </span>
                        </div>
                        <p style={{ fontSize: '11px', color: '#94a3b8', margin: '4px 0 10px 0', lineHeight: 1.4 }}>
                          {survivabilityScore.label}
                        </p>

                        <div className="survivability-factor-row">
                          <span style={{ width: '110px' }}>Terrain Mobility:</span>
                          <div className="factor-track">
                            <div
                              className="factor-fill"
                              style={{ width: `${survivabilityScore.factors?.mobility?.score ?? survivabilityScore.factors?.mobility ?? 95}%`, background: '#5cffb0' }}
                            />
                          </div>
                          <b style={{ width: '40px', textAlign: 'right' }}>{survivabilityScore.factors?.mobility?.score ?? survivabilityScore.factors?.mobility ?? 95}%</b>
                        </div>

                        <div className="survivability-factor-row">
                          <span style={{ width: '110px' }}>O₂ &amp; Power Margin:</span>
                          <div className="factor-track">
                            <div
                              className="factor-fill"
                              style={{ width: `${survivabilityScore.factors?.resources?.score ?? survivabilityScore.factors?.resources ?? 90}%`, background: '#38bdf8' }}
                            />
                          </div>
                          <b style={{ width: '40px', textAlign: 'right' }}>{survivabilityScore.factors?.resources?.score ?? survivabilityScore.factors?.resources ?? 90}%</b>
                        </div>

                        <div className="survivability-factor-row">
                          <span style={{ width: '110px' }}>Return Feasibility:</span>
                          <div className="factor-track">
                            <div
                              className="factor-fill"
                              style={{ width: `${survivabilityScore.factors?.returnFeasibility?.score ?? survivabilityScore.factors?.return_feasibility?.score ?? 92}%`, background: '#a855f7' }}
                            />
                          </div>
                          <b style={{ width: '40px', textAlign: 'right' }}>{survivabilityScore.factors?.returnFeasibility?.score ?? survivabilityScore.factors?.return_feasibility?.score ?? 92}%</b>
                        </div>

                        <div className="survivability-factor-row">
                          <span style={{ width: '110px' }}>Radiation Safety:</span>
                          <div className="factor-track">
                            <div
                              className="factor-fill"
                              style={{
                                width: `${survivabilityScore.factors?.radiation?.score ?? survivabilityScore.factors?.radiation ?? 95}%`,
                                background: speActive ? '#ef4444' : '#5cffb0',
                              }}
                            />
                          </div>
                          <b style={{ width: '40px', textAlign: 'right', color: speActive ? '#ef4444' : 'inherit' }}>
                            {survivabilityScore.factors?.radiation?.score ?? survivabilityScore.factors?.radiation ?? 95}%
                          </b>
                        </div>

                        <div className="survivability-factor-row">
                          <span style={{ width: '110px' }}>RF Communications:</span>
                          <div className="factor-track">
                            <div
                              className="factor-fill"
                              style={{ width: `${survivabilityScore.factors?.comms?.score ?? survivabilityScore.factors?.comms ?? 90}%`, background: '#ffb867' }}
                            />
                          </div>
                          <b style={{ width: '40px', textAlign: 'right' }}>{survivabilityScore.factors?.comms?.score ?? survivabilityScore.factors?.comms ?? 90}%</b>
                        </div>
                      </div>

                      {/* 2. Solar Particle Event (SPE) Simulator */}
                      <div className="eva-metric-card" style={{ borderColor: speActive ? '#ef4444' : undefined }}>
                        <div className="eva-card-title-row">
                          <h4>☀️ SOLAR PARTICLE EVENT (SPE) SCENARIO</h4>
                          <span className={`status-pill ${speActive ? 'crit' : 'ok'}`}>
                            {speActive ? `ACTIVE (${speSeverity})` : 'BASELINE GCR'}
                          </span>
                        </div>
                        <div style={{ display: 'flex', gap: '8px', margin: '8px 0' }}>
                          <button
                            type="button"
                            className={`plan-button ${speActive ? 'danger' : ''}`}
                            style={{ height: '32px', fontSize: '11px', margin: 0 }}
                            onClick={() => setSpeActive((v) => !v)}
                          >
                            {speActive ? '☀️ Cancel SPE Simulation' : '☀️ Simulate Solar Particle Event'}
                          </button>
                          {speActive && (
                            <button
                              type="button"
                              className="secondary-button"
                              style={{ height: '32px', fontSize: '11px', padding: '0 10px' }}
                              onClick={() => {
                                setSpeActive(false);
                                setSpeSeverity('S2');
                                setNotice('Reset radiation simulation to baseline galactic cosmic ray (GCR) conditions.');
                              }}
                            >
                              Reset
                            </button>
                          )}
                        </div>

                        {speActive && (
                          <div style={{ margin: '10px 0' }}>
                            <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '4px' }}>SEVERITY LEVEL:</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
                              {['S1', 'S2', 'S3', 'S4'].map((s) => (
                                <button
                                  key={s}
                                  type="button"
                                  className={`secondary-button ${speSeverity === s ? 'active' : ''}`}
                                  style={{
                                    fontSize: '11px',
                                    fontWeight: 700,
                                    padding: '4px',
                                    background: speSeverity === s ? '#ef4444' : 'rgba(255,255,255,0.06)',
                                    color: speSeverity === s ? '#ffffff' : '#cbd5e1',
                                  }}
                                  onClick={() => setSpeSeverity(s)}
                                >
                                  {s}
                                </button>
                              ))}
                            </div>
                            <div style={{ fontSize: '10px', color: '#fca5a5', marginTop: '6px' }}>
                              Dose rate: <strong>{SPE_SEVERITY_LEVELS[speSeverity]?.doseRateMsvH} mSv/h</strong> (Normal: 0.05 mSv/h)
                            </div>
                          </div>
                        )}

                        <div className="shelter-callout" style={{ marginTop: '10px' }}>
                          <div className="shelter-head">
                            <span className="shelter-pin">🛡️</span>
                            <strong>NEAREST TERRAIN SHELTER:</strong>
                          </div>
                          <div className="shelter-details">
                            <span className="shelter-name">{nearestShelter.name}</span>
                            <span className="shelter-meta">
                              {nearestShelter.distanceM} m away · Bearing {nearestShelter.bearingDeg}° · {(nearestShelter.shieldingFactor * 100).toFixed(0)}% Shielding Factor
                            </span>
                          </div>
                          <button
                            type="button"
                            className="secondary-button"
                            style={{ width: '100%', marginTop: '6px', fontSize: '10.5px', padding: '4px' }}
                            onClick={() => {
                              setDestination({ lon: nearestShelter.coordinates[0], lat: nearestShelter.coordinates[1], name: nearestShelter.name });
                              setNotice(`Emergency destination set to: ${nearestShelter.name}`);
                            }}
                          >
                            Set Shelter as Destination
                          </button>
                        </div>
                      </div>

                      {/* 3. Dual-Radius Walk-Back Safety */}
                      <div className="eva-metric-card">
                        <div className="eva-card-title-row">
                          <h4>🚶 DUAL-RADIUS WALK-BACK SAFETY</h4>
                          <span className={`status-pill ${walkBackSafety.safe ? 'ok' : 'crit'}`}>
                            {walkBackSafety.safe ? 'SAFE FOOT RETURN' : 'ROVER SUPPORT REQ'}
                          </span>
                        </div>
                        <dl className="compact-dl" style={{ margin: '8px 0' }}>
                          <dt>Distance to Habitat Base:</dt>
                          <dd><b>{walkBackSafety.distKm} km</b></dd>
                          <dt>Safe On-Foot Return Limit:</dt>
                          <dd><b>1.80 km</b> (at 1.0 m/s)</dd>
                          <dt>Rover-Assisted Envelope:</dt>
                          <dd><b>5.20 km</b> (vehicle range)</dd>
                          <dt>Estimated Walking Time:</dt>
                          <dd><b>{walkBackSafety.walkDurationH} hrs</b></dd>
                        </dl>
                        <div className={`walkback-verdict-banner ${walkBackSafety.safe ? 'safe' : 'warn'}`}>
                          {walkBackSafety.safe
                            ? '✅ WITHIN SAFE ON-FOOT WALK-BACK RADIUS — Emergency walk-back to base feasible within PLSS oxygen reserves.'
                            : '⚠️ ROUTE EXCEEDS ON-FOOT WALK-BACK RADIUS — ROVER SUPPORT REQUIRED FOR RETURN. Walking return exceeds safe single-suit endurance.'}
                        </div>
                      </div>

                      {/* 4. Planetary Protection Special Regions */}
                      <div className="eva-metric-card" style={{ borderColor: protectionCheck.conflict ? '#ef4444' : undefined }}>
                        <div className="eva-card-title-row">
                          <h4>🪐 PLANETARY PROTECTION REGIONS</h4>
                          <span className={`status-pill ${protectionCheck.conflict ? 'crit' : 'ok'}`}>
                            {protectionCheck.conflict ? 'CONFLICT DETECTED' : 'CLEAR'}
                          </span>
                        </div>
                        {protectionCheck.conflict ? (
                          <div style={{ marginTop: '8px' }}>
                            <div className="rule-box warning-red">
                              <strong>🚨 RESTRICTED SPECIAL REGION INTERSECTION:</strong>
                              <p style={{ margin: '4px 0' }}>
                                Planned route traverses <strong>{protectionCheck.conflictingZones.map((z) => z.name).join(', ')}</strong> ({protectionCheck.conflictingZones[0]?.category}). Human access strictly restricted under COSPAR Policy.
                              </p>
                            </div>
                            <button
                              type="button"
                              className="plan-button"
                              style={{ width: '100%', marginTop: '8px', fontSize: '11px', height: '34px' }}
                              onClick={() => setScoutRoverModalOpen(true)}
                            >
                              DISPATCH SCOUT ROVER (SIMULATION)
                            </button>
                          </div>
                        ) : (
                          <div style={{ marginTop: '6px' }}>
                            <p style={{ fontSize: '11px', color: '#94a3b8', margin: '6px 0' }}>
                              ✅ Route remains clear of designated COSPAR Category IVc Special Regions (Neretva Vallis Delta Deposit, Hydrated Silica beds).
                            </p>
                            <div style={{ display: 'flex', gap: '6px', marginTop: '6px' }}>
                              <button
                                type="button"
                                className="secondary-button"
                                style={{ flex: 1, fontSize: '11px', padding: '5px' }}
                                onClick={() => setSelectedProtectionZone(PLANETARY_PROTECTION_ZONES[0])}
                              >
                                🪐 Inspect Cat IVc Zone
                              </button>
                              <button
                                type="button"
                                className="plan-button"
                                style={{ flex: 1, fontSize: '11px', padding: '5px' }}
                                onClick={() => setScoutRoverModalOpen(true)}
                              >
                                🤖 Dispatch Scout Rover
                              </button>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* 5. RF Communications & Orbiter Pass */}
                      <div className="eva-metric-card">
                        <div className="eva-card-title-row">
                          <h4>📡 RF COMMS &amp; ORBITER PASSES</h4>
                          <span className="status-pill" style={{ color: rfComms.labelColor, borderColor: rfComms.labelColor }}>
                            {rfComms.status}
                          </span>
                        </div>
                        <dl className="compact-dl" style={{ margin: '8px 0' }}>
                          <dt>Direct LOS to Base Antenna:</dt>
                          <dd><b>{rfComms.losBasePercentage}%</b></dd>
                          <dt>Active UHF Relay Orbiters:</dt>
                          <dd><b>MRO, TGO, Odyssey</b></dd>
                          <dt>Next Orbiter Overhead Pass:</dt>
                          <dd><b>T-42m (MRO Electra)</b></dd>
                        </dl>
                        <p style={{ fontSize: '10.5px', color: '#94a3b8', margin: '4px 0', lineHeight: 1.35 }}>
                          {rfComms.advice}
                        </p>
                      </div>

                      {/* 6. Authentic NASA Surface Vantage Points */}
                      <div className="eva-metric-card">
                        <div className="eva-card-title-row">
                          <h4>📷 AUTHENTIC NASA SURFACE IMAGERY</h4>
                          <span className="status-pill ok">3 VANTAGE POINTS</span>
                        </div>
                        <p style={{ fontSize: '10.5px', color: '#94a3b8', margin: '4px 0 8px 0' }}>
                          Verified high-resolution Mastcam-Z &amp; SuperCam ground photography from NASA PDS Photojournal archives.
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                          {Object.values(AUTHENTIC_NASA_SURFACE_IMAGERY).map(photo => (
                            <button
                              key={photo.pdsPhotojournalId}
                              type="button"
                              className="secondary-button"
                              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', padding: '6px 8px', textAlign: 'left' }}
                              onClick={() => setSelectedNasaPhoto(photo)}
                            >
                              <span>📷 <b>{photo.pdsPhotojournalId}</b> · {photo.name}</span>
                              <span style={{ fontSize: '10px', color: '#94a3b8' }}>Sol {photo.sol}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Export Controls */}
                  <div className="export-controls">
                    <select aria-label="Export format" value={exportFormat} onChange={e => setExportFormat(e.target.value)}>
                      <option value="json">JSON manifest</option>
                      <option value="geojson">GeoJSON Feature</option>
                      <option value="csv">CSV (Segments)</option>
                      <option value="pdf">PDF Mission Dossier (.pdf)</option>
                      <option value="brief">Mission Brief (.md)</option>
                      <option value="config">Mission Config (.json)</option>
                    </select>
                    <button onClick={download} disabled={!result}>
                      <Icon name="download" />
                      Export
                    </button>
                  </div>

                  {result?.limitations?.length > 0 && (
                    <details className="analysis-limitations">
                      <summary>Engineering limitations ({result.limitations.length})</summary>
                      <ul>
                        {result.limitations.map((lim, i) => (
                          <li key={i}>{lim}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              )}
            </div>
          </aside>
        )}

        {layersOpen && (
          <section className="layers-popover glass" aria-label="Map layers">
            <div className="panel-heading">
              <h2>Layers</h2>
              <button className="icon-button" onClick={() => setLayersOpen(false)} aria-label="Close map layers">
                <Icon name="close" />
              </button>
            </div>
            <LayerToggle label="Recorded traverse" color="amber" checked={showHistory} onChange={setShowHistory} />
            <LayerToggle label="Recorded waypoints" color="violet" checked={showWaypoints} onChange={setShowWaypoints} />
            <LayerToggle label="Planned route" color="mint" checked={showRoute} onChange={setShowRoute} />
            <LayerToggle label="Alternatives" color="gray" checked={showAlternatives} onChange={setShowAlternatives} />
            <LayerToggle label="Reachable return zone" color="mint" checked={showReachableZone} onChange={setShowReachableZone} />
            <LayerToggle label="Rescue time map" color="amber" checked={showRescueMap} onChange={setShowRescueMap} />
            <LayerToggle label="Hazards & Obstacles" color="amber" checked={hazards} onChange={setHazards} />
            <LayerToggle label="Data coverage" color="gray" checked={coverage} onChange={setCoverage} />
            <LayerToggle label="Live Orbiters (MRO/ODY/MEX/TGO)" color="mint" checked={showOrbiters} onChange={setShowOrbiters} />
            <LayerToggle label="Orbiter Ground Tracks" color="gray" checked={showGroundTracks} onChange={setShowGroundTracks} />
            <LayerToggle label="Orbital Footprints" color="amber" checked={showFootprints} onChange={setShowFootprints} />
            <LayerToggle label="Science Targets (Jezero)" color="mint" checked={showScienceTargets} onChange={setShowScienceTargets} />
            <LayerToggle label="Curiosity Gale Traverse" color="amber" checked={showCuriosity} onChange={setShowCuriosity} />

            <div className="layer-divider" />
            <div className="layer-section-label">Planetary Imagery & Terrain Sources</div>
            <LayerToggle label="Viking Global Mosaic (232m)" color="gray" checked={showViking} onChange={setShowViking} />
            {showViking && (
              <div className="slider-field compact">
                <label htmlFor="viking-opacity">
                  Viking Opacity <strong>{Math.round(vikingOpacity * 100)}%</strong>
                </label>
                <input
                  id="viking-opacity"
                  type="range"
                  min="0"
                  max="1.0"
                  step="0.05"
                  value={vikingOpacity}
                  onChange={e => setVikingOpacity(Number(e.target.value))}
                />
              </div>
            )}

            <LayerToggle label="CTX Regional Mosaic (6m)" color="mint" checked={showCtx} onChange={setShowCtx} />
            {showCtx && (
              <div className="slider-field compact">
                <label htmlFor="ctx-opacity">
                  CTX Opacity <strong>{Math.round(ctxOpacity * 100)}%</strong>
                </label>
                <input
                  id="ctx-opacity"
                  type="range"
                  min="0"
                  max="1.0"
                  step="0.05"
                  value={ctxOpacity}
                  onChange={e => setCtxOpacity(Number(e.target.value))}
                />
              </div>
            )}

            <LayerToggle label="HiRISE Orthomosaic (0.25m)" color="mint" checked={showHirise} onChange={setShowHirise} />
            {showHirise && (
              <div className="slider-field compact">
                <label htmlFor="hirise-opacity">
                  HiRISE Opacity <strong>{Math.round(hiriseOpacity * 100)}%</strong>
                </label>
                <input
                  id="hirise-opacity"
                  type="range"
                  min="0"
                  max="1.0"
                  step="0.05"
                  value={hiriseOpacity}
                  onChange={e => setHiriseOpacity(Number(e.target.value))}
                />
              </div>
            )}

            <LayerToggle label="MOLA-HRSC Terrain (200m)" color="amber" checked={showMolaTerrain} onChange={setShowMolaTerrain} />
            {showMolaTerrain && (
              <div className="slider-field compact">
                <label htmlFor="mola-opacity">
                  MOLA Terrain Opacity <strong>{Math.round(molaOpacity * 100)}%</strong>
                </label>
                <input
                  id="mola-opacity"
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  value={molaOpacity}
                  onChange={e => setMolaOpacity(Number(e.target.value))}
                />
              </div>
            )}

            <LayerToggle label="Derived DEM Hillshade" color="gray" checked={showHillshade} onChange={setShowHillshade} />
            <LayerToggle label="Derived Slope Heatmap" color="amber" checked={showSlope} onChange={setShowSlope} />
            <LayerToggle label="Derived Surface Roughness" color="violet" checked={showRoughness} onChange={setShowRoughness} />

            <div className="layer-basemap">
              <span>Basemap Mode</span>
              <div className="segmented">
                <button className={base === 'auto' || base === 'imagery' ? 'active' : ''} onClick={() => setBase('auto')}>
                  Auto
                </button>
                <button className={base === 'viking' ? 'active' : ''} onClick={() => setBase('viking')}>
                  Viking
                </button>
                <button className={base === 'ctx' ? 'active' : ''} onClick={() => setBase('ctx')}>
                  CTX
                </button>
                <button className={base === 'hirise' ? 'active' : ''} onClick={() => setBase('hirise')}>
                  HiRISE
                </button>
                <button className={base === 'relief' ? 'active' : ''} onClick={() => setBase('relief')}>
                  Relief
                </button>
              </div>
            </div>
            <div className="slider-field">
              <label htmlFor="terrain-opacity">
                DEM Overlays Opacity <strong>{Math.round(terrainOpacity * 100)}%</strong>
              </label>
              <input
                id="terrain-opacity"
                type="range"
                min="0.1"
                max="1.0"
                step="0.05"
                value={terrainOpacity}
                onChange={e => setTerrainOpacity(Number(e.target.value))}
              />
            </div>
            {view3d && (
              <div className="slider-field">
                <label htmlFor="exaggeration">
                  Elevation exaggeration <strong>×{exaggeration}</strong>
                </label>
                <input
                  id="exaggeration"
                  type="range"
                  min="2"
                  max="10"
                  step="1"
                  value={exaggeration}
                  onChange={e => setExaggeration(Number(e.target.value))}
                />
              </div>
            )}
            <p className="field-note">
              {live ? 'Hazards display segment-level terrain evidence flags.' : 'Heatmap displays slope and roughness derived locally.'}{' '}
              Basemap is for visual reference; routing uses verified DEM rasters.
            </p>
          </section>
        )}

        {historyMode ? (
          <TraverseTimeline
            cut={solCut}
            max={maxSol}
            minSol={minSol}
            stats={historyStats}
            windowStats={windowStats}
            onChange={v => { setSolCut(v); setWaypoint(null); }}
            onAll={showAllHistory}
            onFit={() => mapActions.current?.fitFullTraverse?.()}
            windowSize={15}
          />
        ) : plannerMode ? (
          <Profile
            route={active}
            onHover={setHover}
            expanded={profileExpanded}
            onToggle={value => setProfileExpanded(v => (typeof value === 'boolean' ? value : !v))}
            busy={busy}
            activeProfileTab={activeProfileTab}
            onSelectProfileTab={setActiveProfileTab}
          />
        ) : null}

        <div className="traverse-key glass">
          <span><i className="recorded" style={{ background: '#bfa07a' }} />Full traverse</span>
          <span><i className="highlighted" style={{ background: '#ffb867' }} />15-sol window</span>
          <span><i className="stops" />Waypoints</span>
          {showRoute && <span><i className="planned" />Planned route</span>}
        </div>

        {notice && <div className="notice-toast glass" role="status">{notice}</div>}
      </main>

      {/* Backend API Connection & Diagnostics Dialog */}
      {showSettings && (
        <Dialog onClose={() => setShowSettings(false)} label="Close API connection settings">
          <p className="eyebrow">Backend integration</p>
          <h2>Connect Mission Control</h2>
          <p>
            Connect to the MarsPath FastAPI backend. We validate service health, terrain dataset readiness, layer capabilities, and the OpenAPI contract.
          </p>
          <label>
            Backend Base URL
            <input
              type="url"
              placeholder="http://localhost:8000"
              value={apiUrl}
              onChange={e => setApiUrl(e.target.value)}
            />
          </label>
          <div className="origin-note">
            CORS Origin Requirement:
            <code>{location.origin}</code>
          </div>

          {api && (
            <div className="api-diagnostics-box">
              <div className="status-row">
                <span>Service Status:</span>
                <strong className={apiConnectionState === 'connected' ? 'text-ok' : 'text-warn'}>
                  {api.health?.status?.toUpperCase() || 'UNKNOWN'} ({apiConnectionState})
                </strong>
              </div>
              <div className="status-row">
                <span>Active Data Mode:</span>
                <code>{provenance.dataMode}</code>
              </div>
              <div className="status-row">
                <span>Real DEM Loaded:</span>
                <span>{api.status?.real_dem_loaded ? 'Yes (MOLA-HRSC)' : 'No (Synthetic / Missing)'}</span>
              </div>
              <div className="status-row">
                <span>Local Integrity:</span>
                <span>{provenance.fileIntegrityText}</span>
              </div>
              <div className="status-row">
                <span>Upstream Checksum:</span>
                <span>{provenance.upstreamChecksumText}</span>
              </div>
              <div className="status-row">
                <span>HiRISE Status:</span>
                <span>{api.status?.hirise_status || 'disabled'}</span>
              </div>
              {api.status?.blocking_errors?.length > 0 && (
                <div className="blocking-errors-list">
                  <span>Blocking Errors:</span>
                  <ul>
                    {api.status.blocking_errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {connectionError && (
            <div className="error-message" role="alert">
              {connectionError}
            </div>
          )}

          <div className="dialog-button-row">
            <button className="plan-button" onClick={connect} disabled={connecting || !apiUrl.trim()}>
              {connecting ? 'Checking backend…' : api ? 'Re-validate connection' : 'Connect and validate'}
              <Icon name="arrow" />
            </button>
            {api && (
              <button className="secondary-button" onClick={disconnectApi}>
                Disconnect (Use local)
              </button>
            )}
          </div>
          <p className="field-note">
            The bundled planner remains fully operational offline. Dijkstra remains available in the bundled planner if the Python API exposes only A*.
          </p>
        </Dialog>
      )}

      {/* Planetary Protection Special Region Dialog */}
      {selectedProtectionZone && (
        <Dialog onClose={() => setSelectedProtectionZone(null)} label="Planetary Protection Details">
          <p className="eyebrow">COSPAR Planetary Protection Directive</p>
          <h2>{selectedProtectionZone.name}</h2>
          <div className="protection-badge-row" style={{ margin: '8px 0 12px 0' }}>
            <span
              className={`category-badge ${
                selectedProtectionZone.category === 'COSPAR Category IVc'
                  ? 'cat-ivc'
                  : selectedProtectionZone.category === 'Candidate Sensitive'
                  ? 'candidate'
                  : 'science'
              }`}
            >
              {selectedProtectionZone.category}
            </span>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>ID: <strong>{selectedProtectionZone.id}</strong></span>
          </div>

          <div className="protection-modal-body">
            <div className="rule-box warning-red">
              <strong>RESTRICTION MANDATE:</strong>
              <p style={{ margin: '4px 0 0 0' }}>
                Human boots-on-the-ground exploration is strictly restricted in this region to prevent forward bio-contamination of potential Martian astrobiological niches.
              </p>
            </div>

            <div className="rule-box">
              <strong>COSPAR BIOBURDEN SPECIFICATION:</strong>
              <p style={{ margin: '4px 0 0 0' }}>
                {selectedProtectionZone.sterilizationRules || 'Bioburden limit < 0.03 bacterial spores / m². Certified dry heat microbial reduction or hydrogen peroxide vapor.'}
              </p>
            </div>

            <p style={{ fontSize: '12px', lineHeight: 1.5, color: '#cbd5e1', margin: 0 }}>
              {selectedProtectionZone.description}
            </p>

            <div className="dialog-button-row" style={{ marginTop: '12px' }}>
              <button
                type="button"
                className="plan-button"
                onClick={() => {
                  setScoutRoverModalOpen(true);
                  setSelectedProtectionZone(null);
                }}
              >
                DISPATCH SCOUT ROVER (SIMULATION)
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setSelectedProtectionZone(null)}
              >
                Close
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Scout Rover Conceptual Robotic Handoff Dialog */}
      {scoutRoverModalOpen && (
        <Dialog onClose={() => setScoutRoverModalOpen(false)} label="Scout Rover Dispatch">
          <p className="eyebrow">Robotic Asset Coordination</p>
          <h2>Dispatch Sterilized Scout Rover</h2>
          <p style={{ fontSize: '12px', color: '#94a3b8', margin: '4px 0 14px 0' }}>
            Autonomous robotic sampling reconnaissance into COSPAR Category IVc Special Region.
          </p>

          <div className="scout-modal-body">
            <div className="rule-box" style={{ borderColor: 'rgba(56, 189, 248, 0.4)' }}>
              <strong style={{ color: '#38bdf8' }}>MISSION PROFILE:</strong>
              <p style={{ margin: '4px 0 0 0' }}>
                Sterilized robotic scout rover SC-01 will traverse restricted sediments, perform microscopic Raman/SHERLOC spectrometry, collect sealed core samples, and transmit data back to the astronaut habitat.
              </p>
            </div>

            <div className="scout-specs-grid">
              <div className="spec-cell">
                <span className="cell-lbl">Asset Identifier</span>
                <span className="cell-val">Perseverance Scout SC-01</span>
              </div>
              <div className="spec-cell">
                <span className="cell-lbl">Sterilization Certification</span>
                <span className="cell-val">Cat IVc (&lt;0.024 spores/m²)</span>
              </div>
              <div className="spec-cell">
                <span className="cell-lbl">Science Payload</span>
                <span className="cell-val">SHERLOC-Lite + Raman + Core Drill</span>
              </div>
              <div className="spec-cell">
                <span className="cell-lbl">Telemetry Uplink</span>
                <span className="cell-val">Direct UHF Crew Habitat</span>
              </div>
            </div>

            <p style={{ fontSize: '10px', color: '#64748b', fontStyle: 'italic', margin: '6px 0 0 0' }}>
              [SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST — CONCEPTUAL HANDOFF ONLY]
            </p>

            <div className="dialog-button-row" style={{ marginTop: '12px' }}>
              <button
                type="button"
                className="plan-button"
                onClick={() => {
                  setScoutRoverDispatched(true);
                  setScoutRoverModalOpen(false);
                  setNotice('Scout Rover SC-01 dispatched to restricted Special Region for autonomous sampling.');
                }}
              >
                CONFIRM SCOUT DISPATCH
              </button>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setScoutRoverModalOpen(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Authentic NASA Surface Imagery Lightbox Modal */}
      {selectedNasaPhoto && (
        <Dialog onClose={() => setSelectedNasaPhoto(null)} label="Authentic NASA Surface Photograph">
          <p className="eyebrow">NASA Planetary Data System (PDS) Ground Truth</p>
          <h2 style={{ fontSize: '16px' }}>{selectedNasaPhoto.title}</h2>

          <div className="nasa-photo-modal-body">
            <div className="nasa-photo-container">
              <img
                src={selectedNasaPhoto.imageUrl}
                alt={selectedNasaPhoto.title}
                className="nasa-photo-img"
                loading="lazy"
              />
            </div>

            <div className="photo-meta-grid">
              <div><strong>Photojournal ID:</strong> {selectedNasaPhoto.pdsPhotojournalId}</div>
              <div><strong>Instrument:</strong> {selectedNasaPhoto.instrument}</div>
              <div><strong>Mission Sol:</strong> Sol {selectedNasaPhoto.sol}</div>
              <div><strong>UTC Time:</strong> {new Date(selectedNasaPhoto.acquisitionDateUtc).toLocaleDateString()}</div>
              <div><strong>Location:</strong> {selectedNasaPhoto.name}</div>
              <div><strong>Credit:</strong> {selectedNasaPhoto.credit}</div>
            </div>

            <p className="photo-context-desc">
              {selectedNasaPhoto.description}
            </p>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '6px' }}>
              <a
                href={selectedNasaPhoto.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="pds-external-link"
              >
                Open Official NASA/JPL PDS Photojournal Entry ↗
              </a>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setSelectedNasaPhoto(null)}
              >
                Close
              </button>
            </div>
          </div>
        </Dialog>
      )}

      {/* Command Palette */}
      {commandsOpen && (
        <Dialog onClose={() => setCommandsOpen(false)} label="Close command bar">
          <div className="command-search">
            <Icon name="search" />
            <input
              autoFocus
              type="search"
              aria-label="Search commands"
              placeholder="What would you like to do?"
              value={commandQuery}
              onChange={e => {
                setCommandQuery(e.target.value);
                setCommandIndex(0);
              }}
              onKeyDown={e => {
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                  e.preventDefault();
                  setCommandIndex(i =>
                    matches.length ? (i + (e.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length : 0
                  );
                } else if (e.key === 'Enter') {
                  e.preventDefault();
                  execute(matches[commandIndex]);
                }
              }}
            />
          </div>
          <div className="command-list">
            {matches.map((c, i) => (
              <button
                key={c.name}
                disabled={c.disabled}
                className={i === commandIndex ? 'selected' : ''}
                onClick={() => execute(c)}
                onPointerEnter={() => setCommandIndex(i)}
              >
                <Icon name={c.icon} />
                <span>
                  {c.name}
                  <small>{c.hint}</small>
                </span>
                <kbd>↵</kbd>
              </button>
            ))}
            {!matches.length && <p>No matching actions.</p>}
          </div>
          <div className="command-footer">
            <span>↑ ↓ Navigate</span>
            <span>Enter Select</span>
            <span>Esc Close</span>
          </div>
        </Dialog>
      )}
    </div>
  );
}

function formatPoint(p) {
  if (!p || !Number.isFinite(Number(p.lat)) || !Number.isFinite(Number(p.lon))) return '—';
  return (
    Math.abs(Number(p.lat)).toFixed(4) +
    '°' +
    (Number(p.lat) < 0 ? 'S' : 'N') +
    ', ' +
    Math.abs(Number(p.lon)).toFixed(4) +
    '°' +
    (Number(p.lon) < 0 ? 'W' : 'E')
  );
}

function parsePoint(text) {
  const clean = text.trim().toUpperCase().replace(/°/g, '');
  const match = clean.match(/^([+-]?\d+(?:\.\d+)?)\s*([NS]?)\s*[,;]\s*([+-]?\d+(?:\.\d+)?)\s*([EW]?)$/);
  if (!match) return null;
  let lat = Number(match[1]);
  let lon = Number(match[3]);
  if (match[2] === 'S') lat = -Math.abs(lat);
  if (match[4] === 'W') lon = -Math.abs(lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 360) return null;
  return { lat, lon };
}

function CoordinateRow({ point, label, marker, active, onPick, onCommit, onDraft, onRemove }) {
  const [text, setText] = useState(() => formatPoint(point));
  const ref = useRef();
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) {
      setText(formatPoint(point));
      ref.current?.setCustomValidity('');
    }
  }, [point?.lat, point?.lon]);

  function validate(value) {
    const p = parsePoint(value);
    ref.current?.setCustomValidity(p ? '' : 'Enter latitude, longitude, for example 18.39°N, 77.40°E.');
    return p;
  }

  return (
    <div className="coordinate-row">
      <span className={'pin-letter ' + (marker.startsWith('W') ? 'waypoint' : '')}>{marker}</span>
      <label>
        <span>{label}</span>
        <input
          ref={ref}
          type="text"
          value={text}
          required
          aria-label={label + ' coordinates'}
          spellCheck="false"
          onFocus={() => {
            focused.current = true;
          }}
          onChange={e => {
            setText(e.target.value);
            validate(e.target.value);
            onDraft();
          }}
          onBlur={() => {
            focused.current = false;
            const p = validate(text);
            if (p) {
              onCommit(p);
              setText(formatPoint(p));
            }
          }}
          onKeyDown={e => {
            if (e.key === 'Enter') {
              e.preventDefault();
              e.currentTarget.blur();
            }
          }}
        />
      </label>
      <div className="coordinate-actions">
        <button
          type="button"
          className={'icon-button pick-button ' + (active ? 'active' : '')}
          onClick={onPick}
          aria-label={'Pick ' + label.toLowerCase() + ' on map'}
          title={'Pick ' + label.toLowerCase() + ' on map'}
          aria-pressed={active}
        >
          <Icon name="crosshair" />
        </button>
        {onRemove && (
          <button
            type="button"
            className="icon-button remove-waypoint-btn"
            onClick={onRemove}
            aria-label="Remove science stop"
            title="Remove stop"
          >
            <Icon name="close" />
          </button>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value, digits = 1, unit, primary }) {
  const [shown, setShown] = useState(0);
  const previous = useRef(0);

  useEffect(() => {
    if (!Number.isFinite(value)) return;
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(value);
      previous.current = value;
      return;
    }
    const from = previous.current;
    const start = performance.now();
    let frame;
    function tick(t) {
      const p = Math.min(1, (t - start) / 420);
      const v = from + (value - from) * (1 - (1 - p) ** 3);
      setShown(v);
      if (p < 1) frame = requestAnimationFrame(tick);
      else previous.current = value;
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);

  return (
    <div className={'metric ' + (primary ? 'primary' : '')}>
      <span>{label}</span>
      <strong>
        {Number.isFinite(value) ? fmt(shown, digits) : '—'}
        <small>{unit}</small>
      </strong>
    </div>
  );
}

function LayerToggle({ label, color, checked, onChange }) {
  return (
    <label className="layer-toggle">
      <i className={color} />
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} />
    </label>
  );
}

createRoot(document.getElementById('root')).render(<App />);
