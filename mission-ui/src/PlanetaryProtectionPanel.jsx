import React, { useState } from 'react';
import {
  JEZERO_SPECIAL_REGIONS,
  dispatchScoutRoverRecon,
} from './planetary_protection.js';

export default function PlanetaryProtectionPanel({
  planetaryProtectionAssessment,
  showOfficialZones,
  setShowOfficialZones,
  showCandidateZones,
  setShowCandidateZones,
  showDemoZones,
  setShowDemoZones,
  selectedRegionId,
  setSelectedRegionId,
  onZoneSelect,
  apiUrl = '',
}) {
  const [activeZone, setActiveZone] = useState(
    JEZERO_SPECIAL_REGIONS.find((z) => z.id === selectedRegionId) || JEZERO_SPECIAL_REGIONS[0]
  );
  const [showScoutModal, setShowScoutModal] = useState(false);
  const [scoutResponse, setScoutResponse] = useState(null);
  const [isDispatching, setIsDispatching] = useState(false);

  const pp = planetaryProtectionAssessment;
  const isApproved = pp?.human_route_approved ?? true;
  const violations = pp?.policy_violations || [];
  const warnings = pp?.warnings || [];
  const intersections = pp?.intersected_regions || [];

  const handleSelectZone = (zoneId) => {
    setSelectedRegionId(zoneId);
    const z = JEZERO_SPECIAL_REGIONS.find((item) => item.id === zoneId);
    if (z) {
      setActiveZone(z);
      if (onZoneSelect) onZoneSelect(z);
    }
  };

  const handleDispatchScout = async () => {
    setIsDispatching(true);
    try {
      const resp = await dispatchScoutRoverRecon(activeZone.id, apiUrl);
      setScoutResponse(resp);
    } catch (err) {
      console.error('Failed to dispatch scout rover:', err);
    } finally {
      setIsDispatching(false);
    }
  };

  return (
    <div className="planetary-protection-panel">
      {/* Header */}
      <div className="section-header-compact">
        <div className="flex-row items-center justify-between">
          <div className="flex-row items-center gap-2">
            <span className={`pulse-dot ${isApproved ? 'green' : 'red'}`} />
            <h4 className="section-title-sm">PLANETARY PROTECTION GEOFENCE</h4>
          </div>
          <span className={`badge-pill ${isApproved ? 'status-safe' : 'status-exceeded'}`}>
            {isApproved ? 'HUMAN ACCESS APPROVED' : 'RESTRICTED — HUMAN ROUTE BARRED'}
          </span>
        </div>
      </div>

      {/* Critical Violation Alert */}
      {!isApproved && (
        <div className="geofence-alert-box red" role="alert">
          <div className="flex-row items-start gap-2">
            <span className="alert-icon text-lg">🛑</span>
            <div>
              <strong className="text-xs uppercase tracking-wide text-rose-200">
                CRITICAL PLANETARY PROTECTION RESTRICTION
              </strong>
              <p className="text-xs text-rose-100 mt-1">
                Traverse intersects designated COSPAR Category IVc Special Region. Human astronaut EVA access is strictly barred to prevent terrestrial biological contamination.
              </p>
              {violations.map((v, i) => (
                <div key={i} className="text-[11px] text-rose-300 mt-1 font-mono bg-rose-950/60 p-1.5 rounded">
                  {v}
                </div>
              ))}
              <div className="mt-2.5 flex-row items-center gap-2">
                <button
                  className="btn-scout-dispatch"
                  onClick={() => setShowScoutModal(true)}
                >
                  DISPATCH SCOUT ROVER RECONNAISSANCE
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Candidate / Advisory Warning */}
      {isApproved && warnings.length > 0 && (
        <div className="geofence-alert-box amber" role="alert">
          <div className="flex-row items-start gap-2">
            <span className="alert-icon text-lg">⚠️</span>
            <div>
              <strong className="text-xs uppercase tracking-wide text-amber-200">
                PLANETARY PROTECTION ADVISORY
              </strong>
              {warnings.map((w, i) => (
                <p key={i} className="text-xs text-amber-100 mt-1">
                  {w}
                </p>
              ))}
              <div className="mt-2">
                <button
                  className="btn-scout-dispatch secondary"
                  onClick={() => setShowScoutModal(true)}
                >
                  DISPATCH SCOUT ROVER RECONNAISSANCE
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Geofence Map Layer Controls */}
      <div className="geofence-layers-box mt-3">
        <span className="text-xs font-mono text-slate-300 uppercase tracking-wider block mb-2">
          SPECIAL REGION GEOFENCE LAYERS
        </span>

        <div className="geofence-toggles-grid">
          {/* Official Restricted Zones */}
          <label className="geofence-toggle-label official">
            <input
              type="checkbox"
              checked={showOfficialZones}
              onChange={(e) => setShowOfficialZones(e.target.checked)}
            />
            <span className="color-chip red" />
            <div className="toggle-text">
              <div className="font-semibold text-xs text-rose-200">Official Restricted Zones</div>
              <div className="text-[11px] text-slate-400">COSPAR Cat IVc · Solid red boundary · Human barred</div>
            </div>
          </label>

          {/* Candidate Sensitive Regions */}
          <label className="geofence-toggle-label candidate">
            <input
              type="checkbox"
              checked={showCandidateZones}
              onChange={(e) => setShowCandidateZones(e.target.checked)}
            />
            <span className="color-chip amber" />
            <div className="toggle-text">
              <div className="font-semibold text-xs text-amber-200">Candidate Sensitive Regions</div>
              <div className="text-[11px] text-slate-400">CRISM hydrated minerals/RSL · Amber boundary · Advisory</div>
            </div>
          </label>

          {/* Demonstration Scenarios */}
          <label className="geofence-toggle-label demo">
            <input
              type="checkbox"
              checked={showDemoZones}
              onChange={(e) => setShowDemoZones(e.target.checked)}
            />
            <span className="color-chip purple-dashed" />
            <div className="toggle-text">
              <div className="font-semibold text-xs text-purple-200">Demonstration Scenarios</div>
              <div className="text-[11px] text-slate-400">Hypothetical ice-cemented regolith drill · Dashed purple</div>
            </div>
          </label>
        </div>
      </div>

      {/* Special-Region Information Panel */}
      <div className="special-region-info-panel mt-3">
        <div className="flex-row items-center justify-between mb-2">
          <span className="text-xs font-mono text-slate-300 uppercase tracking-wider">
            SPECIAL-REGION INFORMATION PANEL
          </span>
          <select
            className="zone-selector-dropdown font-mono text-xs"
            value={activeZone.id}
            onChange={(e) => handleSelectZone(e.target.value)}
          >
            {JEZERO_SPECIAL_REGIONS.map((z) => (
              <option key={z.id} value={z.id}>
                {z.name} ({z.classification === 'official_restricted_zone' ? 'OFFICIAL' : z.classification === 'candidate_sensitive_region' ? 'CANDIDATE' : 'DEMO'})
              </option>
            ))}
          </select>
        </div>

        {/* Selected Zone Card */}
        <div className="selected-zone-card">
          <div className="flex-row items-center justify-between pb-2 border-b border-slate-800">
            <div>
              <h4 className="font-semibold text-sm text-slate-100">{activeZone.name}</h4>
              <span className="text-xs font-mono text-slate-400">ID: {activeZone.id}</span>
            </div>
            <span
              className={`badge-pill text-[10px] ${activeZone.classification === 'official_restricted_zone' ? 'status-exceeded' : activeZone.classification === 'candidate_sensitive_region' ? 'status-limited' : 'status-demo'}`}
            >
              {activeZone.classification.toUpperCase()}
            </span>
          </div>

          <div className="zone-details-grid mt-2">
            <div className="detail-item">
              <span className="label">PRIMARY DATASET</span>
              <span className="val font-mono">{activeZone.dataset}</span>
            </div>
            <div className="detail-item">
              <span className="label">OBSERVATION ID</span>
              <span className="val font-mono text-cyan-300">{activeZone.dataset_id}</span>
            </div>
            <div className="detail-item">
              <span className="label">INSTRUMENT</span>
              <span className="val">{activeZone.instrument}</span>
            </div>
            <div className="detail-item">
              <span className="label">ACQUISITION DATE</span>
              <span className="val font-mono">{activeZone.acquisition_date}</span>
            </div>
            <div className="detail-item">
              <span className="label">SPATIAL RESOLUTION</span>
              <span className="val">{activeZone.spatial_resolution_m} m/pixel</span>
            </div>
            <div className="detail-item">
              <span className="label">DATA QUALITY</span>
              <span className="val">{activeZone.data_quality}</span>
            </div>
            <div className="detail-item full-width">
              <span className="label">RESTRICTION POLICY</span>
              <span className="val text-rose-300">{activeZone.restriction_policy}</span>
            </div>
            <div className="detail-item full-width">
              <span className="label">HUMAN ACCESS STATUS</span>
              <span className={`val font-mono font-bold ${activeZone.human_access_status === 'STRICTLY_PROHIBITED' ? 'text-rose-400' : 'text-amber-300'}`}>
                {activeZone.human_access_status}
              </span>
            </div>
            <div className="detail-item full-width">
              <span className="label">SCIENTIFIC RATIONALE</span>
              <span className="val text-xs text-slate-300 leading-relaxed">{activeZone.scientific_rationale}</span>
            </div>
            <div className="detail-item full-width">
              <span className="label">PROVENANCE & ZERO-FABRICATION NOTE</span>
              <span className="val text-[11px] text-slate-400 font-mono leading-relaxed bg-slate-900/80 p-2 rounded">
                {activeZone.provenance_notes}
              </span>
            </div>
          </div>

          {/* Action Row */}
          <div className="mt-3 flex-row items-center justify-between pt-2 border-t border-slate-800">
            <span className="text-xs text-slate-400">
              Robotic Scout Eligible: <strong className="text-emerald-400">{activeZone.scout_rover_eligible ? 'YES' : 'NO'}</strong>
            </span>
            <button
              className="btn-scout-dispatch"
              onClick={() => setShowScoutModal(true)}
            >
              DISPATCH SCOUT ROVER
            </button>
          </div>
        </div>
      </div>

      {/* Scout Rover Dispatch Simulation Modal */}
      {showScoutModal && (
        <div className="modal-backdrop" onClick={() => setShowScoutModal(false)}>
          <div className="modal-content scout-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="flex-row items-center gap-2">
                <span className="scout-icon">🛰️</span>
                <h3 className="modal-title font-mono text-sm tracking-wider">
                  SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST
                </h3>
              </div>
              <button className="close-btn" onClick={() => setShowScoutModal(false)}>×</button>
            </div>

            <div className="modal-body">
              {/* Mandatory Simulation Disclaimer */}
              <div className="disclaimer-banner mb-3">
                <strong>MOCK MISSION SIMULATION ONLY.</strong>
                <p className="text-[11px] mt-0.5 text-slate-300">
                  This conceptual reconnaissance request generates simulated robotic scout telemetry for mission planning drills and does not interface with active NASA spacecraft operations.
                </p>
              </div>

              {!scoutResponse ? (
                <>
                  <div className="scout-params-grid">
                    <div className="param-item">
                      <span className="param-label">TARGET SPECIAL REGION</span>
                      <span className="param-val font-semibold text-slate-100">{activeZone.name}</span>
                    </div>
                    <div className="param-item">
                      <span className="param-label">TARGET CENTROID</span>
                      <span className="param-val font-mono text-cyan-300">
                        {activeZone.center[0]}°E, {activeZone.center[1]}°N
                      </span>
                    </div>
                    <div className="param-item">
                      <span className="param-label">RECON PLATFORM</span>
                      <span className="param-val">Ingenuity-Class Aerial Scout / Sample Fetch Micro-Rover</span>
                    </div>
                    <div className="param-item">
                      <span className="param-label">STERILIZATION LEVEL</span>
                      <span className="param-val font-mono text-emerald-300">
                        Cat IVb Post-Bakeout (&lt; 300 spores/m²)
                      </span>
                    </div>
                    <div className="param-item full">
                      <span className="param-label">STERILIZED INSTRUMENT SUITE</span>
                      <span className="param-val font-mono text-slate-200">
                        Alpha Particle X-Ray Spectrometer (APXS) · Raman Bio-Signature Spectrometer · Microscopic Imager
                      </span>
                    </div>
                    <div className="param-item">
                      <span className="param-label">SCHEDULED RECON SOL</span>
                      <span className="param-val font-mono">Sol 2024</span>
                    </div>
                    <div className="param-item">
                      <span className="param-label">ESTIMATED SORTIE ETA</span>
                      <span className="param-val font-mono">4.5 hours</span>
                    </div>
                  </div>

                  <div className="mt-4 flex-row items-center justify-end gap-2">
                    <button
                      className="btn-secondary-sm"
                      onClick={() => setShowScoutModal(false)}
                    >
                      Cancel
                    </button>
                    <button
                      className="btn-primary-sm btn-confirm-dispatch"
                      onClick={handleDispatchScout}
                      disabled={isDispatching}
                    >
                      {isDispatching ? 'Transmitting Simulated Request...' : 'CONFIRM SIMULATED DISPATCH'}
                    </button>
                  </div>
                </>
              ) : (
                <div className="scout-success-state">
                  <div className="success-banner mb-3">
                    <span className="success-icon">✅</span>
                    <div>
                      <strong className="text-emerald-300 text-sm">SIMULATED RECONNAISSANCE SORTIE LOGGED</strong>
                      <p className="text-xs text-slate-300 mt-0.5">
                        Robotic scout sortie authorized under Planetary Protection protocol. Telemetry queued for synthetic execution.
                      </p>
                    </div>
                  </div>

                  <div className="telemetry-box font-mono text-xs">
                    <div>SORTIE ID: <span className="text-cyan-300">{scoutResponse.recon_mission_id}</span></div>
                    <div>STATUS: <span className="text-emerald-400">{scoutResponse.status}</span></div>
                    <div>TARGET: <span>{scoutResponse.target_region_name}</span></div>
                    <div>COORDINATES: <span>[{scoutResponse.target_coordinates?.[0]}°E, {scoutResponse.target_coordinates?.[1]}°N]</span></div>
                    <div>DISPATCH UTC: <span>{scoutResponse.timestamp_utc}</span></div>
                    <div>CLEANLINESS: <span>{scoutResponse.bio_cleanliness_level}</span></div>
                  </div>

                  <div className="mt-4 flex-row justify-end">
                    <button
                      className="btn-primary-sm"
                      onClick={() => {
                        setScoutResponse(null);
                        setShowScoutModal(false);
                      }}
                    >
                      Done
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
