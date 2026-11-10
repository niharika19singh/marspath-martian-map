# MARSPath Phase 6.2 — API Contract Verification & Staging Test Preparation

## 1. Audited Repository State

| Reference | Branch Name | Commit SHA | Notes |
|---|---|---|---|
| **Backend Implementation Baseline Audited** | `feature/niharika-geospatial-routing` | `2ad3fcbea7d24b86b658e6ddf18bd8cf27131ed4` | Phase 6.1.2 application code baseline audited in this report |
| **Current PR #1 Head / Phase 6.2 Audit Commit** | `feature/niharika-geospatial-routing` | `ae057bcb54fcda99e5d5445122a9c8c1d2c0cbdd` | Pull Request [#1](https://github.com/niharika19singh/marspath-martian-map/pull/1) targets `main` (**OPEN**, **UNMERGED**) |
| **Frontend** | `kunal` (`origin/kunal`) | `58f348c669ffbbbb84ed4c41b666b9851c6b3725` | Audited read-only under `mission-ui/` |
| **Main (PR #1 Base)** | `main` (`origin/main`) | `2495f69cf317d016000dedc7e48b14f36435e876` | Target base branch for PR #1 |

> **Verification Status:** All contract verifications in this document were executed against the actual FastAPI application (`backend/app/main.py`) using deterministic local fixtures and `TestClient`. Live hosted cloud staging has **not** been executed because no deployed Render/Vercel staging URL or cloud credentials have been provisioned.

---

## 2. Backend API Contract Audit

### 2.1 `GET /health`
- **Implementation:** `backend/app/api/v1/health.py:9-59` (`get_health`)
- **Required Headers:** None (plus standard `Origin` header when called cross-origin from browser).
- **Request Body:** None.
- **External Data Dependency:** None when `MARSPATH_USE_REAL_DEM=false` (uses deterministic synthetic Jezero fixture) or when `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true`.
- **Actual Response Structure (`200 OK`, `application/json`):**
  - `status`: `str` (`"healthy"`)
  - `service`: `str`
  - `version`: `str` (`"0.1.0"`)
  - `environment`: `str` (`"development"` or `"production"`)
  - `planetary_target`: `str` (`"Mars"`)
  - `pilot_region`: `str` (`"Jezero Crater"`)
  - `data_readiness`: `dict` containing:
    - `dem_loaded`: `bool` (`False` when synthetic, `True` when real DEM loaded)
    - `real_dem_requested`: `bool`
    - `real_dem_loaded`: `bool`
    - `is_synthetic`: `bool`
    - `data_mode`: `str` (`"synthetic_test_fixture"`, `"synthetic_fallback"`, `"real_official_endpoint_unverified_checksum"`, `"real"`, or `"real_unverified_source"`)
    - `real_data_validation_status`: `str`
    - `local_integrity_verified`: `bool | None`
    - `source_checksum_verified`: `bool`
    - `dem_resolution_meters`: `float`
    - `grid_shape`: `list[int]` (`[rows, cols]`)
    - `spatial_coverage`: `dict` (`min_lon`, `max_lon`, `min_lat`, `max_lat`)
    - `crs`: `str` (`"IAU2000:49900"`)
    - `dataset_name`: `str | None`
    - `official_product_id`: `str | None`
    - `official_source_url`: `str | None`
    - `fallback_reason`: `str | None`
    - `blocking_errors`: `list[str]`
- **Error Responses:** `503 Service Unavailable` only if `MARSPATH_USE_REAL_DEM=true`, `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false`, and the real DEM file is missing or invalid (`TerrainDataUnavailableError`).

### 2.2 `GET /api/v1/data/status`
- **Implementation:** `backend/app/api/v1/data_status.py:9-18` (`get_data_status`), `backend/app/services/data_catalog.py:282-387` (`DataCatalogService.get_data_status`), schema `DataStatusResponse` (`backend/app/schemas/routes.py:1082-1141`).
- **Required Headers:** None.
- **Request Body:** None.
- **External Data Dependency:** None in synthetic mode (`MARSPATH_USE_REAL_DEM=false`).
- **Actual Response Structure (`200 OK`, `DataStatusResponse`):**
  - `status`: `str` (`"healthy"` or `"degraded_synthetic_fallback"`)
  - `data_mode`: `str`
  - `real_data_validation_status`: `str`
  - `dem_loaded`: `bool`
  - `real_dem_requested`: `bool`
  - `real_dem_loaded`: `bool`
  - `local_integrity_verified`: `bool | None`
  - `source_checksum_verified`: `bool`
  - `is_synthetic`: `bool`
  - `active_pilot_region`: `str` (`"Jezero Crater, Mars"`)
  - `pilot_bounds`: `BoundingBox` (`min_lon: 77.2`, `min_lat: 18.15`, `max_lon: 77.95`, `max_lat: 18.65`)
  - `crs`: `CRSInfo` (`identifier: "IAU2000:49900"`, `name`, `ellipsoid_radius_meters: 3396190.0`, `latitude_type: "planetocentric"`, `longitude_direction: "positive_east"`, `projection`)
  - `loaded_dem`: `str | None`
  - `active_dem_dataset_name`: `str | None`
  - `active_dem_product_id`: `str | None` (`None` when synthetic or unverified)
  - `active_dem_source_url`: `str | None` (`None` when synthetic or unverified)
  - `fallback_reason`: `str | None`
  - `dem_resolution_meters`: `float`
  - `grid_shape`: `list[int]`
  - `valid_data_fraction`: `float` (`0.0` to `1.0`)
  - `active_dem_provenance`: `dict[str, Any]`
  - `hirise_enabled`: `bool`
  - `hirise_loaded`: `bool`
  - `hirise_status`: `str`
  - `hirise_validation_reason`: `str | None`
  - `hirise_dem_provenance`: `dict[str, Any] | None`
  - `configured_products`: `list[dict[str, Any]]`
  - `limitations`: `list[str]`
  - `blocking_errors`: `list[str]`

### 2.3 `GET /api/v1/layers`
- **Implementation:** `backend/app/api/v1/layers.py:9-18` (`list_layers`), `backend/app/services/data_catalog.py:113-280` (`DataCatalogService.get_layer_list`), schema `LayerListResponse` / `LayerInfo` (`backend/app/schemas/layers.py:17-81`).
- **Required Headers:** None.
- **Request Body:** None.
- **External Data Dependency:** None in synthetic mode.
- **Actual Response Structure (`200 OK`, `LayerListResponse`):**
  - `count`: `int` (`5` by default; `6` when a valid HiRISE DTM is enabled and loaded)
  - `pilot_region`: `str` (`"Jezero Crater, Mars"`)
  - `layers`: `list[LayerInfo]`, where each `LayerInfo` contains:
    - `id`: `str` (`mars_elevation_jezero`, `mars_slope_degrees`, `mars_roughness_tri`, `mars_traversability_mask`, `mars_trek_imagery_basemap`, and optionally `mars_hirise_jezero_delta_dtm`)
    - `name`, `category`, `layer_type`, `description`, `units`, `resolution_meters`, `bounds`, `crs`
    - `source_name`, `source_url` (`None` when synthetic), `product_id` (`None` when synthetic), `validation_status`, `source_checksum_verified`, `provenance_note`
    - `is_numerical`: `bool`
    - `is_available`: `bool` (`True` when available to backend routing/analysis operations)
    - `is_renderable`: `bool` (`False` for all numerical/analysis layers including `mars_hirise_jezero_delta_dtm`; `True` **only** for `mars_trek_imagery_basemap`)
    - `render_url`: `str | None` (`None` for all backend numerical layers; populated only for `mars_trek_imagery_basemap` with the NASA Mars Trek XYZ tile template)
    - `is_synthetic`: `bool`

### 2.4 `GET /openapi.json`
- **Implementation:** FastAPI built-in OpenAPI 3.1.0 schema endpoint (`backend/app/main.py:16-22`).
- **Actual Response Structure (`200 OK`, `application/json`):**
  - `paths`: Includes `"/health"`, `"/api/v1/layers"`, `"/api/v1/data/status"`, `"/api/v1/routes/plan"`, `"/"`.
  - `components.schemas.RoutePlanRequest`:
    - `required`: `["start", "destination"]`
    - `properties`: `start`, `destination`, `crs_identifier`, `mode`, `constraints`, `science_waypoints`, `num_alternatives`, `robustness_config` (note: `algorithm` is **not** a property, as the backend implements A* exclusively).

### 2.5 `POST /api/v1/routes/plan`
- **Implementation:** `backend/app/api/v1/routes.py:10-30` (`plan_route`), `backend/app/services/route_service.py:55-592` (`RouteService.plan_route`), schemas `RoutePlanRequest` and `RoutePlanResponse` (`backend/app/schemas/routes.py:300-336, 1050-1080`).
- **Required Headers:** `Content-Type: application/json`.
- **External Data Dependency:** None in synthetic mode (`MARSPATH_USE_REAL_DEM=false`).
- **Request Body (`RoutePlanRequest`):**
  - `start` (**required**, `MarsCoordinate`): `{"lon": float, "lat": float}`. `lon` is positive-East degrees (auto-normalized via `% 360.0`), `lat` is planetocentric degrees `[-90, 90]`. Must fall within Jezero pilot bounds `[77.20, 77.95]` E, `[18.15, 18.65]` N.
  - `destination` (**required**, `MarsCoordinate`): `{"lon": float, "lat": float}`.
  - `crs_identifier` (optional, `str`, default `"IAU2000:49900"`): Validated against `SUPPORTED_MARS_CRS = {"IAU2000:49900", "IAU:49900", "MARS_2000_IAU_IAG"}`. Earth CRS identifiers (e.g. `EPSG:4326`, `EPSG:3857`) are rejected with `422`.
  - `mode` (optional, `OptimizationMode`, default `"balanced"`): `"safety_first"`, `"balanced"`, or `"science_first"`.
  - `constraints` (optional, `RouteConstraints`): `max_slope_deg` (`float`, `1.0..45.0`, default `20.0`), `max_roughness` (`float`, `0.05..1.0`, default `0.85`), `avoid_unobserved_terrain` (`bool`, default `True`), `corridor_padding_deg` (`float`, `0.01..0.25`, default `0.04`).
  - `science_waypoints` (optional, `list[MarsCoordinate]`, default `[]`): Ordered intermediate waypoints `[{"lon": float, "lat": float}, ...]`.
  - `num_alternatives` (optional, `int`, `1..3`, default `1`): Number of distinct route candidates requested.
  - `robustness_config` (optional, `RobustnessConfig | None`, default `None`): Perturbation stress-testing configuration.
- **Actual Response Structure (`200 OK`, `RoutePlanResponse`):**
  - `mission_id`: `str` (`"mission_<12-hex-chars>"`)
  - `status`: `str` (`"success"`)
  - `crs`: `CRSInfo` (`identifier: "IAU2000:49900"`, etc.)
  - `pilot_region`: `str` (`"Jezero Crater, Mars"`)
  - `data_mode`: `str`
  - `provenance`: `dict[str, Any]`
  - `source_selection`: `TerrainSourceSelectionReport` (`selected_source_id`, `hirise_selected`, `effective_resolution_meters`, `single_source_invariant_enforced`, etc.)
  - `routes`: `list[RouteAlternative]` (`1..3` items), each containing:
    - `route_id`: `str` (`"route_primary_opt"`, `"route_alt_corridor"`, `"route_safety_backup"`)
    - `name`: `str`
    - `mode`: `str`
    - `score_rank`: `int` (`1`, `2`, `3`)
    - `total_cost`: `float`
    - `cost_breakdown`: `dict[str, float]` (`base_distance_cost`, `slope_penalty`, `roughness_penalty`, `hazard_penalty`, `extra_penalty`)
    - `summary`: `RouteSummary` (`total_distance_meters`, `horizontal_distance_meters`, `surface_3d_distance_meters`, `distance_measurement_basis`, `elevation_gain_meters`, `elevation_loss_meters`, `min_elevation_meters`, `max_elevation_meters`, `max_slope_deg`, `average_slope_deg`, `average_roughness`, `data_coverage_fraction`, `elevation_sample_coverage_fraction`, `is_complete_measurement`, `estimated_duration_hours`, `observed_duration_hours_partial`, `motion_profile`, `energy_index`, `observed_energy_index_partial`, `science_score`, `hazard_exposure_meters`, `observed_hazard_exposure_meters_min`, `unobserved_step_distance_meters`, `risk_category`, `risk_assessment_status`)
    - `geometry`: `GeoJSONGeometry` (`type: "LineString"`, `coordinates: list[list[float]]` ordered as **`[lon, lat, elevation_meters]`** 3D tuples when all route vertices have valid elevation observations, or 2D `[lon, lat]` tuples if any vertex lacks valid elevation; never fabricates `0.0` elevation)
    - `waypoints_visited`: `list[MarsCoordinate]`
    - `science_targets_visited`: `list[str]`
    - `science_targets_nearby`: `list[str]`
    - `warnings`: `list[str]` (includes explanations when secondary or safety-backup alternative corridors are suppressed or unviable)
    - `evidence_passport`: `RouteEvidencePassport` (`schema_version: "1.0.0"`, `assessment_scope`, `scientific_disclaimer`, `quality_tier` in `{"high", "moderate", "low", "unverified"}`, `tier_explanation`, `quality_flags`, `source`, `coverage`, `resolution_assessment`, `known_limitations`, `segments: list[RouteSegment]`)
  - `stats`: `ComputationStats` (`algorithm_used`, `search_duration_seconds`, `nodes_expanded`, `grid_rows`, `grid_cols`, `cell_size_meters`)
  - `limitations`: `list[str]`
  - `robustness_assessment`: `RouteRobustnessAssessment | None`
- **Error Response Structure & Status Codes:**
  - **FastAPI / Pydantic Schema Validation (`422 Unprocessable Entity`):**
    `{"detail": [{"type": "...", "loc": ["body", ...], "msg": "...", "input": ...}]}`
  - **Domain Exceptions (`MarsPathError` subclasses raised via `HTTPException` in `backend/app/api/v1/routes.py:21-25`):**
    `{"detail": {"error": "<human-readable message>", "details": {...}}}`
    - `422 Unprocessable Entity`: `UnsupportedCRSError`, `CoordinateOutOfBoundsError`, `InvalidWaypointConstraintError`
    - `413 Content Too Large`: `ComputationalBoundExceededError` (corridor distance $> 50\text{ km}$ or grid cells $> 250,000$)
    - `404 Not Found`: `UnreachableDestinationError` (start/destination on impassable slope/roughness/nodata or disconnected corridor)
    - `504 Gateway Timeout`: `RoutingTimeoutError` (A* traversal exceeds `ROUTING_TIMEOUT_SECONDS`, default `10.0s`)
    - `503 Service Unavailable`: `TerrainDataUnavailableError`

---

## 3. Frontend Implementation Comparison (`origin/kunal` @ `58f348c669ffbbbb84ed4c41b666b9851c6b3725`)

1. **API Base URL Configuration (`mission-ui/src/main.jsx:7, 15, 41`):**
   - Initializes `apiUrl` exclusively from `localStorage.getItem('marspath-api-url') || ''` (`main.jsx:7`).
   - Does not read `import.meta.env.VITE_API_URL` or any build-time/window configuration variable. Users must manually open the settings dialog (`main.jsx:41`), type the backend URL, and click "Connect and validate".
   - Furthermore, `run()` (`main.jsx:14`, `if(!raw)return;`) and the map stage (`main.jsx:31`, `terrain ? <MapView .../> : ...`) require the local static file `/mission-data/jezero-dem.json` (`raw`) to load before the UI allows route planning, even in `api` mode.
2. **Handshake Consumption (`mission-ui/src/main.jsx:15`):**
   - `connect()` validates the URL protocol (`http:` allowed only for `localhost` and `127.0.0.1`; `https:` required for remote hosts) and concurrently fetches `/health`, `/api/v1/data/status`, `/api/v1/layers`, and `/openapi.json` with a 30s timeout (`AbortSignal.timeout(30000)`).
   - Verifies `openapi.paths?.['/api/v1/routes/plan']` and checks `openapi.components?.schemas?.RoutePlanRequest?.properties?.algorithm` to set `algorithmSupported: false`.
3. **Route Request Construction (`mission-ui/src/main.jsx:13-14`):**
   - `request()` builds `{start: {lon, lat}, destination: {lon, lat}, algorithm, mode, constraints: {max_slope_deg, max_roughness, avoid_unobserved_terrain: true}, science_waypoints: [], num_alternatives, crs_identifier: 'IAU2000:49900'}`.
   - `run()` strips `payload.algorithm` when `!api.algorithmSupported` and sends `POST /api/v1/routes/plan` with a 45s `AbortController` timeout.
   - Note: `science_waypoints` is always `[]` because the planner UI has no controls for adding intermediate waypoints.
4. **Route Response & Geometry Handling (`mission-ui/src/main.jsx:8`, `MapView.jsx:12-13`, `Profile.jsx:3`):**
   - `accept()` (`main.jsx:8`) verifies `Array.isArray(response.routes) && response.routes.length && !response.routes.some(r => !Array.isArray(r.geometry?.coordinates))`.
   - `MapView.jsx:12` maps `r.geometry.coordinates` via `project(c[0], c[1])` (`[lon, lat]`).
   - `Profile.jsx:3` extracts `c[0], c[1]` for horizontal step distance and `z: Number.isFinite(c[2]) ? c[2] : null` for elevation, plus `route.evidence_passport?.segments?.[Math.max(0, i-1)]?.slope_deg` for segment slope coloring.
5. **Alternative Route Count & Shortfall Handling (`mission-ui/src/main.jsx:37`):**
   - Renders candidate buttons for `result?.routes`.
   - Does **not** compare `result.routes.length < lastRequest.current.num_alternatives` or inspect `result.routes[0].warnings`.
   - Instead checks `{result?.limitations?.length > 3 && <p className="partial-note">{result.limitations.at(-1)}</p>}`. In `RouteService.plan_route` (`backend/app/services/route_service.py:512-568`), `limitations` is built dynamically from terrain resolution/HiRISE selection, synthetic vs. real data mode, validation status, and provenance limitations—it is **not** a route-count or alternative-shortfall indicator, and its length varies by operating mode. Alternative generation failures or suppressed alternatives are communicated via `routes[0].warnings` (`backend/app/routing/alternatives.py:489-501, 564`) where applicable. Relying on `limitations.length > 3` is therefore an unreliable heuristic that surfaces a scientific/provenance disclaimer as `.partial-note` whenever more than 3 disclaimers are present.
6. **Terrain Provenance & Evidence Display (`mission-ui/src/main.jsx:18, 30, 37`):**
   - Top header chip (`main.jsx:30`) displays `{raw ? 'Terrain ready' : 'Loading terrain'} <b>{live ? 'Python API' : 'Local engine'}</b>` without showing `api.status.data_mode` or `api.status.is_synthetic`.
   - Details panel (`main.jsx:18, 37`) displays `evidence_passport.quality_tier`, `effectiveGrid`, `local_integrity_verified`, `source_checksum_verified`, and `dataName`.
   - **Provenance Link Defect (`main.jsx:37`):** Renders `<a href={raw?.source_page||'https://astrogeology.usgs.gov/'}>Terrain source ↗</a>`, unconditionally linking to the USGS page even when `live === true` and the backend is serving synthetic terrain (`active.evidence_passport.source.official_source_url === null`).
7. **Layer Availability & Renderability (`mission-ui/src/main.jsx:15, 38`, `MapView.jsx:5, 8-10, 12`):**
   - `api.layers` is fetched during `connect()` (`main.jsx:15`) but never read anywhere in `main.jsx` or `MapView.jsx`.
   - `MapView.jsx` is **not** a backend raster-tile client; it renders bundled static files (`/mission-data/jezero-imagery.jpg`, `/mission-data/jezero-hirise.webp`) and client-side canvas hillshades.
   - When `live === true`, `MapView.jsx:9, 12` disables the full-grid client-side hazard/coverage rasters and instead draws route-segment hazard vectors from `r.evidence_passport.segments` and the pilot bounding box from `backendStatus.pilot_bounds`.
8. **Error & Timeout Handling (`mission-ui/src/main.jsx:14`):**
   - Parses `json.detail?.error || json.error || (Array.isArray(json.detail) ? json.detail.map(d => d.msg).join('; ') : 'Route request failed (' + response.status + ').')`.
   - Correctly extracts both `MarsPathError` (`json.detail.error`) and FastAPI 422 validation error arrays (`json.detail[i].msg`), as well as `AbortError` timeouts.
9. **CORS Compatibility (`render.yaml:19-20`, `backend/app/core/config.py:52-132`):**
   - Production Render config allows `https://marspath.vercel.app`. Local development config allows `localhost` and `127.0.0.1` on ports `3000`, `5173`, `4173`, and `8080`.

---

## 4. Integration Compatibility Matrix

| Integration area | Backend contract | Frontend expectation | Status | Owner | Evidence |
|---|---|---|---|---|---|
| **API Base URL & Env Discovery** | FastAPI serves at configured host/port (`PORT` / `MARSPATH_PORT`, default `8000`). | Reads only `localStorage.getItem('marspath-api-url') \|\| ''`; does not read `import.meta.env.VITE_API_URL` or window config. Requires manual URL entry in dialog. | **Confirmed Defect** (Manual step required on fresh sessions) | **Frontend-owned** | `mission-ui/src/main.jsx:7, 15, 41` |
| **Connection Handshake (`/health`, `/api/v1/data/status`, `/api/v1/layers`, `/openapi.json`)** | All 4 endpoints return `200 OK` JSON; `/openapi.json` exposes `paths['/api/v1/routes/plan']` and `components.schemas.RoutePlanRequest.properties` (without `algorithm`). | `connect()` fetches all 4 concurrently (30s timeout), verifies `/api/v1/routes/plan` in OpenAPI paths, sets `algorithmSupported = !!props.algorithm` (`false`), and locks algorithm to `'astar'`. | **Compatible** | **No issue found** | `backend/app/api/v1/*.py`, `mission-ui/src/main.jsx:15, 35` |
| **Route Plan Request (`POST /api/v1/routes/plan`)** | Expects `RoutePlanRequest`: `start` (`{lon, lat}`), `destination` (`{lon, lat}`), `crs_identifier` (`"IAU2000:49900"`), `mode`, `constraints`, `science_waypoints`, `num_alternatives` (`1..3`). | `request()` & `run()` send matching JSON body and delete `payload.algorithm` when `!api.algorithmSupported`. (`science_waypoints` is always `[]`). | **Compatible** | **No issue found** | `backend/app/schemas/routes.py:300-336`, `mission-ui/src/main.jsx:13-14` |
| **3D Route Geometry (`GeoJSONGeometry`)** | Returns `LineString` with `[lon, lat, elevation_m]` 3D tuples when elevations are valid (or 2D `[lon, lat]` if incomplete). | `MapView.jsx` projects `[c[0], c[1]]`; `Profile.jsx` reads `c[0], c[1]` for distance and `Number.isFinite(c[2]) ? c[2] : null` for elevation profile. | **Compatible** | **No issue found** | `backend/app/routing/alternatives.py:104-107, 193-196`, `mission-ui/src/MapView.jsx:12`, `mission-ui/src/Profile.jsx:3` |
| **Summary & Cost Breakdown Metrics** | Returns `RouteSummary` (`total_distance_meters`, `estimated_duration_hours`, `max_slope_deg`, `elevation_gain_meters`, `elevation_loss_meters`, `data_coverage_fraction`, `risk_category`, etc.) and `cost_breakdown`. | Reads and displays `total_distance_meters`, `estimated_duration_hours`, `total_cost`, `data_coverage_fraction`, `risk_category`, `max_slope_deg`, `elevation_gain_meters`, `elevation_loss_meters`, and all 5 `cost_breakdown` keys. | **Compatible** | **No issue found** | `backend/app/schemas/routes.py:431-585`, `mission-ui/src/main.jsx:17, 37`, `mission-ui/src/Profile.jsx:3` |
| **Alternative Route Count & Shortfall Notice** | Returns `1..N` feasible routes; communicates alternative generation failures or suppressed alternatives via `routes[0].warnings` where applicable. `RoutePlanResponse.limitations` is built dynamically from terrain resolution, data mode, validation status, and provenance limitations (`route_service.py:512-568`), not route count. | Does not compare `routes.length < num_alternatives` or read `routes[0].warnings`; uses the unreliable `result?.limitations?.length > 3` heuristic to render `result.limitations.at(-1)` as `.partial-note`. | **Confirmed Defect** (Unreliable `limitations.length > 3` heuristic in API mode) | **Frontend-owned** | `backend/app/routing/alternatives.py:489-501, 564`, `backend/app/services/route_service.py:512-568`, `mission-ui/src/main.jsx:37` |
| **Terrain Provenance & Source Attribution** | In synthetic mode, sets `official_source_url: null` and `active_dem_source_url: null` so synthetic data is never attributed to USGS. | Top header chip omits `data_mode` / `is_synthetic`; details panel hardcodes `<a href={raw?.source_page\|\|'https://astrogeology.usgs.gov/'}>Terrain source ↗</a>` even when backend is in synthetic mode. | **Confirmed Defect** (Synthetic backend routes link to USGS source page) | **Frontend-owned** | `backend/app/services/data_catalog.py:45-57`, `mission-ui/src/main.jsx:30, 37` |
| **Layer Availability vs. Renderability** | `/api/v1/layers` distinguishes `is_available` (backend calculation ready) from `is_renderable` + `render_url` (browser tile layer; `True` only for `mars_trek_imagery_basemap`). | Fetches `/api/v1/layers` into `api.layers` but never reads it; uses bundled static imagery/HiRISE `.webp` and route-segment hazard vectors in `live` mode. | **Compatible** (`api.layers` unused; no invalid tile requests made) | **No issue found** | `backend/app/schemas/layers.py:60-70`, `backend/app/services/data_catalog.py:124-275`, `mission-ui/src/MapView.jsx:8-12` |
| **Error & Timeout Response Parsing** | Returns `{"detail": {"error": "...", "details": {...}}}` for `MarsPathError` (`404`, `413`, `422`, `503`, `504`) and `{"detail": [{"msg": "..."}]}` for FastAPI validation (`422`). | Extracts `json.detail?.error \|\| json.error \|\| (Array.isArray(json.detail) ? json.detail.map(d => d.msg).join('; ') : ...)` and handles `AbortError`. | **Compatible** | **No issue found** | `backend/app/api/v1/routes.py:21-30`, `mission-ui/src/main.jsx:14` |
| **CORS Origin Enforcement** | Fail-closed `validate_cors_origins` & `configure_cors`. Production `render.yaml` allows `https://marspath.vercel.app`; dev defaults allow `localhost` / `127.0.0.1` ports `3000, 5173, 4173, 8080`. | Browser sends `Origin` header from hosted Vercel domain or local dev server. If a preview/staging Vercel URL differs from `https://marspath.vercel.app`, it must be added to `MARSPATH_CORS_ORIGINS`. | **Compatible** (Pending actual staging URL if different from prod) | **Deployment/environment-owned** | `backend/app/core/config.py:52-132`, `backend/app/main.py:14-28`, `render.yaml:19-20` |

---

## 5. Confirmed Defects and Ownership Summary

### Frontend-Owned Defects (`mission-ui/` on branch `kunal` — Kunal)
1. **Unconditional USGS Attribution Link in API Mode (`mission-ui/src/main.jsx:37`):**
   - Always renders `href={raw?.source_page || 'https://astrogeology.usgs.gov/'}` regardless of `live` state or `active?.evidence_passport?.source?.official_source_url`. When the backend operates in `synthetic_test_fixture` or `synthetic_fallback` mode (`official_source_url: null`), the UI should hide the external USGS link and explicitly badge the session as synthetic in the header (`main.jsx:30`).
2. **Alternative Shortfall Heuristic Mismatch (`mission-ui/src/main.jsx:37`):**
   - Uses `result?.limitations?.length > 3` to display `result.limitations.at(-1)` as `.partial-note`. In the Python backend (`RouteService.plan_route`, `backend/app/services/route_service.py:512-568`), `limitations` is built dynamically based on terrain resolution, synthetic/real data mode, validation status, and provenance limitations—it is not a route-count or alternative-shortfall indicator, and its length is not constant across operating modes. Alternative generation failures or suppressed alternatives are communicated through the primary route's `warnings` (`routes[0].warnings`, `backend/app/routing/alternatives.py:489-501, 564`) where applicable. The `limitations.length > 3` heuristic is therefore unreliable and should be replaced by checking `result.routes.length < (lastRequest.current?.num_alternatives || numAlternatives)` and displaying `result.routes[0]?.warnings` when fewer alternatives are returned.
3. **No Build-Time Environment Variable Fallback for Backend URL (`mission-ui/src/main.jsx:7, 15`):**
   - Reads only `localStorage.getItem('marspath-api-url') || ''`. Should fall back to `import.meta.env.VITE_API_URL || ''` so deployed environments can pre-populate the backend endpoint.

### Deployment / Environment-Owned Items
1. **Staging Deployment & CORS Origin Registration:**
   - Neither the Render staging service nor the Vercel preview/staging deployment has been provisioned yet. If the hosted Vercel staging URL differs from `https://marspath.vercel.app`, that exact origin must be appended to `MARSPATH_CORS_ORIGINS` on Render.

### Backend-Owned Defects
- **None.** All 5 audited endpoints, schemas, error envelopes, provenance rules, and fail-closed CORS validations operate in compliance with the contract.

---

## 6. Reproducible Staging Smoke-Test Plan

> **Important:** The commands below are prepared for execution once a live staging backend is deployed. Set `MARSPATH_STAGING_API_URL` to the deployed Render URL (or `http://localhost:8000` for local pre-staging verification).

```bash
export MARSPATH_STAGING_API_URL="https://your-marspath-staging.onrender.com"
```

### 6.1 Health & Data Readiness Check (`GET /health`)
```bash
curl -sS -f "${MARSPATH_STAGING_API_URL}/health" | jq '{
  status,
  planetary_target,
  pilot_region,
  dem_loaded: .data_readiness.dem_loaded,
  is_synthetic: .data_readiness.is_synthetic,
  data_mode: .data_readiness.data_mode,
  real_data_validation_status: .data_readiness.real_data_validation_status,
  local_integrity_verified: .data_readiness.local_integrity_verified,
  crs: .data_readiness.crs,
  blocking_errors: .data_readiness.blocking_errors
}'
```
- **Expected (`200 OK` on Render with provisioned USGS DEM):**
  - `status`: `"healthy"`, `planetary_target`: `"Mars"`, `crs`: `"IAU2000:49900"`
  - `dem_loaded`: `true`, `is_synthetic`: `false`, `data_mode`: `"real_official_endpoint_unverified_checksum"`, `local_integrity_verified`: `true`, `blocking_errors`: `[]`.

### 6.2 Planetary Data Status (`GET /api/v1/data/status`)
```bash
curl -sS -f "${MARSPATH_STAGING_API_URL}/api/v1/data/status" | jq '{
  status,
  data_mode,
  is_synthetic,
  crs_id: .crs.identifier,
  pilot_bounds,
  dem_resolution_meters,
  valid_data_fraction
}'
```
- **Expected (`200 OK`):** `crs_id == "IAU2000:49900"`, `pilot_bounds` covering `77.2..77.95` E / `18.15..18.65` N, `valid_data_fraction > 0.95`.

### 6.3 Layer Catalog & Renderability Contract (`GET /api/v1/layers`)
```bash
curl -sS -f "${MARSPATH_STAGING_API_URL}/api/v1/layers" | jq '{
  count,
  layers: [.layers[] | {id, is_available, is_renderable, has_render_url: (.render_url != null)}]
}'
```
- **Expected (`200 OK`):** `count >= 5`; numerical layers (`mars_elevation_jezero`, `mars_slope_degrees`, `mars_roughness_tri`, `mars_traversability_mask`) have `is_available: true, is_renderable: false, has_render_url: false`; `mars_trek_imagery_basemap` has `is_available: true, is_renderable: true, has_render_url: true`.

### 6.4 OpenAPI Contract Verification (`GET /openapi.json`)
```bash
curl -sS -f "${MARSPATH_STAGING_API_URL}/openapi.json" | jq '{
  has_plan_path: (.paths | has("/api/v1/routes/plan")),
  request_required: .components.schemas.RoutePlanRequest.required,
  request_properties: (.components.schemas.RoutePlanRequest.properties | keys)
}'
```
- **Expected (`200 OK`):** `has_plan_path: true`, `request_required: ["start", "destination"]`.

### 6.5 CORS Preflight Verification (`OPTIONS /api/v1/routes/plan`)
```bash
# 1. Authorized production origin must return 200 OK and matching access-control-allow-origin
curl -sS -D - -o /dev/null -X OPTIONS "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Origin: https://marspath.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"

# 2. Unauthorized origin must NOT receive access-control-allow-origin header
curl -sS -D - -o /dev/null -X OPTIONS "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Origin: https://unauthorized-origin.example" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
```

### 6.6 Safe Corridor Route Planning Smoke Test (`POST /api/v1/routes/plan`)
```bash
curl -sS -f -X POST "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"lon": 77.40, "lat": 18.39},
    "destination": {"lon": 77.44, "lat": 18.42},
    "crs_identifier": "IAU2000:49900",
    "mode": "balanced",
    "constraints": {
      "max_slope_deg": 20.0,
      "max_roughness": 0.85,
      "avoid_unobserved_terrain": true
    },
    "science_waypoints": [],
    "num_alternatives": 2
  }' | jq '{
    status,
    mission_id,
    data_mode,
    routes_returned: (.routes | length),
    primary_route_id: .routes[0].route_id,
    first_coord: .routes[0].geometry.coordinates[0],
    first_coord_dim: (.routes[0].geometry.coordinates[0] | length),
    first_coord_has_valid_elev: (if (.routes[0].geometry.coordinates[0] | length) == 3 then (.routes[0].geometry.coordinates[0][2] | type == "number") else null end),
    distance_m: .routes[0].summary.total_distance_meters,
    max_slope_deg: .routes[0].summary.max_slope_deg,
    quality_tier: .routes[0].evidence_passport.quality_tier,
    algorithm_used: .stats.algorithm_used,
    nodes_expanded: .stats.nodes_expanded
  }'
```
- **Expected (`200 OK`):** `status: "success"`, `routes_returned >= 1`, `first_coord` is either a 3-element `[lon, lat, elevation_m]` array (when all route vertices have valid elevation observations, with `first_coord_has_valid_elev: true`) or a 2-element `[lon, lat]` array (when elevation observations are incomplete, with `first_coord_has_valid_elev: null`), `distance_m > 0`, `max_slope_deg <= 20.0`, `quality_tier` in `["high", "moderate", "low", "unverified"]`.

### 6.7 Error & Guardrail Smoke Tests
```bash
# 1. Invalid Earth CRS -> HTTP 422 with detail.error
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" -X POST "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lon":77.40,"lat":18.39},"destination":{"lon":77.44,"lat":18.42},"crs_identifier":"EPSG:4326"}'

# 2. Out-of-bounds coordinates -> HTTP 422 with detail.error
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" -X POST "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lon":150.0,"lat":10.0},"destination":{"lon":77.44,"lat":18.42},"crs_identifier":"IAU2000:49900"}'

# 3. Search radius > 50 km -> HTTP 413 with detail.error
curl -sS -w "\nHTTP_STATUS:%{http_code}\n" -X POST "${MARSPATH_STAGING_API_URL}/api/v1/routes/plan" \
  -H "Content-Type: application/json" \
  -d '{"start":{"lon":77.20,"lat":18.15},"destination":{"lon":77.95,"lat":18.65},"crs_identifier":"IAU2000:49900"}'
```

---

## 7. Known Limitations & Prerequisites for Real Browser Staging Validation

1. **Deployment Provisioning Prerequisite:** A live Render web service (from `render.yaml`) and a live Vercel deployment (from `mission-ui/`) must be deployed and reachable over HTTPS (`main.jsx:15` rejects plain `http:` for non-loopback hosts).
2. **CORS Alignment Prerequisite:** If the Vercel staging/preview URL is a branch domain (e.g., `https://marspath-git-kunal-...vercel.app`) rather than `https://marspath.vercel.app`, that exact origin must be added to `MARSPATH_CORS_ORIGINS` in the Render service environment before browser `connect()` calls will succeed.
3. **Cold-Start Timing:** Free-tier Render instances may take 30–50 seconds to wake from sleep and run `start_render.sh` on first request; `connect()` in `main.jsx:15` uses `AbortSignal.timeout(30000)`, so a cold instance may require one retry after wakeup.
