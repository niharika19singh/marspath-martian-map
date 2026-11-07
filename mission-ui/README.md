# MarsPath Mission Control

React 19 + Vite + OpenLayers dashboard added at `/mission-control/`. The existing NASA landing and catalogue remain available. The Mission Control navigation link opens this planner.

## What works

- Mars-specific equirectangular metric map and coordinate/pin selection in the Jezero extract.
- Real, bundled USGS MOLA–HRSC global 200 m v2 DEM subset (253 × 179 cells). Browser checks the dataset JSON SHA-256 before computing.
- Genuine bounded A* and Dijkstra searches in a web worker: nonnegative terrain costs, admissible distance heuristic, 8-neighbor graph, no diagonal corner cutting, slope/roughness masks and conservative nodata exclusion.
- Up to three genuinely distinct candidates. Missing alternatives are reported rather than invented. Primary route is green; alternatives are gray.
- Original backend mode weights and terrain-cost components; deterministic hazard-exposure risk categories. Both algorithms minimize weighted terrain cost, not necessarily shortest geometric distance.
- NASA/JPL Mars Trek Viking MDIM2.1 imagery and elevation-derived color relief. Imagery and terrain have separate, explicit georeferenced extents. Imagery does not determine slope or routing costs.
- Measured slope/roughness hazard overlay and valid/missing DEM coverage. No invented communications model or individual HRSC/MOLA observation footprints.
- Route selection, elevation profile linked to map hover, distance/time/elevation metrics, reconciled cost breakdown, data provenance and evidence limitations.
- JSON response-style mission manifest and selected-route GeoJSON-style planetary export. Exports include Mars CRS information and are not executable rover instructions.
- Python FastAPI connector: health, data status, layers and OpenAPI validation; request cancellation, errors and timeouts. The current contract does not accept an algorithm parameter, so live Dijkstra is disabled while remaining available in the browser planner. A deployed API URL and appropriate CORS allowlist are required; no reachable API URL was supplied.

## Provenance and limits

`extract-dem.mjs` reads only the Jezero window through HTTP range requests from the official USGS S3 GeoTIFF, not the multi-gigabyte archive. The full upstream archive checksum was not independently verified. The extract therefore carries `official_endpoint_retrieved_checksum_unverified` provenance and at most moderate terrain evidence quality, even after its local file integrity is verified. This is regional topographic screening, not flight-grade rover navigation or meter-scale obstacle detection.

The browser planner is an independent implementation informed by the Python routing contract. Selecting Python backend sends real requests to that API; the UI never labels browser computation as a live Python response. In API mode the bundled map remains a reference basemap. Global terrain hazard rasters are not returned by the current API, so it displays elevated-risk route segments from the returned evidence passport instead. Backend coverage indicates extract bounds, not per-sensor observations.

## Development

From this directory:

- `npm install`
- `npm run build` → `../dist/mission-control/`
- `node check-engine.mjs` → algorithm-equivalence, constraints, nodata-barrier, validation, cost reconciliation, dataset hash, and selected-route-export checks.

DEM/imagery files live in `../dist/mission-data/`. OpenLayers and React render entirely in the client; no Python runtime is embedded in the static Site.

## Validation

Production build passed. Browser QA exercised Dijkstra, candidate comparison, map-click coordinate updates, replanning, layer controls, API settings, and a completed GeoJSON download. The remote Python API connection is not verified because its deployed URL is unknown.

The generated route response was also validated against the current Python `RoutePlanResponse` Pydantic model from the repository's geospatial-routing branch. Local file integrity refers specifically to the bundled JSON extract; the full upstream GeoTIFF checksum remains unverified.

## Map-first interface

One header replaces the breadcrumb strip and footer. Route design is a collapsible 340 px glass panel; algorithm, source and constraints live in a closed Settings accordion. Analysis starts as a small distance/time card and expands to candidate selection, cost share, details and exports. The bottom profile drawer starts collapsed, expands by click or vertical drag, and links pointer scrubbing to the map. Its line colors reflect observed segment slopes.

