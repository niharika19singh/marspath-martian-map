import React, { useState, useEffect, useMemo } from 'react';
import Icon from './Icons.jsx';
import {
  fetchDataFreshness,
  fetchNormalizedObservations,
  fetchKnowledgeGraph,
  fetchNodeEvidence,
  fetchNodeImpacts,
  fetchScenarios,
  createScenario,
  analyzeScenario,
  compareScenario,
  evaluateRouteRisk,
} from './fusion_client.js';

export default function MissionIntelligencePanel(props) {
  const {
    apiUrl = '',
    onClose,
    onFocusCoordinates,
    activeRoute,
    onHighlightSegment,
  } = props;

  const [activeTab, setActiveTab] = useState('evidence'); // 'evidence' | 'graph' | 'propagation' | 'scenarios' | 'freshness'
  
  // Data states
  const [freshness, setFreshness] = useState(null);
  const [observations, setObservations] = useState([]);
  const [graphData, setGraphData] = useState({ nodes: [], edges: [] });
  const [scenarios, setScenarios] = useState([]);
  const [activeScenarioId, setActiveScenarioId] = useState('');
  const [scenarioAnalysis, setScenarioAnalysis] = useState(null);
  const [scenarioComparison, setScenarioComparison] = useState(null);
  const [propagationResult, setPropagationResult] = useState(null);

  // Filter states
  const [searchQuery, setSearchQuery] = useState('');
  const [filterInstrument, setFilterInstrument] = useState('all');
  const [filterProvenance, setFilterProvenance] = useState('all');
  const [filterTier, setFilterTier] = useState('all');
  const [selectedObs, setSelectedObs] = useState(null);

  // Graph interaction states
  const [selectedNode, setSelectedNode] = useState(null);
  const [graphFilterType, setGraphFilterType] = useState('all');
  const [evidenceTrace, setEvidenceTrace] = useState(null);
  const [impactTrace, setImpactTrace] = useState(null);
  const [traceLoading, setTraceLoading] = useState(false);

  // What-If Builder State
  const [newScenarioName, setNewScenarioName] = useState('Custom Dust & Slope Stress Test');
  const [modTau, setModTau] = useState(1.0);
  const [modPower, setModPower] = useState(0.7);
  const [modSlope, setModSlope] = useState(11.0);
  const [modWheel, setModWheel] = useState(0.8);
  const [modComm, setModComm] = useState(false);
  const [isSubmittingScenario, setIsSubmittingScenario] = useState(false);
  const [loading, setLoading] = useState(false);

  // Load initial datasets
  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetchDataFreshness(apiUrl).catch(() => null),
      fetchNormalizedObservations({}, apiUrl).catch(() => []),
      fetchKnowledgeGraph({}, apiUrl).catch(() => ({ nodes: [], edges: [] })),
      fetchScenarios(apiUrl).catch(() => []),
    ]).then(([fr, obs, gr, sc]) => {
      if (cancelled) return;
      if (fr) setFreshness(fr);
      if (obs) {
        setObservations(obs);
        if (obs.length > 0) setSelectedObs(obs[0]);
      }
      if (gr) {
        setGraphData(gr);
        if (gr.nodes && gr.nodes.length > 0) setSelectedNode(gr.nodes[0]);
      }
      if (sc && sc.length > 0) {
        setScenarios(sc);
        setActiveScenarioId(sc[0].scenario_id);
      }
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [apiUrl]);

  // Evaluate risk propagation when activeRoute changes or when entering propagation tab
  useEffect(() => {
    if (activeTab === 'propagation' || activeTab === 'scenarios') {
      const routePayload = activeRoute || {
        route_id: 'primary',
        geometry: {
          type: 'LineString',
          coordinates: [
            [77.4120, 18.4200, -2540.0],
            [77.4180, 18.4240, -2532.0],
            [77.4250, 18.4290, -2524.0],
            [77.4350, 18.4350, -2510.0],
          ]
        }
      };
      evaluateRouteRisk(routePayload, 14.0, 0.85, apiUrl)
        .then(setPropagationResult)
        .catch(err => console.error('Error evaluating route risk:', err));
    }
  }, [activeTab, activeRoute, apiUrl]);

  // Run scenario analysis and comparison when activeScenarioId changes
  useEffect(() => {
    if (!activeScenarioId) return;
    const routePayload = activeRoute || null;
    analyzeScenario(activeScenarioId, routePayload, apiUrl)
      .then(setScenarioAnalysis)
      .catch(console.error);

    compareScenario(activeScenarioId, 'primary', apiUrl)
      .then(setScenarioComparison)
      .catch(console.error);
  }, [activeScenarioId, activeRoute, apiUrl]);

  // Tracing handlers for Knowledge Graph
  const handleTraceEvidence = async (nodeId) => {
    if (!nodeId) return;
    setTraceLoading(true);
    setEvidenceTrace(null);
    try {
      const res = await fetchNodeEvidence(nodeId, 5, apiUrl);
      setEvidenceTrace(res);
    } catch (e) {
      console.error(e);
    } finally {
      setTraceLoading(false);
    }
  };

  const handleTraceImpacts = async (nodeId) => {
    if (!nodeId) return;
    setTraceLoading(true);
    setImpactTrace(null);
    try {
      const res = await fetchNodeImpacts(nodeId, 5, apiUrl);
      setImpactTrace(res);
    } catch (e) {
      console.error(e);
    } finally {
      setTraceLoading(false);
    }
  };

  const handleCreateCustomScenario = async () => {
    setIsSubmittingScenario(true);
    try {
      const payload = {
        name: newScenarioName,
        description: 'User-configured what-if contingency scenario',
        baseline_route_id: 'primary',
        modifiers: {
          tau_atmospheric_increase: parseFloat(modTau),
          power_budget_factor: parseFloat(modPower),
          max_slope_ceiling_deg: parseFloat(modSlope),
          max_roughness_limit: 0.85,
          wheel_degradation_factor: parseFloat(modWheel),
          comm_window_constrained: modComm,
        },
        tags: ['custom', 'what_if']
      };
      const created = await createScenario(payload, apiUrl);
      setScenarios(prev => [created, ...prev]);
      setActiveScenarioId(created.scenario_id);
    } catch (e) {
      alert(`Scenario creation failed: ${e.message}`);
    } finally {
      setIsSubmittingScenario(false);
    }
  };

  // Filtered observations
  const filteredObservations = useMemo(() => {
    return observations.filter(obs => {
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchTitle = obs.title && obs.title.toLowerCase().includes(q);
        const matchInst = obs.instrument && obs.instrument.toLowerCase().includes(q);
        const matchId = obs.observation_id && obs.observation_id.toLowerCase().includes(q);
        if (!matchTitle && !matchInst && !matchId) return false;
      }
      if (filterInstrument !== 'all') {
        if (!obs.instrument || !obs.instrument.toLowerCase().includes(filterInstrument.toLowerCase())) return false;
      }
      if (filterProvenance !== 'all') {
        if (!obs.provenance_kind || obs.provenance_kind.toLowerCase() !== filterProvenance.toLowerCase()) return false;
      }
      if (filterTier !== 'all') {
        if (!obs.quality_tier || obs.quality_tier.toUpperCase() !== filterTier.toUpperCase()) return false;
      }
      return true;
    });
  }, [observations, searchQuery, filterInstrument, filterProvenance, filterTier]);

  // Graph nodes filtered
  const filteredNodes = useMemo(() => {
    if (graphFilterType === 'all') return graphData.nodes || [];
    return (graphData.nodes || []).filter(n => n.node_type && n.node_type.toLowerCase() === graphFilterType.toLowerCase());
  }, [graphData.nodes, graphFilterType]);

  const getNodeColor = (type) => {
    switch (type) {
      case 'DATASET': return '#38bdf8';
      case 'OBSERVATION': return '#2dd4bf';
      case 'HAZARD': return '#f87171';
      case 'ROUTE_SEGMENT': return '#facc15';
      case 'OPERATIONAL_CONSTRAINT': return '#c084fc';
      case 'TERRAIN_REGION': return '#4ade80';
      case 'ROUTE': return '#fb923c';
      case 'SCIENCE_TARGET': return '#a78bfa';
      default: return '#94a3b8';
    }
  };

  return (
    <div
      className="mission-intelligence-panel flex flex-col h-full overflow-hidden"
      style={{
        backgroundColor: '#0a1017',
        color: '#e2e8f0',
        fontFamily: 'Inter, system-ui, sans-serif'
      }}
    >
      {/* Top Header */}
      <div className="flex items-center justify-between border-b border-cyan-900/40 px-5 py-3.5 bg-[#0d1622]/90 backdrop-blur-md">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-cyan-950/80 border border-cyan-500/30 text-cyan-400">
            <Icon name="radar" className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold tracking-wider text-cyan-300 uppercase">Mission Intelligence & Risk Fusion</h2>
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-500/40">
                ACTIVE
              </span>
            </div>
            <p className="text-[11px] text-slate-400 font-mono">
              Geospatial Knowledge Graph &bull; Multi-Source Traceability &bull; Risk Propagation
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-md hover:bg-slate-800 text-slate-400 hover:text-white transition-colors"
          title="Close Intelligence Workspace"
        >
          <Icon name="close" className="w-4 h-4" />
        </button>
      </div>

      {/* Primary Subsystem Navigation Tabs */}
      <div className="flex border-b border-slate-800 bg-[#080d14] text-xs font-medium">
        <button
          onClick={() => setActiveTab('evidence')}
          className={`flex-1 py-2.5 px-3 text-center border-b-2 transition-colors ${
            activeTab === 'evidence'
              ? 'border-cyan-400 text-cyan-300 bg-cyan-950/20 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          }`}
        >
          <span className="flex items-center justify-center gap-1.5">
            <Icon name="layers" className="w-3.5 h-3.5" />
            Evidence Explorer
          </span>
        </button>
        <button
          onClick={() => setActiveTab('graph')}
          className={`flex-1 py-2.5 px-3 text-center border-b-2 transition-colors ${
            activeTab === 'graph'
              ? 'border-cyan-400 text-cyan-300 bg-cyan-950/20 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          }`}
        >
          <span className="flex items-center justify-center gap-1.5">
            <Icon name="network" className="w-3.5 h-3.5" />
            Knowledge Graph
          </span>
        </button>
        <button
          onClick={() => setActiveTab('propagation')}
          className={`flex-1 py-2.5 px-3 text-center border-b-2 transition-colors ${
            activeTab === 'propagation'
              ? 'border-cyan-400 text-cyan-300 bg-cyan-950/20 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          }`}
        >
          <span className="flex items-center justify-center gap-1.5">
            <Icon name="alert-triangle" className="w-3.5 h-3.5" />
            Risk Propagation
          </span>
        </button>
        <button
          onClick={() => setActiveTab('scenarios')}
          className={`flex-1 py-2.5 px-3 text-center border-b-2 transition-colors ${
            activeTab === 'scenarios'
              ? 'border-cyan-400 text-cyan-300 bg-cyan-950/20 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          }`}
        >
          <span className="flex items-center justify-center gap-1.5">
            <Icon name="sliders" className="w-3.5 h-3.5" />
            What-If Scenarios
          </span>
        </button>
        <button
          onClick={() => setActiveTab('freshness')}
          className={`py-2.5 px-3 text-center border-b-2 transition-colors ${
            activeTab === 'freshness'
              ? 'border-cyan-400 text-cyan-300 bg-cyan-950/20 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/50'
          }`}
          title="Multi-Source Freshness & Coverage"
        >
          <span className="flex items-center justify-center gap-1">
            <Icon name="activity" className="w-3.5 h-3.5" />
            Health
          </span>
        </button>
      </div>

      {/* Main Tab Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">

        {/* ===================== TAB 1: EVIDENCE EXPLORER ===================== */}
        {activeTab === 'evidence' && (
          <div className="space-y-3.5">
            {/* Search and Filters */}
            <div className="p-3 rounded-lg bg-slate-900/70 border border-slate-800 space-y-2.5">
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search observation by ID, instrument, or description..."
                  className="w-full bg-[#0d1622] text-xs text-slate-200 pl-8 pr-3 py-1.5 rounded border border-slate-700/60 focus:outline-none focus:border-cyan-500"
                />
                <Icon name="search" className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              </div>
              <div className="grid grid-cols-3 gap-2 text-[11px]">
                <div>
                  <label className="text-slate-400 block mb-1">Instrument</label>
                  <select
                    value={filterInstrument}
                    onChange={e => setFilterInstrument(e.target.value)}
                    className="w-full bg-[#0d1622] text-slate-300 rounded px-2 py-1 border border-slate-700 focus:outline-none"
                  >
                    <option value="all">All Sensors</option>
                    <option value="hirise">HiRISE (Visual/DTM)</option>
                    <option value="themis">THEMIS (Thermal IR)</option>
                    <option value="meda">MEDA (In-Situ Weather)</option>
                    <option value="mola">MOLA-HRSC (DEM)</option>
                    <option value="rover">Rover Waypoints</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Provenance</label>
                  <select
                    value={filterProvenance}
                    onChange={e => setFilterProvenance(e.target.value)}
                    className="w-full bg-[#0d1622] text-slate-300 rounded px-2 py-1 border border-slate-700 focus:outline-none"
                  >
                    <option value="all">All Provenance</option>
                    <option value="measured">Measured (In-situ)</option>
                    <option value="derived">Derived (DEM/IR)</option>
                    <option value="computed">Computed</option>
                    <option value="historical">Historical</option>
                  </select>
                </div>
                <div>
                  <label className="text-slate-400 block mb-1">Quality Tier</label>
                  <select
                    value={filterTier}
                    onChange={e => setFilterTier(e.target.value)}
                    className="w-full bg-[#0d1622] text-slate-300 rounded px-2 py-1 border border-slate-700 focus:outline-none"
                  >
                    <option value="all">All Tiers</option>
                    <option value="GOLD">Gold (PDS Calibrated)</option>
                    <option value="SILVER">Silver (Standard)</option>
                    <option value="BRONZE">Bronze (Advisory)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Results Counter */}
            <div className="flex items-center justify-between text-xs text-slate-400 font-mono px-1">
              <span>Matching Observations: {filteredObservations.length}</span>
              <span className="text-[11px] text-cyan-400">USGS &bull; PDS &bull; ASU THEMIS</span>
            </div>

            {/* Observations List */}
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {filteredObservations.map(obs => (
                <div
                  key={obs.observation_id}
                  onClick={() => setSelectedObs(obs)}
                  className={`p-2.5 rounded-lg border text-xs cursor-pointer transition-all ${
                    selectedObs?.observation_id === obs.observation_id
                      ? 'bg-cyan-950/40 border-cyan-500/80 shadow-md shadow-cyan-950/30'
                      : 'bg-slate-900/40 border-slate-800 hover:border-slate-700 hover:bg-slate-900/70'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <span className="font-semibold text-slate-200">{obs.title || obs.observation_id}</span>
                      <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-2">
                        <span>{obs.instrument}</span>
                        <span>&bull;</span>
                        <span className="font-mono text-cyan-400">{obs.spatial_resolution_m ? `${obs.spatial_resolution_m} m/px` : 'In-situ'}</span>
                      </div>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${
                        obs.quality_tier === 'GOLD'
                          ? 'bg-amber-950 text-amber-300 border border-amber-600/40'
                          : 'bg-slate-800 text-slate-300'
                      }`}>
                        {obs.quality_tier}
                      </span>
                      <span className="text-[9px] uppercase px-1 py-0.5 rounded bg-slate-800/80 text-slate-400 font-mono">
                        {obs.provenance_kind}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Selected Observation Detail Inspector */}
            {selectedObs && (
              <div className="p-3.5 rounded-lg bg-slate-900/80 border border-cyan-800/40 space-y-2.5">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold text-cyan-300 uppercase tracking-wide">Observation Evidence Passport</h3>
                  {selectedObs.bbox && onFocusCoordinates && (
                    <button
                      onClick={() => onFocusCoordinates([(selectedObs.bbox[0] + selectedObs.bbox[2]) / 2, (selectedObs.bbox[1] + selectedObs.bbox[3]) / 2])}
                      className="text-[11px] text-cyan-400 hover:text-cyan-200 flex items-center gap-1 font-mono"
                    >
                      <Icon name="crosshair" className="w-3 h-3" />
                      Center on Map
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-2 gap-2 text-[11px] font-mono bg-slate-950/60 p-2.5 rounded border border-slate-800">
                  <div>
                    <span className="text-slate-400 block text-[10px]">Product / ID:</span>
                    <span className="text-slate-200 truncate block">{selectedObs.observation_id}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Source Archive:</span>
                    <span className="text-cyan-400">{selectedObs.source_id}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Instrument:</span>
                    <span className="text-slate-200">{selectedObs.instrument}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block text-[10px]">Measurement Type:</span>
                    <span className="text-slate-300 truncate block">{selectedObs.measurement_type}</span>
                  </div>
                  {selectedObs.doi && (
                    <div className="col-span-2">
                      <span className="text-slate-400 block text-[10px]">Authoritative DOI:</span>
                      <a
                        href={`https://doi.org/${selectedObs.doi}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-400 hover:underline break-all"
                      >
                        doi:{selectedObs.doi}
                      </a>
                    </div>
                  )}
                  {selectedObs.uncertainty_info && Object.keys(selectedObs.uncertainty_info).length > 0 && (
                    <div className="col-span-2 bg-slate-900/80 p-2 rounded border border-slate-800 text-[10px]">
                      <span className="text-amber-400 font-semibold block mb-0.5">Quantified Uncertainty Bounds:</span>
                      <pre className="text-slate-300 overflow-x-auto whitespace-pre-wrap">
                        {JSON.stringify(selectedObs.uncertainty_info, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
                {selectedObs.official_url && (
                  <a
                    href={selectedObs.official_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-cyan-400 hover:text-cyan-300 font-medium"
                  >
                    View Official NASA PDS / USGS Record <Icon name="external-link" className="w-3 h-3" />
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {/* ===================== TAB 2: MISSION KNOWLEDGE GRAPH ===================== */}
        {activeTab === 'graph' && (
          <div className="space-y-3.5">
            {/* Graph Filter Bar */}
            <div className="flex items-center justify-between text-xs">
              <span className="text-slate-400 font-mono">Filter Entities:</span>
              <div className="flex gap-1">
                {['all', 'hazard', 'route_segment', 'observation', 'dataset', 'operational_constraint'].map(type => (
                  <button
                    key={type}
                    onClick={() => setGraphFilterType(type)}
                    className={`text-[10px] px-2 py-0.5 rounded font-mono uppercase transition-colors ${
                      graphFilterType === type
                        ? 'bg-cyan-900 text-cyan-200 border border-cyan-500'
                        : 'bg-slate-900 text-slate-400 hover:text-slate-200 border border-slate-800'
                    }`}
                  >
                    {type.replace('_', ' ')}
                  </button>
                ))}
              </div>
            </div>

            {/* Interactive Graph Node Browser */}
            <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 max-h-64 overflow-y-auto space-y-1.5">
              <div className="text-[10px] text-slate-500 font-mono uppercase mb-1">
                Showing {filteredNodes.length} nodes &bull; Click to Trace Multi-Hop Evidence & Impacts
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {filteredNodes.map(node => (
                  <button
                    key={node.node_id}
                    onClick={() => {
                      setSelectedNode(node);
                      setEvidenceTrace(null);
                      setImpactTrace(null);
                    }}
                    className={`p-2 rounded text-left text-xs border transition-all flex items-start gap-2 ${
                      selectedNode?.node_id === node.node_id
                        ? 'bg-cyan-950/60 border-cyan-500 text-cyan-200'
                        : 'bg-slate-900/60 border-slate-800 text-slate-300 hover:border-slate-700'
                    }`}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full mt-1 shrink-0"
                      style={{ backgroundColor: getNodeColor(node.node_type) }}
                    />
                    <div className="overflow-hidden">
                      <span className="font-semibold block truncate">{node.label}</span>
                      <span className="text-[10px] text-slate-400 font-mono">{node.node_type}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Selected Node Details & Action Buttons */}
            {selectedNode && (
              <div className="p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-xs font-bold text-cyan-300">{selectedNode.label}</span>
                    <p className="text-[11px] text-slate-400 mt-0.5">{selectedNode.description}</p>
                  </div>
                  <span
                    className="text-[10px] font-mono px-2 py-0.5 rounded font-bold"
                    style={{
                      backgroundColor: `${getNodeColor(selectedNode.node_type)}20`,
                      color: getNodeColor(selectedNode.node_type),
                      border: `1px solid ${getNodeColor(selectedNode.node_type)}50`
                    }}
                  >
                    {selectedNode.node_type}
                  </span>
                </div>

                {/* Traversal Actions */}
                <div className="flex gap-2">
                  <button
                    onClick={() => handleTraceEvidence(selectedNode.node_id)}
                    disabled={traceLoading}
                    className="flex-1 py-1.5 px-3 rounded bg-cyan-900/60 hover:bg-cyan-800 text-cyan-200 text-xs font-medium border border-cyan-500/40 flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Icon name="arrow-left" className="w-3.5 h-3.5" />
                    Trace Upstream Evidence
                  </button>
                  <button
                    onClick={() => handleTraceImpacts(selectedNode.node_id)}
                    disabled={traceLoading}
                    className="flex-1 py-1.5 px-3 rounded bg-amber-900/60 hover:bg-amber-800 text-amber-200 text-xs font-medium border border-amber-500/40 flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    <Icon name="arrow-right" className="w-3.5 h-3.5" />
                    Trace Downstream Impacts
                  </button>
                </div>

                {/* Upstream Evidence Results */}
                {evidenceTrace && (
                  <div className="p-3 rounded bg-slate-950/80 border border-cyan-900/50 space-y-2 text-xs">
                    <span className="text-cyan-400 font-bold block flex items-center gap-1">
                      <Icon name="check-circle" className="w-3.5 h-3.5" />
                      Upstream Evidence Lineage:
                    </span>
                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      {evidenceTrace.explanation || evidenceTrace.scientific_narrative}
                    </p>
                    <div className="text-[10px] font-mono text-slate-400 space-y-1 bg-slate-900/70 p-2 rounded">
                      <span className="text-slate-500 uppercase block font-bold">Causal Traverse Sequence:</span>
                      <div className="flex flex-wrap items-center gap-1">
                        {evidenceTrace.causal_chain.map((cId, idx) => (
                          <React.Fragment key={cId}>
                            <span className="bg-slate-800 px-1.5 py-0.5 rounded text-cyan-300">{cId}</span>
                            {idx < evidenceTrace.causal_chain.length - 1 && <span className="text-slate-600">&rarr;</span>}
                          </React.Fragment>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Downstream Impact Results */}
                {impactTrace && (
                  <div className="p-3 rounded bg-slate-950/80 border border-amber-900/50 space-y-2 text-xs">
                    <span className="text-amber-400 font-bold block flex items-center gap-1">
                      <Icon name="alert-circle" className="w-3.5 h-3.5" />
                      Downstream Mission Impacts:
                    </span>
                    <p className="text-[11px] text-slate-300 leading-relaxed">
                      {impactTrace.mission_impact_summary}
                    </p>
                    <div className="text-[10px] font-mono text-slate-400 space-y-1 bg-slate-900/70 p-2 rounded">
                      <span className="text-slate-500 uppercase block font-bold">Impacted Entities ({impactTrace.affected_nodes.length}):</span>
                      <div className="flex flex-wrap gap-1">
                        {impactTrace.affected_nodes.map(n => (
                          <span
                            key={n.node_id}
                            className="px-1.5 py-0.5 rounded font-mono"
                            style={{
                              backgroundColor: `${getNodeColor(n.node_type)}20`,
                              color: getNodeColor(n.node_type),
                              border: `1px solid ${getNodeColor(n.node_type)}50`
                            }}
                          >
                            {n.label}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ===================== TAB 3: RISK PROPAGATION ===================== */}
        {activeTab === 'propagation' && (
          <div className="space-y-3.5">
            {propagationResult ? (
              <div className="space-y-3.5">
                {/* Metric Summary Cards */}
                <div className="grid grid-cols-3 gap-2 text-center">
                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-mono uppercase">Traversability</span>
                    <span className={`text-xs font-bold font-mono ${
                      propagationResult.overall_traversability_state === 'NOMINAL'
                        ? 'text-emerald-400'
                        : propagationResult.overall_traversability_state.includes('CONSTRAINED')
                          ? 'text-amber-400'
                          : 'text-red-400'
                    }`}>
                      {propagationResult.overall_traversability_state}
                    </span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-mono uppercase">Relative Effort</span>
                    <span className="text-sm font-bold font-mono text-cyan-400">
                      {propagationResult.relative_route_effort_index.toFixed(2)}x
                    </span>
                  </div>
                  <div className="p-2.5 rounded bg-slate-900 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block font-mono uppercase">Hazard Exposure</span>
                    <span className="text-sm font-bold font-mono text-amber-400">
                      {propagationResult.hazard_exposure_distance_m.toFixed(0)} m
                    </span>
                  </div>
                </div>

                {/* Causal Chain Explanations */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wide block">
                    Causal Risk Propagation Chains
                  </span>
                  {propagationResult.causal_chains && propagationResult.causal_chains.length > 0 ? (
                    propagationResult.causal_chains.map((chain, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-slate-900/70 border border-slate-800 text-xs space-y-1.5">
                        <div className="flex items-center justify-between text-cyan-300 font-semibold">
                          <span>{chain.hazard_identified}</span>
                          <span className="text-[10px] font-mono text-slate-400">{chain.instrument}</span>
                        </div>
                        <div className="text-[11px] text-slate-300">
                          <span className="text-slate-400">Impact: </span>{chain.operational_impact}
                        </div>
                        <div className="text-[11px] text-emerald-400 bg-emerald-950/30 p-1.5 rounded border border-emerald-800/30">
                          <span className="font-semibold">Mitigation: </span>{chain.mitigation_recommendation}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="p-3 rounded bg-slate-900/40 text-xs text-slate-400 text-center font-mono">
                      No active critical hazard exposures identified along primary corridor.
                    </div>
                  )}
                </div>

                {/* Segment By Segment Grid */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wide block">
                    Evaluated Route Segments ({propagationResult.segment_evaluations.length})
                  </span>
                  <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                    {propagationResult.segment_evaluations.map(seg => (
                      <div
                        key={seg.segment_index}
                        onClick={() => onHighlightSegment && onHighlightSegment(seg.segment_index)}
                        className="p-2 rounded bg-slate-900/60 border border-slate-800 text-xs flex items-center justify-between hover:border-slate-700 cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-cyan-400 font-bold">#{seg.segment_index}</span>
                          <div>
                            <span className="text-slate-200">{seg.distance_m} m</span>
                            <span className="text-[10px] text-slate-400 ml-2 font-mono">Slope: {seg.slope_deg}°</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[10px] font-mono text-slate-400">{seg.dem_resolution_m} m DEM</span>
                          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${
                            seg.operational_status === 'NOMINAL'
                              ? 'bg-emerald-950 text-emerald-400'
                              : seg.operational_status === 'CONSTRAINED'
                                ? 'bg-amber-950 text-amber-400'
                                : 'bg-red-950 text-red-400'
                          }`}>
                            {seg.operational_status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Scientific Disclaimer */}
                <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-400 font-mono leading-relaxed">
                  <span className="text-amber-400 font-semibold block mb-0.5">Planning Indicator Caveat:</span>
                  {propagationResult.scientific_disclaimer}
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-400 font-mono">
                Evaluating active route against multi-source risk propagation index...
              </div>
            )}
          </div>
        )}

        {/* ===================== TAB 4: WHAT-IF SCENARIOS ===================== */}
        {activeTab === 'scenarios' && (
          <div className="space-y-4">
            {/* Scenario Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-slate-300 uppercase tracking-wide block">
                Select Mission What-If Scenario
              </label>
              <select
                value={activeScenarioId}
                onChange={e => setActiveScenarioId(e.target.value)}
                className="w-full bg-slate-900 text-xs text-slate-200 rounded p-2 border border-slate-700 focus:outline-none focus:border-cyan-500"
              >
                {scenarios.map(sc => (
                  <option key={sc.scenario_id} value={sc.scenario_id}>
                    {sc.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Scenario Side-by-Side Comparison Report */}
            {scenarioComparison && (
              <div className="p-3.5 rounded-lg bg-slate-900/80 border border-cyan-800/40 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-cyan-300 uppercase tracking-wide">
                    Scenario vs Baseline Comparison
                  </span>
                  <span className={`text-[10px] font-bold font-mono px-2 py-0.5 rounded ${
                    scenarioComparison.return_feasibility === 'FEASIBLE'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-600/40'
                      : scenarioComparison.return_feasibility === 'MARGINAL'
                        ? 'bg-amber-950 text-amber-300 border border-amber-600/40'
                        : 'bg-red-950 text-red-300 border border-red-600/40'
                  }`}>
                    Return: {scenarioComparison.return_feasibility}
                  </span>
                </div>

                {/* Comparison Delta Metrics */}
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Traverse Distance:</span>
                    <span className="text-slate-200">{scenarioComparison.scenario_distance_m} m </span>
                    <span className="text-cyan-400 font-bold">
                      ({scenarioComparison.delta_distance_m >= 0 ? `+${scenarioComparison.delta_distance_m}` : scenarioComparison.delta_distance_m} m)
                    </span>
                  </div>
                  <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Relative Route Effort:</span>
                    <span className="text-slate-200">{scenarioComparison.scenario_relative_effort}x </span>
                    <span className={scenarioComparison.delta_relative_effort > 0 ? 'text-amber-400' : 'text-emerald-400'}>
                      ({scenarioComparison.delta_relative_effort >= 0 ? `+${scenarioComparison.delta_relative_effort}` : scenarioComparison.delta_relative_effort})
                    </span>
                  </div>
                  <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Hazard Exposure Delta:</span>
                    <span className={scenarioComparison.delta_hazard_exposure_distance_m > 0 ? 'text-amber-400 font-bold' : 'text-emerald-400 font-bold'}>
                      {scenarioComparison.delta_hazard_exposure_distance_m >= 0 ? `+${scenarioComparison.delta_hazard_exposure_distance_m}` : scenarioComparison.delta_hazard_exposure_distance_m} m
                    </span>
                  </div>
                  <div className="p-2 rounded bg-slate-950/70 border border-slate-800">
                    <span className="text-[10px] text-slate-400 block">Impassable Segments:</span>
                    <span className={scenarioComparison.scenario_impassable_count > 0 ? 'text-red-400 font-bold' : 'text-emerald-400'}>
                      {scenarioComparison.scenario_impassable_count} segments ({scenarioComparison.delta_impassable_segments >= 0 ? `+${scenarioComparison.delta_impassable_segments}` : scenarioComparison.delta_impassable_segments})
                    </span>
                  </div>
                </div>

                {/* Key Operational Tradeoffs */}
                <div className="space-y-1.5 text-xs">
                  <span className="text-[11px] font-bold text-slate-300 block">Operational Impact Tradeoffs:</span>
                  <ul className="list-disc list-inside text-[11px] text-slate-400 space-y-1">
                    {scenarioComparison.key_tradeoffs.map((tradeoff, i) => (
                      <li key={i}>{tradeoff}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}

            {/* What-If Custom Scenario Generator Form */}
            <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800 space-y-3">
              <span className="text-xs font-bold text-slate-200 uppercase tracking-wide block">
                Author Custom Stress-Test Scenario
              </span>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Scenario Name</label>
                <input
                  type="text"
                  value={newScenarioName}
                  onChange={e => setNewScenarioName(e.target.value)}
                  className="w-full bg-[#0d1622] text-xs text-slate-200 p-1.5 rounded border border-slate-700 focus:outline-none"
                />
              </div>

              {/* Sliders */}
              <div className="space-y-2 text-xs">
                <div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>Dust Opacity Surge (&Delta;&tau;):</span>
                    <span className="font-mono text-cyan-400">+{modTau}</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="3.0"
                    step="0.1"
                    value={modTau}
                    onChange={e => setModTau(e.target.value)}
                    className="w-full h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>Solar Power Budget Factor:</span>
                    <span className="font-mono text-cyan-400">{Math.round(modPower * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.3"
                    max="1.0"
                    step="0.05"
                    value={modPower}
                    onChange={e => setModPower(e.target.value)}
                    className="w-full h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>Max Traversing Slope Ceiling:</span>
                    <span className="font-mono text-cyan-400">{modSlope}&deg;</span>
                  </div>
                  <input
                    type="range"
                    min="8.0"
                    max="20.0"
                    step="0.5"
                    value={modSlope}
                    onChange={e => setModSlope(e.target.value)}
                    className="w-full h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>

                <div>
                  <div className="flex justify-between text-[11px] text-slate-400">
                    <span>Wheel Drive Efficiency (Wear):</span>
                    <span className="font-mono text-cyan-400">{Math.round(modWheel * 100)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.4"
                    max="1.0"
                    step="0.05"
                    value={modWheel}
                    onChange={e => setModWheel(e.target.value)}
                    className="w-full h-1 bg-slate-800 rounded appearance-none cursor-pointer accent-cyan-400"
                  />
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="commWindowCheck"
                    checked={modComm}
                    onChange={e => setModComm(e.target.checked)}
                    className="rounded bg-slate-800 border-slate-700 text-cyan-500 focus:ring-0"
                  />
                  <label htmlFor="commWindowCheck" className="text-[11px] text-slate-300">
                    Enforce strict MRO UHF relay pass time constraint
                  </label>
                </div>
              </div>

              <button
                onClick={handleCreateCustomScenario}
                disabled={isSubmittingScenario}
                className="w-full py-2 px-3 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-bold text-xs uppercase tracking-wide transition-colors disabled:opacity-50"
              >
                {isSubmittingScenario ? 'Simulating Scenario...' : 'Create & Run Scenario'}
              </button>
            </div>
          </div>
        )}

        {/* ===================== TAB 5: DATA FRESHNESS & HEALTH ===================== */}
        {activeTab === 'freshness' && (
          <div className="space-y-3.5">
            {freshness ? (
              <div className="space-y-3.5">
                {/* Health Overview */}
                <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-between text-xs">
                  <div>
                    <span className="text-slate-400 block text-[10px] uppercase font-mono">Subsystem Health</span>
                    <span className="text-emerald-400 font-bold font-mono text-sm uppercase">{freshness.status}</span>
                  </div>
                  <div className="text-right font-mono text-[11px] text-slate-400">
                    <div>Connected: {freshness.connected_count} / {freshness.sources_count}</div>
                    <div className="text-[10px] text-slate-500">Stale Sources: {freshness.stale_count}</div>
                  </div>
                </div>

                {/* Integrated NASA Sources List */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-300 uppercase tracking-wide block">
                    8 Registered Planetary Data Sources
                  </span>
                  <div className="space-y-1.5 max-h-60 overflow-y-auto pr-1">
                    {freshness.sources.map(src => (
                      <div key={src.source_id} className="p-2.5 rounded bg-slate-900/60 border border-slate-800 text-xs space-y-1">
                        <div className="flex items-center justify-between font-semibold text-slate-200">
                          <span>{src.source_name}</span>
                          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-600/30">
                            {src.freshness}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 leading-tight">{src.freshness_explanation}</p>
                        <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/60">
                          <span>Items: {src.item_count}</span>
                          {src.latency_ms && <span>Latency: {src.latency_ms.toFixed(1)} ms</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Spatial Coverage Gaps */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-amber-400 uppercase tracking-wide flex items-center gap-1.5">
                    <Icon name="alert-triangle" className="w-3.5 h-3.5" />
                    Spatial Coverage Gaps Detected ({freshness.coverage_gaps.length})
                  </span>
                  {freshness.coverage_gaps.map(gap => (
                    <div key={gap.gap_id} className="p-3 rounded-lg bg-amber-950/20 border border-amber-800/40 text-xs space-y-1.5">
                      <div className="flex items-center justify-between font-bold text-amber-300">
                        <span>{gap.region_name}</span>
                        <span className="text-[10px] font-mono text-slate-400">Fallback: {gap.available_fallback_resolution_m} m</span>
                      </div>
                      <p className="text-[11px] text-slate-300">{gap.risk_assessment}</p>
                      <div className="text-[10px] text-cyan-300 font-mono bg-cyan-950/40 p-1.5 rounded border border-cyan-800/30">
                        <span className="font-semibold">Recon Recommendation: </span>{gap.recommended_reconnaissance}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-xs text-slate-400 font-mono">
                Auditing live connection and synchronization freshness...
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
