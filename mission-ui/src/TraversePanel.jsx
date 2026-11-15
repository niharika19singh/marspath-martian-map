import React from 'react';
import Icon from './Icons.jsx';

export function TraversePanel({
  data,
  stats,
  windowStats,
  selected,
  onFit,
  onExport,
  onPlan,
  error,
  solCut,
  windowSize = 15,
}) {
  const p = selected?.properties || stats?.latest?.properties;
  const startSol = Math.max(0, (solCut ?? 2022) - windowSize + 1);
  const endSol = solCut ?? 2022;
  const hasDrivesInWindow = (windowStats?.segments ?? stats?.segments ?? 0) > 0;

  return (
    <div className="traverse-panel">
      <div className="rover-identity">
        <span className="rover-symbol">
          <Icon name="crosshair" />
        </span>
        <div>
          <h2>Perseverance Rover</h2>
          <p>Jezero Crater · Complete recorded traverse</p>
        </div>
      </div>

      <p className="traverse-description">
        Continuous archive of all published drive segments from landing through Sol {data?.features?.at(-1)?.properties?.sol ?? 2022}.
        Passive track shows complete travel history; gold highlighting isolates the selected 15-sol observation window.
      </p>

      {error && <p className="error-message">{error}</p>}

      <div className="traverse-stats">
        <div>
          <small>Total archive distance</small>
          <strong>
            {Number.isFinite(stats?.distance) ? (stats.distance / 1000).toFixed(2) : '45.25'} <span>km</span>
          </strong>
        </div>
        <div>
          <small>Total drive segments</small>
          <strong>{data?.features?.length ?? 559}</strong>
        </div>
      </div>

      <div className="window-stats-badge" style={{ marginTop: '10px', padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,184,103,0.08)', border: '1px solid rgba(255,184,103,0.22)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <small style={{ color: '#ffb867', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Active Window: 15 sols (Sol {startSol}–{endSol})
          </small>
          <span style={{ font: '11px var(--mono)', color: '#ffe2b8' }}>
            {hasDrivesInWindow ? `${windowStats?.segments ?? 0} drives` : '0 drives'}
          </span>
        </div>
        {!hasDrivesInWindow && (
          <p style={{ margin: '6px 0 0', fontSize: '11px', color: '#ffbb70' }}>
            No recorded drives in this window (rover stationary, sampling, or data gap). Full passive traverse remains visible.
          </p>
        )}
      </div>

      <button className="plan-button" onClick={onFit} style={{ marginTop: '14px' }}>
        Fit full traverse <Icon name="fit" />
      </button>

      <div className="waypoint-inspector">
        <div className="eyebrow">{selected ? 'Selected waypoint' : `Active position (Sol ${p?.sol ?? endSol})`}</div>
        {p ? (
          <>
            <div className="waypoint-line">
              <b>Sol {p.sol}</b>
              <span>Site {p.site ?? '—'} · drive {p.drive ?? '—'}</span>
            </div>
            <p>{p.Note || 'Recorded rover localization'}</p>
            <div className="waypoint-location">
              {Number(p.lat ?? (selected || stats?.latest)?.geometry?.coordinates?.[1] ?? 18.435).toFixed(5)}°N,{' '}
              {Number(p.lon ?? (selected || stats?.latest)?.geometry?.coordinates?.[0] ?? 77.233).toFixed(5)}°E
            </div>
            <button className="text-action" onClick={() => onPlan(selected || stats?.latest)}>
              Plan a route from here <Icon name="arrow" />
            </button>
          </>
        ) : (
          <p>No recorded waypoint in this range.</p>
        )}
      </div>

      <div className="history-actions">
        <button onClick={onExport} disabled={!data?.features?.length}>
          <Icon name="download" /> Export visible tracks
        </button>
        <a href={data?.marspath_metadata?.source || 'https://mars.nasa.gov'} target="_blank" rel="noopener">
          Data source <Icon name="arrow" />
        </a>
      </div>

      <p className="field-note">
        Official NASA PDS M20 traverse archive. Full recorded track remains continuously rendered across Jezero Crater.
      </p>
    </div>
  );
}

export function TraverseTimeline({
  cut,
  max,
  minSol = 14,
  stats,
  windowStats,
  onChange,
  onAll,
  onFit,
  windowSize = 15,
}) {
  const startSol = Math.max(0, cut - windowSize + 1);
  const hasDrives = (windowStats?.segments ?? 0) > 0;

  return (
    <section className="history-timeline glass" aria-label="Rover traverse 15-sol timeline scrubber">
      <div className="timeline-heading">
        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <i style={{ background: '#ffb867', width: '16px', height: '3px', borderRadius: '2px', display: 'inline-block' }} />
          <span>
            Highlighted window: <b style={{ color: '#ffb867' }}>15 sols</b> (Sol {startSol}–{cut})
          </span>
          {!hasDrives && (
            <span
              style={{
                marginLeft: '8px',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(245,158,11,0.18)',
                color: '#ffbb70',
                fontSize: '11px',
                fontWeight: 600,
              }}
            >
              No recorded drives in this window
            </span>
          )}
        </span>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          {onFit && (
            <button type="button" onClick={onFit} title="Fit entire recorded traverse in view">
              Fit full traverse
            </button>
          )}
          <button type="button" onClick={onAll} aria-pressed={cut === max}>
            Latest (Sol {max})
          </button>
        </div>
      </div>

      <div className="timeline-slider">
        <small>Sol {minSol}</small>
        <input
          type="range"
          min={minSol}
          max={max || 2022}
          step="1"
          value={cut}
          onChange={e => onChange(Number(e.target.value))}
          aria-label="Scrub traverse 15-sol window"
        />
        <span style={{ minWidth: '90px', font: '11px var(--mono)', color: '#ffe2b8' }}>
          Sol {cut} (15 sols)
        </span>
      </div>
    </section>
  );
}
