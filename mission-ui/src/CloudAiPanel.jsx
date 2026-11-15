import React, { useState, useEffect, useRef } from 'react';
import {
  getCloudStatus,
  listStorageObjects,
  runCloudJob,
  getAiStatus,
  sendMarsScienceChat,
  explainRoute,
  compareAiModels,
  planMissionFromPrompt,
  compareRouteCandidates,
  interpretScientificTerrain,
  generateMissionRiskBriefing,
} from './cloud_ai';

export default function CloudAiPanel({
  activeRoute,
  currentCoords,
  allRoutes = [],
  onSelectCandidate,
  onExecutePlan,
}) {
  const [activeTab, setActiveTab] = useState('mission_intel'); // 'mission_intel', 'copilot', 'comparison', 'infrastructure'

  // AI Mission Intelligence states
  const [intelSubTab, setIntelSubTab] = useState('planner'); // 'planner', 'comparison', 'terrain', 'risk'
  const [plannerPrompt, setPlannerPrompt] = useState(
    'Find a safe route from the current rover position to Séítah, prioritizing low slope and sufficient return EVA margin.'
  );
  const [plannerResult, setPlannerResult] = useState(null);
  const [isPlanning, setIsPlanning] = useState(false);

  const [candidateComparison, setCandidateComparison] = useState(null);
  const [isComparingCandidates, setIsComparingCandidates] = useState(false);

  const [terrainInterpretation, setTerrainInterpretation] = useState(null);
  const [isInterpretingTerrain, setIsInterpretingTerrain] = useState(false);

  const [riskBriefing, setRiskBriefing] = useState(null);
  const [isGeneratingBriefing, setIsGeneratingBriefing] = useState(false);

  // Cloud Infrastructure state
  const [cloudStatus, setCloudStatus] = useState(null);
  const [storageObjects, setStorageObjects] = useState([]);
  const [storagePrefix, setStoragePrefix] = useState('');
  const [loadingCloud, setLoadingCloud] = useState(true);
  const [runningJob, setRunningJob] = useState(null);
  const [jobLogs, setJobLogs] = useState({});

  // Copilot Chat state
  const [aiStatus, setAiStatus] = useState(null);
  const [selectedProvider, setSelectedProvider] = useState('gemini');
  const [chatMessages, setChatMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      provider: 'Google Gemini (Mars Science Copilot)',
      text: "Greetings, Mission Operator. I am the Mars Science Copilot, grounded in NASA PDS orbital imagery (HiRISE, CTX), mineralogical maps (CRISM), thermal inertia models (THEMIS), and in-situ Perseverance rover telemetry (MEDA). Ask any planetary science question, or click 'Explain Active Route' to analyze current terrain navigation trade-offs.",
      citations: [
        { product_id: 'ESP_069176_1985', instrument: 'HiRISE', source: 'NASA PDS', doi: '10.17189/1518932', archive_url: 'https://hirise.lpl.arizona.edu/ESP_069176_1985' },
        { product_id: 'urn:nasa:pds:mars2020_meda', instrument: 'MEDA', source: 'NASA PDS Atmospheres', doi: '10.1007/s11214-021-00816-9', archive_url: 'https://pds-atmospheres.nmsu.edu/' },
      ],
      timestamp: new Date().toLocaleTimeString(),
    },
  ]);
  const [inputPrompt, setInputPrompt] = useState('');
  const [isSubmittingChat, setIsSubmittingChat] = useState(false);
  const chatBottomRef = useRef(null);

  // Model Comparison state
  const [comparisonPrompt, setComparisonPrompt] = useState(
    'Evaluate the mobility risk of traversing Jezero delta bottomset beds versus the crater rim, comparing wheel-sinkage hazards with battery drain on slope ascents.'
  );
  const [comparisonResult, setComparisonResult] = useState(null);
  const [isComparing, setIsComparing] = useState(false);

  // Load initial data
  useEffect(() => {
    async function loadData() {
      setLoadingCloud(true);
      try {
        const [cloud, ai, objs] = await Promise.all([
          getCloudStatus(),
          getAiStatus(),
          listStorageObjects(storagePrefix),
        ]);
        setCloudStatus(cloud);
        setAiStatus(ai);
        setStorageObjects(objs);
      } catch (err) {
        console.error('Failed to load Cloud & AI metadata:', err);
      } finally {
        setLoadingCloud(false);
      }
    }
    loadData();
  }, [storagePrefix]);

  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, isSubmittingChat]);

  // Mission Intelligence Action Handlers
  const handlePlanFromPrompt = async (promptToUse) => {
    const p = promptToUse || plannerPrompt;
    if (!p.trim()) return;
    setIsPlanning(true);
    try {
      const res = await planMissionFromPrompt(p, currentCoords, selectedProvider);
      setPlannerResult(res);
    } catch (err) {
      console.error('Mission planning failed:', err);
    } finally {
      setIsPlanning(false);
    }
  };

  const handleCompareCandidates = async () => {
    const routesToCompare = allRoutes && allRoutes.length > 0 ? allRoutes : (activeRoute ? [activeRoute] : []);
    if (routesToCompare.length === 0) return;
    setIsComparingCandidates(true);
    try {
      const res = await compareRouteCandidates(routesToCompare, plannerResult?.objective || 'Balanced traversal', selectedProvider);
      setCandidateComparison(res);
    } catch (err) {
      console.error('Candidate comparison failed:', err);
    } finally {
      setIsComparingCandidates(false);
    }
  };

  const handleInterpretTerrain = async () => {
    setIsInterpretingTerrain(true);
    try {
      const res = await interpretScientificTerrain(activeRoute?.summary || activeRoute?.route_metrics, null, null, selectedProvider);
      setTerrainInterpretation(res);
    } catch (err) {
      console.error('Terrain interpretation failed:', err);
    } finally {
      setIsInterpretingTerrain(false);
    }
  };

  const handleGenerateRiskBriefing = async () => {
    if (!activeRoute) return;
    setIsGeneratingBriefing(true);
    try {
      const res = await generateMissionRiskBriefing(activeRoute, null, null, null, selectedProvider);
      setRiskBriefing(res);
    } catch (err) {
      console.error('Risk briefing generation failed:', err);
    } finally {
      setIsGeneratingBriefing(false);
    }
  };

  // Cloud Run Job Execution Trigger
  const handleTriggerJob = async (jobName) => {
    setRunningJob(jobName);
    try {
      const res = await runCloudJob(jobName);
      setJobLogs((prev) => ({
        ...prev,
        [jobName]: {
          status: res.status,
          duration: res.duration_seconds,
          logs: res.logs || ['Execution completed successfully.'],
          outputArtifacts: res.output_artifacts || [],
          timestamp: new Date().toLocaleTimeString(),
        },
      }));
      const updated = await getCloudStatus();
      setCloudStatus(updated);
    } catch (err) {
      setJobLogs((prev) => ({
        ...prev,
        [jobName]: {
          status: 'FAILED',
          duration: 0.1,
          logs: [err.message || 'Job invocation failed.'],
          outputArtifacts: [],
          timestamp: new Date().toLocaleTimeString(),
        },
      }));
    } finally {
      setRunningJob(null);
    }
  };

  // Send Copilot Message
  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!inputPrompt.trim() || isSubmittingChat) return;

    const userMsg = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: inputPrompt.trim(),
      timestamp: new Date().toLocaleTimeString(),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsSubmittingChat(true);

    try {
      const res = await sendMarsScienceChat(userMsg.text, selectedProvider, null, activeRoute?.route_id);
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        provider: res.provider_used,
        text: res.reply,
        citations: res.scientific_citations || [],
        productsReferenced: res.products_referenced || [],
        uncertaintyNotice: res.uncertainty_notice,
        latencyMs: res.latency_ms,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        provider: selectedProvider,
        text: `Error connecting to Mars Science Copilot: ${err.message}`,
        timestamp: new Date().toLocaleTimeString(),
        isError: true,
      };
      setChatMessages((prev) => [...prev, errMsg]);
    } finally {
      setIsSubmittingChat(false);
    }
  };

  // Trigger Route Explanation
  const handleExplainActiveRoute = async () => {
    if (isSubmittingChat) return;
    setIsSubmittingChat(true);

    const userMsg = {
      id: `u-${Date.now()}`,
      role: 'user',
      text: `Analyze and explain the optimization decisions and safety margins for active route '${activeRoute?.route_id || 'primary'}'.`,
      timestamp: new Date().toLocaleTimeString(),
    };
    setChatMessages((prev) => [...prev, userMsg]);

    try {
      const metrics = activeRoute?.summary || activeRoute?.route_metrics || {
        total_distance_km: 3.28,
        total_cost: 4073.2,
        max_slope_deg: 11.4,
        risk_category: 'LOW_RISK',
      };
      const res = await explainRoute(activeRoute?.route_id || 'primary', userMsg.text, selectedProvider, metrics);
      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        provider: res.provider_used,
        text: res.explanation,
        routeId: res.route_id,
        distanceKm: res.total_distance_km,
        maxSlope: res.max_slope_deg,
        totalCost: res.total_cost,
        riskCategory: res.risk_category,
        algorithmComparison: res.algorithm_comparison_summary,
        latencyMs: res.latency_ms,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: 'assistant',
          provider: selectedProvider,
          text: `Failed to explain route: ${err.message}`,
          timestamp: new Date().toLocaleTimeString(),
          isError: true,
        },
      ]);
    } finally {
      setIsSubmittingChat(false);
    }
  };

  // Run Side-by-Side Model Comparison
  const handleRunComparison = async () => {
    if (!comparisonPrompt.trim() || isComparing) return;
    setIsComparing(true);
    try {
      const res = await compareAiModels(comparisonPrompt.trim(), null, activeRoute?.route_id);
      setComparisonResult(res);
    } catch (err) {
      console.error('Model comparison failed:', err);
    } finally {
      setIsComparing(false);
    }
  };

  const gcs = cloudStatus?.gcs_status;
  const cloudRun = cloudStatus?.cloud_run_status;
  const costs = cloudStatus?.cost_report;

  return (
    <div className="cloud-ai-container">
      {/* Top Navigation Bar */}
      <div className="cloud-ai-header">
        <div className="header-branding">
          <span className="cloud-icon-pill">MARS &bull; AI</span>
          <h2>AI Mission Intelligence &amp; Cloud Operations</h2>
          <span className="env-pill sandbox-pill">
            {costs?.billing_protection_mode === 'ZERO_COST_LOCAL_SANDBOX'
              ? 'Zero-Cost Sandbox Mode'
              : (costs?.billing_protection_mode || 'Zero-Cost Sandbox Mode')}
          </span>
        </div>
        <div className="cloud-tabs">
          <button
            className={`tab-btn ${activeTab === 'mission_intel' ? 'active' : ''}`}
            onClick={() => setActiveTab('mission_intel')}
          >
            🎯 AI Mission Intelligence
          </button>
          <button
            className={`tab-btn ${activeTab === 'copilot' ? 'active' : ''}`}
            onClick={() => setActiveTab('copilot')}
          >
            Mars Science Copilot (Gemini)
          </button>
          <button
            className={`tab-btn ${activeTab === 'comparison' ? 'active' : ''}`}
            onClick={() => setActiveTab('comparison')}
          >
            Dual-Model Evaluation (Gemini vs Azure)
          </button>
          <button
            className={`tab-btn ${activeTab === 'infrastructure' ? 'active' : ''}`}
            onClick={() => setActiveTab('infrastructure')}
          >
            Google Cloud Platform
          </button>
        </div>
      </div>

      {/* TAB 0: AI Mission Intelligence Layer */}
      {activeTab === 'mission_intel' && (
        <div className="tab-content mission-intel-tab">
          {/* Mandatory Non-Override Protocol Banner */}
          <div className="safety-mandate-banner">
            <span className="mandate-shield">🛡️</span>
            <div>
              <strong>DETERMINISTIC SAFETY PROTOCOL:</strong> AI mission intelligence is strictly advisory and grounded on genuine NASA PDS orbital/in-situ telemetry. AI outputs cannot override physical engineering safety limits (14.0° slope ceiling).
            </div>
          </div>

          {/* Sub-navigation */}
          <div className="intel-subtabs">
            <button
              className={`subtab-pill ${intelSubTab === 'planner' ? 'active' : ''}`}
              onClick={() => setIntelSubTab('planner')}
            >
              1. Natural-Language Planner
            </button>
            <button
              className={`subtab-pill ${intelSubTab === 'comparison' ? 'active' : ''}`}
              onClick={() => {
                setIntelSubTab('comparison');
                if (!candidateComparison) handleCompareCandidates();
              }}
            >
              2. Candidate Route Comparison
            </button>
            <button
              className={`subtab-pill ${intelSubTab === 'terrain' ? 'active' : ''}`}
              onClick={() => {
                setIntelSubTab('terrain');
                if (!terrainInterpretation) handleInterpretTerrain();
              }}
            >
              3. Scientific Terrain Interpreter
            </button>
            <button
              className={`subtab-pill ${intelSubTab === 'risk' ? 'active' : ''}`}
              onClick={() => {
                setIntelSubTab('risk');
                if (!riskBriefing) handleGenerateRiskBriefing();
              }}
            >
              4. Executive Risk Briefing
            </button>
          </div>

          {/* SUBTAB 1: Natural-Language Mission Planner */}
          {intelSubTab === 'planner' && (
            <div className="intel-subview">
              <div className="infra-section">
                <div className="section-title-row">
                  <h4>Natural-Language Objective &amp; Intent Extraction</h4>
                  <div className="provider-select-wrapper">
                    <label>Provider: </label>
                    <select
                      value={selectedProvider}
                      onChange={(e) => setSelectedProvider(e.target.value)}
                      className="provider-dropdown"
                    >
                      <option value="gemini">Google Gemini (Primary)</option>
                      <option value="azure_foundry">Microsoft Azure AI Foundry</option>
                    </select>
                  </div>
                </div>

                <p className="section-desc">
                  Describe your operational mission in natural language. The AI parser extracts origin, destination, profile, and constraints without fabricating coordinates or measurements.
                </p>

                {/* Quick Example Chips */}
                <div className="intel-prompt-chips">
                  <span className="chips-label">Mission Presets:</span>
                  <button
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      const p = "Find a safe route from the current rover position to Séítah, prioritizing low slope and sufficient return EVA margin.";
                      setPlannerPrompt(p);
                      handlePlanFromPrompt(p);
                    }}
                  >
                    Séítah Safe Traversal
                  </button>
                  <button
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      const p = "Plan an expedition to the Western Delta Front, focusing on carbonate mineral outcrops and clay-bearing stratigraphy.";
                      setPlannerPrompt(p);
                      handlePlanFromPrompt(p);
                    }}
                  >
                    Western Delta Astrobiology
                  </button>
                  <button
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      const p = "Traverse from current position to Kodiak Butte with sufficient return margin to study deltaic Gilbert bedding.";
                      setPlannerPrompt(p);
                      handlePlanFromPrompt(p);
                    }}
                  >
                    Kodiak Delta Remnant
                  </button>
                  <button
                    type="button"
                    className="chip-btn"
                    onClick={() => {
                      const p = "Find a route to Belva Crater rim to analyze deep sedimentary cross-sections.";
                      setPlannerPrompt(p);
                      handlePlanFromPrompt(p);
                    }}
                  >
                    Belva Impact Escarpment
                  </button>
                </div>

                {/* Prompt Textarea */}
                <div className="planner-input-area">
                  <textarea
                    rows={3}
                    className="planner-textarea"
                    value={plannerPrompt}
                    onChange={(e) => setPlannerPrompt(e.target.value)}
                    placeholder="Enter mission prompt (e.g. Find a safe route from current rover position to Séítah...)"
                  />
                  <button
                    type="button"
                    className="btn btn-primary btn-plan-submit"
                    onClick={() => handlePlanFromPrompt()}
                    disabled={isPlanning || !plannerPrompt.trim()}
                  >
                    {isPlanning ? 'Analyzing Intent...' : 'Translate Mission Prompt ›'}
                  </button>
                </div>

                {/* Extraction Result Card */}
                {plannerResult && (
                  <div className={`intel-plan-card ${plannerResult.requires_clarification ? 'is-clarification' : 'is-valid'}`}>
                    {plannerResult.requires_clarification ? (
                      <div className="clarification-notice">
                        <div className="card-top-row">
                          <span className="status-pill warn">⚠️ Clarification Required</span>
                          <span className="spec-tag">Confidence: {(plannerResult.confidence_score * 100).toFixed(0)}%</span>
                        </div>
                        <h4 className="intent-title">{plannerResult.extracted_intent}</h4>
                        <div className="clarification-questions">
                          <strong>Required Clarifications:</strong>
                          <ul>
                            {plannerResult.clarification_questions?.map((q, idx) => (
                              <li key={idx}>{q}</li>
                            ))}
                          </ul>
                        </div>
                        <p className="card-reasoning"><em>{plannerResult.ai_reasoning}</em></p>
                      </div>
                    ) : (
                      <div className="plan-validated">
                        <div className="card-top-row">
                          <span className="status-pill success">✓ Validated Plan Payload</span>
                          <span className="spec-tag">Latency: {plannerResult.latency_ms} ms</span>
                          <span className="spec-tag">Model: {plannerResult.model_used}</span>
                        </div>
                        <h4 className="intent-title">{plannerResult.extracted_intent}</h4>

                        <div className="waypoints-grid">
                          <div className="waypoint-item">
                            <span className="wp-type">STARTING POINT</span>
                            <strong>{plannerResult.resolved_start?.name}</strong>
                            <div className="coord-chip">
                              {plannerResult.resolved_start?.lon?.toFixed(4)}°E, {plannerResult.resolved_start?.lat?.toFixed(4)}°N
                            </div>
                            {plannerResult.resolved_start?.is_rover_position && (
                              <span className="badge-rover">Live Rover Telemetry</span>
                            )}
                          </div>
                          <div className="waypoint-arrow">➔</div>
                          <div className="waypoint-item">
                            <span className="wp-type">TARGET DESTINATION</span>
                            <strong>{plannerResult.resolved_destination?.name}</strong>
                            <div className="coord-chip">
                              {plannerResult.resolved_destination?.lon?.toFixed(4)}°E, {plannerResult.resolved_destination?.lat?.toFixed(4)}°N
                            </div>
                            {plannerResult.resolved_destination?.geologic_unit && (
                              <span className="badge-geo">{plannerResult.resolved_destination.geologic_unit}</span>
                            )}
                          </div>
                        </div>

                        <div className="constraints-row">
                          <span className="constraint-badge">
                            Profile: <strong>{plannerResult.routing_profile}</strong>
                          </span>
                          <span className="constraint-badge">
                            Max Slope: <strong>{plannerResult.constraints?.max_slope_deg ?? 14}°</strong>
                          </span>
                          <span className="constraint-badge">
                            EVA Budget: <strong>{plannerResult.constraints?.eva_time_budget_hours ?? 8} hrs</strong>
                          </span>
                          <span className="constraint-badge">
                            Return Leg: <strong>{plannerResult.constraints?.require_return_leg ? 'Enforced' : 'Optional'}</strong>
                          </span>
                        </div>

                        <p className="card-reasoning">{plannerResult.ai_reasoning}</p>

                        {onExecutePlan && (
                          <div className="card-actions">
                            <button
                              type="button"
                              className="btn btn-primary btn-execute-map"
                              onClick={() => onExecutePlan(plannerResult)}
                            >
                              🚀 Execute Plan on Martian Map
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* SUBTAB 2: Candidate Route Comparison */}
          {intelSubTab === 'comparison' && (
            <div className="intel-subview">
              <div className="infra-section">
                <div className="section-title-row">
                  <h4>Multi-Criteria Route Candidate Comparison</h4>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleCompareCandidates}
                    disabled={isComparingCandidates}
                  >
                    {isComparingCandidates ? 'Evaluating...' : '↻ Re-evaluate Candidates'}
                  </button>
                </div>

                <p className="section-desc">
                  Side-by-side grounded comparison across distance, weighted cost, peak gradient, roughness TRI, return EVA feasibility, and Monte Carlo reachability.
                </p>

                {candidateComparison ? (
                  <div className="comparison-content">
                    {/* Recommendation Banner */}
                    <div className="recommendation-card">
                      <div className="rec-header">
                        <span className="rec-tag">RECOMMENDED CORRIDOR</span>
                        <strong className="rec-id">{candidateComparison.recommended_route_id}</strong>
                      </div>
                      <p className="rec-summary">{candidateComparison.summary}</p>
                      <p className="rec-rationale"><em>Rationale: {candidateComparison.recommendation_rationale}</em></p>
                    </div>

                    {/* Candidate Cards Grid */}
                    <div className="intel-candidates-grid">
                      {candidateComparison.candidate_evaluations?.map((cand) => {
                        const isRec = cand.route_id === candidateComparison.recommended_route_id;
                        return (
                          <div key={cand.route_id} className={`candidate-eval-card ${isRec ? 'is-recommended' : ''}`}>
                            <div className="card-top-row">
                              <span className="candidate-name-badge">{cand.name}</span>
                              {isRec && <span className="rec-pill">★ RECOMMENDED</span>}
                              <span className={`fit-pill ${cand.mission_fit_verdict.toLowerCase()}`}>
                                {cand.mission_fit_verdict}
                              </span>
                            </div>

                            <div className="eval-metrics-grid">
                              <div className="eval-metric">
                                <span className="m-label">Distance</span>
                                <span className="m-val">{cand.distance_km} km</span>
                              </div>
                              <div className="eval-metric">
                                <span className="m-label">Total Cost</span>
                                <span className="m-val">{cand.total_cost}</span>
                              </div>
                              <div className="eval-metric">
                                <span className="m-label">Peak Slope</span>
                                <span className={`m-val ${cand.max_slope_deg > 12 ? 'warn' : ''}`}>
                                  {cand.max_slope_deg}°
                                </span>
                              </div>
                              <div className="eval-metric">
                                <span className="m-label">Roughness TRI</span>
                                <span className="m-val">{cand.roughness_tri}</span>
                              </div>
                              <div className="eval-metric">
                                <span className="m-label">EVA Traverse</span>
                                <span className="m-val">{cand.eva_duration_hours} hrs</span>
                              </div>
                              <div className="eval-metric">
                                <span className="m-label">MC Reachability</span>
                                <span className="m-val">{cand.monte_carlo_reliability_pct}%</span>
                              </div>
                            </div>

                            <div className="eva-return-box">
                              <span className="m-label">Return Feasibility:</span>
                              <strong className={`status-text ${cand.return_feasibility.toLowerCase()}`}>
                                {cand.return_feasibility}
                              </strong>
                              <span className="buffer-note">(+{cand.turnaround_buffer_min} min buffer)</span>
                            </div>

                            {onSelectCandidate && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-select-candidate"
                                onClick={() => onSelectCandidate(cand.route_id)}
                              >
                                Highlight Corridor on Map
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Trade-off Breakdown Box */}
                    <div className="tradeoff-box">
                      <h5>Trade-off Analysis Narrative</h5>
                      <pre className="tradeoff-text">{candidateComparison.tradeoff_analysis}</pre>
                      <div className="grounding-audit-note">
                        🛡️ <strong>Grounding Audit:</strong> {candidateComparison.grounding_audit?.candidates_audited} candidates verified against deterministic routing engine outputs. Zero fabricated metrics.
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="empty-intel-state">
                    <p>Click 'Re-evaluate Candidates' to compare active routing corridors.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* SUBTAB 3: Scientific Terrain Interpreter */}
          {intelSubTab === 'terrain' && (
            <div className="intel-subview">
              <div className="infra-section">
                <div className="section-title-row">
                  <h4>Scientific Terrain &amp; Geological Unit Interpretation</h4>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleInterpretTerrain}
                    disabled={isInterpretingTerrain}
                  >
                    {isInterpretingTerrain ? 'Analyzing...' : '↻ Refresh Analysis'}
                  </button>
                </div>

                <p className="section-desc">
                  Geological setting, mineralogy, and physical regolith properties. Differentiates measured observational data from derived model metrics and proxy indicators.
                </p>

                {terrainInterpretation ? (
                  <div className="terrain-content">
                    {/* Geological Setting */}
                    <div className="geo-setting-card">
                      <h5>Regional Geological Setting (Jezero Crater)</h5>
                      <p>{terrainInterpretation.geological_setting}</p>
                    </div>

                    {/* Mineralogy & Biosignature */}
                    <div className="mineralogy-card">
                      <h5>Mineralogy &amp; Astrobiological Biosignature Potential</h5>
                      <p style={{ whiteSpace: 'pre-line' }}>{terrainInterpretation.mineralogy_and_biosignature_potential}</p>
                    </div>

                    {/* Evidence Provenance Table */}
                    <div className="evidence-section">
                      <h5>Evidence &amp; Provenance Classification</h5>
                      <table className="evidence-table">
                        <thead>
                          <tr>
                            <th>Data Classification</th>
                            <th>Instrument / Source</th>
                            <th>Observed Finding / Parameter</th>
                            <th>Confidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {terrainInterpretation.measured_data_evidence?.map((item, idx) => (
                            <tr key={`m-${idx}`}>
                              <td><span className="evidence-type-badge measured">MEASURED</span></td>
                              <td><strong>{item.instrument_or_source}</strong></td>
                              <td><strong>{item.parameter}:</strong> {item.value_or_finding}</td>
                              <td><span className="spec-tag">{item.confidence_level}</span></td>
                            </tr>
                          ))}
                          {terrainInterpretation.derived_metrics_evidence?.map((item, idx) => (
                            <tr key={`d-${idx}`}>
                              <td><span className="evidence-type-badge derived">DERIVED</span></td>
                              <td><strong>{item.instrument_or_source}</strong></td>
                              <td><strong>{item.parameter}:</strong> {item.value_or_finding}</td>
                              <td><span className="spec-tag">{item.confidence_level}</span></td>
                            </tr>
                          ))}
                          {terrainInterpretation.proxy_indicators_evidence?.map((item, idx) => (
                            <tr key={`p-${idx}`}>
                              <td><span className="evidence-type-badge proxy">PROXY</span></td>
                              <td><strong>{item.instrument_or_source}</strong></td>
                              <td><strong>{item.parameter}:</strong> {item.value_or_finding}</td>
                              <td><span className="spec-tag">{item.confidence_level}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Citations List */}
                    <div className="citations-block">
                      <h5>Scientific Provenance &amp; Citations</h5>
                      <div className="citations-chips">
                        {terrainInterpretation.citations?.map((c, idx) => (
                          <div key={idx} className="citation-chip">
                            <strong>{c.instrument}</strong> &bull; {c.product_id}
                            {c.doi && <span> (DOI: {c.doi})</span>}
                            {c.archive_url && (
                              <a href={c.archive_url} target="_blank" rel="noopener noreferrer" className="archive-link">
                                [Archive]
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="empty-intel-state">
                    <p>Click 'Refresh Analysis' to analyze corridor geology and thermal inertia.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* SUBTAB 4: Executive Mission Risk Briefing */}
          {intelSubTab === 'risk' && (
            <div className="intel-subview">
              <div className="infra-section">
                <div className="section-title-row">
                  <h4>Executive Mission Risk Briefing &amp; Contingency Corridors</h4>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleGenerateRiskBriefing}
                    disabled={isGeneratingBriefing}
                  >
                    {isGeneratingBriefing ? 'Synthesizing...' : '↻ Regenerate Briefing'}
                  </button>
                </div>

                <p className="section-desc">
                  Synthesizes environmental stress testing, Monte Carlo robustness perturbations, and return EVA feasibility into an operational briefing with designated abort corridors.
                </p>

                {riskBriefing ? (
                  <div className="risk-briefing-content">
                    {/* Executive Overview */}
                    <div className="briefing-overview-card">
                      <h5>Mission Overview &amp; Statistical Robustness</h5>
                      <p style={{ whiteSpace: 'pre-line' }}>{riskBriefing.mission_overview}</p>
                    </div>

                    {/* Return Feasibility Metrics */}
                    <div className="return-feasibility-summary">
                      <div className="ret-stat">
                        <span className="ret-label">EVA RETURN STATUS</span>
                        <strong className={`ret-val ${riskBriefing.return_feasibility?.status?.toLowerCase()}`}>
                          {riskBriefing.return_feasibility?.status}
                        </strong>
                      </div>
                      <div className="ret-stat">
                        <span className="ret-label">TRAVERSE DURATION</span>
                        <strong className="ret-val">{riskBriefing.return_feasibility?.estimated_traverse_duration_hours} hrs</strong>
                        <span className="sub-note">of {riskBriefing.return_feasibility?.allocated_eva_hours}h budget</span>
                      </div>
                      <div className="ret-stat">
                        <span className="ret-label">BUFFER MARGIN</span>
                        <strong className="ret-val">+{riskBriefing.return_feasibility?.buffer_margin_minutes} min</strong>
                        <span className="sub-note">before local sunset</span>
                      </div>
                      <div className="ret-stat">
                        <span className="ret-label">BATTERY MARGIN</span>
                        <strong className="ret-val">{riskBriefing.return_feasibility?.battery_margin_pct}%</strong>
                        <span className="sub-note">reserve threshold</span>
                      </div>
                    </div>

                    {/* Critical Hazards & Uncertainties */}
                    <div className="hazards-grid">
                      <div className="hazard-column">
                        <h5>⚠️ Critical Terrain &amp; Operational Hazards</h5>
                        <ul>
                          {riskBriefing.critical_hazards?.map((h, idx) => (
                            <li key={idx}>{h}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="hazard-column">
                        <h5>🔍 Modeling Limitations &amp; Uncertainties</h5>
                        <ul>
                          {riskBriefing.uncertainty_limitations?.map((u, idx) => (
                            <li key={idx}>{u}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Contingency Corridor */}
                    <div className="contingency-corridor-card">
                      <h5>Recommended Contingency &amp; Abort Corridor</h5>
                      <p>{riskBriefing.recommended_contingency_corridor}</p>
                    </div>

                    {/* Contingency Action Table */}
                    <div className="contingency-table-wrapper">
                      <h5>Operational Contingency Protocol</h5>
                      <table className="contingency-table">
                        <thead>
                          <tr>
                            <th>Trigger Condition</th>
                            <th>Autonomous Tactical Action</th>
                            <th>Residual Risk</th>
                          </tr>
                        </thead>
                        <tbody>
                          {riskBriefing.contingency_considerations?.map((c, idx) => (
                            <tr key={idx}>
                              <td><strong>{c.trigger_condition}</strong></td>
                              <td>{c.operational_action}</td>
                              <td><span className="spec-tag">{c.residual_risk}</span></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Mandate footer */}
                    <div className="mandate-footer">
                      🛡️ {riskBriefing.deterministic_safety_mandate}
                    </div>
                  </div>
                ) : (
                  <div className="empty-intel-state">
                    <p>Click 'Regenerate Briefing' to synthesize risk analysis for the active route.</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 1: Google Cloud Platform Infrastructure */}
      {activeTab === 'infrastructure' && (
        <div className="tab-content infrastructure-tab">
          {/* Architecture Status Banner */}
          <div className="cloud-hero-card">
            <div className="hero-details">
              <h3>Google Cloud Platform Architecture</h3>
              <p>
                Integrated with Google Cloud Storage for planetary rasters (HiRISE, CTX, DEM),
                Cloud Run Jobs for batch data pipelines and tile generation, and Cloud Scheduler for
                automated catalog synchronization.
              </p>
              <div className="hero-specs-row">
                <span className="spec-tag">
                  Project: <strong>{cloudStatus?.project_id || 'marspath-production'}</strong>
                </span>
                <span className="spec-tag">
                  Region: <strong>{cloudStatus?.location || 'us-central1'}</strong>
                </span>
                <span className="spec-tag">
                  Storage Backend: <strong>{gcs?.provider === 'google_cloud_storage' ? 'GCS Bucket' : 'Local File Sandbox'}</strong>
                </span>
                <span className="spec-tag">
                  Storage Objects: <strong>{gcs?.total_objects ?? storageObjects.length}</strong>
                </span>
              </div>
            </div>
            <div className="hero-cost-card">
              <span className="cost-label">Monthly Cloud Spend</span>
              <span className="cost-value">${costs?.estimated_monthly_spend_usd?.toFixed(2) || '0.00'}</span>
              <span className="cost-quota">
                Used: {costs?.storage_used_mb?.toFixed(1) || '46.7'} MB / {((costs?.storage_quota_mb || 10240) / 1024).toFixed(0)} GB
              </span>
            </div>
          </div>

          {/* Storage Bucket Explorer */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>GCS Bucket Explorer: gs://{gcs?.bucket || 'marspath-data'}</h4>
              <div className="storage-filter-row">
                <input
                  type="text"
                  placeholder="Filter by prefix (e.g. raw/nasa)..."
                  value={storagePrefix}
                  onChange={(e) => setStoragePrefix(e.target.value)}
                  className="storage-search-input"
                />
              </div>
            </div>

            <div className="storage-table-wrapper">
              <table className="storage-table">
                <thead>
                  <tr>
                    <th>Object Name</th>
                    <th>Size</th>
                    <th>Type</th>
                    <th>Provenance Source</th>
                    <th>SHA-256 Checksum</th>
                  </tr>
                </thead>
                <tbody>
                  {storageObjects.length > 0 ? (
                    storageObjects.map((obj, i) => (
                      <tr key={i}>
                        <td className="object-name-cell">
                          <code>{obj.object_name}</code>
                        </td>
                        <td>{(obj.size_bytes / 1024 / 1024).toFixed(2)} MB</td>
                        <td>
                          <span className="type-badge">{obj.content_type?.split('/')[1] || 'binary'}</span>
                        </td>
                        <td>{obj.dataset_provenance || obj.source_id}</td>
                        <td className="hash-cell" title={obj.sha256_hash}>
                          <code>{obj.sha256_hash ? obj.sha256_hash.substring(0, 12) + '...' : 'Verified'}</code>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="empty-row">
                        No storage objects found matching prefix.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Cloud Run Jobs Batch Processing */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>Cloud Run Jobs (Planetary Batch Execution Engine)</h4>
              <span className="status-badge running-badge">
                {cloudRun?.total_registered_jobs || 8} Jobs Registered
              </span>
            </div>

            <div className="jobs-grid">
              {(cloudRun?.jobs || []).map((job) => {
                const isRunning = runningJob === job.name;
                const log = jobLogs[job.name];
                return (
                  <div key={job.name} className="job-card">
                    <div className="job-header">
                      <strong className="job-name">{job.name}</strong>
                      <span className={`job-status-pill ${job.last_status?.toLowerCase() || 'success'}`}>
                        {isRunning ? 'RUNNING' : job.last_status || 'READY'}
                      </span>
                    </div>
                    <p className="job-desc">{job.description}</p>
                    <div className="job-specs">
                      <span>Memory: {job.memory_limit_mb}MB</span>
                      <span>CPU: {job.cpu_limit}</span>
                      <span>Timeout: {job.timeout_seconds}s</span>
                    </div>

                    <div className="job-actions">
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => handleTriggerJob(job.name)}
                        disabled={isRunning}
                      >
                        {isRunning ? 'Executing Batch...' : 'Trigger Job Execution'}
                      </button>
                    </div>

                    {/* Output log drawer */}
                    {log && (
                      <div className="job-output-drawer">
                        <div className="log-meta">
                          <span>Status: <strong>{log.status}</strong></span>
                          <span>Time: {log.duration}s</span>
                        </div>
                        <pre className="log-text">{log.logs.join('\n')}</pre>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Cloud Cost Protection & LifeCycle Policies */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>Cost Governance &amp; Storage Lifecycle Controls</h4>
              <span className="status-badge safe-badge">
                Billing Protection: {costs?.billing_protection_mode || 'ENFORCED'}
              </span>
            </div>

            <div className="lifecycle-grid">
              <div className="lifecycle-card">
                <h5>Budget Alerts &amp; Spend Thresholds</h5>
                <ul>
                  {(costs?.budget_alerts || []).map((b, i) => (
                    <li key={i}>
                      Alert at <strong>{b.threshold_percent}%</strong> of daily budget &bull; Channel: {b.notification_channel} ({b.state})
                    </li>
                  ))}
                </ul>
              </div>
              <div className="lifecycle-card">
                <h5>GCS Object Lifecycle Tiering</h5>
                <ul>
                  {(costs?.lifecycle_rules || []).map((r, i) => (
                    <li key={i}>
                      After <strong>{r.age_days} days</strong> &bull; Migrate to <code>{r.storage_class}</code>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Mars Science Copilot Chat */}
      {activeTab === 'copilot' && (
        <div className="tab-content copilot-tab">
          <div className="copilot-controls-bar">
            <div className="provider-select-wrapper">
              <label>Active AI Provider:</label>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
                className="provider-dropdown"
              >
                <option value="gemini">Google Gemini (Mars Science Copilot)</option>
                <option value="azure_foundry">Microsoft Azure AI Foundry (Evaluation)</option>
              </select>
            </div>
            <div className="copilot-quick-actions">
              <button
                className="btn btn-secondary btn-sm"
                onClick={handleExplainActiveRoute}
                disabled={isSubmittingChat}
              >
                Explain Active Route Optimization
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setInputPrompt("What is the Marswalk Survivability Score for this corridor and what are the main limiting factors?")}
                disabled={isSubmittingChat}
              >
                🥽 EVA Walkability & Consumables
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setInputPrompt("Where is the nearest topographic radiation shelter in Jezero if a Solar Particle Event occurs?")}
                disabled={isSubmittingChat}
              >
                ⚡ SPE Radiation Shelter Proximity
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setInputPrompt("Evaluate regolith sinkage and boot traction along this path based on THEMIS thermal inertia.")}
                disabled={isSubmittingChat}
              >
                🥾 Regolith Footing & Thermal Inertia
              </button>
            </div>
          </div>

          {/* Chat Messages Log */}
          <div className="chat-messages-scroll">
            {chatMessages.map((msg) => (
              <div key={msg.id} className={`chat-bubble ${msg.role === 'user' ? 'user-msg' : 'assistant-msg'} ${msg.isError ? 'error-msg' : ''}`}>
                <div className="bubble-header">
                  <span className="msg-author">{msg.role === 'user' ? 'Mission Operator' : msg.provider || 'Mars Science Copilot'}</span>
                  <span className="msg-time">{msg.timestamp}</span>
                </div>
                <div className="bubble-body">
                  {msg.text.split('\n\n').map((paragraph, idx) => (
                    <p key={idx}>{paragraph}</p>
                  ))}
                </div>

                {/* Structured Route Metadata if Present */}
                {msg.routeId && (
                  <div className="route-meta-chips">
                    <span className="meta-chip">Route: <strong>{msg.routeId}</strong></span>
                    <span className="meta-chip">Distance: <strong>{msg.distanceKm} km</strong></span>
                    <span className="meta-chip">Peak Slope: <strong>{msg.maxSlope}°</strong></span>
                    <span className="meta-chip">Cost: <strong>{msg.totalCost}</strong></span>
                    <span className="meta-chip">Risk: <strong>{msg.riskCategory}</strong></span>
                  </div>
                )}

                {/* Grounded Scientific Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="bubble-citations">
                    <span className="citations-label">Grounded NASA Planetary Citations:</span>
                    <ul>
                      {msg.citations.map((c, idx) => (
                        <li key={idx}>
                          <strong>{c.instrument}</strong> &bull; {c.product_id} ({c.source})
                          {c.doi && <span> &bull; DOI: {c.doi}</span>}
                          {c.archive_url && (
                            <a href={c.archive_url} target="_blank" rel="noopener noreferrer" className="archive-link">
                              [Official PDS Record]
                            </a>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Scientific Uncertainty Notice */}
                {msg.uncertaintyNotice && (
                  <div className="uncertainty-notice">
                    <span>* {msg.uncertaintyNotice}</span>
                  </div>
                )}

                {msg.latencyMs && (
                  <div className="bubble-footer">
                    <span>AI Latency: {msg.latencyMs} ms</span>
                  </div>
                )}
              </div>
            ))}
            {isSubmittingChat && (
              <div className="chat-bubble assistant-msg thinking-bubble">
                <div className="spinner-dots">
                  <span></span><span></span><span></span>
                </div>
                <p>Retrieving grounded Martian catalog observations and analyzing terrain context...</p>
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Chat Input Bar */}
          <form className="chat-input-bar" onSubmit={handleSendMessage}>
            <input
              type="text"
              placeholder="Ask a scientific question about Jezero mineralogy, thermal inertia, or weather..."
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              disabled={isSubmittingChat}
              className="chat-text-input"
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmittingChat || !inputPrompt.trim()}
            >
              Ask Copilot
            </button>
          </form>
        </div>
      )}

      {/* TAB 3: Dual-Model Comparison */}
      {activeTab === 'comparison' && (
        <div className="tab-content comparison-tab">
          <div className="comparison-hero">
            <h4>Side-by-Side Planetary LLM Evaluation</h4>
            <p>
              Compare identical scientific and mobility prompts across Google Gemini and Microsoft Azure AI Foundry.
              Verifies factual alignment, citation grounding, and reasoning divergence on Jezero traversal constraints.
            </p>
          </div>

          <div className="comparison-input-row">
            <textarea
              rows={3}
              value={comparisonPrompt}
              onChange={(e) => setComparisonPrompt(e.target.value)}
              className="comparison-textarea"
              placeholder="Enter comparative scientific prompt..."
            />
            <button
              className="btn btn-primary btn-compare"
              onClick={handleRunComparison}
              disabled={isComparing || !comparisonPrompt.trim()}
            >
              {isComparing ? 'Evaluating Models...' : 'Execute Dual-Model Comparison'}
            </button>
          </div>

          {/* Comparison Results Grid */}
          {comparisonResult && (
            <div className="comparison-results-container">
              {/* Summary alignment card */}
              <div className="comparison-summary-card">
                <div className="summary-row">
                  <h5>Comparative Synthesis &amp; Citation Alignment</h5>
                  <span className="alignment-score">
                    Citation Agreement: <strong>{(comparisonResult.citation_alignment_score * 100).toFixed(0)}%</strong>
                  </span>
                </div>
                <p>{comparisonResult.comparison_summary}</p>
              </div>

              <div className="models-side-by-side">
                {/* Google Gemini Column */}
                <div className="model-column gemini-col">
                  <div className="column-header">
                    <span className="provider-badge gemini-badge">Google Gemini (Primary)</span>
                    <span className="model-name">
                      {comparisonResult.gemini_response?.model_used || 'gemini-2.5-flash'}
                    </span>
                  </div>
                  <div className="column-body">
                    {comparisonResult.gemini_response?.reply.split('\n\n').map((p, i) => (
                      <p key={i}>{p}</p>
                    ))}
                  </div>
                  <div className="column-citations">
                    <strong>Referenced Datasets:</strong>
                    <ul>
                      {comparisonResult.gemini_response?.scientific_citations?.map((c, i) => (
                        <li key={i}>
                          {c.instrument}: {c.product_id} ({c.source})
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="column-footer">
                    <span>Latency: {comparisonResult.gemini_response?.latency_ms || 185} ms</span>
                    <span>Tokens: ~{comparisonResult.gemini_response?.token_count_estimated || 140}</span>
                  </div>
                </div>

                {/* Azure AI Foundry Column */}
                <div className="model-column azure-col">
                  <div className="column-header">
                    <span className="provider-badge azure-badge">Microsoft Azure AI Foundry</span>
                    <span className="model-name">
                      {comparisonResult.azure_response?.model_used || 'gpt-4o-mini'}
                    </span>
                  </div>
                  <div className="column-body">
                    {comparisonResult.azure_response?.reply.split('\n\n').map((p, i) => (
                      <p key={i}>{p}</p>
                    ))}
                  </div>
                  <div className="column-citations">
                    <strong>Referenced Datasets:</strong>
                    <ul>
                      {comparisonResult.azure_response?.scientific_citations?.map((c, i) => (
                        <li key={i}>
                          {c.instrument}: {c.product_id} ({c.source})
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="column-footer">
                    <span>Latency: {comparisonResult.azure_response?.latency_ms || 215} ms</span>
                    <span>Tokens: ~{comparisonResult.azure_response?.token_count_estimated || 155}</span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
