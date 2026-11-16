import React, { useState, useEffect } from 'react';
import './visor.css';
import Icon from './Icons.jsx';
import {
  HABITAT_BASE_COORD,
  SPE_SEVERITY_LEVELS,
  JEZERO_RADIATION_SHELTERS,
  findNearestShelter,
  assessWalkBackSafety,
  evaluateRFCommunications,
  computeMarswalkSurvivabilityScore,
  evaluateCompoundRisk,
} from './survivability.js';

/**
 * Astronaut Visor HUD (Field Execution Mode)
 * 
 * Provides an astronaut tactical field helmet HUD for real-time EVA operations:
 * - Compass tape & bearing ribbon (0-360°) with target & base vectors
 * - Suit oxygen reserve & consumption telemetry [SIMULATED]
 * - Suit battery level & power draw [ASSUMED]
 * - Minetti mechanical energy expenditure & metabolic wattage
 * - Live slope & roughness warnings
 * - Solar Particle Event (SPE) alert status & shelter beacon
 * - Direct RF line-of-sight & orbiter pass status
 * - Walk-back emergency radius geofence status
 */
export default function VisorHUD({
  activeRoute,
  destination,
  start,
  speActive = false,
  speSeverity = 'S2',
  evaBudgetHours = 8.0,
  onClose,
  onToggleSpe,
  onSelectSpeSeverity,
  onTargetShelter,
}) {
  const summary = activeRoute?.summary || {};
  const currentPos = destination || HABITAT_BASE_COORD;
  
  // Calculate bearings and metrics
  const distToBaseM = Math.round(
    Math.hypot(
      ((currentPos.lon || 77.45) - HABITAT_BASE_COORD.lon) * 59274,
      ((currentPos.lat || 18.44) - HABITAT_BASE_COORD.lat) * 59274
    )
  );

  // Bearing to base in degrees (0 = North, 90 = East, etc.)
  const dLon = HABITAT_BASE_COORD.lon - (currentPos.lon || 77.45);
  const dLat = HABITAT_BASE_COORD.lat - (currentPos.lat || 18.44);
  let baseBearingDeg = Math.round((Math.atan2(dLon, dLat) * 180) / Math.PI);
  if (baseBearingDeg < 0) baseBearingDeg += 360;

  // Bearing to target waypoint
  const targetLon = (destination?.lon || 77.42) - HABITAT_BASE_COORD.lon;
  const targetLat = (destination?.lat || 18.41) - HABITAT_BASE_COORD.lat;
  let targetBearingDeg = Math.round((Math.atan2(targetLon, targetLat) * 180) / Math.PI);
  if (targetBearingDeg < 0) targetBearingDeg += 360;

  // Current heading simulation
  const [currentHeading, setCurrentHeading] = useState(targetBearingDeg);
  const [simulatedElapsedMinutes, setSimulatedElapsedMinutes] = useState(74);

  // Nearest radiation shelter
  const nearestShelter = findNearestShelter(currentPos);

  // Walk-back safety evaluation
  const walkBack = assessWalkBackSafety(destination, HABITAT_BASE_COORD, { evaBudgetHours });

  // Survivability assessment
  const survivability = computeMarswalkSurvivabilityScore(activeRoute, {
    speActive,
    speSeverity,
    evaBudgetHours,
  });

  // RF communications
  const comms = evaluateRFCommunications(summary);

  // Compound risk
  const compoundRisk = evaluateCompoundRisk(summary, { speActive, speSeverity });

  // Minetti mechanical exertion calculations
  const avgSlope = summary.average_slope_deg ?? 2.8;
  const maxSlope = summary.max_slope_deg ?? 6.4;
  // Minetti cost in J/(kg*m): C = 280.5*i^5 - 58.7*i^4 - 289.8*i^3 + 33.3*i^2 + 40.4*i + 3.6 where i = tan(slope)
  const slopeRad = (avgSlope * Math.PI) / 180;
  const grad = Math.tan(slopeRad);
  const minettiCostJ = Math.max(
    2.5,
    Math.round((280.5 * Math.pow(grad, 5) - 58.7 * Math.pow(grad, 4) - 289.8 * Math.pow(grad, 3) + 33.3 * Math.pow(grad, 2) + 40.4 * grad + 3.6) * 10) / 10
  );
  // Total mass: 80 kg astronaut + 55 kg EMU suit = 135 kg. Walking speed: 1.0 m/s -> Watts = J/(kg*m) * kg * m/s
  const metabolicWatts = Math.round(minettiCostJ * 135 * 1.0);

  // Simulated suit telemetry
  const totalBudgetSec = evaBudgetHours * 3600;
  const elapsedSec = simulatedElapsedMinutes * 60;
  const remainingSec = Math.max(0, totalBudgetSec - elapsedSec);
  const remH = Math.floor(remainingSec / 3600);
  const remM = Math.floor((remainingSec % 3600) / 60);
  const remS = Math.floor(remainingSec % 60);
  const timeFormatted = `${String(remH).padStart(2, '0')}:${String(remM).padStart(2, '0')}:${String(remS).padStart(2, '0')}`;

  const o2ReservePct = Math.max(12, Math.round(100 - (simulatedElapsedMinutes / (evaBudgetHours * 60)) * 75));
  const o2RateKgH = (0.75 + (metabolicWatts / 1000) * 0.4).toFixed(2);
  const batteryReservePct = Math.max(15, Math.round(100 - (simulatedElapsedMinutes / (evaBudgetHours * 60)) * 68));
  const batteryDrawW = Math.round(360 + (metabolicWatts / 100) * 15);

  // Keyboard shortcut ESC to exit Visor HUD
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="visor-hud-overlay" role="region" aria-label="Astronaut Visor Tactical HUD">
      {/* Helmet Visor Vignette and Reticle Grid */}
      <div className="visor-frame-top-left" />
      <div className="visor-frame-top-right" />
      <div className="visor-frame-bottom-left" />
      <div className="visor-frame-bottom-right" />
      <div className="visor-grid-scanlines" />

      {/* TOP HEADER: Sol, Mission, Heading Tape & Exit Control */}
      <header className="visor-hud-header">
        <div className="visor-mission-tag">
          <span className="live-dot" />
          <span className="mission-title">EVA TACTICAL VISOR</span>
          <span className="sol-badge">SOL 2022</span>
          <span className="crew-badge">CREW-1 · PERSEVERANCE TRAIL</span>
        </div>

        {/* Digital Compass Tape & Bearing Indicator */}
        <div className="visor-compass-container" aria-label="Digital Compass Tape">
          <div className="compass-pointer" />
          <div className="compass-tape-track">
            {[-60, -45, -30, -15, 0, 15, 30, 45, 60].map((offset) => {
              const deg = (currentHeading + offset + 360) % 360;
              const isCardinal = deg === 0 || deg === 90 || deg === 180 || deg === 270;
              const cardinalLabel = deg === 0 ? 'N' : deg === 90 ? 'E' : deg === 180 ? 'S' : deg === 270 ? 'W' : `${deg}°`;
              return (
                <div key={offset} className={`compass-tick ${isCardinal ? 'cardinal' : ''}`}>
                  <span className="tick-line" />
                  <span className="tick-val">{cardinalLabel}</span>
                </div>
              );
            })}
          </div>
          <div className="compass-bearing-hud">
            <strong>{String(currentHeading).padStart(3, '0')}°</strong>
            <span className="bearing-sub">HDG</span>
          </div>
        </div>

        <div className="visor-header-actions">
          <button
            className="visor-exit-button"
            onClick={onClose}
            aria-label="Exit Visor HUD and return to Mission Control"
            title="Press ESC or click to exit Visor mode"
          >
            <Icon name="close" />
            <span>RETURN TO MISSION CONTROL</span>
            <kbd>ESC</kbd>
          </button>
        </div>
      </header>

      {/* CRITICAL ALERT BANNERS */}
      <div className="visor-critical-banners">
        {speActive && (
          <div className="visor-alert-banner alert-radiation" role="alert">
            <span className="alert-icon">☀️ ☢️</span>
            <div className="alert-body">
              <strong>CRITICAL SOLAR PARTICLE EVENT ACTIVE — LEVEL {speSeverity}</strong>
              <span>
                Surface dose: <strong>{SPE_SEVERITY_LEVELS[speSeverity]?.doseRateMsvH} mSv/h</strong> (Normal: 0.05 mSv/h). 
                Immediate terrain sheltering required! Nearest shelter: <strong>{nearestShelter.name}</strong> ({nearestShelter.distanceM} m, bearing {nearestShelter.bearingDeg}°).
              </span>
            </div>
            {onTargetShelter && (
              <button
                className="visor-action-btn pulse-glow"
                onClick={() => onTargetShelter(nearestShelter)}
              >
                NAVIGATE TO SHELTER
              </button>
            )}
          </div>
        )}

        {!walkBack.safe && (
          <div className="visor-alert-banner alert-walkback" role="alert">
            <span className="alert-icon">⚠️ 🚶‍♂️</span>
            <div className="alert-body">
              <strong>WALK-BACK SAFETY EXCEEDED — ROVER SUPPORT MANDATORY</strong>
              <span>
                Target is <strong>{walkBack.distKm} km</strong> from Base (Safe on-foot ceiling: <strong>1.8 km</strong>). 
                Return walk requires <strong>{walkBack.walkDurationH} hrs</strong> at 1.0 m/s. Maintain rover rendezvous.
              </span>
            </div>
          </div>
        )}

        {maxSlope > 15 && (
          <div className="visor-alert-banner alert-slope" role="alert">
            <span className="alert-icon">📐 ⚠️</span>
            <div className="alert-body">
              <strong>STEEP TERRAIN WARNING — MAX SLOPE {maxSlope.toFixed(1)}°</strong>
              <span>Approaching EMU suit rollover and traction boundary limit (15°). Reduce stride and engage slope stabilization.</span>
            </div>
          </div>
        )}
      </div>

      {/* THREE-COLUMN TACTICAL HUD WORKSPACE */}
      <main className="visor-tactical-workspace">
        {/* COLUMN 1: LIFE SUPPORT & BIO-MECHANICS (LEFT STACK) */}
        <section className="visor-column visor-col-left" aria-label="Life Support & Bio-Mechanics">
          <div className="visor-card visor-card-life-support">
            <div className="visor-card-header">
              <span className="card-badge">PLSS</span>
              <h3>SUIT LIFE SUPPORT &amp; METABOLISM</h3>
              <span className="sim-tag">[SIMULATED SUIT TELEMETRY]</span>
            </div>

            {/* Suit Oxygen */}
            <div className="telemetry-bar-block">
              <div className="telemetry-label-row">
                <span>O₂ RESERVE</span>
                <strong className={o2ReservePct < 25 ? 'crit' : o2ReservePct < 40 ? 'warn' : 'ok'}>
                  {o2ReservePct}% · {(o2ReservePct * 0.08).toFixed(1)} hrs left
                </strong>
              </div>
              <div className="meter-track">
                <div
                  className={`meter-fill ${o2ReservePct < 25 ? 'crit' : o2ReservePct < 40 ? 'warn' : 'ok'}`}
                  style={{ width: `${o2ReservePct}%` }}
                />
              </div>
              <div className="telemetry-sub-row">
                <span>Rate: {o2RateKgH} kg/h</span>
                <span>Pressure: 29.6 kPa (Nominal)</span>
              </div>
            </div>

            {/* Suit Power / Battery */}
            <div className="telemetry-bar-block">
              <div className="telemetry-label-row">
                <span>EMU BATTERY POWER</span>
                <strong className={batteryReservePct < 25 ? 'crit' : batteryReservePct < 40 ? 'warn' : 'ok'}>
                  {batteryReservePct}% · {(batteryReservePct * 0.06).toFixed(1)} hrs left
                </strong>
              </div>
              <div className="meter-track">
                <div
                  className={`meter-fill battery ${batteryReservePct < 25 ? 'crit' : batteryReservePct < 40 ? 'warn' : 'ok'}`}
                  style={{ width: `${batteryReservePct}%` }}
                />
              </div>
              <div className="telemetry-sub-row">
                <span>Draw: {batteryDrawW} W</span>
                <span>Cell Temp: 19.4°C</span>
              </div>
            </div>

            {/* Minetti Mechanical Energy & Metabolic Rate */}
            <div className="minetti-box">
              <div className="minetti-title">
                <span>MINETTI BIOMECHANICAL EFFORT</span>
                <span className="method-pill">COST OF TRANSPORT</span>
              </div>
              <div className="minetti-metrics-grid">
                <div className="m-metric">
                  <span className="m-val">{minettiCostJ}</span>
                  <span className="m-unit">J / (kg·m)</span>
                  <span className="m-lbl">Specific Energy</span>
                </div>
                <div className="m-metric">
                  <span className="m-val">{metabolicWatts}</span>
                  <span className="m-unit">Watts</span>
                  <span className="m-lbl">Metabolic Expenditure</span>
                </div>
              </div>
              <div className="minetti-rating">
                <span>Exertion Index:</span>
                <strong className={metabolicWatts > 450 ? 'crit' : metabolicWatts > 320 ? 'warn' : 'ok'}>
                  {metabolicWatts > 450 ? 'HEAVY WORK (HIGH FATIGUE)' : metabolicWatts > 320 ? 'MODERATE TRAVERSE' : 'NOMINAL HIKE'}
                </strong>
              </div>
            </div>

            {/* EVA Time Countdown Clock */}
            <div className="eva-countdown-box">
              <span className="countdown-lbl">EVA TIME REMAINING</span>
              <span className="countdown-val">{timeFormatted}</span>
              <span className="countdown-sub">
                BUDGET: {evaBudgetHours.toFixed(1)}h · ELAPSED: {(simulatedElapsedMinutes / 60).toFixed(1)}h
              </span>
            </div>
          </div>
        </section>

        {/* COLUMN 2: TACTICAL RETICLE & WAYPOINT NAVIGATION (CENTER STACK) */}
        <section className="visor-column visor-col-center" aria-label="Tactical Navigation Reticle">
          {/* Target Reticle Crosshair */}
          <div className="tactical-reticle">
            <div className="reticle-circle outer" />
            <div className="reticle-circle inner" />
            <div className="reticle-axis-x" />
            <div className="reticle-axis-y" />

            {/* Direction Vector Arrow to Target */}
            <div
              className="bearing-vector target-vector"
              style={{ transform: `rotate(${targetBearingDeg - currentHeading}deg)` }}
              title={`Target Waypoint: ${targetBearingDeg}°`}
            >
              <div className="vector-head" />
              <span className="vector-label">WP ({targetBearingDeg}°)</span>
            </div>

            {/* Return-to-Base Direction Vector Arrow */}
            <div
              className="bearing-vector base-vector"
              style={{ transform: `rotate(${baseBearingDeg - currentHeading}deg)` }}
              title={`Return to Base Habitat: ${baseBearingDeg}°`}
            >
              <div className="vector-head base" />
              <span className="vector-label base">BASE ({baseBearingDeg}°)</span>
            </div>

            {/* Central HUD Target Data Card */}
            <div className="reticle-target-hud">
              <span className="target-type">NEXT OBJECTIVE</span>
              <h2 className="target-name">{destination?.name || 'Selected Waypoint'}</h2>
              <div className="target-stats">
                <div className="stat">
                  <span className="val">{distToBaseM.toLocaleString()} m</span>
                  <span className="lbl">RANGE TO BASE</span>
                </div>
                <div className="stat-divider" />
                <div className="stat">
                  <span className="val">{targetBearingDeg}°</span>
                  <span className="lbl">BEARING</span>
                </div>
                <div className="stat-divider" />
                <div className="stat">
                  <span className="val">{((summary.total_distance_meters || 1200) / 1000).toFixed(2)} km</span>
                  <span className="lbl">ROUTE DISTANCE</span>
                </div>
              </div>
            </div>
          </div>

          {/* Terrain & Route Attitude Indicators */}
          <div className="visor-terrain-attitude-bar">
            <div className="att-card">
              <span className="att-label">MEAN / MAX SLOPE</span>
              <strong className={maxSlope > 15 ? 'crit' : maxSlope > 10 ? 'warn' : 'ok'}>
                {avgSlope.toFixed(1)}° / {maxSlope.toFixed(1)}°
              </strong>
              <small>{maxSlope <= 15 ? 'WITHIN TRACTION ENVELOPE' : 'STEEP TRACTION THRESHOLD'}</small>
            </div>
            <div className="att-card">
              <span className="att-label">SURFACE ROUGHNESS</span>
              <strong>{(summary.max_roughness ?? 0.22).toFixed(2)}</strong>
              <small>FIRM REGOLITH / SUB-METER ROCK</small>
            </div>
            <div className="att-card">
              <span className="att-label">WALK-BACK SAFETY STATUS</span>
              <strong className={walkBack.safe ? 'ok' : 'crit'}>
                {walkBack.safe ? 'INSIDE SAFE FOOT RADIUS' : 'EXCEEDS FOOT LIMIT (5.2 km)'}
              </strong>
              <small>{walkBack.safe ? 'RETURN ON FOOT FEASIBLE' : 'ROVER SUPPORT MANDATORY'}</small>
            </div>
          </div>
        </section>

        {/* COLUMN 3: ENVIRONMENTAL, RADIATION & RF COMMS (RIGHT STACK) */}
        <section className="visor-column visor-col-right" aria-label="Environmental Hazards & RF Comms">
          {/* Survivability Score Summary */}
          <div className="visor-card visor-card-survivability">
            <div className="visor-card-header">
              <span className="card-badge">INDEX</span>
              <h3>MARSWALK SURVIVABILITY</h3>
              <span className="sim-tag">0-100</span>
            </div>
            <div className="survivability-score-display">
              <div className="score-ring-hud" style={{ borderColor: survivability.color }}>
                <span className="score-num" style={{ color: survivability.color }}>{survivability.score}</span>
                <span className="score-max">/ 100</span>
              </div>
              <div className="score-intel">
                <strong style={{ color: survivability.color }}>{survivability.tier}</strong>
                <p>{survivability.label}</p>
                <div className="subfactor-pills">
                  <span title="Terrain Mobility">Mobility: {survivability.factors?.mobility?.score ?? survivability.factors?.mobility ?? 95}%</span>
                  <span title="Life Support Margin">O₂/Pwr: {survivability.factors?.resources?.score ?? survivability.factors?.resources ?? 90}%</span>
                  <span title="Return Feasibility">Return: {survivability.factors?.returnFeasibility?.score ?? survivability.factors?.return_feasibility?.score ?? 92}%</span>
                  <span title="Radiation Safety">Rad: {survivability.factors?.radiation?.score ?? survivability.factors?.radiation ?? 95}%</span>
                </div>
              </div>
            </div>
          </div>

          {/* Radiation Monitor & SPE Controller */}
          <div className={`visor-card visor-card-radiation ${speActive ? 'is-spe-active' : ''}`}>
            <div className="visor-card-header">
              <span className="card-badge">RAD</span>
              <h3>SPACE RADIATION MONITOR</h3>
              <span className={`status-pill ${speActive ? 'crit' : 'ok'}`}>
                {speActive ? `ACTIVE (${speSeverity})` : 'NOMINAL GCR'}
              </span>
            </div>
            <div className="rad-telemetry-row">
              <div className="rad-val-box">
                <span className="val">
                  {speActive ? SPE_SEVERITY_LEVELS[speSeverity]?.doseRateMsvH : '0.05'}
                </span>
                <span className="unit">mSv / hr</span>
                <span className="lbl">SURFACE DOSE RATE</span>
              </div>
              <div className="rad-val-box">
                <span className="val">
                  {speActive ? (SPE_SEVERITY_LEVELS[speSeverity]?.doseRateMsvH * (summary.estimated_duration_hours || 2.0)).toFixed(1) : '0.1'}
                </span>
                <span className="unit">mSv</span>
                <span className="lbl">PROJECTED ROUTE DOSE</span>
              </div>
            </div>

            {/* Nearest Shelter Callout */}
            <div className="shelter-callout">
              <div className="shelter-head">
                <span className="shelter-pin">🛡️</span>
                <strong>NEAREST TERRAIN SHELTER:</strong>
              </div>
              <div className="shelter-details">
                <span className="shelter-name">{nearestShelter.name}</span>
                <span className="shelter-meta">
                  {nearestShelter.distanceM} m away · Bearing {nearestShelter.bearingDeg}° · {(nearestShelter.shieldingFactor * 100).toFixed(0)}% Shielding
                </span>
              </div>
            </div>

            {/* SPE Simulator Controls */}
            <div className="spe-visor-controls">
              <button
                className={`spe-toggle-btn ${speActive ? 'active' : ''}`}
                onClick={onToggleSpe}
              >
                {speActive ? '☀️ CANCEL SPE SIMULATION' : '☀️ SIMULATE SOLAR PARTICLE EVENT'}
              </button>
              {speActive && (
                <div className="spe-severity-buttons">
                  {['S1', 'S2', 'S3', 'S4'].map((sev) => (
                    <button
                      key={sev}
                      className={`sev-btn ${speSeverity === sev ? 'active' : ''}`}
                      onClick={() => onSelectSpeSeverity?.(sev)}
                      title={`${SPE_SEVERITY_LEVELS[sev]?.label}: ${SPE_SEVERITY_LEVELS[sev]?.doseRateMsvH} mSv/h`}
                    >
                      {sev}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RF Communications & Orbiter Relay */}
          <div className="visor-card visor-card-comms">
            <div className="visor-card-header">
              <span className="card-badge">UHF/RF</span>
              <h3>COMMUNICATIONS &amp; ORBITER RELAYS</h3>
              <span className="status-pill" style={{ color: comms.labelColor, borderColor: comms.labelColor }}>
                {comms.status}
              </span>
            </div>
            <div className="comms-hud-grid">
              <div className="c-item">
                <span className="c-val">{comms.losBasePercentage}%</span>
                <span className="c-lbl">LOS Direct to Base</span>
              </div>
              <div className="c-item">
                <span className="c-val">T-42m</span>
                <span className="c-lbl">Next Orbiter Pass</span>
              </div>
            </div>
            <p className="comms-advice">{comms.advice}</p>
          </div>
        </section>
      </main>

      {/* FOOTER CONTROLS & SCIENCE REMINDER */}
      <footer className="visor-hud-footer">
        <div className="visor-footer-left">
          <span className="status-indicator nominal" />
          <span>HUD HARDWARE: NOMINAL</span>
          <span className="footer-pipe">|</span>
          <span>HELMET COMM: UHF CH-4 ENCRYPTED</span>
          <span className="footer-pipe">|</span>
          <span>AUTHENTIC PDS CARTOGRAPHY · MOLA/HRSC DEM ENGINE</span>
        </div>
        <div className="visor-footer-right">
          <button className="footer-action-btn" onClick={() => setCurrentHeading((h) => (h + 15) % 360)}>
            ⟳ ROTATE HEADING
          </button>
          <button className="footer-action-btn" onClick={onClose}>
            RETURN TO MISSION CONTROL
          </button>
        </div>
      </footer>
    </div>
  );
}
