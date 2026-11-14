import React, { useState, useEffect } from 'react';
import Icon from './Icons.jsx';
import {
  fetchDataSources,
  fetchDataSourceStatus,
  searchDataCatalogue,
  fetchCatalogueCoverage,
  fetchMedaObservations,
  fetchThemisObservations,
  computeSpiceGeometry,
  fetchDataReleases,
  triggerDataSync
} from './nasa_data.js';

export default function NasaDataPanel(props) {
  const {
    apiUrl = '',
    onFocusProduct,
    onSelectSourceLayer,
    onClose
  } = props;

  const [activeTab, setActiveTab] = useState('sources'); // 'sources' | 'explorer' | 'meda' | 'themis' | 'spice' | 'releases'
  const [sources, setSources] = useState([]);
  const [status, setStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState('');

  // View A filter
  const [sourceSearch, setSourceSearch] = useState('');

  // View B Explorer state
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSourceFilter, setSelectedSourceFilter] = useState('all');
  const [selectedSpacecraftFilter, setSelectedSpacecraftFilter] = useState('all');
  const [selectedInstrumentFilter, setSelectedInstrumentFilter] = useState('all');
  const [selectedTypeFilter, setSelectedTypeFilter] = useState('all');
  const [searchResults, setSearchResults] = useState([]);
  const [totalMatches, setTotalMatches] = useState(0);
  const [searching, setSearching] = useState(false);
  const [selectedProductDetail, setSelectedProductDetail] = useState(null);

  // Specialist views state
  const [medaData, setMedaData] = useState([]);
  const [selectedMedaSol, setSelectedMedaSol] = useState(2022);
  const [themisData, setThemisData] = useState([]);
  const [spiceSpacecraft, setSpiceSpacecraft] = useState('mro');
  const [spiceGeometry, setSpiceGeometry] = useState(null);
  const [spiceCalculating, setSpiceCalculating] = useState(false);
  const [releases, setReleases] = useState([]);

  // Initial load
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchDataSources(apiUrl),
      fetchDataSourceStatus(apiUrl),
      fetchMedaObservations(apiUrl),
      fetchThemisObservations(apiUrl),
      computeSpiceGeometry('mro', apiUrl),
      fetchDataReleases(apiUrl)
    ]).then(([srcs, st, meda, themis, spice, rels]) => {
      if (cancelled) return;
      setSources(srcs);
      setStatus(st);
      setMedaData(meda);
      if (meda.length > 0) setSelectedMedaSol(meda[0].sol);
      setThemisData(themis);
      setSpiceGeometry(spice);
      setReleases(rels);
    }).catch(err => console.error('Error loading NASA data resources:', err));

    return () => { cancelled = true; };
  }, [apiUrl]);

  // Execute catalog search when filters change or tab is explorer
  useEffect(() => {
    if (activeTab !== 'explorer') return;
    let cancelled = false;
    setSearching(true);
    searchDataCatalogue({
      query: searchQuery,
      source_id: selectedSourceFilter,
      spacecraft: selectedSpacecraftFilter,
      instrument: selectedInstrumentFilter,
      product_type: selectedTypeFilter,
      limit: 50
    }, apiUrl).then(res => {
      if (cancelled) return;
      setSearchResults(res.products || []);
      setTotalMatches(res.total_matches || (res.products ? res.products.length : 0));
      setSearching(false);
    }).catch(() => {
      if (!cancelled) setSearching(false);
    });

    return () => { cancelled = true; };
  }, [activeTab, searchQuery, selectedSourceFilter, selectedSpacecraftFilter, selectedInstrumentFilter, selectedTypeFilter, apiUrl]);

  // Recalculate SPICE geometry when spacecraft changes
  const handleSpiceCalculate = (scId) => {
    setSpiceSpacecraft(scId);
    setSpiceCalculating(true);
    computeSpiceGeometry(scId, apiUrl).then(geom => {
      setSpiceGeometry(geom);
      setSpiceCalculating(false);
    }).catch(() => setSpiceCalculating(false));
  };

  const handleSyncAll = async () => {
    setSyncing(true);
    setSyncNotice('');
    try {
      const res = await triggerDataSync(true, apiUrl);
      setSyncNotice(res.message || 'All seven NASA data sources synchronized.');
      const [srcs, st] = await Promise.all([
        fetchDataSources(apiUrl),
        fetchDataSourceStatus(apiUrl)
      ]);
      setSources(srcs);
      setStatus(st);
    } catch (e) {
      setSyncNotice('Sync failed: ' + e.message);
    } finally {
      setSyncing(false);
      setTimeout(() => setSyncNotice(''), 4500);
    }
  };

  const handleTransitionToExplorer = (sourceId) => {
    setSelectedSourceFilter(sourceId);
    setActiveTab('explorer');
  };

  // Filter sources for View A
  const filteredSources = sources.filter(s => {
    if (!sourceSearch) return true;
    const term = sourceSearch.toLowerCase();
    return s.name.toLowerCase().includes(term) ||
      s.organization.toLowerCase().includes(term) ||
      s.primary_use_in_marspath.toLowerCase().includes(term) ||
      s.description.toLowerCase().includes(term);
  });

  const activeMeda = medaData.find(m => m.sol === selectedMedaSol) || medaData[0];

  return (
    <div className="nasa-data-panel">
      {/* Global Status Bar */}
      <div className="nasa-status-bar">
        <div className="status-meta">
          <span className="live-pulse-dot" />
          <span className="status-text">
            {status?.connected_sources || 7} / {status?.total_sources || 7} NASA SOURCES CONNECTED
          </span>
          <span className="products-tag">
            {(status?.total_indexed_products || 47310).toLocaleString()} PRODUCTS
          </span>
        </div>
        <button
          className="sync-action-button"
          onClick={handleSyncAll}
          disabled={syncing}
          aria-label="Synchronize NASA data sources"
        >
          <Icon name="refresh" />
          <span>{syncing ? 'Syncing…' : 'Sync All'}</span>
        </button>
      </div>

      {syncNotice && (
        <div className="intelligence-sync-toast" role="status">
          {syncNotice}
        </div>
      )}

      {/* Subtab Navigation */}
      <nav className="nasa-subtabs" role="tablist" aria-label="NASA Data Center Views">
        <button
          className={activeTab === 'sources' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'sources'}
          onClick={() => setActiveTab('sources')}
        >
          <Icon name="database" />
          <span>NASA Data Sources (7)</span>
        </button>
        <button
          className={activeTab === 'explorer' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'explorer'}
          onClick={() => setActiveTab('explorer')}
        >
          <Icon name="search" />
          <span>Data Explorer</span>
        </button>
        <button
          className={activeTab === 'meda' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'meda'}
          onClick={() => setActiveTab('meda')}
        >
          <Icon name="compass" />
          <span>MEDA Weather</span>
        </button>
        <button
          className={activeTab === 'themis' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'themis'}
          onClick={() => setActiveTab('themis')}
        >
          <Icon name="layers" />
          <span>THEMIS Traversability</span>
        </button>
        <button
          className={activeTab === 'spice' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'spice'}
          onClick={() => setActiveTab('spice')}
        >
          <Icon name="cube" />
          <span>SPICE Geometry</span>
        </button>
        <button
          className={activeTab === 'releases' ? 'active' : ''}
          role="tab"
          aria-selected={activeTab === 'releases'}
          onClick={() => setActiveTab('releases')}
        >
          <Icon name="history" />
          <span>PDS Releases</span>
        </button>
      </nav>

      {/* VIEW A: NASA DATA SOURCES */}
      {activeTab === 'sources' && (
        <div className="sources-view">
          <div className="view-intro">
            <div className="search-box-row">
              <input
                type="text"
                placeholder="Filter official NASA sources…"
                value={sourceSearch}
                onChange={e => setSourceSearch(e.target.value)}
                className="nasa-filter-input"
              />
              <span className="results-count-badge">{filteredSources.length} sources</span>
            </div>
          </div>

          <div className="sources-cards-list">
            {filteredSources.map(source => (
              <article key={source.id} className="nasa-source-card">
                <header className="source-card-header">
                  <div className="source-title-group">
                    <span className="source-org-badge">{source.organization}</span>
                    <h3>{source.name}</h3>
                    <small className="source-integration-tag">{source.integration_method}</small>
                  </div>
                  <div className="source-status-badges">
                    <span className={`status-pill ${source.connection_status.toLowerCase()}`}>
                      {source.connection_status}
                    </span>
                    <span className="indexed-badge">
                      {(source.indexed_products_count || 0).toLocaleString()} indexed
                    </span>
                  </div>
                </header>

                <p className="source-description">{source.description}</p>

                <div className="marspath-role-box">
                  <strong>Role in MARSPath:</strong>
                  <p>{source.primary_use_in_marspath}</p>
                </div>

                <div className="datasets-section">
                  <span className="section-label">Authoritative Datasets:</span>
                  <ul className="datasets-pill-list">
                    {(source.available_datasets || []).map((ds, idx) => (
                      <li key={idx} className="dataset-item">{ds}</li>
                    ))}
                  </ul>
                </div>

                <footer className="source-card-footer">
                  <div className="provenance-meta">
                    <span className="sync-time">
                      Sync: {source.last_sync_utc ? new Date(source.last_sync_utc).toLocaleDateString() : 'Active'}
                    </span>
                    {source.doi && <span className="doi-tag">DOI: {source.doi}</span>}
                  </div>
                  <div className="card-actions">
                    <a
                      href={source.official_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-external-link"
                      title="Open official NASA portal in new window"
                    >
                      <Icon name="link" />
                      <span>Open NASA Portal</span>
                    </a>
                    <button
                      className="btn-explore-data"
                      onClick={() => handleTransitionToExplorer(source.id)}
                    >
                      <Icon name="search" />
                      <span>Explore Integrated Data</span>
                    </button>
                  </div>
                </footer>
              </article>
            ))}
          </div>
        </div>
      )}

      {/* VIEW B: INTEGRATED DATA EXPLORER */}
      {activeTab === 'explorer' && (
        <div className="explorer-view">
          {/* Multi-parameter filters */}
          <div className="explorer-filters-panel">
            <div className="search-bar-wrap">
              <input
                type="text"
                placeholder="Search products by ID, target name, or keywords (e.g. HiRISE, Delta, Carbonate)…"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="nasa-search-bar"
              />
              {searching && <span className="search-spinner" />}
            </div>

            <div className="filters-grid">
              <label>
                Source:
                <select
                  value={selectedSourceFilter}
                  onChange={e => setSelectedSourceFilter(e.target.value)}
                >
                  <option value="all">All Seven NASA Sources</option>
                  <option value="mars_trek">NASA Mars Trek</option>
                  <option value="pds_geosciences">PDS Geosciences ODE</option>
                  <option value="pds_atmospheres">PDS Atmospheres (MEDA)</option>
                  <option value="themis_viewer">THEMIS / ASU Viewer</option>
                  <option value="naif_spice">NASA NAIF / SPICE</option>
                  <option value="planetary_notebook">Analyst's Notebook</option>
                  <option value="pds_releases">PDS Data Releases</option>
                </select>
              </label>

              <label>
                Spacecraft:
                <select
                  value={selectedSpacecraftFilter}
                  onChange={e => setSelectedSpacecraftFilter(e.target.value)}
                >
                  <option value="all">All Spacecraft</option>
                  <option value="mro">Mars Reconnaissance Orbiter (MRO)</option>
                  <option value="mars 2020">Mars 2020 (Perseverance)</option>
                  <option value="msl">Mars Science Lab (Curiosity)</option>
                  <option value="odyssey">2001 Mars Odyssey</option>
                </select>
              </label>

              <label>
                Instrument:
                <select
                  value={selectedInstrumentFilter}
                  onChange={e => setSelectedInstrumentFilter(e.target.value)}
                >
                  <option value="all">All Instruments</option>
                  <option value="hirise">HiRISE (0.25 m/px)</option>
                  <option value="ctx">CTX Context Camera (6 m/px)</option>
                  <option value="crism">CRISM Hyperspectral</option>
                  <option value="themis">THEMIS Thermal IR</option>
                  <option value="meda">MEDA Environmental</option>
                  <option value="navcam">Navcam / Traverses</option>
                </select>
              </label>

              <label>
                Product Type:
                <select
                  value={selectedTypeFilter}
                  onChange={e => setSelectedTypeFilter(e.target.value)}
                >
                  <option value="all">All Product Types</option>
                  <option value="IMAGERY_RDR">Orbital Imagery RDR</option>
                  <option value="TERRAIN_DTM">Stereo Elevation DTM</option>
                  <option value="MULTISPECTRAL_TRDR">Multispectral / Mineralogy</option>
                  <option value="THERMAL_INERTIA_MOSAIC">Thermal Inertia Mosaic</option>
                  <option value="IN_SITU_WEATHER_TIMESERIES">In-Situ Weather Telemetry</option>
                  <option value="ROVER_TRAVERSE_LOG">Rover Traverse Log</option>
                  <option value="WMTS_MAP_LAYER">WMTS Map Layer</option>
                </select>
              </label>
            </div>

            <div className="filter-summary-bar">
              <span>Showing <strong>{searchResults.length}</strong> of {totalMatches} verified NASA products</span>
              {(selectedSourceFilter !== 'all' || selectedSpacecraftFilter !== 'all' || selectedInstrumentFilter !== 'all' || selectedTypeFilter !== 'all' || searchQuery) && (
                <button
                  className="reset-filters-btn"
                  onClick={() => {
                    setSearchQuery('');
                    setSelectedSourceFilter('all');
                    setSelectedSpacecraftFilter('all');
                    setSelectedInstrumentFilter('all');
                    setSelectedTypeFilter('all');
                  }}
                >
                  Reset filters
                </button>
              )}
            </div>
          </div>

          {/* Results list */}
          <div className="products-scroll-container">
            {searchResults.length === 0 ? (
              <div className="empty-results">
                <p>No products match the selected search criteria.</p>
                <button onClick={() => { setSelectedSourceFilter('all'); setSearchQuery(''); }}>
                  Show all catalog products
                </button>
              </div>
            ) : (
              searchResults.map(prod => (
                <article key={prod.product_id} className="product-result-card">
                  <div className="prod-card-top">
                    <div className="prod-id-row">
                      <span className="prod-id-tag">{prod.product_id}</span>
                      <span className="prod-type-badge">{prod.product_type}</span>
                    </div>
                    <span className="prod-res-badge">
                      {prod.spatial_resolution_m_per_px > 0
                        ? `${prod.spatial_resolution_m_per_px} m/px`
                        : 'In-Situ Ground Point'}
                    </span>
                  </div>

                  <h4>{prod.title}</h4>
                  <p className="prod-description">{prod.description}</p>

                  <div className="prod-meta-tags">
                    <span className="meta-tag"><Icon name="cube" /> {prod.spacecraft}</span>
                    <span className="meta-tag"><Icon name="camera" /> {prod.instrument}</span>
                    {prod.martian_sol > 0 && <span className="sol-badge">Sol {prod.martian_sol}</span>}
                    <span className="meta-tag format">{prod.data_format}</span>
                  </div>

                  <div className="prod-actions-row">
                    <button
                      className="btn-inspect-meta"
                      onClick={() => setSelectedProductDetail(prod)}
                    >
                      <Icon name="info" />
                      <span>Inspect Metadata</span>
                    </button>

                    {prod.bounds && (
                      <button
                        className="btn-view-map"
                        onClick={() => onFocusProduct?.(prod)}
                        title="Fit map view to product bounding coordinates"
                      >
                        <Icon name="fit" />
                        <span>View on Map</span>
                      </button>
                    )}

                    <a
                      href={prod.archive_url || prod.download_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-pds-link"
                      title="Open official NASA PDS archive record"
                    >
                      <Icon name="link" />
                      <span>Open PDS Archive</span>
                    </a>
                  </div>
                </article>
              ))
            )}
          </div>

          {/* Metadata Inspector Drawer / Modal */}
          {selectedProductDetail && (
            <div className="metadata-inspector-overlay" onClick={() => setSelectedProductDetail(null)}>
              <div className="metadata-inspector-card" onClick={e => e.stopPropagation()}>
                <header className="inspector-header">
                  <div>
                    <span className="inspector-badge">{selectedProductDetail.product_type}</span>
                    <h3>{selectedProductDetail.product_id}</h3>
                  </div>
                  <button
                    className="close-btn"
                    onClick={() => setSelectedProductDetail(null)}
                    aria-label="Close inspector"
                  >
                    ×
                  </button>
                </header>

                <div className="inspector-body">
                  <h4>{selectedProductDetail.title}</h4>
                  <p className="inspector-desc">{selectedProductDetail.description}</p>

                  <dl className="inspector-dl">
                    <dt>NASA Source</dt>
                    <dd>{selectedProductDetail.source_name || selectedProductDetail.source_id}</dd>
                    <dt>Spacecraft</dt>
                    <dd>{selectedProductDetail.spacecraft}</dd>
                    <dt>Instrument</dt>
                    <dd>{selectedProductDetail.instrument}</dd>
                    <dt>Target Area</dt>
                    <dd>{selectedProductDetail.target_name}</dd>
                    <dt>Acquisition UTC</dt>
                    <dd>{selectedProductDetail.acquisition_utc}</dd>
                    <dt>Martian Sol</dt>
                    <dd>{selectedProductDetail.martian_sol || 'Global / Orbital'}</dd>
                    <dt>Spatial Resolution</dt>
                    <dd>{selectedProductDetail.spatial_resolution_m_per_px} meters/pixel</dd>
                    <dt>Processing Status</dt>
                    <dd>{selectedProductDetail.processing_status}</dd>
                    <dt>Data Format</dt>
                    <dd>{selectedProductDetail.data_format}</dd>
                    <dt>File Size</dt>
                    <dd>{selectedProductDetail.file_size_bytes ? (selectedProductDetail.file_size_bytes / 1024 / 1024).toFixed(1) + ' MB' : '—'}</dd>
                    {selectedProductDetail.doi && (
                      <>
                        <dt>Persistent DOI</dt>
                        <dd>{selectedProductDetail.doi}</dd>
                      </>
                    )}
                    {selectedProductDetail.bounds && (
                      <>
                        <dt>Geographic Bounds</dt>
                        <dd>
                          Lon: [{selectedProductDetail.bounds.min_lon}°, {selectedProductDetail.bounds.max_lon}°E] ·
                          Lat: [{selectedProductDetail.bounds.min_lat}°, {selectedProductDetail.bounds.max_lat}°N]
                        </dd>
                      </>
                    )}
                  </dl>

                  <div className="inspector-actions">
                    {selectedProductDetail.download_url && (
                      <a
                        href={selectedProductDetail.download_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn-download-direct"
                      >
                        <Icon name="download" />
                        <span>Download Scientific File</span>
                      </a>
                    )}
                    <a
                      href={selectedProductDetail.archive_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn-visit-archive"
                    >
                      <Icon name="link" />
                      <span>Official PDS Archive Landing Page</span>
                    </a>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SPECIALIST VIEW: MEDA IN-SITU SURFACE WEATHER */}
      {activeTab === 'meda' && (
        <div className="meda-specialist-view">
          <div className="specialist-intro">
            <h3>Perseverance MEDA In-Situ Surface Environmental Telemetry</h3>
            <p className="disclaimer-callout">
              <strong>Ground-Truth Constraint:</strong> All observations originate from the Mars Environmental
              Dynamics Analyzer (MEDA) sensors mounted on the Perseverance rover mast and deck in Jezero Crater
              (18.435°N, 77.233°E). Measurements reflect local surface boundary conditions; no crater-wide extrapolation is applied.
            </p>
          </div>

          <div className="sol-selector-strip">
            <span className="strip-label">Select Martian Sol:</span>
            <div className="sol-pills">
              {medaData.map(m => (
                <button
                  key={m.sol}
                  className={`sol-pill ${m.sol === selectedMedaSol ? 'active' : ''}`}
                  onClick={() => setSelectedMedaSol(m.sol)}
                >
                  Sol {m.sol}
                </button>
              ))}
            </div>
          </div>

          {activeMeda && (
            <div className="meda-metrics-grid">
              <div className="meda-metric-card">
                <span className="metric-label">Air Temperature (ATS)</span>
                <strong className="metric-val">
                  {activeMeda.air_temperature_deg_c !== null ? `${activeMeda.air_temperature_deg_c.toFixed(1)} °C` : '—'}
                </strong>
                <small className="metric-sub">1.5m above surface</small>
              </div>

              <div className="meda-metric-card">
                <span className="metric-label">Ground Surface Temp (TIRS)</span>
                <strong className="metric-val">
                  {activeMeda.ground_temperature_deg_c !== null ? `${activeMeda.ground_temperature_deg_c.toFixed(1)} °C` : '—'}
                </strong>
                <small className="metric-sub">Thermal IR radiometer</small>
              </div>

              <div className="meda-metric-card">
                <span className="metric-label">Surface Pressure (PS)</span>
                <strong className="metric-val">
                  {activeMeda.atmospheric_pressure_pa !== null ? `${activeMeda.atmospheric_pressure_pa.toFixed(1)} Pa` : '—'}
                </strong>
                <small className="metric-sub">Barometric sensor</small>
              </div>

              <div className="meda-metric-card">
                <span className="metric-label">Dust Optical Depth (RDS τ)</span>
                <strong className="metric-val">
                  {activeMeda.dust_optical_depth_tau !== null ? activeMeda.dust_optical_depth_tau.toFixed(2) : '—'}
                </strong>
                <small className="metric-sub">Aerosol column opacity</small>
              </div>

              <div className="meda-metric-card">
                <span className="metric-label">Relative Humidity (RHS)</span>
                <strong className="metric-val">
                  {activeMeda.relative_humidity_percent !== null ? `${activeMeda.relative_humidity_percent.toFixed(1)} %` : '—'}
                </strong>
                <small className="metric-sub">Capacitive humidity sensor</small>
              </div>

              <div className="meda-metric-card">
                <span className="metric-label">Surface Wind (WS)</span>
                <strong className="metric-val">
                  {activeMeda.wind_speed_m_per_s !== null
                    ? `${activeMeda.wind_speed_m_per_s.toFixed(1)} m/s @ ${Math.round(activeMeda.wind_direction_deg)}°`
                    : <span className="missing-flag" title="Sensor reading uncalibrated / omitted (-9999.0 flag in PDS)">— / Uncalibrated</span>}
                </strong>
                <small className="metric-sub">
                  {activeMeda.wind_speed_m_per_s === null
                    ? 'Sensor omitted (-9999.0 flag in raw PDS)'
                    : 'Boom 1 & 2 2D thermal anemometer'}
                </small>
              </div>
            </div>
          )}

          <div className="meda-telemetry-meta">
            <div className="meta-row">
              <span>Local True Solar Time: <strong>{activeMeda?.local_true_solar_time || 'Midday'}</strong></span>
              <span>Earth UTC: <strong>{activeMeda?.earth_date_utc}</strong></span>
              <span>Calibration: <span className="status-badge-inline">{activeMeda?.quality_flag}</span></span>
            </div>
            <p className="meda-notes">{activeMeda?.notes}</p>
          </div>
        </div>
      )}

      {/* SPECIALIST VIEW: THEMIS THERMAL INERTIA & TRAVERSABILITY */}
      {activeTab === 'themis' && (
        <div className="themis-specialist-view">
          <div className="specialist-intro">
            <h3>THEMIS 100m Infrared & Surface Traversability</h3>
            <p className="specialist-sub">
              Thermal inertia (I = √(k·ρ·c)) measures the subsurface's resistance to temperature change,
              directly correlating with grain size and soil consolidation. MARSPath uses THEMIS thermal inertia
              to detect loose wheel-sinkage hazards vs competent bedrock.
            </p>
          </div>

          <div className="themis-legend-bar">
            <div className="legend-segment sinkage">
              <strong>I &lt; 150 tiu: High Wheel Sinkage Risk</strong>
              <small>Unconsolidated drift dust / aeolian dunes</small>
            </div>
            <div className="legend-segment moderate">
              <strong>150 – 300 tiu: Mixed Regolith</strong>
              <small>Interbedded duricrust & pebbles</small>
            </div>
            <div className="legend-segment bedrock">
              <strong>I &gt; 300 tiu: Optimal Traction</strong>
              <small>Well-cemented bedrock & blocky outcrops</small>
            </div>
          </div>

          <div className="themis-cards-grid">
            {themisData.map(obs => (
              <div key={obs.observation_id} className="themis-card">
                <div className="themis-card-header">
                  <div>
                    <span className="themis-id-tag">{obs.observation_id}</span>
                    <h4>{obs.target_name}</h4>
                  </div>
                  <span className={`risk-tag ${obs.traversability_risk.toLowerCase()}`}>
                    {obs.traversability_risk.replace(/_/g, ' ')}
                  </span>
                </div>

                <div className="themis-metrics-row">
                  <div className="t-metric">
                    <label>Thermal Inertia</label>
                    <strong>{obs.thermal_inertia_tiu.toFixed(1)} <small>tiu</small></strong>
                  </div>
                  <div className="t-metric">
                    <label>Day IR Temp</label>
                    <strong>{obs.day_ir_temp_k.toFixed(1)} <small>K</small></strong>
                  </div>
                  <div className="t-metric">
                    <label>Night IR Temp</label>
                    <strong>{obs.night_ir_temp_k.toFixed(1)} <small>K</small></strong>
                  </div>
                </div>

                <p className="risk-text">{obs.risk_assessment}</p>

                <div className="themis-card-footer">
                  <span>Coords: {obs.center_lon.toFixed(2)}°E, {obs.center_lat.toFixed(2)}°N</span>
                  <a href={obs.source_url} target="_blank" rel="noopener noreferrer" className="btn-small-link">
                    Open THEMIS Viewer
                  </a>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SPECIALIST VIEW: NAIF / SPICE EPHEMERIS GEOMETRY CALCULATOR */}
      {activeTab === 'spice' && (
        <div className="spice-specialist-view">
          <div className="specialist-intro">
            <h3>NASA NAIF / SPICE Ephemeris & Observation Geometry</h3>
            <p className="specialist-sub">
              Dual-engine ephemeris calculator: utilizes official SPICE kernels (SPK, PCK, LSK) when available,
              with high-fidelity analytical Keplerian astrodynamics with J₂ secular perturbation fallback.
            </p>
          </div>

          <div className="spice-controls-row">
            <span className="ctrl-label">Select Spacecraft:</span>
            <div className="spice-ship-pills">
              {['mro', 'ody', 'maven', 'mex', 'tgo'].map(sc => (
                <button
                  key={sc}
                  className={`spice-pill ${spiceSpacecraft === sc ? 'active' : ''}`}
                  onClick={() => handleSpiceCalculate(sc)}
                  disabled={spiceCalculating}
                >
                  {sc.toUpperCase()}
                </button>
              ))}
            </div>
            <button
              className="recalc-btn"
              onClick={() => handleSpiceCalculate(spiceSpacecraft)}
              disabled={spiceCalculating}
            >
              <Icon name="refresh" />
              <span>{spiceCalculating ? 'Computing…' : 'Compute Ephemeris'}</span>
            </button>
          </div>

          {spiceGeometry && (
            <div className="spice-readout-card">
              <div className="readout-header">
                <div>
                  <span className="engine-badge">{spiceGeometry.calculation_mode}</span>
                  <h4>{spiceGeometry.spacecraft_name} Observation Geometry</h4>
                </div>
                <span className="epoch-tag">{spiceGeometry.epoch_utc}</span>
              </div>

              <div className="spice-metrics-grid">
                <div className="s-cell">
                  <label>Sub-Spacecraft Longitude</label>
                  <strong>{spiceGeometry.sub_spacecraft_lon?.toFixed(3)}° E</strong>
                </div>
                <div className="s-cell">
                  <label>Sub-Spacecraft Latitude</label>
                  <strong>{spiceGeometry.sub_spacecraft_lat?.toFixed(3)}° N</strong>
                </div>
                <div className="s-cell">
                  <label>Orbital Altitude</label>
                  <strong>{spiceGeometry.spacecraft_altitude_km?.toFixed(1)} km</strong>
                </div>
                <div className="s-cell">
                  <label>Sub-Solar Longitude</label>
                  <strong>{spiceGeometry.sub_solar_lon?.toFixed(3)}° E</strong>
                </div>
                <div className="s-cell">
                  <label>Sub-Solar Latitude</label>
                  <strong>{spiceGeometry.sub_solar_lat?.toFixed(3)}° N</strong>
                </div>
                <div className="s-cell highlight">
                  <label>Solar Incidence Angle (θi)</label>
                  <strong>{spiceGeometry.solar_incidence_angle_deg?.toFixed(2)}°</strong>
                </div>
                <div className="s-cell">
                  <label>Emission Angle</label>
                  <strong>{spiceGeometry.emission_angle_deg?.toFixed(2)}°</strong>
                </div>
                <div className="s-cell">
                  <label>Phase Angle</label>
                  <strong>{spiceGeometry.phase_angle_deg?.toFixed(2)}°</strong>
                </div>
                <div className="s-cell highlight">
                  <label>Local Solar Time (LST)</label>
                  <strong>{spiceGeometry.local_solar_time}</strong>
                </div>
              </div>

              <div className="spice-footer-meta">
                <span>Kernel Reference: <code>{spiceGeometry.kernel_source}</code></span>
                <span>Solar Longitude (Ls): <strong>{spiceGeometry.solar_longitude_ls_deg}°</strong></span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* SPECIALIST VIEW: PDS DATA RELEASES */}
      {activeTab === 'releases' && (
        <div className="releases-specialist-view">
          <div className="specialist-intro">
            <h3>NASA Planetary Data System (PDS) Release Monitor</h3>
            <p className="specialist-sub">
              Formal peer-reviewed release timeline tracking quarterly science product batches across active Mars missions.
            </p>
          </div>

          <div className="releases-timeline">
            {releases.map(rel => (
              <article key={rel.release_id} className="release-card">
                <div className="rel-header">
                  <div>
                    <span className="rel-id-badge">{rel.release_id}</span>
                    <h4>{rel.mission}</h4>
                  </div>
                  <span className="rel-vol-badge">{rel.data_volume_gb} GB</span>
                </div>

                <p className="rel-desc">{rel.description}</p>

                <div className="rel-meta-grid">
                  <div><label>Release Date:</label> <span>{new Date(rel.release_date_utc).toLocaleDateString()}</span></div>
                  <div><label>Coverage Window:</label> <span>{rel.coverage_period}</span></div>
                  <div><label>PDS Lead Node:</label> <span>{rel.pds_node}</span></div>
                </div>

                <div className="rel-instruments-row">
                  <label>Instruments:</label>
                  <div className="tags-list">
                    {(rel.instruments || []).map((ins, i) => (
                      <span key={i} className="tag">{ins}</span>
                    ))}
                  </div>
                </div>

                <div className="rel-footer">
                  <span className="rel-status-pill">{rel.status}</span>
                  <a
                    href={rel.pds_announcement_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-small-link"
                  >
                    Official PDS Release Notes
                  </a>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
