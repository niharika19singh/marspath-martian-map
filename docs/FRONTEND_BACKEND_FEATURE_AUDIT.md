# MARSPath — Frontend & Backend Technical Feature Audit

**Document:** `docs/FRONTEND_BACKEND_FEATURE_AUDIT.md`  
**Audit Date:** 2026-11-13  
**Auditor:** Antigravity Autonomous Engineering Agent  
**Repository:** `niharika19singh/marspath-martian-map`  
**Active Production Deployments:**  
- Frontend: `https://marspath.vercel.app` (Vercel edge proxy)
- Backend: `https://marspath-backend.onrender.com` (Render Uvicorn / FastAPI service)

---

## 1. Executive Summary

This technical audit provides an exhaustive evaluation of the MARSPath Martian Route Intelligence platform across all frontend components, backend endpoints, routing engines, terrain processing pipelines, and geospatial layers.

The audit establishes:
1. **Core Routing & Provenance:** The Python backend routing engine (`POST /api/v1/routes/plan`), data status (`GET /api/v1/data/status`), and health checks (`GET /health`) are fully operational, utilizing the official USGS/ESA Jezero MOLA–HRSC blended DEM with strict cryptographic local integrity and fail-closed readiness.
2. **Reverse Proxy & Single-Origin Communication:** The frontend communicates with the backend via the Vercel edge reverse proxy (`/api/*` and `/health`), eliminating cross-origin errors and preventing exposed origin leakage.
3. **Primary Identified Deficiencies:**
   - **Dijkstra Algorithm Omission:** Although `dijkstra_search` exists in `backend/app/routing/dijkstra.py`, the backend API schema (`RoutePlanRequest`) omits the `algorithm` parameter. Consequently, `RouteService.plan_route` hardcodes `astar_search`, the OpenAPI specification advertises no algorithm selection, and the frontend disables the Dijkstra dropdown option when connected to the Python backend.
   - **Algorithm Comparison Mode Missing:** Neither backend nor frontend implements an A* vs. Dijkstra comparison mode with node expansion counts, runtime benchmarks, or optimality verification.
   - **Imagery Degradation & Blurriness:** The current map displays visible blurring, rectangular gaps, and tile seams caused by downsampled static images (`jezero-imagery.jpg` is only 156×109 pixels; `jezero-hirise.webp` contains missing tile rectangles with HTTP 403 errors; single-canvas data URLs stretched across 50 km).
   - **Initial UI Standby State Ambiguity:** On initial load before route planning is triggered, route metrics, terrain penalty, and elevation profiles display unpopulated placeholder states (`—`, `Unassessed`), which users may confuse with broken functionality.

---

## 2. Comprehensive Feature Integration Matrix

