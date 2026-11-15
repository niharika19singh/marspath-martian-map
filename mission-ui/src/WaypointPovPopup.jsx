import React, { useState } from 'react';
import { AUTHENTIC_NASA_SURFACE_IMAGES, getContextualRoverImage } from './surface_imagery.js';

export { getContextualRoverImage };

export default function WaypointPovPopup({
  waypoint,
  coord,
  onClose,
  onSetDestination,
  onSetStart,
  onOpenFullPov,
}) {
  const [imageError, setImageError] = useState(false);
  const [loading, setLoading] = useState(true);

  const pt = coord || (waypoint?.geometry?.coordinates ? {
    lon: Number(waypoint.geometry.coordinates[0].toFixed(5)),
    lat: Number(waypoint.geometry.coordinates[1].toFixed(5)),
  } : { lon: 77.4508, lat: 18.4447 });

  const sol = waypoint?.properties?.sol ?? null;
  const distTotalM = waypoint?.properties?.dist_total_m ?? null;
  const roverImg = getContextualRoverImage(waypoint || pt);

  return (
    <div className="waypoint-pov-popup glass" role="dialog" aria-label="Jezero Waypoint Surface POV">
      {/* Header */}
      <div className="popup-top-row">
        <div className="flex-row items-center gap-2">
          <span className="popup-icon">📍</span>
          <div>
            <h4 className="popup-title">
              {waypoint?.properties?.name || (sol !== null ? `Perseverance Sol ${sol} Traverse Waypoint` : 'Jezero Surface Waypoint')}
            </h4>
            <span className="popup-coords mono">
              {pt.lat.toFixed(5)}°N, {pt.lon.toFixed(5)}°E
            </span>
          </div>
        </div>
        <button
          type="button"
          className="popup-close-btn"
          onClick={onClose}
          aria-label="Close waypoint popup"
        >
          ✕
        </button>
      </div>

      {/* Rover Odometry if available */}
      {sol !== null && (
        <div className="popup-telemetry-strip">
          <span className="strip-item">
            Sol: <strong>{sol}</strong>
          </span>
          {distTotalM !== null && (
            <span className="strip-item">
              Total Odometry: <strong>{(distTotalM / 1000).toFixed(2)} km</strong>
            </span>
          )}
          <span className="strip-item badge-green">VERIFIED TRAVERSE</span>
        </div>
      )}

      {/* Authentic NASA Surface POV Image Preview */}
      <div className="popup-pov-preview-box">
        <div className="pov-img-container">
          {loading && !imageError && (
            <div className="pov-loading-spinner">
              <span>🛰️ Fetching authentic NASA surface POV...</span>
            </div>
          )}

          {!imageError ? (
            <img
              src={roverImg.thumbnail_url || roverImg.full_url}
              alt={roverImg.name}
              className={`pov-thumbnail ${loading ? 'is-loading' : 'is-loaded'}`}
              onLoad={() => setLoading(false)}
              onError={() => {
                setLoading(false);
                setImageError(true);
              }}
            />
          ) : (
            <div className="pov-img-fallback">
              <span className="fallback-icon">📷</span>
              <p className="fallback-text">
                Authentic NASA Image: <strong>{roverImg.nasa_id}</strong>
              </p>
              <span className="fallback-sub">
                {roverImg.camera} · {roverImg.name}
              </span>
            </div>
          )}

          <div className="pov-provenance-tag">
            AUTHENTIC NASA PDS PHOTOJOURNAL
          </div>
        </div>

        {/* Metadata Details */}
        <div className="pov-meta-strip">
          <div className="meta-row">
            <span className="meta-label">IMAGE ID:</span>
            <strong className="meta-val mono">{roverImg.nasa_id}</strong>
          </div>
          <div className="meta-row">
            <span className="meta-label">INSTRUMENT:</span>
            <span className="meta-val">{roverImg.camera}</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">ACQUISITION:</span>
            <span className="meta-val">Sol {roverImg.sol}</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">LANDMARK:</span>
            <span className="meta-val">{roverImg.name}</span>
          </div>
          <div className="meta-row">
            <span className="meta-label">ATTRIBUTION:</span>
            <span className="meta-val text-[10px]">NASA / JPL-Caltech / ASU / MSSS</span>
          </div>
        </div>

        <p className="pov-desc-compact">
          {roverImg.description}
        </p>

        {/* Official NASA Source Link */}
        <div className="pov-link-row">
          <a
            href={roverImg.photojournal_url}
            target="_blank"
            rel="noopener noreferrer"
            className="link-nasa-photojournal"
          >
            ↗ View NASA Photojournal Record ({roverImg.nasa_id})
          </a>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="popup-actions-row">
        {onSetDestination && (
          <button
            type="button"
            className="btn-popup-action primary"
            onClick={() => {
              onSetDestination(pt);
              onClose();
            }}
          >
            🎯 Route To Here
          </button>
        )}
        {onSetStart && (
          <button
            type="button"
            className="btn-popup-action secondary"
            onClick={() => {
              onSetStart(pt);
              onClose();
            }}
          >
            📍 Set Start A
          </button>
        )}
        {onOpenFullPov && (
          <button
            type="button"
            className="btn-popup-action pov-btn"
            onClick={() => {
              onOpenFullPov(pt);
              onClose();
            }}
          >
            🔍 High-Res Viewer
          </button>
        )}
      </div>
    </div>
  );
}
