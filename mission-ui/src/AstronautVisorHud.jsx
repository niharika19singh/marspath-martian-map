import React, { useState } from 'react';

export function AstronautVisorHud({
  activeRoute,
  destination,
  start,
  isSpeActive,
  onToggleSpe,
  onClose,
  onOpenSurfacePov,
  roverWaypoint,
  sunData,
  medaData,
}) {
  const survivability = activeRoute?.marswalk_survivability;
  const score = survivability?.score ?? 78;
  const category = survivability?.category ?? 'GOOD';
  const isSpe = isSpeActive || survivability?.is_spe_active;

  // Route metrics
  const totalDistM = activeRoute?.summary?.total_distance_meters ?? 1420;
  const maxSlope = activeRoute?.summary?.max_slope_deg ?? 4.2;
  const durationHours = activeRoute?.summary?.estimated_duration_hours ?? 0.85;

  // Simulated PLSS Consumables (explicitly labeled as simulated analog assumptions)
  const simulatedO2HoursTotal = 8.0;
  const simulatedO2RemainingHours = Math.max(0.5, (simulatedO2HoursTotal - durationHours * 2.1)).toFixed(1);
  const simulatedO2Pct = Math.round((simulatedO2RemainingHours / simulatedO2HoursTotal) * 100);
  const simulatedBatteryPct = Math.max(15, Math.round(100 - durationHours * 16.5));
  const estimatedMetabolicWatts = Math.round(280 + Math.pow(Math.max(0, maxSlope - 2), 1.6) * 22);

  // Bearing calculation from start to destination
  const bearingDeg = destination && start ? (() => {
    const dLon = (destination.lon - start.lon) * (Math.PI / 180);
    const y = Math.sin(dLon) * Math.cos(destination.lat * Math.PI / 180);
    const x = Math.cos(start.lat * Math.PI / 180) * Math.sin(destination.lat * Math.PI / 180) -
              Math.sin(start.lat * Math.PI / 180) * Math.cos(destination.lat * Math.PI / 180) * Math.cos(dLon);
    const brng = (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
    return Math.round(brng);
  })() : 284;

  // Heading compass points
  const compassPoints = [
    { label: 'N', deg: 0 },
    { label: 'NE', deg: 45 },
    { label: 'E', deg: 90 },
    { label: 'SE', deg: 135 },
    { label: 'S', deg: 180 },
    { label: 'SW', deg: 225 },
    { label: 'W', deg: 270 },
    { label: 'NW', deg: 315 },
  ];

  const getScoreColor = (sc) => {
    if (sc >= 80) return '#00ff88'; // green
    if (sc >= 65) return '#a3e635'; // lime
    if (sc >= 45) return '#f59e0b'; // amber
    if (sc >= 25) return '#f97316'; // orange
    return '#ef4444'; // red
  };

  const scoreColor = getScoreColor(score);

  // Companion rover assistance requirement
  const needsRoverAssistance = maxSlope > 9.0 || (survivability?.terrain_roughness_penalty ?? 0) > 6.0;

  return (
    <div className={`astronaut-visor-hud-overlay ${isSpe ? 'spe-mode-active' : ''}`}>
      {/* Visor Top Navigation HUD Bar */}
      <div className="visor-header-bar">
        <div className="visor-status-block">
          <span className="visor-badge-pill">🥽 ASTRONAUT FIELD VISOR HUD</span>
          <span className="visor-callsign">EVA-01 · PERSEVERANCE COMPANION FIELD UNIT</span>
        </div>

        {/* Central Heading Tape */}
        <div className="visor-heading-tape">
          <div className="heading-marker-center">▼ {bearingDeg}°</div>
          <div className="heading-ticks-strip">
            {compassPoints.map((pt) => {
              const diff = (pt.deg - bearingDeg + 540) % 360 - 180;
              if (Math.abs(diff) > 70) return null;
              return (
                <div
                  key={pt.label}
                  className="heading-tick"
                  style={{ transform: `translateX(${diff * 2.5}px)` }}
                >
                  <span className="tick-line">|</span>
                  <span className="tick-label">{pt.label}</span>
                </div>
              );
            })}
          </div>
          <div className="heading-dest-info">
            BEARING: <strong className="mono">{bearingDeg}° M-TRUE</strong> · TARGET: <strong>{destination?.name || 'Séítah Swale'}</strong>
          </div>
        </div>

        {/* Action Controls */}
        <div className="visor-action-controls">
          <button
            type="button"
            className={`btn-visor-control ${isSpe ? 'btn-spe-active' : 'btn-spe-nominal'}`}
            onClick={onToggleSpe}
            title="Toggle Solar Particle Event Radiation Scenario"
          >
            {isSpe ? '⚠️ SPE RADIATION ACTIVE' : '⚡ SIMULATE SPE'}
          </button>
          {onOpenSurfacePov && (
            <button
              type="button"
              className="btn-visor-control btn-pov"
              onClick={onOpenSurfacePov}
            >
              📷 SURFACE POV
            </button>
          )}
          <button
            type="button"
            className="btn-visor-control btn-exit-hud"
            onClick={onClose}
            title="Exit Visor HUD"
          >
            ✕ EXIT VISOR
          </button>
        </div>
      </div>

      {/* SPE Alert Banner when active */}
      {isSpe && (
        <div className="visor-spe-alert-banner">
          <span className="spe-icon">⚡</span>
          <div className="spe-text">
            <strong>SOLAR PARTICLE EVENT (SPE) IN PROGRESS:</strong> Acute space radiation flux simulated at ~48.5 mSv/h.
            Immediate seek of natural topographic shelter recommended.
            {survivability?.shelter_proximity_meters && (
              <span> Nearest designated shelter: <strong>{survivability.shelter_proximity_meters}m</strong> ({survivability.recommended_shelter_id}).</span>
            )}
          </div>
        </div>
      )}

      {/* Main Grid: Left Consumables, Center Survivability Gauge, Right Terrain & Hazard */}
      <div className="visor-hud-grid">
        {/* LEFT COLUMN: Simulated Suit Life Support Telemetry */}
        <div className="visor-card visor-left-telemetry glass">
          <div className="card-header-hud">
            <span className="card-icon">🫁</span>
            <h4>PLSS SUIT CONSUMABLES</h4>
            <span className="sim-tag">SIMULATED ASSUMPTIONS</span>
          </div>

          <div className="gauges-stack">
            {/* Oxygen Gauge */}
            <div className="gauge-item">
              <div className="gauge-label-row">
                <span>O₂ RESERVE</span>
                <span className="mono bold" style={{ color: simulatedO2Pct < 30 ? '#ef4444' : '#00ff88' }}>
                  {simulatedO2RemainingHours} hrs ({simulatedO2Pct}%)
                </span>
              </div>
              <div className="gauge-bar-track">
                <div
                  className="gauge-bar-fill"
                  style={{
                    width: `${simulatedO2Pct}%`,
                    backgroundColor: simulatedO2Pct < 30 ? '#ef4444' : '#00ff88',
                  }}
                />
              </div>
              <span className="gauge-sub">Assumed 8.0h mission PLSS tank</span>
            </div>

            {/* Battery Gauge */}
            <div className="gauge-item">
              <div className="gauge-label-row">
                <span>SUIT BATTERY</span>
                <span className="mono bold" style={{ color: simulatedBatteryPct < 25 ? '#ef4444' : '#38bdf8' }}>
                  {simulatedBatteryPct}%
                </span>
              </div>
              <div className="gauge-bar-track">
                <div
                  className="gauge-bar-fill"
                  style={{
                    width: `${simulatedBatteryPct}%`,
                    backgroundColor: simulatedBatteryPct < 25 ? '#ef4444' : '#38bdf8',
                  }}
                />
              </div>
              <span className="gauge-sub">Thermal &amp; CO₂ scrubbing load</span>
            </div>

            {/* Metabolic Exertion */}
            <div className="gauge-item">
              <div className="gauge-label-row">
                <span>METABOLIC EXERTION</span>
                <span className="mono bold" style={{ color: estimatedMetabolicWatts > 420 ? '#ef4444' : '#fbbf24' }}>
                  {estimatedMetabolicWatts} W
                </span>
              </div>
              <div className="gauge-bar-track">
                <div
                  className="gauge-bar-fill"
                  style={{
                    width: `${Math.min(100, (estimatedMetabolicWatts / 500) * 100)}%`,
                    backgroundColor: estimatedMetabolicWatts > 420 ? '#ef4444' : '#fbbf24',
                  }}
                />
              </div>
              <span className="gauge-sub">Baseline: 280W · Minetti human grade scaling</span>
            </div>

            {/* Turnaround Sunset Buffer */}
            <div className="gauge-item">
              <div className="gauge-label-row">
                <span>SUNSET ABORT MARGIN</span>
                <span className="mono bold" style={{ color: '#00ff88' }}>
                  +120 min buffer
                </span>
              </div>
              <div className="gauge-bar-track">
                <div className="gauge-bar-fill" style={{ width: '85%', backgroundColor: '#00ff88' }} />
              </div>
              <span className="gauge-sub">Local True Solar Time: {sunData?.local_true_solar_time?.value || '14:20 LTST'}</span>
            </div>
          </div>

          <div className="disclaimer-callout">
            ⚠️ <em>Simulated PLSS parameters are mathematical approximations based on Apollo/Artemis analog protocols. Always verify against flight telemetry.</em>
          </div>
        </div>

        {/* CENTER COLUMN: Marswalk Survivability Index */}
        <div className="visor-card visor-center-gauge glass">
          <div className="card-header-hud centered">
            <span className="card-icon">🛡️</span>
            <h4>MARSWALK SURVIVABILITY SCORE</h4>
          </div>

          <div className="survivability-score-circle" style={{ borderColor: scoreColor }}>
            <span className="score-number" style={{ color: scoreColor }}>{score}</span>
            <span className="score-denom">/100</span>
            <span className="score-category-pill" style={{ backgroundColor: `${scoreColor}22`, color: scoreColor, borderColor: scoreColor }}>
              {category}
            </span>
          </div>

          <p className="survivability-expl">
            {survivability?.explanation || 'Optimal suited traversal conditions. Terrain gradients remain within nominal exertion boundaries with ample consumables reserve.'}
          </p>

          {/* Contributing Factor Penalty Breakdown */}
          <div className="factors-penalty-breakdown">
            <div className="factor-pill">
              <span className="factor-name">Slope Exertion:</span>
              <span className="factor-val mono">
                {survivability?.mobility_exertion_penalty ? `-${survivability.mobility_exertion_penalty} pts` : '0 pts (Nominal)'}
              </span>
            </div>
            <div className="factor-pill">
              <span className="factor-name">Surface TRI Ruggedness:</span>
              <span className="factor-val mono">
                {survivability?.terrain_roughness_penalty ? `-${survivability.terrain_roughness_penalty} pts` : '0 pts (Smooth)'}
              </span>
            </div>
            <div className="factor-pill">
              <span className="factor-name">Consumables Budget:</span>
              <span className="factor-val mono">
                {survivability?.eva_consumables_penalty ? `-${survivability.eva_consumables_penalty} pts` : '0 pts (Ample)'}
              </span>
            </div>
            <div className="factor-pill">
              <span className="factor-name">Regolith Boot Sinkage:</span>
              <span className="factor-val mono">
                {survivability?.regolith_sinkage_penalty ? `-${survivability.regolith_sinkage_penalty} pts` : '0 pts (Firm)'}
              </span>
            </div>
            <div className="factor-pill">
              <span className="factor-name">Radiation Flux:</span>
              <span className="factor-val mono" style={{ color: isSpe ? '#ef4444' : 'inherit' }}>
                {isSpe ? `-${survivability?.radiation_exposure_penalty || 21.6} pts` : '0 pts (Nominal)'}
              </span>
            </div>
            {isSpe && survivability?.topographic_shelter_bonus > 0 && (
              <div className="factor-pill bonus">
                <span className="factor-name">Shelter Proximity Bonus:</span>
                <span className="factor-val mono" style={{ color: '#00ff88' }}>
                  +{survivability.topographic_shelter_bonus} pts
                </span>
              </div>
            )}
          </div>

          {/* Companion Rover Assistance Prompt */}
          {needsRoverAssistance ? (
            <div className="rover-assist-alert">
              <span className="assist-icon">🤖</span>
              <div>
                <strong>COMPANION ROVER ASSIST RECOMMENDED:</strong>
                <p>Terrain slope ({maxSlope.toFixed(1)}°) or blockiness exceeds solo walking comfort. Dispatch Perseverance / Companion Rover for forward winch or scout line.</p>
              </div>
            </div>
          ) : (
            <div className="rover-assist-nominal">
              <span>🤖 Companion Rover in proximity: Auto-tracking telemetry nominal.</span>
            </div>
          )}
        </div>

        {/* RIGHT COLUMN: Route & Environment Diagnostics */}
        <div className="visor-card visor-right-environment glass">
          <div className="card-header-hud">
            <span className="card-icon">🪐</span>
            <h4>TRAVERSE &amp; ENVIRONMENT</h4>
          </div>

          <div className="env-metrics-list">
            <div className="env-row">
              <span className="env-label">TOTAL DISTANCE:</span>
              <span className="env-val mono bold">
                {totalDistM >= 1000 ? `${(totalDistM / 1000).toFixed(2)} km` : `${Math.round(totalDistM)} m`}
              </span>
            </div>
            <div className="env-row">
              <span className="env-label">ESTIMATED WALK TIME:</span>
              <span className="env-val mono bold">{Math.round(durationHours * 60)} minutes</span>
            </div>
            <div className="env-row">
              <span className="env-label">MAXIMUM CORRIDOR SLOPE:</span>
              <span className="env-val mono bold" style={{ color: maxSlope > 12 ? '#ef4444' : maxSlope > 6 ? '#f59e0b' : '#00ff88' }}>
                {maxSlope.toFixed(1)}° (14.0° ceiling)
              </span>
            </div>
            <div className="env-row">
              <span className="env-label">ATMOSPHERIC PRESSURE:</span>
              <span className="env-val mono">756.4 Pa (MEDA Sol 15)</span>
            </div>
            <div className="env-row">
              <span className="env-label">AIR / GROUND TEMP:</span>
              <span className="env-val mono">-29.4°C / -10.8°C</span>
            </div>
            <div className="env-row">
              <span className="env-label">COLUMN DUST OPACITY (τ):</span>
              <span className="env-val mono">0.41 (Nominal)</span>
            </div>
            <div className="env-row">
              <span className="env-label">COMMS STATUS:</span>
              <span className="env-val mono" style={{ color: '#00ff88' }}>DIRECT LINE-OF-SIGHT (HAB/ORBITER)</span>
            </div>
          </div>

          {/* Natural Topographic Shelters */}
          <div className="topographic-shelter-box">
            <div className="shelter-header">
              <span className="shelter-icon">⛰️</span>
              <strong>DESIGNATED JEZERO SHELTERS</strong>
            </div>
            <ul className="shelter-list">
              <li>
                <strong>Western Rim Overhang:</strong> 77.215°E, 18.460°N
                <span className="shelter-spec">68% overhead proton attenuation</span>
              </li>
              <li>
                <strong>Belva Impact Terraces:</strong> 77.380°E, 18.510°N
                <span className="shelter-spec">60% cliff-face shadow attenuation</span>
              </li>
              <li>
                <strong>Séítah Ridge Swale:</strong> 77.440°E, 18.440°N
                <span className="shelter-spec">55% inter-dune trench attenuation</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
