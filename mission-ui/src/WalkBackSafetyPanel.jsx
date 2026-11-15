import React, { useState } from 'react';
import { WALK_BACK_STATUS, MOBILITY_PROFILES, formatDurationHours } from './walkback.js';

export default function WalkBackSafetyPanel({
  walkBackAssessment,
  showRoverEnvelope,
  setShowRoverEnvelope,
  showWalkbackEnvelope,
  setShowWalkbackEnvelope,
  overlayMode,
  setOverlayMode,
  onInspectSegment,
}) {
  const [showDetails, setShowDetails] = useState(false);
  const [showOrbitersModal, setShowOrbitersModal] = useState(false);

  const onFoot = walkBackAssessment?.on_foot_feasibility;
  const rf = walkBackAssessment?.rf_communication;
  const status = onFoot?.status || WALK_BACK_STATUS.DATA_UNAVAILABLE;
  const exceeds = onFoot?.destination_exceeds_limit;

  const statusBadgeClass =
    status === WALK_BACK_STATUS.SAFE_WITHIN_LIMIT
      ? 'status-safe'
      : status === WALK_BACK_STATUS.LIMITED_MARGIN
      ? 'status-limited'
      : status === WALK_BACK_STATUS.LIMIT_EXCEEDED
      ? 'status-exceeded'
      : 'status-unavailable';

  return (
    <div className="walkback-safety-panel">
      {/* Header */}
      <div className="section-header-compact">
        <div className="flex-row items-center justify-between">
          <div className="flex-row items-center gap-2">
            <span className="pulse-dot green" />
            <h4 className="section-title-sm">ASTRONAUT WALK-BACK SAFETY</h4>
          </div>
          <span className={`badge-pill ${statusBadgeClass}`}>
            {status}
          </span>
        </div>
      </div>

      {/* Prominent On-Foot Feasibility Card */}
      <div className={`on-foot-feasibility-card ${exceeds ? 'card-border-exceeded' : ''}`}>
        <div className="card-top-row">
          <div className="card-label-group">
            <span className="text-xs uppercase tracking-wider text-slate-400 font-mono">
              EMERGENCY VEHICLE-FAILURE RETURN
            </span>
            <h3 className="card-heading">ON-FOOT RETURN FEASIBILITY</h3>
          </div>
          <div className="card-status-badge font-mono">
            {onFoot?.walk_back_duration_formatted || 'N/A'}
          </div>
        </div>

        {/* Exceeded Warning Banner */}
        {exceeds && (
          <div className="walkback-exceeded-banner" role="alert">
            <span className="alert-icon">⚠️</span>
            <div>
              <strong>DESTINATION EXCEEDS CONFIGURED ON-FOOT WALK-BACK LIMIT.</strong>
              <p className="text-xs text-rose-200 mt-0.5">
                {onFoot?.warning_message ||
                  'The planned destination cannot be safely evacuated on foot within life-support constraints.'}
              </p>
            </div>
          </div>
        )}

        {/* Limited Margin Advisory */}
        {!exceeds && status === WALK_BACK_STATUS.LIMITED_MARGIN && (
          <div className="walkback-limited-banner" role="alert">
            <span className="alert-icon">⚠️</span>
            <div className="text-xs text-amber-200">
              <strong>LIMITED RETURN MARGIN:</strong> Conserve suit oxygen and avoid steep ascents.
            </div>
          </div>
        )}

        {/* Primary Metrics Grid */}
        <div className="feasibility-metrics-grid">
          <div className="metric-box">
            <span className="metric-label">WALK-BACK DISTANCE</span>
            <span className="metric-val">
              {onFoot?.walk_back_distance_km != null ? `${onFoot.walk_back_distance_km} km` : '—'}
            </span>
          </div>

          <div className="metric-box">
            <span className="metric-label">EST. WALK DURATION</span>
            <span className="metric-val">
              {onFoot?.walk_back_duration_formatted || '—'}
            </span>
          </div>

          <div className="metric-box">
            <span className="metric-label">EMERGENCY MARGIN</span>
            <span className={`metric-val ${onFoot?.emergency_resource_margin_pct < 25 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {onFoot?.emergency_resource_margin_pct != null ? `${onFoot.emergency_resource_margin_pct}%` : '—'}
            </span>
          </div>

          <div className="metric-box">
            <span className="metric-label">MAX PERMITTED WALK</span>
            <span className="metric-val">
              {onFoot?.max_permitted_walking_hours != null ? `${onFoot.max_permitted_walking_hours}h` : '3.5h'}
            </span>
          </div>

          <div className="metric-box">
            <span className="metric-label">TERRAIN DIFFICULTY</span>
            <span className={`metric-val ${onFoot?.terrain_difficulty === 'SEVERE' ? 'text-rose-400' : onFoot?.terrain_difficulty === 'HIGH' ? 'text-amber-400' : 'text-slate-200'}`}>
              {onFoot?.terrain_difficulty || 'MODERATE'}
            </span>
          </div>

          <div className="metric-box">
            <span className="metric-label">ROVER VS. FOOT RATIO</span>
            <span className="metric-val text-cyan-300">
              {walkBackAssessment?.rover_vs_foot_ratio ? `${walkBackAssessment.rover_vs_foot_ratio}× slower` : '—'}
            </span>
          </div>
        </div>

        {/* High Difficulty Terrain Segments */}
        {onFoot?.high_difficulty_segments && onFoot.high_difficulty_segments.length > 0 && (
          <div className="high-difficulty-container mt-3">
            <div className="flex-row items-center justify-between mb-1.5">
              <span className="text-xs font-mono text-slate-400 uppercase">
                Return Bottlenecks ({onFoot.high_difficulty_segments.length})
              </span>
              <button
                className="btn-link-xs"
                onClick={() => setShowDetails(!showDetails)}
              >
                {showDetails ? 'Hide Segments' : 'View Segments'}
              </button>
            </div>

            {showDetails && (
              <div className="difficulty-segments-list">
                {onFoot.high_difficulty_segments.map((seg, idx) => (
                  <div key={idx} className="difficulty-segment-item">
                    <div className="flex-row items-center justify-between">
                      <span className="font-mono text-xs text-amber-300">
                        Segment #{seg.segment_index + 1} ({seg.length_meters}m)
                      </span>
                      <span className="text-xs text-slate-400">
                        Slope: {seg.slope_deg}° · Score: {seg.difficulty_score}
                      </span>
                    </div>
                    <div className="text-xs text-slate-300 mt-0.5">
                      {seg.reason}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Dual Envelope Map Overlay Controls */}
      <div className="envelope-controls-box mt-3">
        <div className="flex-row items-center justify-between mb-2">
          <span className="text-xs font-mono text-slate-300 uppercase tracking-wider">
            SAFETY RANGE OVERLAYS
          </span>
          <div className="mode-toggle-group">
            <button
              className={`mode-btn ${overlayMode === 'combined' ? 'active' : ''}`}
              onClick={() => setOverlayMode('combined')}
              title="Show both envelopes simultaneously"
            >
              COMBINED
            </button>
            <button
              className={`mode-btn ${overlayMode === 'individual' ? 'active' : ''}`}
              onClick={() => setOverlayMode('individual')}
              title="Toggle individual layers"
            >
              INDIVIDUAL
            </button>
          </div>
        </div>

        <div className="envelope-toggles-grid">
          {/* Rover-Assisted Envelope Toggle */}
          <label className="envelope-toggle-label rover">
            <input
              type="checkbox"
              checked={showRoverEnvelope}
              onChange={(e) => setShowRoverEnvelope(e.target.checked)}
            />
            <span className="color-chip cyan" />
            <div className="toggle-text">
              <div className="font-semibold text-xs text-cyan-200">Rover-Assisted Range</div>
              <div className="text-[11px] text-slate-400">10.0 km/h · 14° slope · 8.0h range</div>
            </div>
          </label>

          {/* On-Foot Walk-Back Envelope Toggle */}
          <label className="envelope-toggle-label walkback">
            <input
              type="checkbox"
              checked={showWalkbackEnvelope}
              onChange={(e) => setShowWalkbackEnvelope(e.target.checked)}
            />
            <span className="color-chip green" />
            <div className="toggle-text">
              <div className="font-semibold text-xs text-emerald-200">On-Foot Walk-Back Range</div>
              <div className="text-[11px] text-slate-400">4.0 km/h · terrain-weighted · 3.5h emergency limit</div>
            </div>
          </label>
        </div>

        {/* Legend */}
        <div className="envelope-legend-box mt-2">
          <div className="text-[11px] text-slate-400 leading-tight">
            <strong>Physical Model Legend:</strong> Cyan envelope represents nominal pressurized rover mobility range.
            Green envelope shows conservative suited astronaut pedestrian return limit derived from backward-Dijkstra DEM terrain travel time.
          </div>
        </div>
      </div>

      {/* RF Line-of-Sight & Relay Shadow Status Card */}
      <div className="rf-comm-card mt-3">
        <div className="flex-row items-center justify-between mb-1">
          <div className="flex-row items-center gap-1.5">
            <span className={`rf-status-dot ${rf?.direct_habitat_los === 'CONNECTED' ? 'green' : rf?.direct_habitat_los === 'POTENTIAL_OBSTRUCTION' ? 'amber' : 'red'}`} />
            <span className="text-xs font-mono uppercase tracking-wider text-slate-300">
              RF LINE-OF-SIGHT & RELAY STATUS
            </span>
          </div>
          <button
            className="btn-link-xs"
            onClick={() => setShowOrbitersModal(true)}
          >
            Orbiter Pass ({rf?.active_orbiters?.filter((o) => o.is_in_view)?.length || 3})
          </button>
        </div>

        <div className="flex-row items-center justify-between text-xs mt-1">
          <span className="text-slate-400">Habitat Direct LOS:</span>
          <span className={`font-mono font-medium ${rf?.direct_habitat_los === 'CONNECTED' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {rf?.direct_habitat_los || 'CONNECTED'}
          </span>
        </div>

        <div className="flex-row items-center justify-between text-xs mt-1">
          <span className="text-slate-400">Terrain Shadow Risk:</span>
          <span className={`font-mono font-medium ${rf?.terrain_shadow_risk === 'LOW' ? 'text-emerald-400' : 'text-amber-400'}`}>
            {rf?.terrain_shadow_risk || 'LOW'}
          </span>
        </div>

        <div className="flex-row items-center justify-between text-xs mt-1">
          <span className="text-slate-400">Active Relay:</span>
          <span className="font-mono text-cyan-300 text-[11px] truncate max-w-[200px]">
            {rf?.best_orbiter_contact || 'MRO (Electra UHF @ 42.5°)'}
          </span>
        </div>
      </div>

      {/* Orbiters Relay Modal */}
      {showOrbitersModal && (
        <div className="modal-backdrop" onClick={() => setShowOrbitersModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">Verified Mars Relay Fleet Availability</h3>
              <button className="close-btn" onClick={() => setShowOrbitersModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p className="text-xs text-slate-300 mb-3">
                UHF Proximity-1 relay links for ground astronaut surface operations over Jezero Crater:
              </p>
              <div className="orbiters-list">
                {(rf?.active_orbiters || []).map((orb, i) => (
                  <div key={i} className="orbiter-row">
                    <div className="flex-row items-center justify-between">
                      <span className="font-semibold text-sm text-slate-100">{orb.spacecraft}</span>
                      <span className={`badge-pill text-[10px] ${orb.is_in_view ? 'status-safe' : 'status-unavailable'}`}>
                        {orb.is_in_view ? `IN VIEW (${orb.elevation_angle_deg}°)` : 'BELOW HORIZON'}
                      </span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      Payload: {orb.payload} ({orb.frequency_band || orb.freq})
                    </div>
                    {orb.pass_window_remaining_min != null && (
                      <div className="text-xs text-cyan-400 mt-0.5">
                        Pass window: {orb.pass_window_remaining_min} mins remaining
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
