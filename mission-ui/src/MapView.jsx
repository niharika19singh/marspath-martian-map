import React, { useEffect, useRef, useState } from 'react';
import Map from 'ol/Map.js';
import View from 'ol/View.js';
import ImageLayer from 'ol/layer/Image.js';
import VectorLayer from 'ol/layer/Vector.js';
import ImageStatic from 'ol/source/ImageStatic.js';
import VectorSource from 'ol/source/Vector.js';
import Projection from 'ol/proj/Projection.js';
import Feature from 'ol/Feature.js';
import Point from 'ol/geom/Point.js';
import LineString from 'ol/geom/LineString.js';
import Polygon from 'ol/geom/Polygon.js';
import Overlay from 'ol/Overlay.js';
import { Style, Stroke, Fill, Circle as CircleStyle, Text } from 'ol/style.js';
import { ScaleLine } from 'ol/control.js';
import { project, unproject, extentFor, rasterImage } from './terrain.js';
import Icon from './Icons.jsx';
import Terrain3D from './Terrain3D.jsx';

export default function MapView(props) {
  const {
    historyMode,
    drives = [],
    waypoints = [],
    showHistory = true,
    showWaypoints = true,
    historyFit,
    waypoint,
    onWaypoint,
    terrain,
    start,
    destination,
    scienceWaypoints = [],
    pick,
    onPin,
    base,
    hazards,
    coverage,
    maxSlope,
    maxRough,
    response,
    selected,
    onSelectRoute,
    hover,
    fitToken,
    live,
    backendStatus,
    provenance,
    showRoute = true,
    showAlternatives = false,
    hoveredRoute = null,
    view3d = false,
    exaggeration = 6,
    layersOpen,
    onLayersToggle,
    onTiltToggle,
    profileExpanded,
    actionsRef
  } = props;

  useEffect(() => {
    fetch('/mission-data/jezero-hirise.json')
      .then(r => (r.ok ? r.json() : null))
      .then(setHiriseMeta)
      .catch(() => {});
  }, []);

  const node = useRef();
  const mapRef = useRef();
  const layers = useRef({});
  const callbacks = useRef({});
  const terrain3D = useRef();
  const midLabel = useRef();
  const [locationVisible, setLocationVisible] = useState(true);
  const [hiriseMeta, setHiriseMeta] = useState(null);
  const [hint, setHint] = useState(() => !localStorage.getItem('marspath-map-hint-dismissed'));

  callbacks.current = { onPin, onSelectRoute, pick, props };

  const interact = () => {
    setHint(false);
    setLocationVisible(false);
    localStorage.setItem('marspath-map-hint-dismissed', '1');
  };

  useEffect(() => {
    const timeout = setTimeout(() => setLocationVisible(false), 4500);
    return () => clearTimeout(timeout);
  }, []);

  useEffect(() => {
    if (!terrain || !node.current) return;
    const extent = extentFor(terrain.b);
    const projection = new Projection({ code: 'MARSPATH:JEZERO_METERS', units: 'm', extent });
    const relief = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(terrain, 'relief'), imageExtent: extent, projection })
    });
    const imagery = new ImageLayer({
      source: new ImageStatic({
        url: '/mission-data/jezero-imagery.jpg',
        imageExtent: extentFor(terrain.raw.imagery_bounds || terrain.b),
        projection
      })
    });
    const hillshade = new ImageLayer({
      source: new ImageStatic({ url: rasterImage(terrain, 'hillshade'), imageExtent: extent, projection }),
      opacity: 0.75
    });
    const hirise = new ImageLayer();
    const risk = new ImageLayer();
    const data = new ImageLayer();
    const historyLayer = new VectorLayer({ source: new VectorSource(), zIndex: 15 });
    const historyPins = new VectorLayer({ source: new VectorSource(), zIndex: 17 });
    const routes = new VectorLayer({ source: new VectorSource(), zIndex: 20 });
    const pins = new VectorLayer({ source: new VectorSource(), zIndex: 22 });
    const hoverLayer = new VectorLayer({ source: new VectorSource(), zIndex: 24 });

    const map = new Map({
      target: node.current,
      layers: [relief, imagery, hirise, hillshade, data, risk, historyLayer, historyPins, routes, pins, hoverLayer],
      view: new View({
        projection,
        center: project(77.47, 18.405),
        resolution: 42,
        constrainOnlyCenter: true,
        minResolution: 0.5,
        maxResolution: 450,
        extent
      }),
      controls: [new ScaleLine({ units: 'metric' })]
    });

    const element = document.createElement('div');
    element.className = 'route-midpoint glass';
    const label = new Overlay({ element, positioning: 'bottom-center', offset: [0, -20], stopEvent: false });
    map.addOverlay(label);
    midLabel.current = label;

    layers.current = {
      projection,
      extent,
      relief,
      imagery,
      hirise,
      hillshade,
      risk,
      data,
      historyLayer,
      historyPins,
      routes,
      pins,
      hoverLayer
    };
    mapRef.current = map;

    map.on('singleclick', e => {
      interact();
      let routeId = null;
      let recorded = null;
      map.forEachFeatureAtPixel(
        e.pixel,
        f => {
          if (f.get('waypoint')) {
            recorded = f.get('waypoint');
            return true;
          }
          if (f.get('driveRecord')) {
            recorded = f.get('driveRecord');
            return true;
          }
          if (f.get('routeId')) {
            routeId = f.get('routeId');
            return true;
          }
        },
        { hitTolerance: 5 }
      );

      if (recorded && !callbacks.current.pick) {
        if (recorded.geometry.type === 'Point') {
          callbacks.current.props.onWaypoint?.(recorded);
        } else {
          callbacks.current.props.onWaypoint?.(
            callbacks.current.props.waypoints.findLast(w => w.properties.sol <= recorded.properties.sol)
          );
        }
        return;
      }
      if (routeId && !callbacks.current.pick) {
        callbacks.current.onSelectRoute(routeId);
        return;
      }
      callbacks.current.onPin(unproject(...e.coordinate));
    });

    map.on('pointerdrag', interact);
    map.on('movestart', () => {
      if (map.getView().getInteracting()) interact();
    });

    const observer = new ResizeObserver(() => map.updateSize());
    observer.observe(node.current);

    let frame,
      last = 0;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    function animate(t) {
      frame = requestAnimationFrame(animate);
      if (document.hidden || reduced || t - last < 42) return;
      last = t;
      if (callbacks.current.props.showRoute !== false) {
        routes.changed();
        pins.changed();
      }
    }
    frame = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      map.setTarget(null);
      mapRef.current = null;
    };
  }, [terrain]);

  useEffect(() => {
    if (!terrain || !mapRef.current) return;
    const l = layers.current;
    l.imagery.setVisible(base === 'imagery');
    l.relief.setVisible(base !== 'imagery');
    l.relief.setSource(
      new ImageStatic({
        url: rasterImage(terrain, base === 'hirise' ? 'context' : 'relief'),
        imageExtent: l.extent,
        projection: l.projection
      })
    );
    l.hirise.setVisible(base === 'hirise');
    l.hillshade.setVisible(base !== 'hirise');
    l.risk.setSource(
      new ImageStatic({
        url: rasterImage(terrain, 'hazards', maxSlope, maxRough),
        imageExtent: l.extent,
        projection: l.projection,
        interpolate: true
      })
    );
    l.data.setSource(
      new ImageStatic({ url: rasterImage(terrain, 'coverage'), imageExtent: l.extent, projection: l.projection })
    );
    l.risk.setVisible(hazards && !live);
    l.data.setVisible(coverage && !live);
  }, [terrain, base, hazards, coverage, maxSlope, maxRough, live]);

  useEffect(() => {
    if (!terrain || !hiriseMeta || !mapRef.current) return;
    const l = layers.current;
    l.hirise.setSource(
      new ImageStatic({
        url: '/mission-data/jezero-hirise.webp',
        imageExtent: extentFor(hiriseMeta.bounds),
        projection: l.projection,
        interpolate: true
      })
    );
    l.hirise.setVisible(base === 'hirise');
  }, [terrain, hiriseMeta]);

  // Render Start, Destination, and intermediate Science Waypoints
  useEffect(() => {
    if (!mapRef.current) return;
    const src = layers.current.pins.getSource();
    src.clear();

    const pinList = [
      [start, 'A', 'start'],
      [destination, 'B', 'destination'],
      ...scienceWaypoints.map((wp, idx) => [wp, `W${idx + 1}`, `waypoint-${idx}`])
    ];

    pinList.forEach(([p, label, type]) => {
      if (!Number.isFinite(Number(p.lon)) || !Number.isFinite(Number(p.lat))) return;
      const f = new Feature(new Point(project(Number(p.lon), Number(p.lat))));
      const isIntermediate = type.startsWith('waypoint');
      f.setStyle(() => {
        if (!callbacks.current.props.showRoute && !callbacks.current.pick) return null;
        const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
        const phase = reduced ? 0 : (performance.now() % 2600) / 2600;
        const strokeColor = isIntermediate ? `rgba(211,140,228,${(1 - phase) * 0.3})` : `rgba(92,255,176,${(1 - phase) * 0.25})`;
        const pinBorderColor = isIntermediate ? '#d38ce4' : '#9becbf';
        const pinTextColor = isIntermediate ? '#f8e6fd' : '#d7f6e5';
        const pinBgColor = isIntermediate ? '#1c1221ed' : '#0a1b15ed';

        return [
          new Style({
            image: new CircleStyle({
              radius: 14 + phase * 14,
              stroke: new Stroke({ color: strokeColor, width: 1 })
            })
          }),
          new Style({
            image: new CircleStyle({
              radius: 12,
              fill: new Fill({ color: pinBgColor }),
              stroke: new Stroke({ color: pinBorderColor, width: 1.5 })
            }),
            text: new Text({
              text: label,
              font: '600 11px Inter, sans-serif',
              fill: new Fill({ color: pinTextColor })
            })
          })
        ];
      });
      src.addFeature(f);
    });
  }, [terrain, start, destination, scienceWaypoints]);

  // Render Route Vectors & Segment Evidence
  useEffect(() => {
    if (!mapRef.current) return;
    const src = layers.current.routes.getSource();
    src.clear();
    if (!response) return;

    [...response.routes].reverse().forEach(r => {
      const primary = r.score_rank === 1;
      const line = new LineString(r.geometry.coordinates.map(c => project(c[0], c[1])));
      const f = new Feature({ geometry: line, routeId: r.route_id });
      const flow = new Stroke({ color: '#d6ffe7bb', width: 1.5, lineDash: [8, 22] });
      const styles = primary
        ? [
            new Style({ stroke: new Stroke({ color: '#000000aa', width: 10 }) }),
            new Style({ stroke: new Stroke({ color: '#5cffb04d', width: 8 }) }),
            new Style({ stroke: new Stroke({ color: '#5cffb0', width: 5 }) }),
            new Style({ stroke: flow })
          ]
        : [
            new Style({ stroke: new Stroke({ color: '#0c171dcc', width: 4 }) }),
            new Style({ stroke: new Stroke({ color: '#b7c5c580', width: 2, lineDash: [6, 5] }) })
          ];

      f.setStyle(() => {
        const p = callbacks.current.props;
        if (!p.showRoute) return null;
        if (!primary && !p.showAlternatives && r.route_id !== p.selected && r.route_id !== p.hoveredRoute) return null;
        flow.setLineDashOffset(matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : -performance.now() / 60);
        return styles;
      });
      src.addFeature(f);

      // Render hazard & segment evidence overlays
      if (live && hazards) {
        for (const s of r.evidence_passport?.segments || []) {
          const startCoord = s.from_coord || { lon: s.start_lon, lat: s.start_lat };
          const endCoord = s.to_coord || { lon: s.end_lon, lat: s.end_lat };
          if (startCoord?.lon === undefined || endCoord?.lon === undefined) continue;

          const isInvalidOrNoData = s.is_valid_data === false || s.quality_flags?.includes('invalid_or_nodata_segment');
          const isNearNoData = s.quality_flags?.includes('near_nodata_boundary');
          const isHighHazard = s.slope_deg > 12 || s.roughness > 0.5;

          if (isInvalidOrNoData) {
            const segFeature = new Feature(
              new LineString([project(startCoord.lon, startCoord.lat), project(endCoord.lon, endCoord.lat)])
            );
            segFeature.setStyle(
              new Style({
                stroke: new Stroke({ color: '#e05252dd', width: 7, lineDash: [6, 6] })
              })
            );
            src.addFeature(segFeature);
          } else if (isNearNoData) {
            const segFeature = new Feature(
              new LineString([project(startCoord.lon, startCoord.lat), project(endCoord.lon, endCoord.lat)])
            );
            segFeature.setStyle(
              new Style({
                stroke: new Stroke({ color: '#e5a038aa', width: 6, lineDash: [8, 4] })
              })
            );
            src.addFeature(segFeature);
          } else if (isHighHazard) {
            const segFeature = new Feature(
              new LineString([project(startCoord.lon, startCoord.lat), project(endCoord.lon, endCoord.lat)])
            );
            segFeature.setStyle(
              new Style({
                stroke: new Stroke({ color: '#c38a6c88', width: 7 })
              })
            );
            src.addFeature(segFeature);
          }
        }
      }
    });

    if (live && coverage && backendStatus?.pilot_bounds) {
      const b = backendStatus.pilot_bounds;
      const e = extentFor([b.min_lon, b.min_lat, b.max_lon, b.max_lat]);
      const f = new Feature(new Polygon([[[e[0], e[1]], [e[2], e[1]], [e[2], e[3]], [e[0], e[3]], [e[0], e[1]]]]));
      f.setStyle(
        new Style({
          stroke: new Stroke({ color: '#83c5aa66', width: 1, lineDash: [5, 5] }),
          fill: new Fill({ color: '#7dc5a812' })
        })
      );
      src.addFeature(f);
    }
  }, [terrain, response, live, hazards, coverage, backendStatus]);

  useEffect(() => {
    if (!mapRef.current) return;
    layers.current.routes.changed();
    layers.current.pins.changed();
    const route = response?.routes.find(r => r.route_id === selected) || response?.routes[0];
    if (route && showRoute && !view3d) {
      const line = new LineString(route.geometry.coordinates.map(c => project(c[0], c[1])));
      const dist = (route.summary.total_distance_meters / 1000).toFixed(2) + ' km';
      const duration = Number.isFinite(route.summary.estimated_duration_hours)
        ? route.summary.estimated_duration_hours.toFixed(1) + ' h'
        : 'Duration unobserved';
      midLabel.current.getElement().textContent = `${dist} · ${duration}`;
      midLabel.current.setPosition(line.getCoordinateAt(0.5));
    } else {
      midLabel.current?.setPosition(undefined);
    }
  }, [terrain, response, selected, showRoute, showAlternatives, hoveredRoute, view3d]);

  // Recorded Historical Traverse
  useEffect(() => {
    if (!mapRef.current) return;
    const l = layers.current;
    const source = l.historyLayer.getSource();
    const pins = l.historyPins.getSource();
    source.clear();
    pins.clear();
    l.historyLayer.setVisible(showHistory);
    l.historyPins.setVisible(showHistory && showWaypoints);

    for (const drive of drives) {
      const f = new Feature({
        geometry: new LineString(drive.geometry.coordinates.map(c => project(c[0], c[1]))),
        driveRecord: drive
      });
      f.setStyle([
        new Style({ stroke: new Stroke({ color: '#101318ed', width: 8, lineCap: 'round', lineJoin: 'round' }) }),
        new Style({ stroke: new Stroke({ color: '#ffb867', width: 4, lineCap: 'round', lineJoin: 'round' }) }),
        new Style({ stroke: new Stroke({ color: '#ffe1aa', width: 1 }) })
      ]);
      source.addFeature(f);
    }

    waypoints.forEach((w, i) => {
      const latest = i === waypoints.length - 1;
      const chosen = w === waypoint;
      const c = w.geometry.coordinates;
      const f = new Feature({ geometry: new Point(project(c[0], c[1])), waypoint: w });
      f.setStyle((feature, resolution) => {
        const ring = latest || chosen || i % 25 === 0 || resolution < 2;
        return [
          new Style({
            image: new CircleStyle({
              radius: latest ? 7 : chosen ? 6 : 2.5,
              fill: new Fill({ color: latest ? '#87f1ee' : chosen ? '#f6a7f3' : '#c982d9' }),
              stroke: new Stroke({ color: '#18151e', width: 1.5 })
            })
          }),
          ...(ring
            ? [
                new Style({
                  image: new CircleStyle({
                    radius: latest ? 15 : chosen ? 20 : 10,
                    stroke: new Stroke({ color: latest ? '#8bf3eeaa' : '#d38ce4aa', width: 1.5 })
                  }),
                  text:
                    latest || chosen
                      ? new Text({
                          text: 'Sol ' + w.properties.sol,
                          font: '500 12px Inter, sans-serif',
                          offsetY: -24,
                          fill: new Fill({ color: '#f7e5fd' }),
                          stroke: new Stroke({ color: '#10151a', width: 4 })
                        })
                      : undefined
                })
              ]
            : [])
        ];
      });
      pins.addFeature(f);
    });
  }, [terrain, drives, waypoints, showHistory, showWaypoints, waypoint]);

  function fitHistory() {
    if (view3d) {
      terrain3D.current?.fit();
      return;
    }
    const coords = drives.flatMap(f => f.geometry.coordinates).map(c => project(c[0], c[1]));
    if (!coords.length || !mapRef.current) return;
    const xs = coords.map(p => p[0]);
    const ys = coords.map(p => p[1]);
    const mobile = innerWidth < 850;
    mapRef.current.getView().fit(
      [Math.min(...xs) - 250, Math.min(...ys) - 250, Math.max(...xs) + 250, Math.max(...ys) + 250],
      {
        padding: mobile ? [200, 75, 150, 25] : [90, 125, 160, 395],
        duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450,
        minResolution: 0.8
      }
    );
  }

  useEffect(() => {
    if (historyMode) fitHistory();
  }, [terrain, historyFit]);

  const fit = () => {
    if (historyMode) {
      fitHistory();
      return;
    }
    if (view3d) {
      terrain3D.current?.fit();
      return;
    }
    mapRef.current?.getView().fit(layers.current.extent, {
      padding: [60, 70, 110, 70],
      duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 450
    });
  };

  const zoom = delta => {
    interact();
    if (view3d) terrain3D.current?.zoom(delta > 0 ? 1.25 : 0.8);
    else mapRef.current?.getView().animate({ zoom: mapRef.current.getView().getZoom() + delta, duration: 180 });
  };

  useEffect(() => {
    if (actionsRef) actionsRef.current = { fit, zoom };
  }, [view3d, terrain, historyMode, drives]);

  useEffect(() => {
    if (historyMode || !response || !mapRef.current) return;
    const ps = response.routes.flatMap(r => r.geometry.coordinates).map(c => project(c[0], c[1]));
    const xs = ps.map(p => p[0]);
    const ys = ps.map(p => p[1]);
    if (!ps.length) return;
    const ext = [Math.min(...xs) - 600, Math.min(...ys) - 600, Math.max(...xs) + 600, Math.max(...ys) + 600];
    const mobile = window.innerWidth < 850;
    mapRef.current.getView().fit(ext, {
      padding: mobile ? [100, 50, 140, 50] : [85, 320, 140, 370],
      duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 500,
      minResolution: 1
    });
  }, [fitToken, historyMode]);

  useEffect(() => {
    if (!mapRef.current) return;
    const s = layers.current.hoverLayer.getSource();
    s.clear();
    if (hover) {
      const f = new Feature(new Point(project(hover[0], hover[1])));
      f.setStyle(
        new Style({
          image: new CircleStyle({
            radius: 5,
            fill: new Fill({ color: '#f4d4a1' }),
            stroke: new Stroke({ color: '#202923', width: 2 })
          })
        })
      );
      s.addFeature(f);
    }
  }, [terrain, hover]);

  const pickInstruction = pick
    ? pick === 'start'
      ? 'Click terrain to place start point A'
      : pick === 'destination'
      ? 'Click terrain to place destination point B'
      : 'Click terrain to place science waypoint'
    : 'Drag to explore. Scroll to zoom.';

  return (
    <div className={'map-surface ' + (view3d ? 'is-3d' : '')}>
      <div
        ref={node}
        className="ol-map"
        style={{ cursor: pick ? 'crosshair' : 'grab', visibility: view3d ? 'hidden' : 'visible' }}
        tabIndex={view3d ? -1 : 0}
        aria-hidden={view3d}
        aria-label="Interactive Jezero Crater map. Select a pin tool then click to place coordinates."
      />
      {view3d && <Terrain3D ref={terrain3D} {...props} hiriseMeta={hiriseMeta} onInteract={interact} />}
      <div className="atmosphere-vignette" />
      <div className={'location-label ' + (locationVisible ? 'visible' : '')}>
        <span />
        Jezero Crater <small>18.38°N · 77.58°E</small>
      </div>
      <div className="map-control-stack glass">
        <button aria-label="Zoom in" onClick={() => zoom(1)}>
          <Icon name="plus" />
        </button>
        <button aria-label="Zoom out" onClick={() => zoom(-1)}>
          <Icon name="minus" />
        </button>
        <button
          aria-label="Fit region"
          title="Fit region"
          onClick={() => {
            interact();
            fit();
          }}
        >
          <Icon name="fit" />
        </button>
      </div>
      <button
        className={'map-layers-button glass icon-button ' + (layersOpen ? 'active' : '')}
        onClick={onLayersToggle}
        aria-label="Map layers"
        aria-expanded={layersOpen}
        title="Map layers"
      >
        <Icon name="layers" />
      </button>
      <button
        className={'map-tilt-button glass icon-button ' + (view3d ? 'active' : '')}
        onClick={onTiltToggle}
        aria-label={view3d ? 'Switch to 2D map' : 'Switch to 3D terrain'}
        title={view3d ? '2D map' : '3D terrain'}
        aria-pressed={view3d}
      >
        <Icon name="cube" />
        <small>{view3d ? '3D' : '2D'}</small>
      </button>
      {(pick || hint) && <div className="map-instruction glass">{pickInstruction}</div>}
      <div className="map-source">
        {base === 'hirise'
          ? 'HiRISE where available · regional relief in gaps · NASA/JPL/USGS'
          : base === 'imagery'
          ? 'NASA/JPL Mars Trek imagery'
          : 'USGS MOLA–HRSC terrain'}{' '}
        ·{' '}
        {live
          ? provenance?.isSynthetic
            ? `Reference basemap only · Routing: Synthetic (${provenance.dataMode})`
            : `Reference basemap · Routing: Python API (${provenance?.dataMode || 'real'})`
          : 'Routing DEM: 200 m'}
      </div>
    </div>
  );
}
