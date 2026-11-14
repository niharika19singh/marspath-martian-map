import React, { useState, useEffect } from 'react';
import Icon from './Icons.jsx';
import {
  fetchIntelligenceStatus,
  fetchSpacecraftList,
  fetchGroundTrack,
  fetchRoverList,
  fetchRoverObservations,
  fetchOrbitalObservations,
  fetchMissionTimeline,
  triggerSync
} from './intelligence.js';

export default function IntelligencePanel(props) {
  const {
    apiUrl = '',
    onSelectSpacecraft,
    selectedSpacecraft,
    onSelectRover,
    selectedRover,
    onSelectObservation,
    selectedObservation,
    onFocusCoordinates,
    onClose,
    syncToken
  } = props;

  const [activeTab, setActiveTab] = useState('orbiters'); // 'orbiters' | 'rovers' | 'imagery' | 'timeline' | 'provenance'
  const [status, setStatus] = useState(null);
  const [spacecraftList, setSpacecraftList] = useState([]);
  const [roverList, setRoverList] = useState([]);
  const [roverObs, setRoverObs] = useState([]);
  const [orbitalObs, setOrbitalObs] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [syncNotice, setSyncNotice] = useState('');
  const [filterInstrument, setFilterInstrument] = useState('all');

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetchIntelligenceStatus(apiUrl),
      fetchSpacecraftList(apiUrl),
      fetchRoverList(apiUrl),
      fetchOrbitalObservations(apiUrl),
      fetchMissionTimeline(25, apiUrl)
    ]).then(([st, sc, rovs, obs, tl]) => {
      if (cancelled) return;
      setStatus(st);
      setSpacecraftList(sc);
      setRoverList(rovs);
      setOrbitalObs(obs);
      setTimeline(tl);
    }).catch(err => console.error('Error loading intelligence data:', err));

    return () => { cancelled = true; };
  }, [apiUrl, syncToken]);

  useEffect(() => {
    if (!selectedRover) return;
    fetchRoverObservations(selectedRover, apiUrl)
      .then(setRoverObs)
      .catch(() => setRoverObs([]));
  }, [selectedRover, apiUrl]);

  const activeShip = spacecraftList.find(s => s.spacecraft_id === selectedSpacecraft) || spacecraftList[0];
  const activeRov = roverList.find(r => r.rover_id === selectedRover) || roverList[0];

  const handleSync = async () => {
    setSyncing(true);
    setSyncNotice('');
    try {
      const res = await triggerSync(true, apiUrl);
      setSyncNotice(res.message || 'Synchronization complete.');
      const [st, sc, rovs, obs, tl] = await Promise.all([
        fetchIntelligenceStatus(apiUrl),
        fetchSpacecraftList(apiUrl),
        fetchRoverList(apiUrl),
        fetchOrbitalObservations(apiUrl),
        fetchMissionTimeline(25, apiUrl)
      ]);
      setStatus(st);
      setSpacecraftList(sc);
      setRoverList(rovs);
      setOrbitalObs(obs);
      setTimeline(tl);
    } catch (e) {
      setSyncNotice('Sync failed: ' + e.message);
    } finally {
      setSyncing(false);
      setTimeout(() => setSyncNotice(''), 4500);
    }
  };

  const filteredObservations = orbitalObs.filter(o => {
    if (filterInstrument === 'all') return true;
    return o.instrument.toLowerCase().includes(filterInstrument.toLowerCase());
  });

  return (
    <aside className="intelligence-panel glass" aria-label="Live Mars Intelligence Console">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Planetary Situational Awareness</p>
          <h2>Live Mars Intelligence</h2>
        </div>
        <button className="icon-button" onClick={onClose} aria-label="Close intelligence panel">
          <Icon name="close" />
        </button>
      </div>

      <div className="intelligence-status-bar">
        <span className="live-pulse-dot" />
        <span className="status-text">
          {status?.status === 'operational' ? 'ONLINE · PDS & SPICE CONNECTED' : 'STANDALONE ORBITAL PROPAGATION'}
        </span>
        <button
          className="sync-action-button"
          onClick={handleSync}
          disabled={syncing}
          title="Query NASA PDS, JPL Horizons & ESA PSA archives"
        >
          <Icon name="rotate" />
          <span>{syncing ? 'Syncing…' : 'Sync Archives'}</span>
        </button>
      </div>

      {syncNotice && <div className="intelligence-sync-toast glass">{syncNotice}</div>}

      <nav className="intelligence-subtabs" aria-label="Intelligence sections">
        <button
          className={activeTab === 'orbiters' ? 'active' : ''}
          onClick={() => setActiveTab('orbiters')}
        >
          <Icon name="satellite" /> Orbiters ({spacecraftList.length})
        </button>
        <button
          className={activeTab === 'rovers' ? 'active' : ''}
          onClick={() => setActiveTab('rovers')}
        >
          <Icon name="rover" /> Rovers ({roverList.length})
        </button>
        <button
          className={activeTab === 'imagery' ? 'active' : ''}
          onClick={() => setActiveTab('imagery')}
        >
          <Icon name="footprint" /> Footprints ({orbitalObs.length})
        </button>
        <button
          className={activeTab === 'timeline' ? 'active' : ''}
          onClick={() => setActiveTab('timeline')}
        >
          <Icon name="timeline" /> Timeline
        </button>
        <button
          className={activeTab === 'provenance' ? 'active' : ''}
          onClick={() => setActiveTab('provenance')}
        >
          <Icon name="shield" /> Provenance
        </button>
      </nav>

      <div className="intelligence-body">
        {/* TAB 1: ORBITAL TRACKING */}
        {activeTab === 'orbiters' && (
          <div className="tab-pane">
            <div className="selector-pills">
              {spacecraftList.map(s => (
                <button
                  key={s.spacecraft_id}
                  className={`pill-btn ${s.spacecraft_id === (activeShip?.spacecraft_id) ? 'active' : ''}`}
                  onClick={() => onSelectSpacecraft?.(s.spacecraft_id)}
                >
                  {s.spacecraft_id.toUpperCase()}
                </button>
              ))}
            </div>

            {activeShip && (
              <div className="intel-card">
                <div className="card-header">
                  <div>
                    <span className="card-badge predicted">PREDICTED EPHEMERIS</span>
                    <h3>{activeShip.name}</h3>
                    <p className="card-subtitle">{activeShip.agency} · {activeShip.mission}</p>
                  </div>
                  <button
                    className="focus-btn"
                    onClick={() => onFocusCoordinates?.({
                      lon: activeShip.current_position.lon,
                      lat: activeShip.current_position.lat,
                      zoom: 2
                    })}
                    title="Center map on spacecraft sub-satellite point"
                  >
                    <Icon name="crosshair" /> Focus
                  </button>
                </div>

                <div className="telemetry-grid">
                  <div className="telemetry-cell">
                    <label>Altitude</label>
                    <strong>{activeShip.current_position.altitude_km.toFixed(1)} <small>km</small></strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Orbital Speed</label>
                    <strong>{activeShip.current_position.velocity_kms.toFixed(2)} <small>km/s</small></strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Sub-Satellite Lat</label>
                    <strong>{activeShip.current_position.lat > 0 ? `${activeShip.current_position.lat.toFixed(3)}°N` : `${Math.abs(activeShip.current_position.lat).toFixed(3)}°S`}</strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Sub-Satellite Lon</label>
                    <strong>{activeShip.current_position.lon > 0 ? `${activeShip.current_position.lon.toFixed(3)}°E` : `${Math.abs(activeShip.current_position.lon).toFixed(3)}°W`}</strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Track Heading</label>
                    <strong>{activeShip.current_position.heading_deg.toFixed(1)}°</strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Orbital Period</label>
                    <strong>{activeShip.orbital_period_minutes.toFixed(1)} <small>min</small></strong>
                  </div>
                </div>

                <div className="intel-meta-section">
                  <p className="description-text">{activeShip.description}</p>
                  <label className="field-caption">Primary Science Payload:</label>
                  <div className="tags-list">
                    {activeShip.primary_instruments.map((inst, idx) => (
                      <span key={idx} className="tag">{inst}</span>
                    ))}
                  </div>

                  <div className="provenance-footnote">
                    <span>Source: {activeShip.ephemeris_source}</span>
                    <span>State: J2-perturbed state propagation · Uncertainty ±0.8 km</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: ROVER TRACKING */}
        {activeTab === 'rovers' && (
          <div className="tab-pane">
            <div className="selector-pills">
              {roverList.map(r => (
                <button
                  key={r.rover_id}
                  className={`pill-btn ${r.rover_id === (activeRov?.rover_id) ? 'active' : ''}`}
                  onClick={() => onSelectRover?.(r.rover_id)}
                >
                  {r.name.split(' ')[0]}
                </button>
              ))}
            </div>

            {activeRov && (
              <div className="intel-card">
                <div className="card-header">
                  <div>
                    <span className="card-badge verified">LATEST AVAILABLE</span>
                    <h3>{activeRov.name}</h3>
                    <p className="card-subtitle">{activeRov.landing_site}</p>
                  </div>
                  <button
                    className="focus-btn"
                    onClick={() => onFocusCoordinates?.({
                      lon: activeRov.lon,
                      lat: activeRov.lat,
                      zoom: activeRov.rover_id === 'perseverance' ? 12 : 5
                    })}
                    title="Center map on rover location"
                  >
                    <Icon name="crosshair" /> Center
                  </button>
                </div>

                <div className="telemetry-grid">
                  <div className="telemetry-cell highlight">
                    <label>Mission Sol</label>
                    <strong>Sol {activeRov.sol}</strong>
                  </div>
                  <div className="telemetry-cell highlight">
                    <label>Total Odometry</label>
                    <strong>{(activeRov.total_odometry_meters / 1000).toFixed(2)} <small>km</small></strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Last Drive</label>
                    <strong>{activeRov.last_drive_distance_meters.toFixed(1)} <small>m</small></strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Elevation</label>
                    <strong>{activeRov.elevation_m.toFixed(1)} <small>m</small></strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Longitude</label>
                    <strong>{activeRov.lon.toFixed(5)}°E</strong>
                  </div>
                  <div className="telemetry-cell">
                    <label>Latitude</label>
                    <strong>{activeRov.lat > 0 ? `${activeRov.lat.toFixed(5)}°N` : `${Math.abs(activeRov.lat).toFixed(5)}°S`}</strong>
                  </div>
                </div>

                <div className="intel-meta-section">
                  <label className="field-caption">Active Instruments:</label>
                  <div className="tags-list">
                    {activeRov.active_instruments.map((inst, idx) => (
                      <span key={idx} className="tag">{inst}</span>
                    ))}
                  </div>

                  <h4 className="subheading">Recent Surface Observations:</h4>
                  <div className="rover-obs-list">
                    {roverObs.map(obs => (
                      <div key={obs.observation_id} className="rover-obs-item">
                        <div className="obs-header">
                          <strong>{obs.instrument}</strong>
                          <span className="sol-tag">Sol {obs.sol}</span>
                        </div>
                        <p className="obs-target">{obs.target_name}</p>
                        <p className="obs-desc">{obs.description}</p>
                      </div>
                    ))}
                    {!roverObs.length && <p className="field-note">Loading verified observation records…</p>}
                  </div>

                  <div className="provenance-footnote">
                    <span>Source: {activeRov.provenance.source_name}</span>
                    <span>Retrieved: {activeRov.earth_date_utc} · Precision &lt;0.2 m</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: OBSERVATION FOOTPRINTS */}
        {activeTab === 'imagery' && (
          <div className="tab-pane">
            <div className="filter-row">
              <span>Filter instrument:</span>
              <div className="segmented-small">
                <button
                  className={filterInstrument === 'all' ? 'active' : ''}
                  onClick={() => setFilterInstrument('all')}
                >
                  All
                </button>
                <button
                  className={filterInstrument === 'hirise' ? 'active' : ''}
                  onClick={() => setFilterInstrument('hirise')}
                >
                  HiRISE
                </button>
                <button
                  className={filterInstrument === 'ctx' ? 'active' : ''}
                  onClick={() => setFilterInstrument('ctx')}
                >
                  CTX
                </button>
                <button
                  className={filterInstrument === 'hrsc' ? 'active' : ''}
                  onClick={() => setFilterInstrument('hrsc')}
                >
                  HRSC
                </button>
              </div>
            </div>

            <div className="observations-scroll-list">
              {filteredObservations.map(obs => (
                <div
                  key={obs.observation_id}
                  className={`observation-card ${selectedObservation === obs.observation_id ? 'selected' : ''}`}
                  onClick={() => onSelectObservation?.(obs.observation_id)}
                >
                  <div className="obs-card-top">
                    <div>
                      <span className="instrument-badge">{obs.instrument}</span>
                      <h4>{obs.observation_id}</h4>
                    </div>
                    <button
                      className="fit-footprint-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectObservation?.(obs.observation_id);
                        onFocusCoordinates?.({ lon: obs.center_lon, lat: obs.center_lat, zoom: 11 });
                      }}
                      title="Fit map to observation footprint"
                    >
                      <Icon name="fit" /> Fit
                    </button>
                  </div>
                  <p className="obs-target-title">{obs.target_name}</p>
                  <div className="obs-stats-row">
                    <span><b>Res:</b> {obs.spatial_resolution_m_per_px} m/px</span>
                    <span><b>Date:</b> {obs.acquisition_utc.split('T')[0]}</span>
                    {obs.martian_sol && <span><b>Sol:</b> {obs.martian_sol}</span>}
                  </div>
                  <div className="obs-links-row">
                    <a href={obs.source_url} target="_blank" rel="noopener noreferrer">
                      PDS Archive Product ↗
                    </a>
                    <span className="status-badge-inline">{obs.processing_status}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 4: TIMELINE */}
        {activeTab === 'timeline' && (
          <div className="tab-pane">
            <div className="timeline-flow">
              {timeline.map(ev => (
                <div key={ev.event_id} className={`timeline-entry type-${ev.event_type}`}>
                  <div className="timeline-marker" />
                  <div className="timeline-content">
                    <div className="timeline-meta">
                      <span className="date-badge">{ev.earth_date_utc.split('T')[0]}</span>
                      {ev.martian_sol && <span className="sol-badge">Sol {ev.martian_sol}</span>}
                    </div>
                    <h4>{ev.title}</h4>
                    <p>{ev.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 5: PROVENANCE */}
        {activeTab === 'provenance' && (
          <div className="tab-pane provenance-tab">
            <h3>Scientific Integrity &amp; Provenance Protocol</h3>
            <p className="disclaimer-callout">
              <strong>Planetary Telemetry Statement:</strong> Mars does not possess continuous live television or video streaming satellites. All surface and orbital datasets arrive according to Deep Space Network (DSN) tracking passes, orbiter relay schedules, and peer-reviewed archive releases.
            </p>

            <div className="provenance-grid">
              <div className="prov-item">
                <span className="prov-state predicted">PREDICTED</span>
                <p>Spacecraft state vectors are calculated using official NAIF SPICE orbital elements and J2 gravitational harmonics. Ground tracks show mathematically computed trajectories.</p>
              </div>
              <div className="prov-item">
                <span className="prov-state verified">LATEST AVAILABLE</span>
                <p>Rover localization waypoints reflect published NASA JPL and PDS operations releases. They represent verified physical positions at the indicated timestamp.</p>
              </div>
              <div className="prov-item">
                <span className="prov-state historical">HISTORICAL</span>
                <p>Complete historical traverse paths retain full vertex precision without downsampling, preserving every recorded wheel rotation and scientific waypoint.</p>
              </div>
            </div>

            <div className="archive-links-block">
              <h4>Authoritative Repositories:</h4>
              <ul>
                <li><a href="https://pds-geosciences.wustl.edu/" target="_blank" rel="noreferrer">NASA Planetary Data System (PDS) Geosciences Node ↗</a></li>
                <li><a href="https://www.uahirise.org/" target="_blank" rel="noreferrer">University of Arizona HiRISE Operations Center ↗</a></li>
                <li><a href="https://archives.esac.esa.int/psa/" target="_blank" rel="noreferrer">ESA Planetary Science Archive (PSA) ↗</a></li>
                <li><a href="https://naif.jpl.nasa.gov/" target="_blank" rel="noreferrer">NASA NAIF SPICE Navigation and Ancillary Information Facility ↗</a></li>
              </ul>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