Hazards start off and use softened amber/coral presentation; the original unblurred numerical masks and searches are unchanged. The primary route uses a mint glow and animated flow, with reduced-motion support. Alternatives appear on selection/hover or through the Layers override. Zoom/fit, layers and 2D/3D controls are consolidated; attribution is a single line. The first-interaction hint is remembered locally.

The optional 3D view projects the actual bundled DEM into a shaded mesh using Canvas 2D, so it works without WebGL. Drag orbits, wheel zooms, and the elevation exaggeration (default ×6) is explicitly labeled and adjustable. It is a regional visualization, not rover-scale geometry. Terrain relief is the default basemap; the bundled Viking imagery remains available, but its 156 × 109 px regional reference is visibly coarse at high zoom. Ctrl/Cmd+K opens quick actions. UI space is reserved at the lower right for host controls; the host's editing overlay is outside product source.

Validation after redesign: production build; DEM checksum, A*/Dijkstra optimal-cost equivalence, distinct candidates, constraints/nodata, cost reconciliation, invalid coordinates and selected-route export checks. Browser inspection covered floating panels, analysis/profile expansion, 2D/3D rendering, layer controls and command actions.

## Recorded Perseverance traverse

The default Mission Control view now shows the full official published Perseverance traverse snapshot through sol 2022. The bundled source contains 559 original LineString drive features, 36,661 source vertices and 708 recorded waypoints. No line is drawn to bridge separate source features. Source odometry at the last waypoint is 45,245.71 m; this differs from recomputing a projected polyline length.

- Drive records: https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json
- Waypoints: https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_waypoints.json
- Retrieved 6 November 2026. This is a snapshot, not a live or complete future telemetry stream. It covers Perseverance, not other rovers' landing sites.
- `Rover history` / `Route planner` switch between recorded travel and generated routes. Amber tracks with a dark casing represent recorded drives; violet points/rings show source waypoints; cyan marks the last waypoint in the selected sol range. Mint represents a computed route.
- A sol slider filters both drive segments and waypoints. `Show all travelled routes` restores all published segments and fits their bounds. Clicking a recorded waypoint or drive shows the matching waypoint details. A selected/latest waypoint can become a planning start.
- Export visible tracks emits the original filtered drive features with Mars target, source, retrieval and selected-sol metadata. Source elevations are retained, not replaced by regional DEM samples. The legacy source CRS84 declaration is omitted to avoid presenting Mars positions as terrestrial WGS84.
- The reference picture's footprint rectangles are not reproduced: verified camera observation footprints were not supplied.

The new default basemap is a grayscale georeferenced derivative of the M20 HiRISE RGB 25 cm v4p2 pyramid, sampled at zoom 14 and bundled at 3584 × 2304 px. Tile metadata: https://mars.nasa.gov/mmgis-maps/M20/Layers/M20_HiRISE_RGB_mosaic_25cm_v4p2/tilemapresource.xml. TMS y indices were converted to north-origin rows and Mercator sampling was resampled by latitude into a rectangular equirectangular image before rendering in the custom Mars projection. This derivative is coarser than the source's nominal 25 cm product; it is reference imagery, not a higher-resolution routing DEM. Coverage gaps and the western extent remain transparent with grayscale regional relief underneath. Numeric routing still uses the unchanged 200 m MOLA–HRSC extract.

The route fit now frames actual route bounds rather than a fixed 14 km box, and a center-only viewport constraint prevents the full traverse from being pushed under the floating form. Reduced motion remains supported. The 3D mesh retains its coarse DEM resolution and labeled elevation exaggeration.

Validation: `node check-traverse.mjs` checks all source segment/vertex counts, no added connections, sol cutoffs, source odometry, invalid geometry and export scope. Existing engine checks and production build pass. Browser QA covers full snapshot, empty/partial/full sol ranges, recorded-track export, route calculation, layer controls and 2D/3D rendering.
