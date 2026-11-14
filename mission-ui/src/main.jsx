import { validateTraverse, visibleDrives, visibleWaypoints, traverseStats, exportTraverse } from './traverse.js';
import { TraversePanel, TraverseTimeline } from './TraversePanel.jsx';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import 'ol/ol.css';
import './style.css';
import MapView, {
  JEZERO_VALIDATED_DEM_BOUNDS,
  JEZERO_HIRISE_ORTHO_BOUNDS,
  JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS,
  JEZERO_CTX_ORTHO_BOUNDS,
} from './MapView.jsx';
import {
  AUTHORITATIVE_MARS_IMAGERY_CATALOG,
  AUTHORITATIVE_MARS_TERRAIN_CATALOG,
  verifyCoordinateDatasetCoverage,
} from './wmts_capabilities.js';
import Profile from './Profile.jsx';
import { exportGeoJSON, exportMissionBriefMarkdown, exportMissionConfigJSON } from './export.js';
import {
  JEZERO_SCIENCE_TARGETS_CLIENT,
  MISSION_PRESETS_CLIENT,
  fetchConditionsForPoint,
  fetchRoverReplayState,
  enrichResponseWithMasterSpec,
} from './planning_enrichment.js';
import { buildTerrain } from './terrain.js';
import Icon from './Icons.jsx';
import { resolveInitialApiUrl, resolveTerrainProvenance, resolveAlternativeShortfall, canSubmitRoute, validateRouteExecutionPreconditions } from './integration.js';
import IntelligencePanel from './IntelligencePanel.jsx';
import NasaDataPanel from './NasaDataPanel.jsx';
import CloudAiPanel from './CloudAiPanel.jsx';
import {
  fetchSpacecraftList,
  fetchGroundTrack,
  fetchOrbitalObservations,
  fetchRoversList,
  fetchIntelligenceTimeline,
  propagateKeplerian,
} from './intelligence.js';

const INITIAL = { start: { lon: 77.40, lat: 18.39 }, destination: { lon: 77.44, lat: 18.42 } };
const fmt = (n, d = 1) => Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }) : '—';
const initialRequest = { ...INITIAL, algorithm: 'astar', mode: 'balanced', constraints: { max_slope_deg: 20, max_roughness: 0.85, avoid_unobserved_terrain: true }, science_waypoints: [], num_alternatives: 3 };

function Dialog({ onClose, children, label = 'Close dialog' }) {
  const ref = useRef();
  useEffect(() => {
    ref.current.showModal();
    ref.current.querySelector('input[autofocus]')?.focus();
  }, []);
  return (
    <dialog ref={ref} className="settings-dialog" onCancel={e => { e.preventDefault(); onClose(); }}>
      <button className="close-dialog" onClick={onClose} aria-label={label}>×</button>
      {children}
    </dialog>
  );
}

