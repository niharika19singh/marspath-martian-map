import React, { useEffect, useState } from 'react';
import { audioAlerts } from './audio_alerts.js';

export default function SuitHudOverlay({
  activeRoute,
  destination,
  start,
  isSpeActive,
  onToggleSpe,
  onClose,
  walkBackAssessment,
  planetaryProtectionAssessment,
}) {
  const [audioEnabled, setAudioEnabled] = useState(() => audioAlerts.isEnabled());
  const [activeAlert, setActiveAlert] = useState(null);
  const [speechSupported, setSpeechSupported] = useState(() => audioAlerts.isSupported());
  const [metSeconds, setMetSeconds] = useState(7425); // Simulated Mission Elapsed Time (~02:03:45)

  // Subscribe to audio alert changes
  useEffect(() => {
    const unsub = audioAlerts.subscribe((state) => {
      setAudioEnabled(state.enabled);
      setActiveAlert(state.currentAlert);
      setSpeechSupported(state.supported);
    });
    return unsub;
  }, []);

  // Update MET counter every second while HUD is active
  useEffect(() => {
    const interval = setInterval(() => {
      setMetSeconds((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const formatMet = (sec) => {
    const h = String(Math.floor(sec / 3600)).padStart(2, '0');
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
    const s = String(sec % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
  };

  // Route metrics
  const totalDistM = activeRoute?.summary?.total_distance_meters ?? 1420;
  const maxSlope = activeRoute?.summary?.max_slope_deg ?? 4.2;
  const durationHours = activeRoute?.summary?.estimated_duration_hours ?? 0.85;

  // Walk-back metrics
  const onFoot = walkBackAssessment?.on_foot_feasibility;
  const returnExceeded = onFoot?.destination_exceeds_limit;
  const walkDurationHours = onFoot?.walk_back_duration_hours ?? durationHours;
  const emergencyMarginPct = onFoot?.emergency_resource_margin_pct ?? 78.5;

  // Simulated PLSS Consumables (explicitly labelled as simulated analog assumptions)
  const simulatedO2HoursTotal = 8.0;
  const simulatedO2RemainingHours = Math.max(0.5, simulatedO2HoursTotal - durationHours * 2.1).toFixed(1);
  const simulatedO2Pct = Math.round((Number(simulatedO2RemainingHours) / simulatedO2HoursTotal) * 100);
  const simulatedBatteryPct = Math.max(12, Math.round(100 - durationHours * 16.5));

  // Determine current route hazard level
  let hazardLevel = 'NOMINAL';
  let hazardColor = '#00e676';
  if (maxSlope > 14.0 || returnExceeded || !planetaryProtectionAssessment?.human_route_approved) {
    hazardLevel = 'CRITICAL HAZARD';
    hazardColor = '#ef4444';
  } else if (maxSlope > 9.0 || emergencyMarginPct < 25.0 || isSpeActive) {
    hazardLevel = 'MODERATE HAZARD';
    hazardColor = '#f59e0b';
  }

  // Determine mission safety status
  let missionStatus = 'GO FOR EVA';
  let missionStatusColor = '#00e676';
  if (returnExceeded || !planetaryProtectionAssessment?.human_route_approved) {
    missionStatus = 'ABORT / REROUTE MANDATORY';
    missionStatusColor = '#ef4444';
  } else if (emergencyMarginPct < 20.0 || isSpeActive || maxSlope > 12.0) {
    missionStatus = 'CAUTION — RESTRICTED';
    missionStatusColor = '#f59e0b';
  }

  // Trigger automated spoken alerts based on real-time route conditions
  useEffect(() => {
    if (returnExceeded) {
      audioAlerts.triggerAlert({
        message: 'Return safety limit exceeded. Reconsider the route.',
        severity: 'CRITICAL',
        key: 'return_exceeded',
      });
    } else if (planetaryProtectionAssessment && !planetaryProtectionAssessment.human_route_approved) {
      audioAlerts.triggerAlert({
        message: 'Planetary protection restricted buffer breached. Human ingress prohibited.',
        severity: 'CRITICAL',
        key: 'planetary_protection_breach',
      });
    } else if (isSpeActive) {
      audioAlerts.triggerAlert({
        message: 'Solar storm radiation spike. Seek topographic shelter.',
        severity: 'WARNING',
        key: 'solar_storm_warning',
      });
    } else if (maxSlope > 12.0) {
      audioAlerts.triggerAlert({
        message: 'Terrain hazard detected ahead. Steep corridor gradient.',
        severity: 'WARNING',
        key: 'terrain_hazard_steep',
      });
    } else if (simulatedO2Pct < 25) {
      audioAlerts.triggerAlert({
        message: 'Simulated suit oxygen reserve is low.',
        severity: 'WARNING',
        key: 'o2_low_warning',
      });
    } else if (simulatedBatteryPct < 20) {
      audioAlerts.triggerAlert({
        message: 'Simulated suit battery reserve is low.',
        severity: 'WARNING',
        key: 'battery_low_warning',
      });
    }
  }, [returnExceeded, planetaryProtectionAssessment?.human_route_approved, isSpeActive, maxSlope, simulatedO2Pct, simulatedBatteryPct]);

  const toggleAudio = () => {
    const nextVal = !audioEnabled;
    audioAlerts.setEnabled(nextVal);
    if (nextVal) {
      audioAlerts.triggerAlert({
        message: 'Audio hazard alerts online.',
        severity: 'ADVISORY',
        force: true,
      });
    }
  };

  return (
    <div className="suit-hud-floating-container">
      {/* Top Floating HUD Bar */}
      <div className="suit-hud-header-bar glass-hud">
        <div className="hud-badge-group">
          <span className="hud-live-dot pulse-dot" />
          <strong className="hud-title">ASTRONAUT SUIT HUD</strong>
          <span className="hud-sub-label">EVA-01 FIELD TABLET</span>
        </div>

        {/* Center Active Alert Ticker */}
        {activeAlert && (
          <div className={`hud-alert-ticker ${activeAlert.severity.toLowerCase()}`}>
            <span className="ticker-icon">
              {activeAlert.severity === 'CRITICAL' ? '🚨' : '⚠️'}
            </span>
            <span className="ticker-text">{activeAlert.message}</span>
          </div>
        )}

        {/* Audio Toggle & Controls */}
        <div className="hud-controls-group">
          <button
            type="button"
            className={`btn-hud-audio ${audioEnabled ? 'audio-active' : 'audio-muted'}`}
            onClick={toggleAudio}
            title={speechSupported ? 'Toggle Web Speech API Hazard Alerts' : 'Speech synthesis unsupported in this browser'}
          >
            {audioEnabled ? '🔊 AUDIO ALERTS ON' : '🔇 AUDIO ALERTS OFF'}
          </button>
          <button
            type="button"
            className={`btn-hud-spe ${isSpeActive ? 'is-active' : ''}`}
            onClick={onToggleSpe}
            title="Toggle Solar Storm Radiation Scenario"
          >
            {isSpeActive ? '⚡ SOLAR STORM ON' : '☀️ SOLAR STORM OFF'}
          </button>
          <button
            type="button"
            className="btn-hud-dismiss"
            onClick={onClose}
            title="Switch back to standard map view"
          >
            ✕ EXIT HUD
          </button>
        </div>
      </div>

      {/* Compact Visor Gauges Strip */}
      <div className="suit-hud-metrics-strip glass-hud">
        {/* Suit Oxygen */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">🫁</span>
            <span className="label">O₂ REMAINING</span>
            <span className="sim-chip">SIMULATED</span>
          </div>
          <div className="metric-body">
            <span
              className="val-large mono"
              style={{ color: simulatedO2Pct < 25 ? '#ef4444' : '#00e676' }}
            >
              {simulatedO2Pct}%
            </span>
            <span className="sub-val mono">{simulatedO2RemainingHours}h / 8.0h</span>
          </div>
          <div className="metric-progress-track">
            <div
              className="metric-progress-bar"
              style={{
                width: `${simulatedO2Pct}%`,
                backgroundColor: simulatedO2Pct < 25 ? '#ef4444' : '#00e676',
              }}
            />
          </div>
        </div>

        {/* Suit Battery */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">🔋</span>
            <span className="label">BATTERY</span>
            <span className="sim-chip">SIMULATED</span>
          </div>
          <div className="metric-body">
            <span
              className="val-large mono"
              style={{ color: simulatedBatteryPct < 20 ? '#ef4444' : '#38bdf8' }}
            >
              {simulatedBatteryPct}%
            </span>
            <span className="sub-val mono">Thermal & CO₂ scrubber</span>
          </div>
          <div className="metric-progress-track">
            <div
              className="metric-progress-bar"
              style={{
                width: `${simulatedBatteryPct}%`,
                backgroundColor: simulatedBatteryPct < 20 ? '#ef4444' : '#38bdf8',
              }}
            />
          </div>
        </div>

        {/* Mission Elapsed Time */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">⏱️</span>
            <span className="label">MISSION ELAPSED</span>
          </div>
          <div className="metric-body">
            <span className="val-large mono text-amber">{formatMet(metSeconds)}</span>
            <span className="sub-val mono">MET (Sol 2026)</span>
          </div>
          <div className="status-mini-tag">ACTIVE TRAVERSE</div>
        </div>

        {/* Route Hazard Level */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">⚠️</span>
            <span className="label">ROUTE HAZARD</span>
          </div>
          <div className="metric-body">
            <span className="val-large" style={{ color: hazardColor, fontSize: '15px', fontWeight: 700 }}>
              {hazardLevel}
            </span>
            <span className="sub-val mono">Max Slope: {maxSlope.toFixed(1)}°</span>
          </div>
          <div className="status-mini-tag" style={{ borderColor: hazardColor, color: hazardColor }}>
            {maxSlope <= 6 ? 'LOW EFFORT' : maxSlope <= 12 ? 'MODERATE INCLINE' : 'STEEP ESCARPMENT'}
          </div>
        </div>

        {/* Distance Remaining */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">📍</span>
            <span className="label">DISTANCE REMAINING</span>
          </div>
          <div className="metric-body">
            <span className="val-large mono">
              {totalDistM >= 1000 ? `${(totalDistM / 1000).toFixed(2)} km` : `${Math.round(totalDistM)} m`}
            </span>
            <span className="sub-val mono">To: {destination?.name || 'Destination'}</span>
          </div>
          <div className="status-mini-tag">CORRIDOR WAYPOINT</div>
        </div>

        {/* Estimated Return Time */}
        <div className="hud-metric-card">
          <div className="metric-header">
            <span className="icon">🔄</span>
            <span className="label">EST. RETURN TIME</span>
          </div>
          <div className="metric-body">
            <span
              className="val-large mono"
              style={{ color: returnExceeded ? '#ef4444' : '#00e676' }}
            >
              {onFoot?.walk_back_duration_formatted || `${Math.round(walkDurationHours * 60)}m`}
            </span>
            <span className="sub-val mono">
              Margin: {emergencyMarginPct.toFixed(0)}% (Ceiling: 3.5h)
            </span>
          </div>
          <div
            className="status-mini-tag"
            style={{
              borderColor: returnExceeded ? '#ef4444' : '#00e676',
              color: returnExceeded ? '#ef4444' : '#00e676',
            }}
          >
            {returnExceeded ? 'EXCEEDS SAFE WALK-BACK' : 'FEASIBLE ON FOOT'}
          </div>
        </div>

        {/* Mission Safety Status */}
        <div className="hud-metric-card status-card">
          <div className="metric-header">
            <span className="icon">🛡️</span>
            <span className="label">MISSION SAFETY STATUS</span>
          </div>
          <div className="metric-body">
            <span
              className="val-large"
              style={{ color: missionStatusColor, fontSize: '14px', fontWeight: 800 }}
            >
              {missionStatus}
            </span>
            <span className="sub-val mono">
              {isSpeActive ? 'SPE STORM DERATING ACTIVE' : 'NOMINAL GCR BACKGROUND'}
            </span>
          </div>
          <div
            className="status-pill-solid"
            style={{ backgroundColor: `${missionStatusColor}26`, color: missionStatusColor, borderColor: missionStatusColor }}
          >
            {returnExceeded ? 'NON-VIABLE RETURN' : !planetaryProtectionAssessment?.human_route_approved ? 'GEOFENCE VIOLATION' : 'CLEARED FOR TRANSIT'}
          </div>
        </div>
      </div>
    </div>
  );
}
