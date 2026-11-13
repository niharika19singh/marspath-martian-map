import { validateTraverse, visibleDrives, visibleWaypoints, traverseStats, exportTraverse } from './traverse.js';
import { TraversePanel, TraverseTimeline } from './TraversePanel.jsx';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import 'ol/ol.css';
import './style.css';
import MapView from './MapView.jsx';
import Profile from './Profile.jsx';
import { exportGeoJSON, exportCSV, exportJSON } from './export.js';
import { buildTerrain } from './terrain.js';
import Icon from './Icons.jsx';
import {
  resolveInitialApiUrl,
  resolveTerrainProvenance,
  resolveAlternativeShortfall,
  canSubmitRoute,
  validateRouteExecutionPreconditions
} from './integration.js';

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
  crs_identifier: 'IAU2000:49900'
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
  const [missionView, setMissionView] = useState(() => (new URLSearchParams(location.search).get('view') === 'planner' ? 'planner' : 'history'));
  const [traverse, setTraverse] = useState(null);
  const [waypointData, setWaypointData] = useState(null);
  const [traverseError, setTraverseError] = useState('');
  const [solCut, setSolCut] = useState(2022);
  const [showHistory, setShowHistory] = useState(true);
  const [showWaypoints, setShowWaypoints] = useState(true);
  const [historyFit, setHistoryFit] = useState(0);
  const [waypoint, setWaypoint] = useState(null);

  const historyMode = missionView === 'history';
  const drives = useMemo(() => visibleDrives(traverse, solCut), [traverse, solCut]);
  const waypoints = useMemo(() => visibleWaypoints(waypointData, solCut), [waypointData, solCut]);
  const historyStats = useMemo(() => traverseStats(drives, waypoints), [drives, waypoints]);
  const maxSol = traverse ? Math.max(...traverse.features.map(f => f.properties.sol)) : 2022;

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetch('/mission-data/perseverance-traverse.geojson'), fetch('/mission-data/perseverance-waypoints.geojson')])
      .then(async rs => {
        if (rs.some(r => !r.ok)) throw Error('The recorded traverse could not load.');
        const [t, w] = await Promise.all(rs.map(r => r.json()));
        validateTraverse(t);
        if (cancelled) return;
        setTraverse(t);
        setWaypointData(w);
        setSolCut(Math.max(...t.features.map(f => f.properties.sol)));
        setHistoryFit(n => n + 1);
      })
      .catch(e => {
        if (!cancelled) setTraverseError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function switchMission(mode) {
    setMissionView(mode);
    setShowRoute(mode === 'planner');
    setProfileExpanded(false);
    setLayersOpen(false);
    setPick(null);
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

  // Layer & view controls
  const [base, setBase] = useState('hirise');
  const [hazards, setHazards] = useState(false);
  const [coverage, setCoverage] = useState(false);

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
  const [apiUrl, setApiUrl] = useState(() => resolveInitialApiUrl() || 'http://localhost:8000');
  const [connecting, setConnecting] = useState(false);
  const [connectionError, setConnectionError] = useState('');
  const [exportFormat, setExportFormat] = useState('json');
  const [notice, setNotice] = useState('');

  // UI Panels
  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth > 760);
  const [rightExpanded, setRightExpanded] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [robustnessSettingsOpen, setRobustnessSettingsOpen] = useState(false);
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

  const terrain = useMemo(() => (raw ? buildTerrain(raw) : null), [raw]);
  const active = result?.routes.find(r => r.route_id === selected) || result?.routes[0];
  const live = sourceMode === 'api';

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
    setResult(response);
    setPreviousResult(null);
    setSelected(response.routes[0].route_id);
    lastRequest.current = request;
    setFitToken(n => n + 1);
    setBusy(false);
    setError('');
  }

  // Load bundled terrain raster for local client worker
  useEffect(() => {
    let disposed = false;
    Promise.all([fetch('/mission-data/jezero-dem.json'), fetch('/mission-data/jezero-dem.sha256')])
      .then(async ([r, h]) => {
        if (!r.ok || !h.ok) throw new Error('The terrain dataset could not be loaded. Refresh this page to retry.');
        const text = await r.text();
        const expected = (await h.text()).trim();
        const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
        const actual = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
        if (actual !== expected) throw new Error('Terrain file integrity check failed. No routes were computed.');
        const data = { ...JSON.parse(text), local_integrity_verified: true, file_sha256: actual };
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
        lastRequest.current = initialRequest;
        w.postMessage({ id: ++sequence.current, raw: data, request: initialRequest });
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

  function invalidate() {
    sequence.current++;
    abort.current?.abort();
    setBusy(false);
    setError('');
    setNotice('');
  }

  function mapPin(p) {
    if (!pick) return;
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

  function buildRequest() {
    const req = {
      start: { lon: Number(start.lon), lat: Number(start.lat) },
      destination: { lon: Number(destination.lon), lat: Number(destination.lat) },
      crs_identifier: 'IAU2000:49900',
      mode,
      constraints: {
        max_slope_deg: Number(maxSlope),
        max_roughness: Number(maxRough),
        avoid_unobserved_terrain: avoidUnobserved
      },
      science_waypoints: scienceWaypoints.map(w => ({ lon: Number(w.lon), lat: Number(w.lat) })),
      num_alternatives: Math.max(1, Math.min(3, Number(numAlternatives)))
    };

    if (robustnessEnabled) {
      req.robustness_config = {
        enabled: true,
        vertical_sigma_m: Number(robustnessConfig.vertical_sigma_m),
        correlation_length_m: Number(robustnessConfig.correlation_length_m),
        scenario_count: Math.max(3, Math.min(20, Number(robustnessConfig.scenario_count))),
        seed: Number(robustnessConfig.seed),
        cost_regret_threshold_fraction: Number(robustnessConfig.cost_regret_threshold_fraction)
      };
    }

    if (!live || api?.algorithmSupported) {
      req.algorithm = algorithm;
    }

    return req;
  }

  async function run() {
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

    const req = buildRequest();
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
      worker.current?.postMessage({ id, raw, request: req });
      return;
    }

    if (algorithm === 'dijkstra' && !api.algorithmSupported) {
      setError('This backend only exposes A* through its API. Select A*, or use the bundled-grid planner for Dijkstra.');
      setBusy(false);
      return;
    }

    const payload = { ...req };
    if (!api.algorithmSupported) {
      delete payload.algorithm;
    }

    const controller = new AbortController();
    abort.current = controller;
    const timeout = setTimeout(() => controller.abort(), 60000);

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

      const fetchEndpoint = async path => {
        try {
          const r = await fetch(url + path, { signal: AbortSignal.timeout(30000) });
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
      localStorage.setItem('marspath-api-url', url);
      setApiUrl(url);

      invalidate();
      setSourceMode('api');
      setAlgorithm('astar');
      setShowSettings(false);

      if (isDegraded) {
        const blockerMsg = status.blocking_errors?.join(', ') || health.data_readiness?.fallback_reason || 'Real DEM not fully provisioned';
        setNotice(`Connected to Python API (Degraded mode: ${blockerMsg}).`);
      } else {
        setNotice('Python API connected. Planetary routing and evidence pipelines ready.');
      }
    } catch (e) {
      setConnectionError(
        `${e.message} If browser-blocked, confirm ${location.origin} is included in backend MARSPATH_CORS_ORIGINS.`
      );
    } finally {
      setConnecting(false);
    }
  }

  function disconnectApi() {
    setApi(null);
    setApiConnectionState('disconnected');
    setSourceMode('browser');
    invalidate();
    setNotice('Disconnected from Python backend. Switched to bundled local planner.');
  }

  function download() {
    if (!result) return;
    const missionId = result.mission_id || 'jezero-mission';
    let fileContent;
    let mimeType;
    let ext;

    if (exportFormat === 'geojson') {
      fileContent = JSON.stringify(exportGeoJSON(result, active.route_id, lastRequest.current), null, 2);
      mimeType = 'application/geo+json';
      ext = 'geojson';
    } else if (exportFormat === 'csv') {
      fileContent = exportCSV(result, active.route_id);
      mimeType = 'text/csv';
      ext = 'csv';
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
        (!leftOpen ? 'left-collapsed' : '')
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

      <main className="map-stage" aria-label="MarsPath mission planner">
        {loadError && !live ? (
          <div className="load-error">
            <h2>Local terrain unavailable</h2>
            <p>{loadError}</p>
            <div className="fallback-actions">
              <button onClick={() => location.reload()}>Retry local DEM</button>
              <button onClick={() => setShowSettings(true)}>Connect Python API</button>
            </div>
          </div>
        ) : terrain || live ? (
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
            start={start}
            destination={destination}
            scienceWaypoints={scienceWaypoints}
            pick={pick}
            onPin={mapPin}
            base={base}
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
            profileExpanded={profileExpanded}
            actionsRef={mapActions}
          />
        ) : (
          <div className="loading-map">
            <span className="spinner" />
            Verifying Jezero terrain…
          </div>
        )}

        {!leftOpen && (
          <button className="route-reopen glass" onClick={() => setLeftOpen(true)} aria-label="Open route design">
            <Icon name="sliders" />
            {historyMode ? 'Rover traverse' : 'Route design'}
          </button>
        )}

        <aside className={'floating-left glass ' + (leftOpen ? '' : 'collapsed')} inert={!leftOpen} aria-label="Route design">
          <div className="panel-heading">
            <h1>{historyMode ? 'Rover traverse' : 'Route design'}</h1>
            <button className="icon-button" onClick={() => setLeftOpen(false)} aria-label="Collapse route design">
              <Icon name="left" />
            </button>
          </div>

          <div className="mission-mode" role="group" aria-label="Mission view">
            <button className={historyMode ? 'active' : ''} aria-pressed={historyMode} onClick={() => switchMission('history')}>
              Rover history
            </button>
            <button className={!historyMode ? 'active' : ''} aria-pressed={!historyMode} onClick={() => switchMission('planner')}>
              Route planner
            </button>
          </div>

          {historyMode ? (
            <TraversePanel
              data={traverse}
              waypoints={waypoints}
              stats={historyStats}
              selected={waypoint}
              onFit={showAllHistory}
              onExport={exportHistory}
              onPlan={planFromWaypoint}
              error={traverseError}
            />
          ) : (
            <>
              {error && (
                <div className="error-message" role="alert">
                  {error}
                </div>
              )}

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
                                Scenarios (3–20)
                                <input
                                  type="number"
                                  min="3"
                                  max="20"
                                  step="1"
                                  value={robustnessConfig.scenario_count}
                                  onChange={e =>
                                    setRobustnessConfig(c => ({ ...c, scenario_count: Number(e.target.value) }))
                                  }
                                />
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

        {!historyMode && (
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
                  </nav>

                  {/* TAB 1: OVERVIEW */}
                  {analysisTab === 'overview' && (
                    <div className="tab-pane overview-pane" role="tabpanel">
                      <div className="route-candidates" role="group" aria-label="Route candidates">
                        {result?.routes.map((r, i) => (
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
                            <span className="radio-dot" />
                            <span>{i === 0 ? 'Primary' : 'Alternative ' + i}</span>
                            <small>
                              {fmt(r.summary?.total_distance_meters / 1000, 2)} km <b>·</b>{' '}
                              {Number.isFinite(r.summary?.estimated_duration_hours)
                                ? fmt(r.summary.estimated_duration_hours, 1) + ' h'
                                : 'ETA unavail'}
                            </small>
                          </button>
                        ))}
                        {!result && (
                          <p className={'empty-routes ' + (busy ? 'shimmer' : '')}>
                            {busy ? 'Analyzing corridors…' : 'Generate a route to compare candidates.'}
                          </p>
                        )}
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

                      <details className="analysis-details" open={detailsOpen} onToggle={e => setDetailsOpen(e.currentTarget.open)}>
                        <summary>
                          <span>Cost & Terrain Breakdown</span>
                          <Icon name="chevron" />
                        </summary>
                        <div className="details-body">
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

                  {/* Export Controls */}
                  <div className="export-controls">
                    <select aria-label="Export format" value={exportFormat} onChange={e => setExportFormat(e.target.value)}>
                      <option value="json">JSON manifest</option>
                      <option value="geojson">GeoJSON Feature</option>
                      <option value="csv">CSV (Segments)</option>
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
            <LayerToggle label="Hazards & Obstacles" color="amber" checked={hazards} onChange={setHazards} />
            <LayerToggle label="Data coverage" color="gray" checked={coverage} onChange={setCoverage} />
            <div className="layer-basemap">
              <span>Basemap</span>
              <div className="segmented">
                <button className={base === 'hirise' ? 'active' : ''} onClick={() => setBase('hirise')}>
                  HiRISE
                </button>
                <button className={base === 'imagery' ? 'active' : ''} onClick={() => setBase('imagery')}>
                  Imagery
                </button>
                <button className={base === 'relief' ? 'active' : ''} onClick={() => setBase('relief')}>
                  Terrain
                </button>
              </div>
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
          <TraverseTimeline cut={solCut} max={maxSol} stats={historyStats} onChange={v => { setSolCut(v); setWaypoint(null); }} onAll={showAllHistory} />
        ) : (
          <Profile route={active} onHover={setHover} expanded={profileExpanded} onToggle={value => setProfileExpanded(v => (typeof value === 'boolean' ? value : !v))} busy={busy} />
        )}

        <div className="traverse-key glass">
          <span><i className="recorded" />Recorded drives</span>
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
