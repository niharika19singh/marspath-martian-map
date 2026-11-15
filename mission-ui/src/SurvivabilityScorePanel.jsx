import React, { useState } from 'react';
import { calculateMarswalkScore, getSurvivabilityTier } from './survivability_scoring.js';

export default function SurvivabilityScorePanel({
  activeRoute,
  walkBackAssessment,
  isStormActive,
  onToggleStorm,
  evaBudgetHours = 8.0,
}) {
  const [showFormulaDetails, setShowFormulaDetails] = useState(false);

  const totalDistM = activeRoute?.summary?.total_distance_meters ?? 1420;
  const maxSlope = activeRoute?.summary?.max_slope_deg ?? 4.2;
  const durationHours = activeRoute?.summary?.estimated_duration_hours ?? 0.85;
  const roughnessTri = activeRoute?.summary?.roughness_tri ?? 0.22;

  const onFoot = walkBackAssessment?.on_foot_feasibility;
  const emergencyMarginPct = onFoot?.emergency_resource_margin_pct ?? 82.0;

  // Calculate score with transparent 5-factor model
  const scoreData = calculateMarswalkScore({
    maxSlopeDeg: maxSlope,
    roughnessTri: roughnessTri,
    durationHours: durationHours,
    evaBudgetHours: evaBudgetHours,
    distanceKm: totalDistM / 1000,
    emergencyMarginPct: emergencyMarginPct,
    isStormActive: isStormActive,
    shelterDistanceM: activeRoute?.marswalk_survivability?.shelter_proximity_meters ?? null,
  });

  const tier = scoreData.tier;

  return (
    <div className="survivability-score-card glass">
      {/* Header with Title and Solar Storm Scenario Toggle */}
      <div className="card-top-row items-center justify-between">
        <div className="flex-row items-center gap-2">
          <span className="pulse-dot green" />
          <h4 className="section-title-sm">MARSWALK SURVIVABILITY SCORE</h4>
        </div>

        {/* Solar Storm Scenario Toggle Button */}
        <button
          type="button"
          className={`btn-storm-toggle ${isStormActive ? 'storm-active' : 'storm-off'}`}
          onClick={onToggleStorm}
          title="Toggle Simulated Solar Storm (SPE) Scenario"
        >
          {isStormActive ? '⚡ SOLAR STORM SCENARIO — ON' : '☀️ SOLAR STORM SCENARIO — OFF'}
        </button>
      </div>

      {/* Prominent Simulated Solar Storm Alert Banner */}
      {isStormActive && (
        <div className="storm-scenario-alert-banner">
          <div className="storm-alert-icon">⚡</div>
          <div className="storm-alert-body">
            <div className="storm-alert-tag">[SIMULATED SCENARIO ONLY — NASA ANALOG DRILL]</div>
            <strong className="storm-alert-title">
              SOLAR PARTICLE EVENT (SPE CLASS X2.5) ACTIVE
            </strong>
            <p className="storm-alert-desc">
              Acute solar proton radiation flux modeled at <strong>~48.5 mSv/h</strong>.
              Safe-return emergency envelope <strong>tightened by 30%</strong>.
              Immediate egress to designated natural topographic shelter recommended.
            </p>
          </div>
        </div>
      )}

      {/* Main Score Display Area */}
      <div className="score-hero-display">
        <div className="score-circle-container">
          <div
            className="score-circle"
            style={{
              borderColor: tier.color,
              boxShadow: `0 0 24px ${tier.color}33`,
            }}
          >
            <span className="score-number mono" style={{ color: tier.color }}>
              {scoreData.score.toFixed(0)}
            </span>
            <span className="score-total">/100</span>
          </div>
        </div>

        <div className="score-summary-text">
          <div className="tier-badge-pill" style={{ backgroundColor: `${tier.color}22`, color: tier.color, borderColor: tier.color }}>
            {tier.badge} · {tier.label}
          </div>
          <p className="score-narrative">
            {isStormActive ? (
              <>
                Corridor survivability reduced from nominal <strong>{scoreData.nominal_score}/100</strong> to <strong>{scoreData.score}/100</strong> due to acute solar particle flux deduction (-{scoreData.stormDeduction} pts).
                {scoreData.shelter_bonus > 0 && <span> Topographic shelter proximity bonus: <strong>+{scoreData.shelter_bonus} pts</strong>.</span>}
              </>
            ) : (
              <>
                Modeled traverse conditions demonstrate <strong>{tier.label.toLowerCase()}</strong> with comfortable slope gradients ({maxSlope.toFixed(1)}°) and {emergencyMarginPct.toFixed(0)}% emergency return margin.
              </>
            )}
          </p>

          {/* Storm Envelope Tightening Notice */}
          {isStormActive && (
            <div className="envelope-tightening-callout">
              ⚠️ <strong>Safe-Return Envelope Tightened:</strong> Maximum permitted walking limit derated by 30% (from 3.5h to 2.45h). Turnaround margin reduced.
            </div>
          )}
        </div>
      </div>

      {/* Factor Breakdown Accordion / Toggle */}
      <div className="factors-breakdown-section">
        <div className="flex-row items-center justify-between mb-2">
          <span className="text-xs uppercase tracking-wider text-slate-400 font-mono font-bold">
            TRANSPARENT 5-FACTOR MODEL BREAKDOWN
          </span>
          <button
            type="button"
            className="btn-toggle-formula"
            onClick={() => setShowFormulaDetails(!showFormulaDetails)}
          >
            {showFormulaDetails ? 'Hide Model Assumptions ▲' : 'Inspect Formula & Weights ▼'}
          </button>
        </div>

        {/* Factor Table */}
        <div className="factors-table-wrap">
          <table className="factors-breakdown-table">
            <thead>
              <tr>
                <th>Factor</th>
                <th>Weight</th>
                <th>Measured Value</th>
                <th>Normalized (0-1)</th>
                <th>Contribution</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(scoreData.factors).map(([key, f]) => {
                const statusColor = f.status === 'NOMINAL' ? '#00e676' : f.status === 'CAUTION' ? '#f59e0b' : '#ef4444';
                return (
                  <tr key={key}>
                    <td className="font-semibold text-slate-200">
                      {f.name}
                      {showFormulaDetails && (
                        <div className="factor-assumption-sub text-slate-400 font-normal">
                          {f.assumption}
                        </div>
                      )}
                    </td>
                    <td className="mono text-slate-300">{(f.weight * 100).toFixed(0)}%</td>
                    <td className="mono font-bold text-slate-100">{f.raw}</td>
                    <td className="mono">{f.normalized.toFixed(2)}</td>
                    <td className="mono font-bold text-slate-100">{f.contribution.toFixed(1)} pts</td>
                    <td>
                      <span className="status-mini-pill" style={{ color: statusColor, borderColor: statusColor }}>
                        {f.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {isStormActive && (
                <tr className="storm-deduction-row">
                  <td className="font-semibold text-red-400">
                    ⚡ Solar Storm Radiation Flux
                    {showFormulaDetails && (
                      <div className="factor-assumption-sub text-red-300 font-normal">
                        Simulated acute proton flux (~48.5 mSv/h) with natural terrain shielding offset
                      </div>
                    )}
                  </td>
                  <td className="mono text-red-400">Modifier</td>
                  <td className="mono font-bold text-red-400">48.5 mSv/h</td>
                  <td className="mono text-red-400">—</td>
                  <td className="mono font-bold text-red-400">-{scoreData.stormDeduction} pts</td>
                  <td>
                    <span className="status-mini-pill" style={{ color: '#ef4444', borderColor: '#ef4444' }}>
                      ACUTE
                    </span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Formula Disclosure */}
        {showFormulaDetails && (
          <div className="formula-disclosure-box">
            <div className="formula-line mono">
              <strong>Formula:</strong> {scoreData.formula}
            </div>
            <p className="formula-notes text-slate-400 text-xs mt-1">
              * Weights are configurable baseline demonstration assumptions derived from terrestrial human terramechanics and Apollo/Artemis EVA analog protocols.
              {scoreData.disclaimer}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
