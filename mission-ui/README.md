# MarsPath Mission Control

React 19 + Vite + OpenLayers dashboard located at `/mission-control/`. The existing landing, catalog, and field guide remain available on the home route. Mission Control operates as an interactive Martian route intelligence workspace designed for the Jezero Crater pilot study area.

---

## 1. Architecture & Backend Integration

The frontend integrates with the Python FastAPI numerical terrain analysis service as specified in the Phase 7.2.1 integration handover.

### Verified Endpoints & Contract
- `GET /health`: Service health and terrain readiness. Returns HTTP 200 (`healthy`) or HTTP 503 (`degraded` when real terrain is requested but unverified/missing), along with `data_readiness` and `blocking_errors`.
- `GET /api/v1/data/status`: Authoritative raster data readiness, CRS, vertical datum, resolution, local file SHA-256 integrity, upstream checksum verification, optional HiRISE DTM status, and pilot bounds.
- `GET /api/v1/layers`: Authoritative layer catalog. Respects `is_renderable: true` and non-null `render_url` (e.g. `mars_trek_imagery_basemap`); analytical layers are marked non-renderable.
- `GET /openapi.json`: Machine-readable contract validation. Verifies route-planning endpoint availability and schema compatibility (including verifying that `algorithm` is omitted from `RoutePlanRequest`).
- `POST /api/v1/routes/plan`: Core mission planning computation. Validates Mars coordinates in positive-east planetocentric degrees, selects terrain source, crops the corridor, evaluates alternatives, and returns geometry, cost breakdown, segment evidence, evidence passport, and optional robustness stress testing.

### Connectivity vs. Terrain Readiness
Transport connection and data readiness are treated as distinct states:
1. **Connected (Healthy)**: Service is reachable and genuine observational terrain is loaded and verified.
2. **Connected (Degraded)**: Service is reachable, but real terrain is missing, fallback synthetic fixture is active, or blocking errors exist. Structured 503 error bodies are parsed to display exact `blocking_errors`.
3. **Synthetic Test Fixture**: Procedural development terrain active; clearly badged on header and panels.
4. **Disconnected**: Python backend unreachable. Mission Control operates in standalone mode using the bundled, SHA-256 verified Jezero MOLA–HRSC regional grid and web worker.

### Race Condition & CORS Protection
- **Recomputation Preservation**: While a new route plan is computing (`busy: true`), the previous successful plan remains visible on screen and is marked with a subtle *"Showing previous plan · Computing new route…"* status banner.
- **Sequence Guards**: Every request is assigned an incrementing sequence token. Superseded or out-of-order responses are dropped automatically.
- **CORS Diagnostics**: Network failures provide exact origin diagnostics referencing `location.origin` for addition to `MARSPATH_CORS_ORIGINS`, without falsely attributing all network failures to CORS.

---

## 2. Mission Planner Features

- **Coordinate Inputs (A / B)**: East longitude and planetocentric latitude entry with coordinate validation and interactive crosshair picking directly on the OpenLayers map.
- **Intermediate Science Waypoints**: Users can add, edit, pick on map, and remove ordered intermediate science waypoints (`W1`, `W2`, etc.). Waypoints are submitted in the `science_waypoints` array and considered in corridor bounding and route guidance.
- **Optimization Modes**:
  - `safety_first`: Strict slope ceiling (≤14°), higher roughness penalty.
  - `balanced`: General-purpose compromise between distance and terrain risk (≤20°).
  - `science_first`: Explores detours to visit high-priority scientific POIs (≤22°).
- **Constraints**: User-configurable slope ceiling (°), roughness limit (0.1–1.0), and strict NoData avoidance toggle.
- **Candidate Shortfall Detection**: Compares requested `num_alternatives` with returned `routes.length`. Displays a shortfall banner explaining that terrain constraints or corridor boundaries prevented additional feasible corridors.
- **Robustness Stress Testing Settings**: Collapsible section in Settings (disabled by default). When enabled, validates strictly positive user hypotheses:
  - `vertical_sigma_m` (default 1.5 m)
  - `correlation_length_m` (default 400.0 m)
  - `scenario_count` (3–20, default 5)
  - `seed` (default 42)
  - `cost_regret_threshold_fraction` (default 0.05)

---

## 3. Four-Tab Route Analysis Panel

The expanded floating analysis panel organizes deep analytics into four dedicated tabs:

### Tab 1: Overview
- **Key Metrics**: Total distance (km), slope-derated estimated time (hrs, null-safe), weighted cost (units), and observed terrain coverage (%).
- **Candidate Cards**: Primary and alternative cards displaying distance, duration, and score rank.
- **Terrain Penalty Gauge**: Visual share of weighted cost attributable to slope, roughness, and hazards.
- **Cost Breakdown**: Reconciled itemization of `base_distance_cost`, `slope_penalty`, `roughness_penalty`, `hazard_penalty`, and `extra_penalty`.
- **Physical Traversal Risk**: Displays `risk_category` (`nominal`, `moderate`, `high`), `risk_assessment_status`, and `hazard_exposure_meters`. Explicitly notes that this is a deterministic traversal heuristic, not a calibrated failure probability.

### Tab 2: Terrain Evidence
- **Terrain Evidence Passport**:
  - Quality Tier badge (`HIGH`, `MODERATE`, `LOW`, `UNVERIFIED`) and backend-generated `tier_explanation`.
  - Quality flags list (e.g. `single_source_enforced`, `regional_resolution_not_subpixel`).
  - Independent route path coverage vs. corridor area coverage progress bars.
  - Proximity warning if segments pass near NoData boundaries (`near_nodata_segment_count`).
