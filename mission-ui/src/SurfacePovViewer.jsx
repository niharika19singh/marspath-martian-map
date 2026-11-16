import React, { useState } from 'react';
import { AUTHENTIC_NASA_SURFACE_IMAGES } from './surface_imagery.js';

export { AUTHENTIC_NASA_SURFACE_IMAGES };

export function SurfacePovViewer({ inspectCoord, onClose }) {
  const [selectedId, setSelectedId] = useState(() => {
    if (!inspectCoord) return AUTHENTIC_NASA_SURFACE_IMAGES[0].landmark_id;
    // Find closest landmark
    let closest = AUTHENTIC_NASA_SURFACE_IMAGES[0];
    let minD = 999999;
    for (const img of AUTHENTIC_NASA_SURFACE_IMAGES) {
      const dLat = (inspectCoord.lat - img.lat) * 111320;
      const dLon = (inspectCoord.lon - img.lon) * 111320 * Math.cos(img.lat * Math.PI / 180);
      const d = Math.sqrt(dLat * dLat + dLon * dLon);
      if (d < minD) {
        minD = d;
        closest = img;
      }
    }
    return closest.landmark_id;
  });

  const activeImage = AUTHENTIC_NASA_SURFACE_IMAGES.find(i => i.landmark_id === selectedId) || AUTHENTIC_NASA_SURFACE_IMAGES[0];

  const distanceToInspect = inspectCoord ? (() => {
    const dLat = (inspectCoord.lat - activeImage.lat) * 111320;
    const dLon = (inspectCoord.lon - activeImage.lon) * 111320 * Math.cos(activeImage.lat * Math.PI / 180);
    const dMeters = Math.sqrt(dLat * dLat + dLon * dLon);
    return dMeters < 1000 ? `${Math.round(dMeters)} m` : `${(dMeters / 1000).toFixed(2)} km`;
  })() : null;

  return (
    <div className="surface-pov-modal glass">
      <div className="surface-pov-header">
        <div className="pov-title-group">
          <span className="pov-badge">📷 AUTHENTIC NASA SURFACE POV</span>
          <h3>Perseverance Mastcam-Z Ground Imagery</h3>
          <span className="pov-subtitle">Official NASA JPL / PDS Photojournal Planetary Records</span>
        </div>
        {onClose && (
          <button type="button" className="btn-close-pov" onClick={onClose} title="Close POV Viewer">
            ✕
          </button>
        )}
      </div>

      <div className="surface-pov-selector-tabs">
        {AUTHENTIC_NASA_SURFACE_IMAGES.map(img => (
          <button
            key={img.landmark_id}
            type="button"
            className={`pov-tab-btn ${img.landmark_id === selectedId ? 'active' : ''}`}
            onClick={() => setSelectedId(img.landmark_id)}
          >
            <span className="pov-tab-name">{img.name.split(' (')[0]}</span>
            <span className="pov-tab-sol">Sol {img.sol} · {img.nasa_id}</span>
          </button>
        ))}
      </div>

      <div className="surface-pov-main-display">
        <div className="surface-pov-image-card">
          <div className="pov-img-frame">
            <img
              src={activeImage.full_url}
              alt={activeImage.name}
              className="pov-full-img"
              loading="lazy"
              onError={(e) => {
                if (activeImage.external_fallback_url && e.target.src !== activeImage.external_fallback_url) {
                  e.target.src = activeImage.external_fallback_url;
                } else if (activeImage.thumbnail_url && e.target.src !== activeImage.thumbnail_url) {
                  e.target.src = activeImage.thumbnail_url;
                }
              }}
            />
            <div className="pov-img-overlay-info">
              <span className="overlay-pill">Sol {activeImage.sol} · {activeImage.camera}</span>
              <span className="overlay-pill id-pill">{activeImage.nasa_id}</span>
            </div>
          </div>

          <div className="pov-details-pane">
            <h4>{activeImage.name}</h4>
            <p className="pov-desc">{activeImage.description}</p>

            <div className="pov-meta-grid">
              <div className="pov-meta-item">
                <span className="meta-lbl">COORDINATES</span>
                <span className="meta-val mono">{activeImage.lat.toFixed(4)}°N, {activeImage.lon.toFixed(4)}°E</span>
              </div>
              <div className="pov-meta-item">
                <span className="meta-lbl">DISTANCE FROM PIN</span>
                <span className="meta-val mono">{distanceToInspect || 'Nearby'}</span>
              </div>
              <div className="pov-meta-item">
                <span className="meta-lbl">MISSION ACQUISITION</span>
                <span className="meta-val">Sol {activeImage.sol} (Mars 2020)</span>
              </div>
              <div className="pov-meta-item">
                <span className="meta-lbl">IMAGING INSTRUMENT</span>
                <span className="meta-val">{activeImage.camera}</span>
              </div>
            </div>

            <div className="pov-terrain-note">
              <strong>SURFACE TERRAMECHANICS INSIGHT:</strong>
              <p>{activeImage.scientific_context}</p>
            </div>

            <div className="pov-provenance-bar">
              <span className="prov-status">✅ Official NASA JPL / Caltech Release</span>
              <a
                href={activeImage.photojournal_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-pds-link"
              >
                View on NASA JPL Photojournal ({activeImage.nasa_id}) ↗
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