function App() {
  const [missionView, setMissionView] = useState(() => {
    const v = new URLSearchParams(location.search).get('view');
    return v === 'planner' ? 'planner' : v === 'intelligence' ? 'intelligence' : v === 'nasa-data' ? 'nasa-data' : v === 'cloud-ai' ? 'cloud-ai' : 'history';
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

  const historyMode = missionView === 'history';
  const intelligenceMode = missionView === 'intelligence';
  const nasaDataMode = missionView === 'nasa-data';
  const cloudAiMode = missionView === 'cloud-ai';
  const plannerMode = missionView === 'planner';

  const drives = useMemo(() => visibleDrives(traverse, solCut), [traverse, solCut]);
  const waypoints = useMemo(() => visibleWaypoints(waypointData, solCut), [waypointData, solCut]);
  const historyStats = useMemo(() => traverseStats(drives, waypoints), [drives, waypoints]);
  const maxSol = traverse ? Math.max(...traverse.features.map(f => f.properties.sol)) : 2022;

  // Intelligence State
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

  // Layer toggles
  const [showOrbiters, setShowOrbiters] = useState(true);
  const [showGroundTracks, setShowGroundTracks] = useState(true);
  const [showFootprints, setShowFootprints] = useState(true);
  const [showCuriosity, setShowCuriosity] = useState(false);
  const [showThemisOverlay, setShowThemisOverlay] = useState(false);
  const [showScienceTargets, setShowScienceTargets] = useState(true);
  const [activeBookmark, setActiveBookmark] = useState('jezero');

  // Phase 2-4 Mission Clock, Presets & Time Machine state
  const [departureUtc, setDepartureUtc] = useState('2026-06-15T08:00:00Z');
  const [maxEvaHours, setMaxEvaHours] = useState(8.0);
  const [selectedPresetId, setSelectedPresetId] = useState('flagship_jezero_expedition');
  const [timeMachineOpen, setTimeMachineOpen] = useState(false);
  const [timeMachineUtc, setTimeMachineUtc] = useState('2026-06-15T08:00:00Z');
  const [timeMachineSol, setTimeMachineSol] = useState(415);
  const [conditionsData, setConditionsData] = useState(null);
  const [roverReplayState, setRoverReplayState] = useState(null);
  const [activeProfileTab, setActiveProfileTab] = useState('elevation');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/mission-data/perseverance-traverse.geojson'),
      fetch('/mission-data/perseverance-waypoints.geojson')
    ]).then(async rs => {
      if (rs.some(r => !r.ok)) throw Error('The recorded traverse could not load.');
      const [t, w] = await Promise.all(rs.map(r => r.json()));
      validateTraverse(t);
      if (cancelled) return;
      setTraverse(t);
      setWaypointData(w);
      setSolCut(Math.max(...t.features.map(f => f.properties.sol)));
      setHistoryFit(n => n + 1);
    }).catch(e => {
      if (!cancelled) setTraverseError(e.message);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch('/mission-data/curiosity-traverse.geojson'),
      fetch('/mission-data/curiosity-waypoints.geojson')
    ]).then(async rs => {
      if (rs.some(r => !r.ok)) return;
      const [t, w] = await Promise.all(rs.map(r => r.json()));
      if (!cancelled) {
        setCuriosityTraverse(t);
        setCuriosityWaypoints(w.features || w);
      }
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  function switchMission(mode) {
    setMissionView(mode);
    setShowRoute(mode === 'planner');
    setProfileExpanded(false);
    setLayersOpen(false);
    setPick(null);
    const url = new URL(window.location);
    if (mode === 'planner') url.searchParams.set('view', 'planner');
    else if (mode === 'intelligence') url.searchParams.set('view', 'intelligence');
    else if (mode === 'nasa-data') url.searchParams.set('view', 'nasa-data');
    else if (mode === 'cloud-ai') url.searchParams.set('view', 'cloud-ai');
    else url.searchParams.delete('view');
    window.history.replaceState({}, '', url);

    if (mode === 'history') setHistoryFit(n => n + 1);
    else if (mode === 'planner') setFitToken(n => n + 1);
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

  const [raw, setRaw] = useState(null);
  const [hiriseRaw, setHiriseRaw] = useState(null);
  const [hiriseLoadStatus, setHiriseLoadStatus] = useState('loading');
  const [hiriseLoadReason, setHiriseLoadReason] = useState('Verifying USGS HiRISE 1 m DTM (10.5066/P9REJ9JN)...');
  const [demSourcePreference, setDemSourcePreference] = useState('hirise_1m');
  const [loadError, setLoadError] = useState('');
  const [start, setStart] = useState(INITIAL.start);
  const [destination, setDestination] = useState(INITIAL.destination);
  const [pick, setPick] = useState(null);
  const [algorithm, setAlgorithm] = useState('astar');
  const [mode, setMode] = useState('balanced');
  const [maxSlope, setMaxSlope] = useState(20);
  const [maxRough, setMaxRough] = useState(0.85);
  const [numAlternatives, setNumAlternatives] = useState(3);
  const [base, setBase] = useState('auto');
  const [hazards, setHazards] = useState(false);
  const [coverage, setCoverage] = useState(false);
  const [showHillshade, setShowHillshade] = useState(false);
  const [showSlope, setShowSlope] = useState(false);
  const [showRoughness, setShowRoughness] = useState(false);
  const [imageryOpacity, setImageryOpacity] = useState(1.0);
  const [terrainOpacity, setTerrainOpacity] = useState(0.72);
  const [wmtsLiveStatus, setWmtsLiveStatus] = useState(null);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [hover, setHover] = useState(null);
  const [cursor, setCursor] = useState({ lon: 77.58, lat: 18.38 });
  const [fitToken, setFitToken] = useState(0);
  const [sourceMode, setSourceMode] = useState('browser');
  const [api, setApi] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [apiUrl, setApiUrl] = useState(() => resolveInitialApiUrl());
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [exportFormat, setExportFormat] = useState('json');
  const [notice, setNotice] = useState('');

  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth > 760);
  const [rightExpanded, setRightExpanded] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
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

  const terrain = useMemo(() => raw ? buildTerrain(raw) : null, [raw]);
  const hiriseTerrain = useMemo(() => hiriseRaw ? buildTerrain(hiriseRaw) : null, [hiriseRaw]);
  const coordCoverage = useMemo(() => verifyCoordinateDatasetCoverage(start, destination), [start, destination]);
  const activeDemRaw = useMemo(() => {
    if (demSourcePreference === 'mola_hrsc_200m') return raw;
    if (hiriseRaw && coordCoverage.bothInLocalHiriseDtmCorridor) return hiriseRaw;
    return raw;
  }, [demSourcePreference, hiriseRaw, raw, coordCoverage.bothInLocalHiriseDtmCorridor]);
  const activeDemTerrain = useMemo(() => {
    if (demSourcePreference === 'mola_hrsc_200m') return terrain;
    if (hiriseTerrain && coordCoverage.bothInLocalHiriseDtmCorridor) return hiriseTerrain;
    return terrain;
  }, [demSourcePreference, hiriseTerrain, terrain, coordCoverage.bothInLocalHiriseDtmCorridor]);
  const active = result?.routes.find(r => r.route_id === selected) || result?.routes[0];
  const live = sourceMode === 'api';

  // Load intelligence datasets
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

    return () => { cancelled = true; };
  }, [api]);

  useEffect(() => {
    let cancelled = false;
    const backend = api?.url || '';
    const scIds = ['mro', 'ody', 'mex', 'tgo', 'maven'];
    Promise.all(scIds.map(id => fetchGroundTrack(id, 120, 60, backend)))
      .then(tracks => {
        if (!cancelled) setGroundTracks(tracks.filter(Boolean));
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [api]);

  // Real-time orbiter propagation ticker
  useEffect(() => {
    const updateOrbiterPositions = () => {
      const now = new Date();
      const scIds = ['mro', 'ody', 'mex', 'tgo', 'maven'];
      const positions = scIds.map(id => propagateKeplerian(id, now));
      setSpacecraftPositions(positions);
    };
    updateOrbiterPositions();
    const timer = setInterval(updateOrbiterPositions, 3500);
    return () => clearInterval(timer);
  }, []);

  // Synchronize Mars24 surface conditions & DEM terrain shadows
  useEffect(() => {
    let cancelled = false;
    const lat = Number(start.lat) || 18.4447;
    const lon = Number(start.lon) || 77.4508;
    fetchConditionsForPoint(lat, lon, timeMachineUtc, terrain).then(cond => {
      if (!cancelled && cond) setConditionsData(cond);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [start.lat, start.lon, timeMachineUtc, terrain]);

  // Synchronize Perseverance Rover Replay with Mars Time Machine Sol/UTC
  useEffect(() => {
    let cancelled = false;
    const wpFeatures = waypointData?.features || [];
    fetchRoverReplayState(wpFeatures, { sol: timeMachineSol, utcIso: timeMachineUtc }).then(rep => {
      if (!cancelled && rep) setRoverReplayState(rep);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [waypointData, timeMachineSol, timeMachineUtc]);

  function accept(response, request) {
    if (!Array.isArray(response.routes) || !response.routes.length || response.routes.some(r => !Array.isArray(r.geometry?.coordinates))) {
      throw new Error('The server returned no usable route geometry.');
    }
    const enriched = enrichResponseWithMasterSpec(response, terrain, request);
    setResult(enriched);
    setSelected(enriched.routes[0].route_id);
    lastRequest.current = request;
    setFitToken(n => n + 1);
    setBusy(false);
    setError('');
    setRightExpanded(true);
  }

  useEffect(() => {
    let disposed = false;
    Promise.all([
      fetch('/mission-data/jezero-dem.json'),
      fetch('/mission-data/jezero-dem.sha256'),
      fetch('/mission-data/jezero-hirise-dtm.json').catch(() => null),
      fetch('/mission-data/jezero-hirise-dtm.sha256').catch(() => null),
    ]).then(async ([r, h, hr, hh]) => {
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
      const initialDemForRoute = hiData || data;
      const initReq = { ...initialRequest, preferred_dem_source: hiData ? 'hirise_1m' : 'mola_hrsc_200m' };
      lastRequest.current = initReq;
      w.postMessage({ id: ++sequence.current, raw: initialDemForRoute, request: initReq });
    }).catch(e => {
      if (!disposed) setLoadError(e.message);
    });
    return () => {
      disposed = true;
      worker.current?.terminate();
      abort.current?.abort();
    };
  }, []);

  function invalidate() {
    sequence.current++;
    abort.current?.abort();
    setBusy(false);
    setResult(null);
    setSelected('');
    setHover(null);
    setError('');
    setNotice('');
  }

  function coordinateChange(which, key, value) {
    invalidate();
    (which === 'start' ? setStart : setDestination)(p => ({ ...p, [key]: value }));
  }

  function isWithinJezeroDem(pt) {
    const b = terrain?.b || JEZERO_VALIDATED_DEM_BOUNDS;
    return Number.isFinite(pt.lon) && Number.isFinite(pt.lat) && pt.lon >= b[0] && pt.lon <= b[2] && pt.lat >= b[1] && pt.lat <= b[3];
  }

  function mapPin(p) {
    if (!pick) return;
    invalidate();
    const v = { lon: Number(p.lon.toFixed(5)), lat: Number(p.lat.toFixed(5)) };
    if (!isWithinJezeroDem(v)) {
      setError('Global imagery available. High-resolution elevation and route optimization are not currently supported in this region.');
      setLeftOpen(true);
      return;
    }
    if (pick === 'start') {
      setStart(v);
      setPick('destination');
    } else {
      setDestination(v);
      setPick(null);
    }
  }

  function selectBrowserDemForRequest(req, prefOverride) {
    const pref = prefOverride || req.preferred_dem_source || demSourcePreference;
    if (pref === 'mola_hrsc_200m') return { dem: raw, fallbackNote: null };
    const cov = verifyCoordinateDatasetCoverage(req.start, req.destination);
    const waypointsInHi = (req.science_waypoints || []).every(wp => {
      const b = JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS;
      return wp.lon >= b[0] && wp.lon <= b[2] && wp.lat >= b[1] && wp.lat <= b[3];
    });
    if (hiriseRaw && cov.bothInLocalHiriseDtmCorridor && waypointsInHi) {
      return { dem: hiriseRaw, fallbackNote: null };
    }
    const reason = !hiriseRaw
      ? `HiRISE 1 m DTM unavailable (${hiriseLoadStatus}: ${hiriseLoadReason}). Falling back to USGS MOLA-HRSC 200 m DEM.`
      : `Route corridor extends outside validated USGS HiRISE 1 m DTM window [${JEZERO_HIRISE_DTM_CORRIDOR_BOUNDS.join(', ')}]. Falling back to USGS MOLA-HRSC 200 m DEM.`;
    return { dem: raw, fallbackNote: reason };
  }

  function request(overrides = {}) {
    return {
      start: overrides.start || { lon: Number(start.lon), lat: Number(start.lat) },
      destination: overrides.destination || { lon: Number(destination.lon), lat: Number(destination.lat) },
      algorithm: overrides.algorithm || algorithm,
      mode: overrides.mode || mode,
      constraints: { max_slope_deg: Number(maxSlope), max_roughness: Number(maxRough), avoid_unobserved_terrain: true },
      science_waypoints: overrides.science_waypoints || [],
      num_alternatives: Number(numAlternatives),
      departure_utc: overrides.departure_utc || departureUtc,
      max_eva_hours: Number(overrides.max_eva_hours || maxEvaHours),
      include_return_leg: true,
      preferred_dem_source: overrides.preferred_dem_source || demSourcePreference,
      crs_identifier: 'IAU2000:49900'
    };
  }

  function applyPreset(presetId) {
    const preset = MISSION_PRESETS_CLIENT.find(p => p.preset_id === presetId) || MISSION_PRESETS_CLIENT[0];
    setSelectedPresetId(preset.preset_id);
    invalidate();
    setStart(preset.start);
    setDestination(preset.destination);
    const uiMode = preset.profile === 'safest' ? 'safety_first' : preset.profile === 'direct' ? 'science_first' : 'balanced';
    setMode(uiMode);
    setDepartureUtc(preset.departure_utc || '2026-06-15T08:00:00Z');
    setTimeMachineUtc(preset.departure_utc || '2026-06-15T08:00:00Z');
    setMaxEvaHours(preset.max_eva_hours || 8.0);
    setMissionView('planner');
    setShowRoute(true);
    setProfileExpanded(true);
    setRightExpanded(true);
    if (preset.preset_id === 'flagship_jezero_expedition') {
      setActiveProfileTab('science');
      setNotice('Loaded Flagship Integrated Jezero Robust Science Expedition (Landing → Three Forks → Hawksbill Gap).');
    } else {
      setNotice(`Loaded Mission Preset: ${preset.title}`);
    }
    const req = request({
      start: preset.start,
      destination: preset.destination,
      mode: uiMode,
      departure_utc: preset.departure_utc,
      max_eva_hours: preset.max_eva_hours,
      science_waypoints: preset.waypoints || [],
    });
    if (raw && !live) {
      const { dem, fallbackNote } = selectBrowserDemForRequest(req);
      if (fallbackNote) setNotice(fallbackNote);
      setBusy(true);
      lastRequest.current = req;
      worker.current?.postMessage({ id: ++sequence.current, raw: dem, request: req });
    }
  }

  async function run(opts = {}) {
    if (routeForm.current && !routeForm.current.checkValidity()) {
      setError('Enter valid latitude, longitude coordinates.');
      setLeftOpen(true);
      return;
    }
    const pre = validateRouteExecutionPreconditions({ live, raw, loadError, api, algorithm });
    if (!pre.ok) {
      setError(pre.error);
      setLeftOpen(true);
      setBusy(false);
      return;
    }
    setError('');
    setNotice('');
    setResult(null);
    setHover(null);
    const req = request(opts.demSourceOverride ? { preferred_dem_source: opts.demSourceOverride } : {});
    if ([req.start.lon, req.start.lat, req.destination.lon, req.destination.lat].some(n => !Number.isFinite(n))) {
      setError('Enter valid numeric latitude and longitude values.');
      return;
    }
    if (!isWithinJezeroDem(req.start) || !isWithinJezeroDem(req.destination)) {
      setError('Global imagery available. High-resolution elevation and route optimization are not currently supported in this region.');
      setLeftOpen(true);
      return;
    }
    lastRequest.current = req;
    setBusy(true);
    const id = ++sequence.current;
    if (!live) {
      const { dem, fallbackNote } = selectBrowserDemForRequest(req, opts.demSourceOverride);
      if (fallbackNote) setNotice(fallbackNote);
      worker.current?.postMessage({ id, raw: dem, request: req });
      return;
    }
    const payload = { ...req };
    if (!api.algorithmSupported) delete payload.algorithm;
    const controller = new AbortController();
    abort.current = controller;
    const timeout = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(api.url + '/api/v1/routes/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      const json = await response.json();
      if (!response.ok) {
        throw new Error(json.detail?.error || json.error || (Array.isArray(json.detail) ? json.detail.map(d => d.msg).join('; ') : 'Route request failed (' + response.status + ').'));
      }
      if (id === sequence.current) accept(json, req);
    } catch (e) {
      if (id === sequence.current) {
        setError(e.name === 'AbortError' ? 'The backend did not respond in time. Retry after its service has started.' : e.message + ' Check backend availability and CORS settings.');
        setBusy(false);
      }
    } finally {
      clearTimeout(timeout);
    }
  }

  async function connect() {
    setConnecting(true);
    setConnectionError('');
    try {
      const u = new URL(apiUrl.trim());
      if (!['https:', 'http:'].includes(u.protocol) || u.username || u.password || u.search || u.hash) {
        throw new Error('Enter a plain HTTP(S) backend URL without credentials, query parameters, or fragments.');
      }
      if (u.protocol === 'http:' && !['localhost', '127.0.0.1'].includes(u.hostname)) {
        throw new Error('Use HTTPS for a remote backend.');
      }
      const url = u.href.replace(/\/$/, '');
      const get = async p => {
        const r = await fetch(url + p, { signal: AbortSignal.timeout(30000) });
        if (!r.ok) throw new Error('Backend ' + p + ' returned ' + r.status);
        return r.json();
      };
      const [health, status, layers, openapi] = await Promise.all([
        get('/health'),
        get('/api/v1/data/status'),
        get('/api/v1/layers'),
        get('/openapi.json')
      ]);
      const props = openapi.components?.schemas?.RoutePlanRequest?.properties || {};
      if (!openapi.paths?.['/api/v1/routes/plan']) throw new Error('This server does not expose the MarsPath route-planning endpoint.');
      setApi({ url, health, status, layers, algorithmSupported: !!props.algorithm });
      localStorage.setItem('marspath-api-url', url);
      setApiUrl(url);
      invalidate();
      setSourceMode('api');
      setAlgorithm('astar');
      if (!raw) {
        setMissionView('planner');
        setShowRoute(true);
      }
      setShowSettings(false);
      setNotice('Python API connected. Plan a route or inspect live intelligence.');
    } catch (e) {
      setConnectionError(e.message + '. If this is a CORS error, allow ' + location.origin + ' in MARSPATH_CORS_ORIGINS.');
    } finally {
      setConnecting(false);
    }
  }

  useEffect(() => {
    if (apiUrl && !api && !connecting) {
      connect();
    }
  }, []);

  function download() {
    if (!result) return;
    if (exportFormat === 'brief') {
      const md = exportMissionBriefMarkdown(result, active.route_id, lastRequest.current);
      const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `marspath-mission-brief-${result.mission_id || 'jezero'}.md`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice('Printable Markdown Operational Mission Brief exported.');
      return;
    }
    if (exportFormat === 'config') {
      const cfg = exportMissionConfigJSON({
        preset_id: selectedPresetId,
        start,
        destination,
        algorithm,
        mode,
        departure_utc: departureUtc,
        max_eva_hours: maxEvaHours,
        constraints: { max_slope_deg: maxSlope, max_roughness: maxRough },
        basemap: base,
      });
      const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `marspath-mission-config-${result.mission_id || 'jezero'}.json`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice('Shareable Mission Configuration JSON exported.');
      return;
    }
    const payload = exportFormat === 'geojson' ? exportGeoJSON(result, active.route_id, lastRequest.current) : {
      ...result,
      routes: [active],
      selected_route_id: active.route_id,
      request: lastRequest.current,
      export_manifest: {
        created_at: new Date().toISOString(),
        planetary_target: 'Mars',
        planetary_crs: 'IAU2000:49900',
        purpose: 'Regional planning data; not executable rover commands'
      }
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: exportFormat === 'geojson' ? 'application/geo+json' : 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `marspath-${result.mission_id}.${exportFormat}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice('Mission manifest exported with route geometry and provenance.');
  }

  const penalty = active ? ['slope_penalty', 'roughness_penalty', 'hazard_penalty', 'extra_penalty'].reduce((s, k) => s + (active.cost_breakdown?.[k] || 0), 0) : null;
  const provenance = useMemo(() => resolveTerrainProvenance({ live, raw: activeDemRaw || raw, loadError, api, result, active }), [live, activeDemRaw, raw, loadError, api, result, active]);
  const shortfall = useMemo(() => resolveAlternativeShortfall(result, lastRequest.current?.num_alternatives ?? numAlternatives), [result, numAlternatives]);
  const canPlan = canSubmitRoute({ live, raw, api, busy });
  const dataName = provenance.datasetName;
  const effectiveGrid = active?.evidence_passport?.resolution_assessment?.effective_resolution_meters || result?.source_selection?.effective_resolution_meters || (live ? api?.status?.dem_resolution_meters : activeDemTerrain ? Math.max(activeDemTerrain.dx, activeDemTerrain.dy) : null);
  const nativeGrid = active?.evidence_passport?.resolution_assessment?.native_effective_resolution_meters || result?.source_selection?.native_resolution_meters || (activeDemRaw?.native_resolution_meters ?? 200);

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

  const commands = [
    { name: 'Live Mars Intelligence', hint: 'Orbiters, rovers, and footprints', icon: 'layers', run: () => switchMission('intelligence') },
    { name: 'Focus Curiosity (Gale Crater)', hint: 'MSL traverse and telemetry', icon: 'crosshair', run: () => { setShowCuriosity(true); mapActions.current?.focus({ lon: 137.3582, lat: -4.6881, zoom: 6 }); } },
    { name: 'Focus Perseverance (Jezero)', hint: 'M20 traverse and telemetry', icon: 'crosshair', run: () => { mapActions.current?.focus({ lon: 77.2332, lat: 18.4356, zoom: 11 }); } },
    { name: 'Swap start and destination', hint: 'Reverse A / B', icon: 'swap', run: swap },
    { name: 'Generate route', hint: busy ? 'Computing…' : algorithm === 'astar' ? 'A* search' : algorithm === 'dijkstra' ? 'Dijkstra search' : 'Compare A* vs Dijkstra', icon: 'arrow', run: () => { switchMission('planner'); run(); }, disabled: !canPlan },
    { name: 'Algorithm: A* search', hint: 'Heuristic search directed to goal', icon: 'sliders', run: () => { setAlgorithm('astar'); invalidate(); } },
    { name: 'Algorithm: Dijkstra', hint: 'Uniform-cost search with zero heuristic', icon: 'sliders', run: () => { setAlgorithm('dijkstra'); invalidate(); } },
    { name: 'Algorithm: Compare A* vs Dijkstra', hint: 'Benchmark node expansions and verify optimality', icon: 'sliders', run: () => { setAlgorithm('compare'); invalidate(); } },
    { name: 'Toggle hazards', hint: hazards ? 'Hide overlay' : 'Show terrain heatmap', icon: 'layers', run: () => setHazards(v => !v) },
    { name: 'Routing settings', hint: 'Algorithm, source and limits', icon: 'sliders', run: () => { setLeftOpen(true); setSettingsOpen(true); } },
    { name: 'Toggle terrain profile', hint: profileExpanded ? 'Collapse drawer' : 'Expand drawer', icon: 'chevron', run: () => { if (historyMode) { switchMission('planner'); setProfileExpanded(true); } else setProfileExpanded(v => !v); } },
    { name: 'Toggle route analysis', hint: rightExpanded ? 'Collapse analysis' : 'Expand analysis', icon: 'sliders', run: toggleAnalysis },
    { name: 'Fit region', hint: 'Reset map extent', icon: 'fit', run: () => mapActions.current?.fit(), disabled: !terrain },
    { name: 'Toggle 2D / 3D terrain', hint: 'DEM elevation view', icon: 'cube', run: () => setView3d(v => !v), disabled: !terrain },
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

  const penaltyShare = active && active.total_cost > 0 ? Math.min(100, (penalty || 0) / active.total_cost * 100) : 0;

  return (
    <div className={'mission-app ' + (historyMode ? 'history-view ' : '') + (intelligenceMode ? 'intelligence-view ' : '') + (profileExpanded ? 'profile-expanded ' : '') + (!leftOpen ? 'left-collapsed' : '')}>
      <header className="mission-header">
        <div className="brand-group">
          <a className="brand" href="/#home" aria-label="Return to MarsPath home">
            MarsPath<span><Icon name="arrow"/></span>
          </a>
          <span className="brand-rule"/>
          <span className="project-brand">Mission Control</span>
        </div>
        <nav className="mission-breadcrumb" aria-label="Breadcrumb">
          <a href="/#missions/planets/mars">Mars</a>
          <span>/</span>
          <span>Jezero Crater</span>
          {intelligenceMode && <span> / Live Mars Intelligence</span>}
        </nav>
        <div className="header-actions">
          <button
            type="button"
            className={'status-chip' + (timeMachineOpen ? ' active' : '')}
            onClick={() => setTimeMachineOpen(v => !v)}
            aria-expanded={timeMachineOpen}
            aria-label="Toggle Mars24 Time Machine and Surface Conditions"
            style={{ cursor: 'pointer', border: timeMachineOpen ? '1px solid rgba(92,255,176,0.5)' : undefined }}
          >
            <i className={conditionsData?.mars24?.is_daylight !== false ? 'ready' : 'synthetic'}/>
            <span>Mars24: {conditionsData?.mars24?.ltst_hms || '10:15:00'} LTST</span>
            <b>{conditionsData?.terrain_shadow?.shadow_state || conditionsData?.terrain_shadow?.illumination_state || 'ILLUMINATED'}</b>
          </button>
          <span className={'status-chip' + (provenance.isSynthetic ? ' synthetic' : '')}>
            <i className={provenance.headerReady ? 'ready' : provenance.isSynthetic ? 'synthetic' : ''}/>
            {provenance.headerStatusText}
            <b>{provenance.headerEngineLabel}</b>
          </span>
          <button className="command-trigger" onClick={() => { setCommandsOpen(true); setCommandQuery(''); setCommandIndex(0); }} aria-label="Open command bar">
            <Icon name="search"/><kbd>Ctrl K</kbd>
          </button>
          <button className="api-connect" onClick={() => setShowSettings(true)}>
            <i className={api ? 'connected' : ''}/>
            <span>{api ? 'API settings' : 'Connect Python API'}</span>
          </button>
        </div>
      </header>

      <main className="map-stage" aria-label="MarsPath mission planner">
        {terrain ? (
          <MapView
            historyMode={historyMode}
            drives={drives}
            waypoints={waypoints}
            showHistory={showHistory}
            showWaypoints={showWaypoints}
            historyFit={historyFit}
            waypoint={waypoint}
            onWaypoint={setWaypoint}
            terrain={terrain}
            activeDemTerrain={activeDemTerrain}
            start={start}
            destination={destination}
            pick={pick}
            onPin={mapPin}
            base={base}
            hazards={hazards}
            coverage={coverage}
            showHillshade={showHillshade}
            showSlope={showSlope}
            showRoughness={showRoughness}
            imageryOpacity={imageryOpacity}
            terrainOpacity={terrainOpacity}
            onWmtsStatusChange={setWmtsLiveStatus}
            maxSlope={mode === 'safety_first' ? Math.min(maxSlope, 14) : maxSlope}
            maxRough={maxRough}
            response={result}
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
            profileExpanded={profileExpanded}
            actionsRef={mapActions}
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
            roverReplayState={roverReplayState}
            activeBookmark={activeBookmark}
            onSelectBookmark={bm => {
              setActiveBookmark(bm.id);
              if (bm.id === 'gale') setShowCuriosity(true);
              if (!bm.hasDem) {
                setError('Global imagery available. High-resolution elevation and route optimization are not currently supported in this region.');
              } else {
                setError('');
              }
            }}
          />
        ) : loadError ? (
          live ? (
            <div className="load-error api-map-fallback" role="status">
              <h2>Local map visualization asset unavailable</h2>
              <p>The bundled local visualization DEM (<code>/mission-data/jezero-dem.json</code>) could not be loaded ({loadError}), so 2D/3D map rendering is unavailable. Python API route planning, summary metrics, elevation profile, evidence passport, and exports remain active.</p>
              {active && <p className="fallback-route-status">Backend route computed: <strong>{active.name}</strong> · {fmt(active.summary?.total_distance_meters / 1000, 2)} km · {active.geometry?.coordinates?.length || 0} vertices ({provenance.dataMode}).</p>}
              <div className="fallback-actions">
                <button onClick={() => location.reload()}>Retry local map asset</button>
                {result && <button onClick={() => setRightExpanded(true)}>Inspect route analysis</button>}
              </div>
            </div>
          ) : (
            <div className="load-error" role="alert">
              <h2>Local browser terrain unavailable</h2>
              <p>{loadError} The browser routing engine requires the bundled local Jezero DEM dataset. Retry loading the local dataset or connect a Python backend to plan routes via the API.</p>
              <div className="fallback-actions">
                <button onClick={() => location.reload()}>Retry local DEM</button>
                <button onClick={() => { switchMission('planner'); setShowSettings(true); }}>Connect Python API</button>
              </div>
            </div>
          )
        ) : (
          <div className="loading-map">
            <span className="spinner"/>
            {live ? 'Loading local reference map… Python API planner is ready.' : 'Verifying Jezero terrain…'}
          </div>
        )}

        {!leftOpen && (
          <button className="route-reopen glass" onClick={() => setLeftOpen(true)} aria-label="Open mission panel">
            <Icon name="sliders"/>
            {historyMode ? 'Rover traverse' : intelligenceMode ? 'Live Intelligence' : nasaDataMode ? 'NASA Data & Intelligence' : 'Route design'}
          </button>
        )}

        <aside className={'floating-left glass ' + (leftOpen ? '' : 'collapsed') + (nasaDataMode ? ' nasa-mode' : '')} inert={!leftOpen} aria-label="Mission Controls">
          <div className="panel-heading">
            <h1>{historyMode ? 'Rover traverse' : intelligenceMode ? 'Live Mars Intelligence' : nasaDataMode ? 'NASA Data & Intelligence' : 'Route design'}</h1>
            <button className="icon-button" onClick={() => setLeftOpen(false)} aria-label="Collapse panel">
              <Icon name="left"/>
            </button>
          </div>
          <div className="mission-mode" role="group" aria-label="Mission view">
            <button className={historyMode ? 'active' : ''} aria-pressed={historyMode} onClick={() => switchMission('history')}>
              Rover history
            </button>
            <button className={plannerMode ? 'active' : ''} aria-pressed={plannerMode} onClick={() => switchMission('planner')}>
              Route planner
            </button>
            <button className={intelligenceMode ? 'active' : ''} aria-pressed={intelligenceMode} onClick={() => switchMission('intelligence')}>
              Live Mars Intelligence
            </button>
            <button className={nasaDataMode ? 'active' : ''} aria-pressed={nasaDataMode} onClick={() => switchMission('nasa-data')}>
              NASA Data &amp; Intelligence
            </button>
            <button className={cloudAiMode ? 'active' : ''} aria-pressed={cloudAiMode} onClick={() => switchMission('cloud-ai')}>
              Cloud &amp; AI Center
            </button>
          </div>

          {cloudAiMode ? (
            <CloudAiPanel
              activeRoute={active}
              currentCoords={start}
            />
          ) : nasaDataMode ? (
            <NasaDataPanel
              apiUrl={api?.url || ''}
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
              apiUrl={api?.url || ''}
            />
          ) : historyMode ? (
            <TraversePanel data={traverse} waypoints={waypoints} stats={historyStats} selected={waypoint} onFit={showAllHistory} onExport={exportHistory} onPlan={planFromWaypoint} error={traverseError}/>
          ) : (
            <>
              {error && <div className="error-message" role="alert">{error}</div>}
              <div className="mission-presets-box" style={{ marginBottom: '10px', padding: '8px 10px', borderRadius: '10px', background: 'rgba(92,255,176,0.06)', border: '1px solid rgba(92,255,176,0.22)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontSize: '11px', fontWeight: 600, color: '#9becbf', letterSpacing: '0.03em' }}>CURATED MISSION PRESETS (5 + FLAGSHIP)</span>
                  <button
                    type="button"
                    onClick={() => applyPreset('flagship_jezero_expedition')}
                    style={{ background: 'rgba(92,255,176,0.2)', color: '#d7f6e5', border: '1px solid rgba(92,255,176,0.5)', borderRadius: '6px', padding: '2px 7px', fontSize: '10.5px', fontWeight: 600, cursor: 'pointer' }}
                  >
                    ★ Run Flagship Expedition
                  </button>
                </div>
                <select
                  aria-label="Mission preset selector"
                  value={selectedPresetId}
                  onChange={e => applyPreset(e.target.value)}
                  style={{ width: '100%', padding: '6px 8px', borderRadius: '7px', background: 'rgba(8,14,18,0.85)', color: '#e2f1ec', border: '1px solid rgba(255,255,255,0.14)', fontSize: '12px' }}
                >
                  {MISSION_PRESETS_CLIENT.map(p => (
                    <option key={p.preset_id} value={p.preset_id}>{p.title}</option>
                  ))}
                </select>
              </div>
              <form ref={routeForm} onSubmit={e => { e.preventDefault(); run(); }}>
                <div className="route-card">
                  <CoordinateRow point={start} label="Start" marker="A" active={pick === 'start'} onDraft={invalidate} onCommit={p => { invalidate(); setStart(p); }} onPick={() => { setShowRoute(true); setPick(pick === 'start' ? null : 'start'); }}/>
                  <div className="swap-divider">
                    <button type="button" onClick={swap} aria-label="Swap start and destination" title="Swap A / B">
                      <Icon name="swap"/>
                    </button>
                  </div>
                  <CoordinateRow point={destination} label="Destination" marker="B" active={pick === 'destination'} onDraft={invalidate} onCommit={p => { invalidate(); setDestination(p); }} onPick={() => { setShowRoute(true); setPick(pick === 'destination' ? null : 'destination'); }}/>
                </div>
                <div className="two-fields" style={{ marginTop: '8px', marginBottom: '8px' }}>
                  <label style={{ fontSize: '11px', color: '#a8bbb6' }}>Departure UTC (Mars24)
                    <input
                      type="text"
                      value={departureUtc}
                      onChange={e => { invalidate(); setDepartureUtc(e.target.value); setTimeMachineUtc(e.target.value); }}
                      style={{ width: '100%', padding: '5px 7px', borderRadius: '6px', background: 'rgba(10,16,20,0.8)', color: '#e3f2ed', border: '1px solid rgba(255,255,255,0.12)', fontSize: '11.5px' }}
                    />
                  </label>
                  <label style={{ fontSize: '11px', color: '#a8bbb6' }}>EVA Budget (hrs)
                    <input
                      type="number"
                      min="1"
                      max="24"
                      step="0.5"
                      value={maxEvaHours}
                      onChange={e => { invalidate(); setMaxEvaHours(Number(e.target.value)); }}
                      style={{ width: '100%', padding: '5px 7px', borderRadius: '6px', background: 'rgba(10,16,20,0.8)', color: '#e3f2ed', border: '1px solid rgba(255,255,255,0.12)', fontSize: '11.5px' }}
                    />
                  </label>
                </div>
                <div className="dem-source-selector-box" style={{ marginBottom: '8px', padding: '7px 9px', borderRadius: '8px', background: 'rgba(100,223,223,0.06)', border: '1px solid rgba(100,223,223,0.22)' }}>
                  <label style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px', color: '#9becbf', fontWeight: 600 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>ACTIVE ROUTING TERRAIN (DEM)</span>
                      <span style={{ fontSize: '10px', color: '#64dfdf', fontWeight: 700 }}>{provenance.datasetDoi ? `DOI: ${provenance.datasetDoi}` : 'USGS Verified'}</span>
                    </div>
                    <select
                      aria-label="Routing terrain DEM source"
                      value={demSourcePreference}
                      onChange={e => {
                        const nextPref = e.target.value;
                        invalidate();
                        setDemSourcePreference(nextPref);
                        run({ demSourceOverride: nextPref });
                      }}
                      style={{ width: '100%', padding: '5px 7px', borderRadius: '6px', background: 'rgba(8,14,18,0.9)', color: '#e2f1ec', border: '1px solid rgba(255,255,255,0.16)', fontSize: '11.5px', fontWeight: 500 }}
                    >
                      <option value="auto">Auto (USGS HiRISE 1 m DTM where covered, else 200 m DEM)</option>
                      <option value="hirise_1m">USGS HiRISE DTM · 1 m/px (DOI: 10.5066/P9REJ9JN)</option>
                      <option value="mola_hrsc_200m">USGS MOLA-HRSC DEM · 200 m/px (DOI: 10.5066/P907276M)</option>
                    </select>
                  </label>
                  <div style={{ fontSize: '10.5px', color: '#b6c9c4', marginTop: '4px', lineHeight: 1.35 }}>
                    {provenance.activeDemSourceLabel} · {effectiveGrid && nativeGrid && effectiveGrid > nativeGrid ? `effective ∼${fmt(effectiveGrid, 1)} m grid (budget-strided from ${fmt(nativeGrid, 0)} m native)` : `∼${fmt(effectiveGrid || 200, 0)} m grid`}
                  </div>
                </div>
                <details className="routing-settings" open={settingsOpen} onToggle={e => setSettingsOpen(e.currentTarget.open)}>
                  <summary>
                    <Icon name="sliders"/>
                    <span>Settings</span>
                    <small>{algorithm === 'astar' ? 'A*' : algorithm === 'dijkstra' ? 'Dijkstra' : 'Compare A* / Dijkstra'} · {mode.replace('_first', ' first')}</small>
                    <Icon name="chevron"/>
                  </summary>
                  <div className="settings-body">
                    <label>Compute source
                      <select value={sourceMode} onChange={e => { invalidate(); setSourceMode(e.target.value); if (e.target.value === 'api') setAlgorithm('astar'); }}>
                        <option value="browser">Bundled USGS terrain</option>
                        <option value="api" disabled={!api}>Python backend{!api ? ' · connect first' : ''}</option>
                      </select>
                    </label>
                    <div className="two-fields">
                      <label>Algorithm
                        <select value={algorithm} onChange={e => { invalidate(); setAlgorithm(e.target.value); }} aria-label="Routing algorithm">
                          <option value="astar">A* search</option>
                          <option value="dijkstra" disabled={live && !api?.algorithmSupported}>Dijkstra</option>
                          <option value="compare" disabled={live && !api?.algorithmSupported}>Compare A* vs Dijkstra</option>
                        </select>
                      </label>
                      <label>Candidates
                        <select value={numAlternatives} onChange={e => { invalidate(); setNumAlternatives(Number(e.target.value)); }} aria-label="Number of route candidates">
                          <option value="1">1 route</option>
                          <option value="2">2 routes</option>
                          <option value="3">3 routes</option>
                        </select>
                      </label>
                    </div>
                    <label>Optimization
                      <select value={mode} onChange={e => { invalidate(); setMode(e.target.value); setMaxSlope(e.target.value === 'safety_first' ? 14 : e.target.value === 'science_first' ? 22 : 20); }} aria-label="Optimization mode">
                        <option value="safety_first">Safety first</option>
                        <option value="balanced">Balanced</option>
                        <option value="science_first">Science first</option>
                      </select>
                    </label>
                    <div className="slider-field">
                      <label htmlFor="max-slope">Slope ceiling <strong>{maxSlope}°</strong></label>
                      <input id="max-slope" type="range" min="5" max="35" step="1" value={maxSlope} onChange={e => { invalidate(); setMaxSlope(Number(e.target.value)); }}/>
                    </div>
                    <div className="slider-field">
                      <label htmlFor="max-rough">Roughness limit <strong>{maxRough.toFixed(2)}</strong></label>
                      <input id="max-rough" type="range" min="0.1" max="1" step="0.05" value={maxRough} onChange={e => { invalidate(); setMaxRough(Number(e.target.value)); }}/>
                    </div>
                    <p className="field-note">
                      {algorithm === 'compare' ? 'Runs both A* and Dijkstra on identical inputs to benchmark state expansion efficiency and verify optimal cost equivalence.' : algorithm === 'dijkstra' ? 'Dijkstra is uniform-cost search (heuristic h=0), expanding strictly in order of accumulated cost.' : live && !api?.algorithmSupported ? 'This API exposes A* only. Use the bundled planner for Dijkstra.' : 'A* guides exploration toward the goal using an admissible Euclidean distance heuristic (faster, fewer node expansions).'}
                    </p>
                  </div>
                </details>
                <button className="plan-button" type="submit" disabled={!canPlan}>
                  {busy ? <><span className="spinner"/>Computing route…</> : <>Generate route<Icon name="arrow"/></>}
                </button>
              </form>
              <p className="route-caption" data-testid="active-dem-caption">
                {provenance.activeDemSourceLabel} · {provenance.datasetDoi ? `DOI ${provenance.datasetDoi} · ` : ''}{effectiveGrid ? `∼${fmt(effectiveGrid, effectiveGrid < 10 ? 1 : 0)} m routing grid` : '∼200 m grid'}
              </p>
            </>
          )}
        </aside>

        {plannerMode && (
          <aside className={'floating-analysis glass ' + (rightExpanded ? 'expanded' : '')} aria-label="Route analysis">
            <div className="analysis-heading">
              <button className="analysis-toggle" onClick={toggleAnalysis} aria-expanded={rightExpanded} aria-label={rightExpanded ? 'Collapse route analysis' : 'Expand route analysis'}>
                <span>Route analysis</span>
                <Icon name="chevron"/>
              </button>
              <button className="icon-button quick-export" onClick={download} disabled={!result} aria-label="Export selected route" title="Export selected route">
                <Icon name="download"/>
              </button>
            </div>
            <div className={'analysis-content ' + (busy ? 'calculating' : '')}>
              <div className="key-metrics">
                <Metric label="Distance" value={active?.summary.total_distance_meters / 1000} digits={2} unit="km" primary/>
                <Metric label="Estimated time" value={active?.summary.estimated_duration_hours} digits={1} unit="hrs" primary/>
                {rightExpanded && (
                  <>
                    <Metric label="Weighted cost" value={active?.total_cost} digits={0} unit="units"/>
                    <Metric label="Traversability" value={active?.total_cost > 0 ? Math.round(((active.cost_breakdown?.base_distance_cost || 0) / active.total_cost) * 100) : null} digits={0} unit="%"/>
                  </>
                )}
              </div>
              {rightExpanded && (
                <>
                  {result?.algorithm_comparison && (
                    <div className="algorithm-benchmark-card">
                      <div className="benchmark-header">
                        <span>Algorithm Benchmark</span>
                        <span className="benchmark-tag">A* vs Dijkstra</span>
                      </div>
                      <table className="benchmark-table">
                        <thead>
                          <tr><th>Metric</th><th>A* (Heuristic)</th><th>Dijkstra (Uniform)</th></tr>
                        </thead>
                        <tbody>
                          <tr><td>Distance</td><td>{fmt(result.algorithm_comparison.astar.path_length_km, 2)} km</td><td>{fmt(result.algorithm_comparison.dijkstra.path_length_km, 2)} km</td></tr>
                          <tr><td>Weighted cost</td><td>{fmt(result.algorithm_comparison.astar.total_cost, 1)}</td><td>{fmt(result.algorithm_comparison.dijkstra.total_cost, 1)}</td></tr>
                          <tr><td>Compute time</td><td>{fmt(result.algorithm_comparison.astar.execution_time_seconds * 1000, 1)} ms</td><td>{fmt(result.algorithm_comparison.dijkstra.execution_time_seconds * 1000, 1)} ms</td></tr>
                          <tr><td>States expanded</td><td>{result.algorithm_comparison.astar.nodes_expanded.toLocaleString()}</td><td>{result.algorithm_comparison.dijkstra.nodes_expanded.toLocaleString()}</td></tr>
                          <tr><td>Max slope</td><td>{fmt(result.algorithm_comparison.astar.max_slope_deg, 1)}°</td><td>{fmt(result.algorithm_comparison.dijkstra.max_slope_deg, 1)}°</td></tr>
                          <tr><td>Assessed risk</td><td>{result.algorithm_comparison.astar.risk_category}</td><td>{result.algorithm_comparison.dijkstra.risk_category}</td></tr>
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
                  <div className="route-candidates" role="group" aria-label="Route candidates">
                    {result?.routes.map((r, i) => (
                      <button key={r.route_id} className={'candidate ' + (r.route_id === selected ? 'selected' : '')} onClick={() => { setSelected(r.route_id); setHover(null); }} onPointerEnter={() => setHoveredRoute(r.route_id)} onPointerLeave={() => setHoveredRoute(null)} onFocus={() => setHoveredRoute(r.route_id)} onBlur={() => setHoveredRoute(null)} aria-pressed={r.route_id === selected}>
                        <span className="radio-dot"/>
                        <span>{i === 0 ? 'Primary' : 'Alternative ' + i}</span>
                        <small>{fmt(r.summary?.total_distance_meters / 1000, 2)} km <b>·</b> {fmt(r.summary?.estimated_duration_hours, 1)} h</small>
                      </button>
                    ))}
                    {!result && <p className={'empty-routes ' + (busy ? 'shimmer' : '')}>{busy ? 'Analyzing corridors…' : 'Select coordinates or click map pins to plan a route.'}</p>}
                  </div>
                  <section className="penalty-gauge">
                    <div>
                      <span>Terrain penalty</span>
                      <span className={'risk-badge ' + (active?.summary.risk_category || '')}>{active?.summary.risk_category?.replaceAll('_', ' ') || 'Unassessed'}</span>
                    </div>
                    <div className="gauge-track" role="meter" aria-label="Terrain penalty share of weighted route cost" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.round(penaltyShare)}>
                      <span style={{ width: penaltyShare + '%' }}/>
                    </div>
                    <small>{active ? Math.round(penaltyShare) + '% of weighted cost' : 'Awaiting a route'} · heuristic, not a failure probability</small>
                  </section>
                  <details className="analysis-details" open={detailsOpen} onToggle={e => setDetailsOpen(e.currentTarget.open)}>
                    <summary>Details & evidence<Icon name="chevron"/></summary>
                    <div className="details-body">
                      <dl>
                        <dt>Max slope</dt><dd>{fmt(active?.summary.max_slope_deg, 1)}°</dd>
                        <dt>Average slope</dt><dd>{fmt(active?.summary.average_slope_deg, 1)}°</dd>
                        <dt>Average roughness</dt><dd>{fmt(active?.summary.average_roughness, 2)}</dd>
                        <dt>Ascent / descent</dt><dd>{fmt(active?.summary.elevation_gain_meters, 0)} / {fmt(active?.summary.elevation_loss_meters, 0)} m</dd>
                        <dt>Hazard exposure</dt><dd>{fmt(active?.summary.hazard_exposure_meters, 0)} m</dd>
                        <dt>Terrain penalty</dt><dd>{fmt(penalty, 1)}</dd>
                        {[['Base distance', 'base_distance_cost'], ['Slope cost', 'slope_penalty'], ['Roughness cost', 'roughness_penalty'], ['Hazard cost', 'hazard_penalty'], ['Extra cost', 'extra_penalty']].map(([label, key]) => (
                          <React.Fragment key={key}><dt>{label}</dt><dd>{fmt(active?.cost_breakdown?.[key], 1)}</dd></React.Fragment>
                        ))}
                        <dt>Data coverage</dt><dd>{active ? fmt(active.summary.data_coverage_fraction * 100, 0) + '%' : '—'}</dd>
                        <dt>Active DEM source</dt><dd>{provenance.activeDemSourceLabel}</dd>
                        <dt>Dataset DOI</dt><dd>{provenance.datasetDoi || '10.5066/P907276M'}</dd>
                        <dt>Product ID</dt><dd style={{ wordBreak: 'break-all', fontSize: '10.5px' }}>{provenance.officialProductId || 'MarsHRSC_MOLA_BlendDEM_Global_200mp_v2'}</dd>
                        <dt>Native DEM resolution</dt><dd>{fmt(nativeGrid || effectiveGrid, (nativeGrid || effectiveGrid) < 10 ? 2 : 0)} m/px</dd>
                        <dt>Effective routing grid</dt><dd>{fmt(effectiveGrid, effectiveGrid < 10 ? 2 : 0)} m/px</dd>
                        <dt>Data mode</dt><dd>{provenance.dataMode}{provenance.isSynthetic ? ' (synthetic)' : ''}</dd>
                        <dt>Source status</dt><dd>{provenance.sourceVerificationText}</dd>
                        <dt>Evidence tier</dt><dd>{active?.evidence_passport?.quality_tier || 'Unassessed'}</dd>
                        <dt>File integrity</dt><dd>{provenance.fileIntegrityText}</dd>
                        <dt>Upstream checksum</dt><dd>{provenance.upstreamChecksumText}</dd>
                      </dl>
                      <p>{dataName}</p>
                      {provenance.isSynthetic && <p className="synthetic-note">Synthetic procedural terrain model — not NASA/USGS observation data.</p>}
                      <p>Regional assessment only; this grid does not resolve rover-scale obstacles.</p>
                      {provenance.officialSourceUrl ? <a href={provenance.officialSourceUrl} target="_blank" rel="noopener noreferrer">Terrain source ↗</a> : <p className="no-source-link">{provenance.isSynthetic ? 'No external source link (synthetic terrain).' : 'No official source URL supplied by backend.'}</p>}
                      {result?.limitations?.length > 0 && (
                        <div className="limitations-block">
                          <span className="limitations-title">Scientific & provenance limitations</span>
                          <ul className="limitations-list">
                            {result.limitations.map((item, idx) => <li key={idx}>{item}</li>)}
                          </ul>
                        </div>
                      )}
                      {result && <p className="computation-stats">{result.stats?.algorithm_used} · {fmt(result.stats?.nodes_expanded, 0)} states · {fmt(result.stats?.search_duration_seconds, 3)} s</p>}
                    </div>
                  </details>
                  <div className="export-controls">
                    <select aria-label="Export format" value={exportFormat} onChange={e => setExportFormat(e.target.value)}>
                      <option value="json">JSON manifest</option>
                      <option value="geojson">GeoJSON</option>
                      <option value="brief">Mission Brief (.md)</option>
                      <option value="config">Mission Config (.json)</option>
                    </select>
                    <button onClick={download} disabled={!result}><Icon name="download"/>Export</button>
                  </div>
                  {shortfall.hasShortfall && <p className="partial-note" role="status">{shortfall.message}</p>}
                </>
              )}
            </div>
          </aside>
        )}

        {timeMachineOpen && (
          <section
            className="layers-popover glass"
            aria-label="Mars24 Time Machine and Surface Conditions"
            style={{ top: '62px', right: '16px', width: '365px', maxHeight: 'calc(100vh - 130px)', overflowY: 'auto', zIndex: 42 }}
          >
            <div className="panel-heading">
              <h2>Mars24 Time Machine &amp; Replay</h2>
              <button className="icon-button" onClick={() => setTimeMachineOpen(false)} aria-label="Close Mars24 Time Machine">
                <Icon name="close"/>
              </button>
            </div>
            <div style={{ fontSize: '11.5px', color: '#d5e3df', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span style={{ color: '#9becbf', fontWeight: 600 }}>Epoch UTC Timestamp (Mars24 &amp; DEM Ray-Marching)</span>
                <input
                  type="text"
                  value={timeMachineUtc}
                  onChange={e => { setTimeMachineUtc(e.target.value); setDepartureUtc(e.target.value); }}
                  style={{ padding: '5px 8px', borderRadius: '6px', background: 'rgba(8,14,18,0.85)', color: '#e6f5f0', border: '1px solid rgba(255,255,255,0.15)', fontSize: '12px' }}
                />
              </label>
              <div style={{ display: 'flex', gap: '5px', flexWrap: 'wrap' }}>
                {[
                  ['Morning (10:15 LTST)', '2026-06-15T08:00:00Z'],
                  ['Low-Sun Afternoon', '2026-06-15T14:30:00Z'],
                  ['Night (Below Horizon)', '2026-06-15T20:00:00Z'],
                  ['Spirit Landing Epoch', '2004-01-03T13:46:31Z'],
                ].map(([lbl, u]) => (
                  <button
                    key={lbl}
                    type="button"
                    onClick={() => { setTimeMachineUtc(u); setDepartureUtc(u); }}
                    style={{ padding: '3px 7px', borderRadius: '5px', fontSize: '10.5px', background: timeMachineUtc === u ? 'rgba(92,255,176,0.2)' : 'rgba(255,255,255,0.06)', color: '#d7f6e5', border: '1px solid rgba(255,255,255,0.12)', cursor: 'pointer' }}
                  >
                    {lbl}
                  </button>
                ))}
              </div>
              {conditionsData && (() => {
                const shState = conditionsData.terrain_shadow?.shadow_state || conditionsData.terrain_shadow?.illumination_state || 'ILLUMINATED';
                const modClim = conditionsData.modelled_climatology || conditionsData.climate?.modelled_climatology || {};
                const medaRec = conditionsData.measured_meda?.nearest_record || conditionsData.climate?.measured_meda_reference;
                return (
                  <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(0,0,0,0.32)', border: '1px solid rgba(255,255,255,0.08)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <strong>NASA GISS Mars24 Solar Geometry</strong>
                      <span style={{ color: '#9becbf', fontWeight: 600 }}>MSD {conditionsData.mars24?.msd}</span>
                    </div>
                    <div>LTST: <b>{conditionsData.mars24?.ltst_hms}</b> · LMST: <b>{conditionsData.mars24?.lmst_hms}</b> · MTC: <b>{conditionsData.mars24?.mtc_hms}</b></div>
                    <div>Solar Longitude (Ls): <b>{conditionsData.mars24?.ls_deg}°</b></div>
                    <div>Solar Elev / Azimuth: <b>{conditionsData.mars24?.solar_elevation_deg}°</b> / <b>{conditionsData.mars24?.solar_azimuth_deg}°</b></div>
                    <div style={{ marginTop: '5px', paddingTop: '5px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                      <span>DEM Shadow State: </span>
                      <b style={{ color: shState === 'ILLUMINATED' ? '#5cffb0' : '#ffb867' }}>
                        {shState}
                      </b>
                      <div style={{ fontSize: '10.5px', color: '#9cb0ab' }}>{conditionsData.terrain_shadow?.explanation}</div>
                    </div>
                    <div style={{ marginTop: '5px', paddingTop: '5px', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                      <div><b>Modelled Climatology:</b> Air {modClim.air_temperature_c}°C · Ground {modClim.ground_temperature_c}°C · {modClim.pressure_pa} Pa</div>
                      {medaRec && (
                        <div style={{ fontSize: '10.5px', color: '#64dfdf', marginTop: '2px' }}>
                          <b>Measured MEDA Ref (Sol {medaRec.sol}):</b> Air {medaRec.air_temperature_c ?? medaRec.air_temp_c}°C · {medaRec.pressure_pa} Pa
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              <div style={{ padding: '8px', borderRadius: '8px', background: 'rgba(0,0,0,0.32)', border: '1px solid rgba(255,255,255,0.08)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <strong>Perseverance Historical Replay</strong>
                  <span style={{ fontSize: '10.5px', padding: '1px 6px', borderRadius: '4px', background: 'rgba(255,184,103,0.18)', color: '#ffb867', fontWeight: 600 }}>
                    {roverReplayState?.archive_status || 'EXACT_SOL_RECORD'}
                  </span>
                </div>
                <label style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px' }}>
                  <span>Mission Sol Selector: <b>Sol {timeMachineSol}</b></span>
                  <small>Range: -5 (Pre-Landing) to 2100</small>
                </label>
                <input
                  type="range"
                  min="-5"
                  max="2100"
                  step="1"
                  value={timeMachineSol}
                  onChange={e => setTimeMachineSol(Number(e.target.value))}
                  style={{ width: '100%', margin: '4px 0' }}
                />
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '5px' }}>
                  {[
                    ['Sol -3 (Pre-Landing)', -3],
                    ['Sol 0 (Touchdown)', 0],
                    ['Sol 14 (1st Drive)', 14],
                    ['Sol 18 (Stationary Gap)', 18],
                    ['Sol 415 (Delta Front)', 415],
                    ['Sol 2080 (Post-Cutoff)', 2080],
                  ].map(([lbl, sVal]) => (
                    <button
                      key={lbl}
                      type="button"
                      onClick={() => setTimeMachineSol(sVal)}
                      style={{ padding: '2px 6px', borderRadius: '4px', fontSize: '10px', background: timeMachineSol === sVal ? 'rgba(255,184,103,0.25)' : 'rgba(255,255,255,0.06)', color: '#ffe1aa', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer' }}
                    >
                      {lbl}
                    </button>
                  ))}
                </div>
                <div style={{ fontSize: '10.5px', color: '#b8c7c3' }}>
                  {roverReplayState?.explanation}
                </div>
              </div>
            </div>
          </section>
        )}

        {layersOpen && (
          <section className="layers-popover glass" aria-label="Scientific Layer Manager" style={{ maxHeight: 'calc(100vh - 115px)', overflowY: 'auto', width: '368px' }}>
            <div className="panel-heading">
              <h2>Scientific Layer Manager</h2>
              <button className="icon-button" onClick={() => setLayersOpen(false)} aria-label="Close map layers">
                <Icon name="close"/>
              </button>
            </div>

            <div style={{ fontSize: '10px', fontWeight: 700, color: '#9becbf', letterSpacing: '0.06em', margin: '6px 0 4px' }}>1. SATELLITE IMAGERY SELECTOR (OGC WMTS)</div>
            <div className="layer-basemap" style={{ marginBottom: '6px' }}>
              <div className="segmented" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '4px' }}>
                <button className={base === 'auto' || base === 'imagery' ? 'active' : ''} onClick={() => setBase('auto')}>Auto Multi-Res (232m→6m→0.25m)</button>
                <button className={base === 'hirise' ? 'active' : ''} onClick={() => setBase('hirise')}>HiRISE 0.25m (10.5066/P9QJDP48)</button>
                <button className={base === 'ctx' || base === 'ctx_global' ? 'active' : ''} onClick={() => setBase('ctx')}>CTX Regional 6m (10.5066/P9GV1ND3)</button>
                <button className={base === 'viking' ? 'active' : ''} onClick={() => setBase('viking')}>Viking Global 232m</button>
                <button className={base === 'relief' ? 'active' : ''} onClick={() => setBase('relief')}>DEM Color Relief</button>
                <button className={base === 'mola_global' ? 'active' : ''} onClick={() => setBase('mola_global')}>MOLA ColorShade 200m</button>
              </div>
            </div>
            <div className="slider-field" style={{ marginBottom: '8px' }}>
              <label htmlFor="imagery-opacity" style={{ fontSize: '11px' }}>Imagery layer opacity <strong>{Math.round(imageryOpacity * 100)}%</strong></label>
              <input id="imagery-opacity" type="range" min="0.2" max="1" step="0.05" value={imageryOpacity} onChange={e => setImageryOpacity(Number(e.target.value))}/>
            </div>

            <div style={{ fontSize: '10px', fontWeight: 700, color: '#64dfdf', letterSpacing: '0.06em', margin: '8px 0 4px' }}>2. TERRAIN SOURCE (DEM) &amp; ANALYTICAL OVERLAYS</div>
            <div style={{ marginBottom: '6px' }}>
              <select
                aria-label="Layer manager DEM source"
                value={demSourcePreference}
                onChange={e => {
                  const nextPref = e.target.value;
                  setDemSourcePreference(nextPref);
                  run({ demSourceOverride: nextPref });
                }}
                style={{ width: '100%', padding: '5px 7px', borderRadius: '6px', background: 'rgba(8,14,18,0.9)', color: '#e2f1ec', border: '1px solid rgba(100,223,223,0.3)', fontSize: '11px' }}
              >
                <option value="auto">Auto DEM: USGS HiRISE 1 m DTM (10.5066/P9REJ9JN)</option>
                <option value="hirise_1m">Force USGS HiRISE 1 m DTM (10.5066/P9REJ9JN)</option>
                <option value="mola_hrsc_200m">Force USGS MOLA-HRSC 200 m DEM (10.5066/P907276M)</option>
              </select>
            </div>
            <LayerToggle label="Terrain Hillshade (from active DEM)" color="mint" checked={showHillshade} onChange={setShowHillshade}/>
            <LayerToggle label="Slope Gradient Heatmap (0°–30°+)" color="amber" checked={showSlope} onChange={setShowSlope}/>
            <LayerToggle label="Terrain Roughness Index (TRI)" color="violet" checked={showRoughness} onChange={setShowRoughness}/>
            <LayerToggle label="Slope &amp; Roughness Hazard Thresholds" color="amber" checked={hazards} onChange={setHazards}/>
            <LayerToggle label="Data Coverage &amp; USGS Product Bounds" color="gray" checked={coverage} onChange={setCoverage}/>
            <div className="slider-field" style={{ marginBottom: '8px' }}>
              <label htmlFor="terrain-opacity" style={{ fontSize: '11px' }}>Terrain overlay opacity <strong>{Math.round(terrainOpacity * 100)}%</strong></label>
              <input id="terrain-opacity" type="range" min="0.15" max="1" step="0.05" value={terrainOpacity} onChange={e => setTerrainOpacity(Number(e.target.value))}/>
            </div>

            <div style={{ fontSize: '10px', fontWeight: 700, color: '#ffd166', letterSpacing: '0.06em', margin: '8px 0 4px' }}>3. USGS DATASET &amp; PROVENANCE INSPECTOR</div>
            <div data-testid="usgs-dataset-inspector" style={{ padding: '7px 8px', borderRadius: '7px', background: 'rgba(0,0,0,0.36)', border: '1px solid rgba(255,255,255,0.1)', fontSize: '10.5px', color: '#d4e4e0', display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '8px' }}>
              <div>
                <strong style={{ color: '#9becbf' }}>Imagery: USGS HiRISE Orthomosaic (0.25 m/px)</strong>
                <div>ID: <code>JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first</code></div>
                <div>DOI: <code>10.5066/P9QJDP48</code> · Bounds: <code>77.2229°E–77.5840°E, 18.3068°N–18.6693°N</code></div>
                <div>Status: <b style={{ color: '#5cffb0' }}>{wmtsLiveStatus?.layers?.hirise?.capabilitiesLoaded ? `WMTS Validated (${wmtsLiveStatus.layers.hirise.tilesLoaded || 0} tiles loaded)` : 'WMTS Capabilities Ready'}</b></div>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '4px' }}>
                <strong style={{ color: '#64dfdf' }}>Elevation: USGS HiRISE DTM Mosaic (1.0 m/px)</strong>
                <div>ID: <code>JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40</code></div>
                <div>DOI: <code>10.5066/P9REJ9JN</code> · Vertical: <code>meters</code> · NoData: <code>-3.4028e+38</code></div>
                <div>Status: <b style={{ color: hiriseTerrain ? '#5cffb0' : '#ffb867' }}>{hiriseTerrain ? `Loaded & SHA-256 Verified (Active: ${provenance.activeDemSourceLabel})` : (hiriseLoadReason || 'Loading…')}</b></div>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '4px' }}>
                <strong style={{ color: '#ffd166' }}>Regional Imagery: USGS CTX Orthomosaic (6.0 m/px)</strong>
                <div>ID: <code>JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0</code> · DOI: <code>10.5066/P9GV1ND3</code></div>
              </div>
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '4px' }}>
                <strong style={{ color: '#e2f1ec' }}>Route Endpoint Coverage Check:</strong>
                <div>Start ({fmt(start.lon, 4)}°E, {fmt(start.lat, 4)}°N) &amp; Dest ({fmt(destination.lon, 4)}°E, {fmt(destination.lat, 4)}°N): <b style={{ color: '#5cffb0' }}>Inside USGS 10.5066/P9QJDP48 &amp; 10.5066/P9REJ9JN</b></div>
              </div>
            </div>

            <div style={{ fontSize: '10px', fontWeight: 700, color: '#ff9f68', letterSpacing: '0.06em', margin: '8px 0 4px' }}>4. SCIENCE TARGETS &amp; THEMIS THERMAL</div>
            <LayerToggle label="Jezero Science Targets (7)" color="amber" checked={showScienceTargets} onChange={setShowScienceTargets}/>
            <LayerToggle label="THEMIS Thermal Inertia Grid (100m)" color="amber" checked={showThemisOverlay} onChange={setShowThemisOverlay}/>

            <div style={{ fontSize: '10px', fontWeight: 700, color: '#c982d9', letterSpacing: '0.06em', margin: '8px 0 4px' }}>5. ROVER DATA &amp; ORBITAL GEOMETRY</div>
            <LayerToggle label="Perseverance Recorded Traverse" color="amber" checked={showHistory} onChange={setShowHistory}/>
            <LayerToggle label="Perseverance Sol Waypoints" color="violet" checked={showWaypoints} onChange={setShowWaypoints}/>
            <LayerToggle label="Curiosity (Gale Crater)" color="violet" checked={showCuriosity} onChange={setShowCuriosity}/>
            <LayerToggle label="Planned Route Corridor" color="mint" checked={showRoute} onChange={setShowRoute}/>
            <LayerToggle label="Alternative Corridors" color="gray" checked={showAlternatives} onChange={setShowAlternatives}/>
            <LayerToggle label="Orbiters (Real-time J2)" color="mint" checked={showOrbiters} onChange={setShowOrbiters}/>
            <LayerToggle label="Orbital Ground Tracks" color="mint" checked={showGroundTracks} onChange={setShowGroundTracks}/>
            <LayerToggle label="Observation Footprints" color="amber" checked={showFootprints} onChange={setShowFootprints}/>

            {view3d && (
              <div className="slider-field">
                <label htmlFor="exaggeration">Elevation exaggeration <strong>×{exaggeration}</strong></label>
                <input id="exaggeration" type="range" min="2" max="10" step="1" value={exaggeration} onChange={e => setExaggeration(Number(e.target.value))}/>
              </div>
            )}
            <p className="field-note">
              Imagery streams live OGC WMTS tiles (`default028mm`). Routing uses numerical USGS DEM elevation (never visual imagery).
            </p>
          </section>
        )}

        {historyMode ? (
          <TraverseTimeline cut={solCut} max={maxSol} stats={historyStats} onChange={v => { setSolCut(v); setWaypoint(null); }} onAll={showAllHistory}/>
        ) : plannerMode ? (
          <Profile
            route={active}
            onHover={setHover}
            expanded={profileExpanded}
            onToggle={value => setProfileExpanded(v => typeof value === 'boolean' ? value : !v)}
            busy={busy}
            activeProfileTab={activeProfileTab}
            onSelectProfileTab={setActiveProfileTab}
          />
        ) : null}

        <div className="traverse-key glass">
          <span><i className="recorded"/>Recorded drives</span>
          <span><i className="stops"/>Waypoints</span>
          {showRoute && <span><i className="planned"/>Planned route</span>}
          {showOrbiters && <span><i className="planned" style={{ background: '#64dfdf' }}/>Orbiters</span>}
          {showFootprints && <span><i className="stops" style={{ background: '#ffd166' }}/>Footprints</span>}
        </div>

        {notice && <div className="notice-toast glass" role="status">{notice}</div>}
      </main>

      {showSettings && (
        <Dialog onClose={() => setShowSettings(false)} label="Close API connection settings">
          <p className="eyebrow">Backend integration</p>
          <h2>Connect Mission Control.</h2>
          <p>Enter your deployed MarsPath FastAPI URL. We validate health, terrain status, layers, and the API contract before enabling it.</p>
          <label>Backend URL
            <input type="url" placeholder="https://your-marspath-backend.example" value={apiUrl} onChange={e => setApiUrl(e.target.value)}/>
          </label>
          <div className="origin-note">Backend CORS must allow:<code>{location.origin}</code></div>
          {connectionError && <div className="error-message" role="alert">{connectionError}</div>}
          <button className="plan-button" onClick={connect} disabled={connecting || !apiUrl.trim()}>
            {connecting ? 'Checking backend…' : 'Connect and validate'}<Icon name="arrow"/>
          </button>
          <p className="field-note">The bundled planner works independently. Live orbital & rover telemetry syncs continuously.</p>
        </Dialog>
      )}

      {commandsOpen && (
        <Dialog onClose={() => setCommandsOpen(false)} label="Close command bar">
          <div className="command-search">
            <Icon name="search"/>
            <input autoFocus type="search" aria-label="Search commands" placeholder="What would you like to do?" value={commandQuery} onChange={e => { setCommandQuery(e.target.value); setCommandIndex(0); }} onKeyDown={e => {
              if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                setCommandIndex(i => matches.length ? (i + (e.key === 'ArrowDown' ? 1 : matches.length - 1)) % matches.length : 0);
              } else if (e.key === 'Enter') {
                e.preventDefault();
                execute(matches[commandIndex]);
              }
            }}/>
          </div>
          <div className="command-list">
            {matches.map((c, i) => (
              <button key={c.name} disabled={c.disabled} className={i === commandIndex ? 'selected' : ''} onClick={() => execute(c)} onPointerEnter={() => setCommandIndex(i)}>
                <Icon name={c.icon}/>
                <span>{c.name}<small>{c.hint}</small></span>
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
  return Math.abs(Number(p.lat)).toFixed(4) + '°' + (Number(p.lat) < 0 ? 'S' : 'N') + ', ' + Math.abs(Number(p.lon)).toFixed(4) + '°' + (Number(p.lon) < 0 ? 'W' : 'E');
}

function parsePoint(text) {
  const clean = text.trim().toUpperCase().replace(/°/g, '');
  const match = clean.match(/^([+-]?\d+(?:\.\d+)?)\s*([NS]?)\s*[,;]\s*([+-]?\d+(?:\.\d+)?)\s*([EW]?)$/);
  if (!match) return null;
  let lat = Number(match[1]), lon = Number(match[3]);
  if (match[2] === 'S') lat = -Math.abs(lat);
  if (match[4] === 'W') lon = -Math.abs(lon);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 360) return null;
  return { lat, lon };
}

function CoordinateRow({ point, label, marker, active, onPick, onCommit, onDraft }) {
  const [text, setText] = useState(() => formatPoint(point));
  const ref = useRef();
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) {
      setText(formatPoint(point));
      ref.current?.setCustomValidity('');
    }
  }, [point.lat, point.lon]);

  function validate(value) {
    const p = parsePoint(value);
    ref.current?.setCustomValidity(p ? '' : 'Enter latitude, longitude, for example 18.39°N, 77.40°E.');
    return p;
  }

  return (
    <div className="coordinate-row">
      <span className="pin-letter">{marker}</span>
      <label>
        <span>{label}</span>
        <input ref={ref} type="text" value={text} required aria-label={label + ' coordinates'} spellCheck="false" onFocus={() => focused.current = true} onChange={e => { setText(e.target.value); validate(e.target.value); onDraft(); }} onBlur={() => { focused.current = false; const p = validate(text); if (p) { onCommit(p); setText(formatPoint(p)); } }} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } }}/>
      </label>
      <button type="button" className={'icon-button pick-button ' + (active ? 'active' : '')} onClick={onPick} aria-label={'Pick ' + label.toLowerCase() + ' on map'} title={'Pick ' + label.toLowerCase() + ' on map'} aria-pressed={active}>
        <Icon name="crosshair"/>
      </button>
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
      <strong>{Number.isFinite(value) ? fmt(shown, digits) : '—'}<small>{unit}</small></strong>
    </div>
  );
}

function LayerToggle({ label, color, checked, onChange }) {
  return (
    <label className="layer-toggle">
      <i className={color}/>
      <span>{label}</span>
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)}/>
    </label>
  );
}

createRoot(document.getElementById('root')).render(<App/>);