| # | Feature / Capability | Backend Implemented | Frontend Implemented | Frontend Calls Backend | Backend Returns Required Data | Frontend Renders Response | Production Status | Root Cause & What Needs Fixing |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **1** | **Rover History** | No (Static GeoJSON) | Yes | N/A (Static asset) | N/A | Yes | **Working** | Pure client-side static asset loading from `/mission-data/perseverance-traverse.geojson`. Works reliably. |
| **2** | **Route Planner** | Yes | Yes | Yes | Yes | Yes | **Working** | Connects via `POST /api/v1/routes/plan` through Vercel edge proxy to Render. |
| **3** | **Start & Destination Selection** | Yes | Yes | Yes | Yes | Yes | **Working** | Latitude/longitude inputs with planetocentric degree validation and map-click pin placement. |
| **4** | **Coordinate Selection & Pin Drop** | Yes | Yes | Yes | Yes | Yes | **Working** | Map crosshair picking mode places pins and snaps to terrain bounding box. |
| **5** | **Coordinate Swapping** | Yes | Yes | Yes | Yes | Yes | **Working** | `swap()` reverses A and B coordinates cleanly, invalidating stale state. |
| **6** | **A\* Routing** | Yes | Yes | Yes | Yes | Yes | **Working** | Executed by `backend/app/routing/astar.py` using admissible Euclidean heuristic in physical meters. |
| **7** | **Dijkstra Routing** | Partial | Partial | **No (Blocked)** | **No** | **No** | **Broken / Missing** | `RoutePlanRequest` lacks `algorithm` field; `RouteService.plan_route` hardcodes A*; frontend disables Dijkstra option when connected to Python API. |
| **8** | **Algorithm Comparison Mode** | **No** | **No** | **No** | **No** | **No** | **Unimplemented** | No comparative execution mode exists to run A* and Dijkstra against identical inputs and display side-by-side metrics. |
| **9** | **Route Alternatives (1–3)** | Yes | Yes | Yes | Yes | Yes | **Working** | Backend generates diverse corridors; frontend displays candidate cards in expandable analysis drawer. |
| **10** | **Safety-First Optimization** | Yes | Yes | Yes | Yes | Yes | **Working** | Strict 14° slope ceiling enforced by `MODE_WEIGHTS[OptimizationMode.SAFETY_FIRST]`. |
| **11** | **Balanced Optimization** | Yes | Yes | Yes | Yes | Yes | **Working** | Balances distance, slope penalty, and roughness penalty. |
| **12** | **Science-First Optimization** | Yes | Yes | Yes | Yes | Yes | **Working** | Rewards traversals near registered scientific targets. |
| **13** | **Terrain Slope Analysis** | Yes | Yes | Yes | Yes | Yes | **Working** | Horn's method slope calculations in degrees; returns `max_slope_deg`, `mean_slope_deg`, and slope penalty cost. |
| **14** | **Terrain Roughness (TRI)** | Yes | Yes | Yes | Yes | Yes | **Working** | Wilson et al. (2007) Terrain Ruggedness Index; normalized [0, 1]. |
| **15** | **Traversability Mask** | Yes | Yes | Yes | Yes | Yes | **Working** | Boolean mask excluding slopes > max slope, excessive roughness, and nodata cells. |
| **16** | **Hazard Assessment** | Yes | Yes | Yes | Yes | Yes | **Working** | Multi-factor hazard evaluation returned in `cost_breakdown.hazard_penalty` and `summary.hazard_distance_meters`. |
| **17** | **Weighted Terrain Cost** | Yes | Yes | Yes | Yes | Yes | **Working** | Exact score breakdown reconciles base distance, slope, roughness, and hazard penalties. |
| **18** | **Distance Calculation** | Yes | Yes | Yes | Yes | Yes | **Working** | Returns horizontal (2D), elevation gain/loss, and true 3D surface distance in meters. |
| **19** | **Estimated Travel Time** | Yes | Yes | Yes | Yes | Yes | **Working** | Physical rover velocity model (Bekker-type speed reduction with slope and roughness). |
| **20** | **Elevation Profile** | Yes | Partial | Yes | Yes | Partial | **Degraded** | Drawer is collapsed by default; points require 3D coordinates; needs richer metrics (avg slope, roughness profile). |
| **21** | **Maximum Slope Metric** | Yes | Yes | Yes | Yes | Yes | **Working** | Displayed in Profile handle, Details drawer, and route summaries. |
| **22** | **Ascent & Descent Metrics** | Yes | Yes | Yes | Yes | Yes | **Working** | Cumulative elevation gain and loss in meters returned and rendered. |
| **23** | **Recorded Drives & Sols** | No | Yes | N/A | N/A | Yes | **Working** | 559 Perseverance drive segments with interactive sol slider (up to Sol 2022). |
| **24** | **Recorded Waypoints** | No | Yes | N/A | N/A | Yes | **Working** | Scientifically cataloged rover sample locations and exploration stops. |
| **25** | **Scientific Waypoints (Planner)** | Yes | Partial | Partial | Yes | Partial | **Partially Implemented** | Backend schema supports `science_waypoints: list[MarsCoordinate]`, but UI lacks interactive waypoint addition tools. |
| **26** | **Route Comparison** | Yes | Yes | Yes | Yes | Yes | **Working** | Compares candidate routes (Primary vs. Alternatives 1 & 2). |
| **27** | **Route Analysis Panel** | Yes | Yes | Yes | Yes | Yes | **Working** | Expandable floating drawer with distance, duration, cost, observed terrain %, details, and evidence. |
| **28** | **Evidence & Provenance** | Yes | Yes | Yes | Yes | Yes | **Working** | Full cryptographic verification status, dataset citations, DOI, resolution, and engineering caveats. |
| **29** | **JSON Manifest Export** | Yes | Yes | Yes | Yes | Yes | **Working** | Generates complete mission planning manifest with request params, CRS, route geometry, and provenance. |
| **30** | **GeoJSON Export** | Yes | Yes | Yes | Yes | Yes | **Working** | Standard RFC 7946 FeatureCollection with LineString geometry, elevation coordinates, and feature properties. |
| **31** | **Map Basemap & Imagery Layers** | Partial | Partial | Partial | Partial | Partial | **Degraded / Blurry** | HiRISE has tile gaps and missing tiles (403 errors); background imagery is a tiny 156×109 px thumbnail stretched to regional scale; relief is a single 216×208 canvas. |
| **32** | **Zoom & Navigation Controls** | N/A | Yes | N/A | N/A | Yes | **Working** | OpenLayers zoom (+/-), region fit, and 2D/3D terrain tilt controls. |

