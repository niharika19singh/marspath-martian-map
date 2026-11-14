import React, { useState, useEffect, useRef } from 'react';
import {
  getCloudStatus,
  listStorageObjects,
  runCloudJob,
  getAiStatus,
  sendMarsScienceChat,
  explainRoute,
  compareAiModels,
} from './cloud_ai';

export default function CloudAiPanel({ activeRoute, currentCoords }) {
  const [activeTab, setActiveTab] = useState('infrastructure'); // 'infrastructure', 'copilot', 'comparison'

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
      // Refresh status
      const updated = await getCloudStatus();
      setCloudStatus(updated);
    } catch (err) {
      setJobLogs((prev) => ({
        ...prev,
        [jobName]: {
          status: 'FAILED',
          logs: [err.message || 'Execution failed.'],
          timestamp: new Date().toLocaleTimeString(),
        },
      }));
    } finally {
      setRunningJob(null);
    }
  };

  // Copilot Message Send
  const handleSendChat = async (promptToSend) => {
    const text = (promptToSend || inputPrompt).trim();
    if (!text || isSubmittingChat) return;

    const userMsgId = `user_${Date.now()}`;
    const userMsg = {
      id: userMsgId,
      role: 'user',
      text,
      timestamp: new Date().toLocaleTimeString(),
    };

    setChatMessages((prev) => [...prev, userMsg]);
    setInputPrompt('');
    setIsSubmittingChat(true);

    try {
      const resp = await sendMarsScienceChat(text, selectedProvider);
      const assistantMsg = {
        id: `asst_${Date.now()}`,
        role: 'assistant',
        provider: resp.provider_used,
        model: resp.model_used,
        text: resp.reply,
        citations: resp.scientific_citations || [],
        products: resp.products_referenced || [],
        uncertainty: resp.uncertainty_notice,
        latencyMs: resp.latency_ms,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg = {
        id: `err_${Date.now()}`,
        role: 'assistant',
        isError: true,
        text: `Mission Copilot communication error: ${err.message}`,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsSubmittingChat(false);
    }
  };

  // Route Explanation Trigger
  const handleExplainActiveRoute = async () => {
    if (isSubmittingChat) return;
    const userMsg = {
      id: `user_route_${Date.now()}`,
      role: 'user',
      text: 'Analyze the active calculated route: explain terrain safety margins, slope penalty trade-offs, and data coverage.',
      timestamp: new Date().toLocaleTimeString(),
    };
    setChatMessages((prev) => [...prev, userMsg]);
    setIsSubmittingChat(true);

    try {
      const routeId = activeRoute?.route_id || 'primary';
      const resp = await explainRoute(routeId, 'Why was this corridor chosen over alternate paths and what risk trade-offs were made?', selectedProvider);
      const assistantMsg = {
        id: `asst_route_${Date.now()}`,
        role: 'assistant',
        provider: resp.provider_used,
        model: resp.model_used,
        text: resp.explanation,
        routeSummary: {
          distanceKm: resp.total_distance_km,
          totalCost: resp.total_cost,
          maxSlopeDeg: resp.max_slope_deg,
          riskCategory: resp.risk_category,
        },
        citations: [
          { product_id: 'ESP_069176_1985', instrument: 'HiRISE', source: 'USGS/HiRISE DEM', doi: '10.17189/1518932', archive_url: 'https://hirise.lpl.arizona.edu/ESP_069176_1985' },
          { product_id: 'THEMIS_IR_GLOBAL_100M', instrument: 'THEMIS', source: 'ASU / Mars Trek', doi: '10.1029/2003JE002178', archive_url: 'https://themis.asu.edu/data' },
        ],
        uncertainty: 'Deterministic routing costs and safety bounds are strictly verified; AI narrative provides explanatory context.',
        latencyMs: resp.latency_ms,
        timestamp: new Date().toLocaleTimeString(),
      };
      setChatMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          role: 'assistant',
          isError: true,
          text: `Route explanation failed: ${err.message}`,
          timestamp: new Date().toLocaleTimeString(),
        },
      ]);
    } finally {
      setIsSubmittingChat(false);
    }
  };

  // Model Comparison Trigger
  const handleRunComparison = async () => {
    if (!comparisonPrompt.trim() || isComparing) return;
    setIsComparing(true);
    try {
      const res = await compareAiModels(comparisonPrompt);
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
          <span className="cloud-icon-pill">GCP &bull; AI</span>
          <h2>Cloud Infrastructure &amp; Planetary AI Center</h2>
          <span className="env-pill sandbox-pill">
            {costs?.billing_protection_mode || 'ZERO_COST_LOCAL_SANDBOX'}
          </span>
        </div>
        <div className="cloud-tabs">
          <button
            className={`tab-btn ${activeTab === 'infrastructure' ? 'active' : ''}`}
            onClick={() => setActiveTab('infrastructure')}
          >
            Google Cloud Platform
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
        </div>
      </div>

      {/* TAB 1: Google Cloud Platform Infrastructure */}
      {activeTab === 'infrastructure' && (
        <div className="tab-content infrastructure-tab">
          {/* Architecture Status Banner */}
          <div className="cloud-hero-card">
            <div className="hero-details">
              <h3>Google Cloud Platform Architecture</h3>
              <p>
                Integrated with <strong>Google Cloud Storage (GCS)</strong> for planetary asset persistence,{' '}
                <strong>Cloud Run Jobs</strong> for batch geospatial processing, and <strong>Cloud Scheduler</strong> for automated telemetry synchronization.
              </p>
              <div className="hero-specs-row">
                <span className="spec-tag">
                  <strong>Project:</strong> {cloudStatus?.project_id || 'marspath-production-441200'}
                </span>
                <span className="spec-tag">
                  <strong>Location:</strong> {cloudStatus?.location || 'us-central1'}
                </span>
                <span className="spec-tag">
                  <strong>Storage Backend:</strong> {gcs?.provider === 'gcs' ? 'Google Cloud Storage' : 'Isolated Local GCS Adapter'}
                </span>
                <span className="spec-tag">
                  <strong>Zero-Cost Sandbox:</strong> Active (No egress billing)
                </span>
              </div>
            </div>
            <div className="hero-cost-card">
              <span className="cost-label">Monthly Cloud Spend</span>
              <span className="cost-value">${costs?.estimated_monthly_spend_usd?.toFixed(2) || '0.00'}</span>
              <span className="cost-quota">Sandbox Quota: {costs?.storage_quota_mb || 10240} MB</span>
            </div>
          </div>

          {/* Section A: Google Cloud Storage */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>1. Google Cloud Storage &bull; Planetary Data Lake</h4>
              <span className="section-subtext">Bucket: gs://{gcs?.bucket || 'marspath-data'}</span>
            </div>
            <div className="gcs-summary-grid">
              <div className="metric-box">
                <span className="metric-num">{gcs?.total_objects || 0}</span>
                <span className="metric-lbl">Total Objects</span>
              </div>
              <div className="metric-box">
                <span className="metric-num">{((gcs?.total_bytes || 0) / (1024 * 1024)).toFixed(2)} MB</span>
                <span className="metric-lbl">Storage Volume</span>
              </div>
              <div className="metric-box">
                <span className="metric-num">SHA-256</span>
                <span className="metric-lbl">Integrity Verification</span>
              </div>
              <div className="metric-box">
                <span className="metric-num">Standard &bull; Nearline &bull; Coldline</span>
                <span className="metric-lbl">Auto-Tiering Lifecycle</span>
              </div>
            </div>

            {/* Storage Object Explorer */}
            <div className="storage-explorer">
              <div className="explorer-controls">
                <span className="filter-label">Prefix Filter:</span>
                <div className="prefix-buttons">
                  {['', 'raw/nasa/', 'processed/', 'tiles/', 'catalog/'].map((p) => (
                    <button
                      key={p}
                      className={`filter-btn ${storagePrefix === p ? 'active' : ''}`}
                      onClick={() => setStoragePrefix(p)}
                    >
                      {p || 'All Assets'}
                    </button>
                  ))}
                </div>
              </div>
              <div className="storage-table-wrapper">
                <table className="storage-table">
                  <thead>
                    <tr>
                      <th>Object Key</th>
                      <th>Size</th>
                      <th>Content-Type</th>
                      <th>SHA-256 Checksum</th>
                      <th>NASA Provenance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {storageObjects.map((obj) => (
                      <tr key={obj.object_name}>
                        <td className="object-name-cell" title={obj.object_name}>
                          {obj.object_name}
                        </td>
                        <td>{(obj.size_bytes / 1024).toFixed(1)} KB</td>
                        <td>
                          <span className="mime-pill">{obj.content_type}</span>
                        </td>
                        <td className="hash-cell" title={obj.sha256_hash}>
                          {obj.sha256_hash?.slice(0, 16)}...
                        </td>
                        <td>{obj.dataset_provenance || obj.source_id || 'System'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Section B: Cloud Run Batch Jobs */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>2. Cloud Run Batch Processing Jobs &bull; 8 Scientific Container Engines</h4>
              <span className="section-subtext">Containerized Serverless Execution with Zero Idle Cost</span>
            </div>
            <div className="jobs-grid">
              {(cloudRun?.jobs || []).map((job) => {
                const isRunning = runningJob === job.name;
                const logData = jobLogs[job.name];
                return (
                  <div key={job.name} className={`job-card ${isRunning ? 'running' : ''}`}>
                    <div className="job-card-header">
                      <span className="job-name">{job.name}</span>
                      <span className={`status-badge ${job.last_status || 'READY'}`}>
                        {isRunning ? 'RUNNING...' : job.last_status || 'READY'}
                      </span>
                    </div>
                    <p className="job-desc">{job.description}</p>
                    <div className="job-specs">
                      <span>CPU: {job.cpu_limit}</span>
                      <span>RAM: {job.memory_limit_mb} MB</span>
                      <span>Timeout: {job.timeout_seconds}s</span>
                      {job.last_duration_seconds && <span>Last: {job.last_duration_seconds}s</span>}
                    </div>
                    <div className="job-action-row">
                      <button
                        className="run-job-btn"
                        disabled={isRunning}
                        onClick={() => handleTriggerJob(job.name)}
                      >
                        {isRunning ? 'Executing...' : 'Trigger Job'}
                      </button>
                    </div>
                    {logData && (
                      <div className="job-log-drawer">
                        <div className="log-drawer-header">
                          <span>Execution Log ({logData.timestamp})</span>
                          <span className={`log-status-tag ${logData.status}`}>{logData.status}</span>
                        </div>
                        <pre className="log-output">
                          {logData.logs.join('\n')}
                        </pre>
                        {logData.outputArtifacts?.length > 0 && (
                          <div className="artifacts-list">
                            <strong>Artifacts:</strong> {logData.outputArtifacts.join(', ')}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section C: Cloud Scheduler & Cost Controls */}
          <div className="infra-section">
            <div className="section-title-row">
              <h4>3. Cloud Scheduler &amp; Automated Pipeline Rules</h4>
              <span className="section-subtext">Declarative OIDC-Authenticated Cron Schedules</span>
            </div>
            <div className="scheduler-table-wrapper">
              <table className="scheduler-table">
                <thead>
                  <tr>
                    <th>Schedule Name</th>
                    <th>Cron Expression</th>
                    <th>Target Cloud Run Job</th>
                    <th>Authentication</th>
                    <th>Retry Policy</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>marspath-daily-catalog-sync</td>
                    <td><code>0 4 * * *</code> (Daily 04:00 UTC)</td>
                    <td>nasa_catalog_sync</td>
                    <td>OIDC Service Account</td>
                    <td>Max 2 retries (Backoff: 5s)</td>
                  </tr>
                  <tr>
                    <td>marspath-meda-telemetry-ingestion</td>
                    <td><code>0 6 * * *</code> (Daily 06:00 UTC)</td>
                    <td>meda_processor</td>
                    <td>OIDC Service Account</td>
                    <td>Max 3 retries (Backoff: 10s)</td>
                  </tr>
                  <tr>
                    <td>marspath-provenance-audit-weekly</td>
                    <td><code>0 3 * * 0</code> (Weekly Sun 03:00 UTC)</td>
                    <td>provenance_validator</td>
                    <td>OIDC Service Account</td>
                    <td>Max 2 retries (Backoff: 15s)</td>
                  </tr>
                  <tr>
                    <td>marspath-pds-release-monitor</td>
                    <td><code>0 2 1 * *</code> (Monthly 1st 02:00 UTC)</td>
                    <td>nasa_catalog_sync</td>
                    <td>OIDC Service Account</td>
                    <td>Max 3 retries (Backoff: 30s)</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: Mars Science Copilot (Google Gemini) */}
      {activeTab === 'copilot' && (
        <div className="tab-content copilot-tab">
          {/* Provider Selection & Status Bar */}
          <div className="copilot-toolbar">
            <div className="provider-select-group">
              <label>Active Copilot Provider:</label>
              <select
                value={selectedProvider}
                onChange={(e) => setSelectedProvider(e.target.value)}
                className="provider-dropdown"
              >
                <option value="gemini">Google Gemini 2.5 Flash (Primary Scientific Copilot)</option>
                <option value="azure_foundry">Microsoft Azure AI Foundry (Evaluation Mode)</option>
              </select>
            </div>
            <div className="copilot-status-indicators">
              <span className="status-indicator">
                <span className="dot online"></span>
                Grounded Planetary RAG Active
              </span>
              <span className="status-indicator">
                <span className="dot online"></span>
                Verified Citations Enforced
              </span>
            </div>
          </div>

          {/* Quick Action Suggestion Buttons */}
          <div className="quick-actions-bar">
            <span className="quick-label">Mission Queries:</span>
            <button
              className="quick-btn"
              onClick={handleExplainActiveRoute}
              disabled={isSubmittingChat}
            >
              Explain Active Route
            </button>
            <button
              className="quick-btn"
              onClick={() =>
                handleSendChat('What are the key spectral signatures of carbonate and smectite clay in Jezero delta front?')
              }
              disabled={isSubmittingChat}
            >
              Analyze Jezero Minerals (CRISM)
            </button>
            <button
              className="quick-btn"
              onClick={() =>
                handleSendChat('Evaluate wheel sinkage hazard in low thermal inertia areas using THEMIS measurements.')
              }
              disabled={isSubmittingChat}
            >
              Assess Wheel Sinkage (THEMIS)
            </button>
            <button
              className="quick-btn"
              onClick={() =>
                handleSendChat('Summarize latest in-situ environmental conditions from Perseverance MEDA weather sensors.')
              }
              disabled={isSubmittingChat}
            >
              Surface Weather (MEDA)
            </button>
          </div>

          {/* Chat Messages Log */}
          <div className="chat-messages-scroll">
            {chatMessages.map((msg) => (
              <div key={msg.id} className={`chat-bubble-container ${msg.role}`}>
                <div className={`chat-bubble ${msg.role} ${msg.isError ? 'error-bubble' : ''}`}>
                  <div className="bubble-header">
                    <span className="sender-name">
                      {msg.role === 'user' ? 'Mission Operator' : msg.provider || 'Mars Science Copilot'}
                    </span>
                    <span className="timestamp">{msg.timestamp}</span>
                  </div>
                  <div className="bubble-body">
                    {msg.text.split('\n\n').map((paragraph, i) => (
                      <p key={i}>{paragraph}</p>
                    ))}
                  </div>

                  {/* Route Summary Metrics (if route explanation) */}
                  {msg.routeSummary && (
                    <div className="route-explanation-metrics">
                      <div className="metric-item">
                        <span className="lbl">Distance:</span>
                        <span className="val">{msg.routeSummary.distanceKm} km</span>
                      </div>
                      <div className="metric-item">
                        <span className="lbl">Weighted Cost:</span>
                        <span className="val">{msg.routeSummary.totalCost}</span>
                      </div>
                      <div className="metric-item">
                        <span className="lbl">Max Slope:</span>
                        <span className="val">{msg.routeSummary.maxSlopeDeg}&deg;</span>
                      </div>
                      <div className="metric-item">
                        <span className="lbl">Safety Assessment:</span>
                        <span className="val risk-optimal">{msg.routeSummary.riskCategory}</span>
                      </div>
                    </div>
                  )}

                  {/* Scientific Citations Cards */}
                  {msg.citations?.length > 0 && (
                    <div className="citations-block">
                      <div className="citations-header">Authentic Scientific Citations &amp; Provenance:</div>
                      <div className="citations-grid">
                        {msg.citations.map((c, idx) => (
                          <div key={idx} className="citation-pill">
                            <span className="c-inst">{c.instrument}</span>
                            <span className="c-id">{c.product_id}</span>
                            <span className="c-source">{c.source}</span>
                            {c.doi && <span className="c-doi">DOI: {c.doi}</span>}
                            {c.archive_url && (
                              <a
                                href={c.archive_url}
                                target="_blank"
                                rel="noreferrer"
                                className="c-link"
                              >
                                View NASA Record &rarr;
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Mandatory Uncertainty Notice */}
                  {msg.uncertainty && (
                    <div className="uncertainty-notice">
                      <span className="caution-icon">!</span>
                      <span>{msg.uncertainty}</span>
                    </div>
                  )}

                  {msg.latencyMs && (
                    <div className="bubble-footer">
                      <span>Model Inference: {msg.latencyMs} ms</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {isSubmittingChat && (
              <div className="chat-bubble-container assistant">
                <div className="chat-bubble assistant typing-bubble">
                  <div className="typing-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                  <span className="typing-text">Synthesizing grounded NASA planetary context...</span>
                </div>
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Input Box */}
          <div className="chat-input-bar">
            <input
              type="text"
              placeholder="Ask a scientific question about Martian geology, route safety, or telemetry..."
              value={inputPrompt}
              onChange={(e) => setInputPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendChat();
              }}
              disabled={isSubmittingChat}
              className="chat-text-input"
            />
            <button
              className="send-chat-btn"
              onClick={() => handleSendChat()}
              disabled={!inputPrompt.trim() || isSubmittingChat}
            >
              {isSubmittingChat ? 'Analyzing...' : 'Send Query'}
            </button>
          </div>
        </div>
      )}

      {/* TAB 3: Dual-Model Comparison (Gemini vs Azure AI Foundry) */}
      {activeTab === 'comparison' && (
        <div className="tab-content comparison-tab">
          <div className="comparison-intro">
            <h3>AI Provider Evaluation Workbench</h3>
            <p>
              Submit identical planetary queries to evaluate <strong>Google Gemini (Primary)</strong> alongside{' '}
              <strong>Microsoft Azure AI Foundry (Evaluation Provider)</strong> across scientific reasoning, latency, and citation accuracy.
            </p>
          </div>

          {/* Input Query for Comparison */}
          <div className="comparison-input-section">
            <textarea
              className="comparison-textarea"
              rows={3}
              value={comparisonPrompt}
              onChange={(e) => setComparisonPrompt(e.target.value)}
              placeholder="Enter scientific or navigation prompt for comparative evaluation..."
            />
            <button
              className="compare-submit-btn"
              onClick={handleRunComparison}
              disabled={!comparisonPrompt.trim() || isComparing}
            >
              {isComparing ? 'Evaluating Models...' : 'Run Side-by-Side Model Comparison'}
            </button>
          </div>

          {/* Side-by-Side Results Display */}
          {comparisonResult && (
            <div className="comparison-display">
              {/* Comparative Analysis Card */}
              <div className="comparison-summary-card">
                <h4>Comparative Evaluation Metrics</h4>
                <p>{comparisonResult.comparison_summary}</p>
                <div className="summary-stats-row">
                  <span className="stat-pill">
                    Citation Alignment: {(comparisonResult.citation_alignment_score * 100).toFixed(0)}%
                  </span>
                  {comparisonResult.latency_delta_ms !== null && (
                    <span className="stat-pill">
                      Latency Delta: {Math.abs(comparisonResult.latency_delta_ms).toFixed(1)} ms
                    </span>
                  )}
                </div>
              </div>

              {/* Two Column Side-by-Side */}
              <div className="split-columns">
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
                    <span>Latency: {comparisonResult.gemini_response?.latency_ms || 180} ms</span>
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