- **Integrity & Provenance**:
  - Independent indicators for **Local File Integrity** (SHA-256 match) vs. **Upstream Archive Checksum** (`source_checksum_verified`).
  - Actual physical pixel spacing (`pixel_resolution_x_meters`, `pixel_resolution_y_meters`) and vertical datum (Mars Areoid / MOLA).
  - Explicit disclaimer: *"Regional corridor planning (~200 m), not rover-scale obstacle detection."*
  - Expandable list of scientific and resolution limitations.

### Tab 3: Source & Science
- **Multi-Resolution Source Selection (`source_selection`)**:
  - Selected DEM product ID and dataset name.
  - Engineering explanation of why the source was selected (`selection_reason`).
  - Single-Source Invariant badge: confirms no raster mosaics or blended seams exist in the route grid.
  - HiRISE candidate evaluation status and rejection reason (e.g. corridor exceeding HiRISE boundary, missing file, or partial coverage).
  - Effective resolution and aggregation details (`aggregation_applied`, `aggregation_factor`, `aggregation_method`).
- **Science Return & POIs**:
  - Science score metric.
  - Visited intermediate waypoints count.
  - Visited science targets (`science_targets_visited`) and nearby targets (`science_targets_nearby`).
  - Detour explanations and route warnings.

### Tab 4: Robustness
- **Scenario Assumptions**: Displays assumed vertical sigma (m), correlation length (m), scenario count, seed, and cost regret threshold.
- **Baseline Route Stability**:
  - Baseline feasibility fraction (% of evaluated scenarios where baseline route remains traversable).
  - Route retention fraction (% feasible and within cost regret threshold).
  - Mean and minimum Jaccard route overlap (%).
  - Mean and maximum cost regret (%).
  - Count of scenarios within regret threshold.
  - Explicit count of failed scenario searches (if any).
- **Mandatory Scientific Disclaimer**:
  > *"Results describe route stability under the specified hypothetical terrain perturbation model. They do not establish the actual probability of rover failure or mission success."*

---

## 4. Map & Profile Visualizations

- **2D/3D Geometry**: Renders GeoJSON `LineString`. If valid Z coordinates are present, 3D positions are preserved. If observations are incomplete, uniform 2D coordinates are drawn without fabricating 0.0 elevation.
- **Elevation Profile**:
  - Plots elevation only when finite Z values exist.
  - Displays clear unavailable notice for 2D routes: *"Elevation profile unavailable for this route (2D planar coordinates returned). Complete elevation observations required."*
  - Segments colored by slope gradient (<7°, 7–12°, >12°).
  - Interactive pointer scrubbing links distance and elevation directly to the map pin.
- **Segment Evidence & Hazard Overlays**:
  - Invalid / NoData segments: distinct dashed coral/red lines (`#e05252dd`).
  - Near-NoData boundary segments: dashed amber lines (`#e5a038aa`).
  - High slope (>12°) or high roughness (>0.5): warm amber/coral lines (`#c38a6c88`).
- **Intermediate Waypoints**: Rendered as distinct violet/amber pins (`W1`, `W2`, ...) on the OpenLayers map alongside `A` (start) and `B` (destination).
- **NASA Mars Trek Basemap**: Used for visual reference only; never used for slope or elevation computation.
- **Historical Rover Traverse**: Full official Perseverance traverse through sol 2022 remains accessible via the *Rover History* switch.

---

## 5. Client-Side Exports

Exporting does not require a backend export endpoint. Three client-side export formats are available for the selected route:

1. **JSON Mission Manifest (`.json`)**: Complete response payload filtered to the selected route, including request parameters, provenance, source selection, evidence passport, and robustness assessment.
2. **GeoJSON Feature (`.geojson`)**: Standard GeoJSON FeatureCollection with `IAU2000:49900` CRS metadata, preserving valid 2D or 3D geometry dimensionality without manufacturing missing elevations, and embedding summary and evidence properties.
3. **CSV Segments (`.csv`)**: Per-segment tabular export containing:
   `segment_index,start_lon,start_lat,end_lon,end_lat,is_valid_data,start_elevation_m,end_elevation_m,elevation_delta_m,slope_deg,roughness,hazard_flags,quality_flags`

---

## 6. Verification & Version Tracking

### Tested Backend Revision
- Remote branch `remotes/origin/feature/niharika-geospatial-routing` at commit `8dd4353` (`feat(ops): validate MARSPath production integration and readiness`).
- The Phase 7.2.1 build-time DEM provisioning and read-only runtime verification work (`feature/marspath-build-time-dem` at `d5dbef48ce5a2b134d5fedd221f627f5f4cbafb6`) was reported as a local unpushed branch.
- The frontend contract implements the authoritative schemas from `feature/niharika-geospatial-routing` and supports both `source` and `source_evidence` property naming.

### Automated Test Suites
Run from `mission-ui/`:
```bash
# 1. Bundled engine, A* vs Dijkstra equivalence, DEM hash, nodata barriers, and GeoJSON export
node check-engine.mjs

# 2. Historical Perseverance traverse continuity, sol filtering, and published odometry
node check-traverse.mjs

# 3. Backend contract, source selection, evidence passport, robustness assessment, and CSV/JSON/GeoJSON exports
node check-integration.mjs

# 4. Production build
npm run build
```
All test suites pass cleanly and output verified JSON summaries.