---

## 3. Investigation of Broken & Degraded Integrations

### Issue 1: Empty Route Metrics (`Distance: — km`, `Estimated time: — hrs`, `Weighted cost: — units`, `Observed terrain: — %`)
- **Observed Behavior:** On initial application launch, the `floating-analysis` panel displays dashes (`—`) for all key metrics.
- **Root Cause Analysis:** This is an **Action Not Triggered / Initial State** issue.
  - The metrics are bound to `active?.summary.total_distance_meters` and `active?.summary.estimated_duration_hours`.
  - Prior to the user submitting the route planning form, `result` and `active` are `null`.
  - The UI does not provide an explicit callout or onboarding state explaining that the user must click **Generate route** to populate metrics.
- **Remediation:**
  - Add an active standby banner ("Standby: Configure waypoints and click Generate Route").
  - Automatically expand the analysis drawer upon successful route calculation so metrics are immediately visible.

### Issue 2: Unassessed Terrain Penalty (`Risk: Unassessed`, `Gauge: 0%`, `Awaiting a route`)
- **Observed Behavior:** The penalty gauge shows `Unassessed` with a 0% progress bar before route calculation.
- **Root Cause Analysis:**
  - `active?.summary.risk_category` defaults to empty string when `active` is null, rendering the fallback string `'Unassessed'`.
  - The penalty share calculation `Math.min(100, (penalty || 0) / active.total_cost * 100)` evaluates to `0`.
- **Remediation:**
  - Clearly delineate the uncalculated pre-plan state from an actual evaluation where risk is zero.
  - Show a pulse/shimmer state during route computation, and immediately populate the risk badge (`low_risk`, `moderate_risk`, `high_risk`) upon response.

### Issue 3: Empty Terrain Profile (`Elevation observations appear after route generation`)
- **Observed Behavior:** The bottom terrain profile drawer shows `—` for max slope, ascent, and descent on load, and when expanded shows "Elevation observations appear after route generation".
- **Root Cause Analysis:**
  - `Profile.jsx` parses `route.geometry.coordinates` where `z` is coordinate index 2 (`c[2]`).
  - When `route` is null, `points` is an empty array, and `valid.length === 0`.
  - Furthermore, if the backend ever returns 2D coordinates `[lon, lat]` (which happens when `all_elevations_valid` is false in `reconstruct_route_summary`), the profile fails to render elevation even after route generation!
- **Remediation:**
  - Ensure `backend/app/routing/alternatives.py` always supplies 3D coordinates `[lon, lat, elev]` for all traversed cells by interpolating or sampling the valid DEM grid.
  - Enhance `Profile.jsx` to display average slope, terrain roughness profile, and interactive crosshair scrubbing linked to the map position.

### Issue 4: Disabled Export Button
- **Observed Behavior:** The `Export` button in the drawer and the quick-export button in the header are disabled (`disabled={!result}`).
- **Root Cause Analysis:**
  - `disabled={!result}` is an intentional design constraint: an export manifest cannot be generated without a computed route.
  - However, because the button is disabled with no explanatory tooltip, users perceive it as a broken button.
- **Remediation:**
  - Add an `aria-disabled` state with tooltip ("Plan a route to enable JSON and GeoJSON export").
  - Activate immediately upon route response.

### Issue 5: A* as the Only Visible / Selectable Algorithm (Dijkstra Disabled)
- **Observed Behavior:** In the routing settings dropdown, the **Dijkstra** option is grayed out and disabled when connected to the Python backend API.
- **Root Cause Analysis:** **CRITICAL BACKEND & SCHEMA OMISSION**.
  1. `backend/app/schemas/routes.py`: `RoutePlanRequest` defines `start`, `destination`, `mode`, `constraints`, `num_alternatives`, but **OMITS** an `algorithm` property!
  2. `mission-ui/src/main.jsx:15`: When connecting to the API, the frontend inspects the OpenAPI schema:
     ```javascript
     const props = openapi.components?.schemas?.RoutePlanRequest?.properties || {};
     setApi({ url, health, status, layers, algorithmSupported: !!props.algorithm });
     ```
     Because `props.algorithm` is undefined, `api.algorithmSupported` is evaluated as `false`!
  3. `mission-ui/src/main.jsx:37`: The dropdown option explicitly disables Dijkstra based on this flag:
     ```javascript
     <option value="dijkstra" disabled={live && !api?.algorithmSupported}>Dijkstra</option>
     ```
  4. `backend/app/services/route_service.py`: `RouteService.plan_route` does not check for an algorithm parameter and hardcodes:
     ```python
     astar_search(...)
     stats = ComputationStats(algorithm_used="A* (with admissible Euclidean heuristic)", ...)
     ```
  5. `backend/app/routing/dijkstra.py` exists as standalone code, but is never invoked by the application API.
- **Remediation:**
  - Add `algorithm: Literal["astar", "dijkstra"] = Field(default="astar", description="Graph search algorithm: astar or dijkstra")` to `RoutePlanRequest`.
  - In `RouteService.plan_route`, branch dynamically between `astar_search` and `dijkstra_search` based on `request.algorithm`.
  - Update `ComputationStats.algorithm_used` to reflect the executed algorithm accurately.
  - Expose Dijkstra in the frontend and implement the requested **Compare A* vs Dijkstra** mode.

---

## 4. Deep-Dive Audit: Mars Imagery Architecture & Blurriness

### 4.1. Current Imagery Pipeline Architecture
The frontend in `mission-ui/src/MapView.jsx` configures three basemap options:
1. `base === 'hirise'`: Attempts to load `/mission-data/jezero-hirise.webp` on top of a grayscale relief canvas.
2. `base === 'imagery'`: Loads static image `/mission-data/jezero-imagery.jpg` using OpenLayers `ImageStatic`.
3. `base === 'relief'`: Generates an on-the-fly 2D canvas of size 216×208 pixels via `rasterImage(terrain, 'relief')`.

### 4.2. Root Causes of Blurring, Rectangular Gaps, and Inconsistent Resolution
1. **Severe Downsampling of Static Rasters:**
   - `dist/mission-data/imagery-source.json` reveals:
     ```json
     {
       "source": "NASA/JPL Mars Trek · Viking MDIM2.1 color mosaic",
       "image_size": [156, 109],
       "bounds": [77.146, 18.100, 78.003, 18.699]
     }
     ```
     An image of only **156×109 pixels** is stretched across an entire degree of Martian surface (~50 km × 35 km). When the user zooms in to view a 3 km rover corridor, each pixel is stretched over 300 meters, producing extreme bilinear blur.
2. **Missing Tiles & HTTP 403 Forbidden Gaps in HiRISE Derivative:**
   - `dist/mission-data/jezero-hirise.json` documents:
     ```json
     {
       "missing_tiles": [
         [11705, 7333, "HTTP Error 403: Forbidden"],
         [11705, 7334, "HTTP Error 403: Forbidden"],
         [11705, 7335, "HTTP Error 403: Forbidden"],
         ...
       ]
     }
     ```
     The static webp derivative was created with rectangular voids where tile fetches failed with HTTP 403, leaving visible dark rectangular gaps on the western edge of the HiRISE coverage.
3. **HiRISE Geographic Coverage Discontinuity:**
   - The HiRISE mosaic only covers longitude `[77.1899°E, 77.4976°E]` and latitude `[18.3545°N, 18.5421°N]` (the Western Delta fan).
   - Outside these bounds, `jezero-hirise.webp` terminates abruptly. Because the underlying fallback was a low-resolution canvas, panning outside the delta reveals an jarring resolution drop.
4. **Single-Canvas Stretched Projection:**
   - `rasterImage` generates a single HTML5 `<canvas>` matching the DEM array dimensions (216×208).
   - When OpenLayers zooms beyond zoom level 10, this static bitmap is resampled across thousands of screen pixels without progressive multi-resolution tile pyramids.

### 4.3. Multi-Resolution Architecture Solution
To achieve a continuous, scientifically honest, and high-quality Martian terrain visualization without artificial blurring:
1. **Multi-Tier Layer Stack:**
   - **Tier 1 (Regional Context):** NASA/USGS HRSC-MOLA blended relief and shaded relief generated at crisp resolution with hillshading.
   - **Tier 2 (Regional Visual Imagery):** NASA/JPL Mars Trek global / regional orthomosaic or CTX mosaic tiles.
   - **Tier 3 (Local HiRISE High-Resolution):** Clean, gap-free HiRISE orthomosaic covering the delta and landing ellipse, with transparent boundaries that blend smoothly into regional context.
2. **Coverage Indicator:**
   - Clearly delineate genuine HiRISE footprint with an honest coverage boundary overlay so users understand where orbital high-resolution data transitions to regional imagery.

---

## 5. Deep-Dive Audit: Dijkstra Implementation & Comparison Mode

### 5.1. Existing Code Audit
- File: `backend/app/routing/dijkstra.py`
- Algorithm: `dijkstra_search(graph, start, dest, max_expansions, penalized_edges)`
- Characteristics:
  - Uses `heapq` priority queue with distance costs.
  - Uses `graph.get_valid_neighbors(curr_r, curr_c, penalized_edges)` with identical edge weights to A*.
  - Enforces safety ceiling `max_expansions` (default 150,000 states).
  - Returns `(path_nodes, total_cost, nodes_expanded, elapsed_seconds)`.
  - Mathematically sound: heuristic is implicitly zero ($h(u) \equiv 0$).

### 5.2. Missing Capabilities
1. **API Integration:** `RoutePlanRequest` must accept `algorithm: Literal["astar", "dijkstra", "compare"]`.
2. **Comparison Execution:** When `algorithm="compare"`, the backend must execute both A* and Dijkstra on the identical graph, record both paths, expansion counts, and runtimes, and verify that both find paths with identical optimal cost ($C_{A^*} \approx C_{Dijkstra}$).
3. **Response Schema:** `RoutePlanResponse` must expose comparison metrics in a structured `algorithm_comparison` block.
4. **Frontend UI:** Add an interactive comparison view displaying side-by-side metrics:
   - Distance (km)
   - Weighted Cost (units)
   - Explored Nodes / States
   - Execution Time (seconds / ms)
   - Maximum Slope
   - Cost Equality Verification Indicator

---

## 6. Implementation Action Plan

### Phase 2: Feature Integration
- [ ] Update `backend/app/schemas/routes.py` to add `algorithm` parameter and comparison schemas.
- [ ] Update `backend/app/services/route_service.py` to support Dijkstra and Compare mode.
- [ ] Update `mission-ui/src/integration.js` and `mission-ui/src/main.jsx` to enable Dijkstra selection and pass algorithm to backend.
- [ ] Connect and expand route analysis metrics, terrain penalties, and elevation profile.
- [ ] Ensure 3D coordinates `[lon, lat, elev]` are always supplied for elevation profiles.
- [ ] Add state tooltips and auto-expansion to improve UX for metrics and export.

### Phase 3: Mars Imagery Pipeline
- [ ] Eliminate missing tile gaps in HiRISE coverage.
- [ ] Provide high-resolution continuous basemap imagery.
- [ ] Provide honest HiRISE coverage boundary indicator.
- [ ] Implement smooth blending between local HiRISE and regional context.

### Phase 4: Dijkstra Implementation & Comparison
- [ ] Implement A* vs. Dijkstra comparison mode in backend.
- [ ] Implement comparison table in frontend UI.
- [ ] Write comprehensive unit and integration tests verifying algorithm equivalence, edge cases, and performance.

---

## 7. Testing Requirements

1. **Backend Unit & Integration Tests:**
   - Dijkstra and A* cost equality across diverse terrain corridors.
   - Algorithm parameter schema validation in FastAPI request models.
   - Comparison response serialization.
   - Obstacle avoidance and corner-cutting prevention in both algorithms.
2. **Frontend Component & Integration Tests:**
   - UI algorithm selection changes API payload.
   - Candidate alternative selection updates map and profile.
   - Elevation profile renders when route is loaded.
   - Export downloads valid JSON and GeoJSON.
3. **Browser E2E Tests:**
   - Execute A* route planning.
   - Execute Dijkstra route planning.
   - Execute Compare mode and verify comparison metrics table.
   - Verify image tiles render without console 404/403 errors.
