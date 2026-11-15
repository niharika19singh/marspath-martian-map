# MARSPath Frontend–Backend Integration Matrix

**Document ID:** `MARSPATH-INT-MAT-001`  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Date:** November 15, 2026  
**Auditor:** Principal Software Architect & QA Lead  
**Scope:** Full-Chain Traceability from User Interface Controls to Backend Engines and Response Visibility  

---

## 1. Traceability Chain Methodology

For every feature across MARSPath, the execution pipeline is mapped through the nine canonical stages:
1. **Control Element:** The physical DOM button, slider, canvas, or form input.
2. **React State:** The local hook (`useState`, `useRef`, `useMemo`) capturing the user intent.
3. **Request Builder:** The JavaScript function assembling parameters into an HTTP payload.
4. **API Client:** The fetch network wrapper (`mission-ui/src/integration.js`, `api.js`, `nasa_data.js`).
5. **Backend Endpoint:** FastAPI route handler in `backend/app/api/v1/`.
6. **Domain Service:** Computational engine in `backend/app/routing/`, `services/`, `conditions/`.
7. **Response Payload:** Pydantic schema model serialized to JSON.
8. **Frontend Handler:** State setter updating the React tree upon response resolution.
9. **UI Visibility & Discoverability:** Where the data appears, whether it is rendered directly, hidden behind collapsed accordions, or obscured by default tab settings.

---

## 2. Comprehensive Traceability Matrix

### 2.1 Mission Configuration & Path Planning Controls

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Mission Presets** | `<button className="preset-chip">` (`main.jsx:1480-1510`) | `startCoord`, `endCoord`, `selectedPreset` | `start: [lat, lon]`, `end: [lat, lon]` | `POST /api/v1/routes/plan` (`routes.py:35`) | `route_service.plan_route()` | `routes[].geometry` | `setStartCoord()`, `setEndCoord()` | **VERIFIED:** Immediately visible; populates input fields instantly. |
| **Map Pin Placement** | OpenLayers Map Click & Drag (`MapView.jsx:450-490`) | `startCoord`, `endCoord` | `start`, `end` coordinates | `POST /api/v1/routes/plan` | `route_service.plan_route()` | `routes[].geometry` | `onStartChange()`, `onEndChange()` | **VERIFIED:** Draggable pins sync bidirectionally with coordinate fields. |
| **Algorithm Selector** | `<select>` (`main.jsx:1614-1628`) | `algorithm` (`'astar'`, `'dijkstra'`, `'compare'`) | `algorithm: str` (`schemas/routes.py:125`) | `POST /api/v1/routes/plan` | `route_service.plan_route()` | `algorithm_comparison`, `stats.algorithm_used` | `setAlgorithm(e.target.value)` | **VERIFIED:** Selecting `compare` returns side-by-side benchmark matrix. |
| **Optimization Mode** | Radio Pill Selector (`main.jsx:1590-1610`) | `mode` (`'balanced'`, `'safety_first'`, `'shortest'`) | `mode: OptimizationMode` | `POST /api/v1/routes/plan` | `cost_model.MODE_WEIGHTS` | `routes[].summary.cost_breakdown` | `setMode(val)` | **VERIFIED:** Changes weighting parameters in graph edge costs. |
| **Slope Threshold** | Slider `5°–30°` (`main.jsx:1675-1710`) | `maxSlopeDeg` | `max_slope_deg: float` | `POST /api/v1/routes/plan` | `cost_model.weights.slope_ceiling_deg` | `routes[].summary.max_slope_deg` | `setMaxSlopeDeg(val)` | **VERIFIED:** Hard traversability barrier enforced; slopes $> \theta$ pruned. |
| **EVA Time Budget** | Number Input `hours` (`main.jsx:1715-1740`) | `evaBudgetHours` (default: 8.0) | `eva_budget_hours: float` | `POST /api/v1/routes/plan` | `route_service._evaluate_feasibility()` | `summary.exceeds_return_budget`, `turnaround` | `setEvaBudgetHours(val)` | **VERIFIED:** Reflected in turnaround calculations and mission brief. |
| **Robustness Scenarios** | Number Input `3–200` (`main.jsx:1867-1880`) | `robustnessScenarios` (default: 50) | `robustness_scenarios: int` | `POST /api/v1/routes/plan` | `robustness_service.assess_robustness()` | `robustness.scenarios_evaluated` | `setRobustnessScenarios(val)` | **VERIFIED:** Runs Monte Carlo perturbations up to $N=200$ runs. |

---

### 2.2 Cost, Energy, Resource & Feasibility Estimation

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Total Routing Cost** | Route Plan Trigger (`main.jsx:750`) | `result`, `active` | None (derived metric) | `POST /api/v1/routes/plan` | `cost_model.calculate_edge_cost()` | `routes[].total_cost` | `setResult(data)` | **OCCLUDED:** Hidden inside `<details open={detailsOpen}>` accordion (`main.jsx:2320`). `detailsOpen` defaults to `false`. |
| **Cost Penalty Breakdown** | Route Plan Trigger | `active.cost_breakdown` | None (derived metric) | `POST /api/v1/routes/plan` | `cost_model.calculate_edge_cost()` | `cost_breakdown.*` (slope, roughness, hazard, extra) | `setResult(data)` | **OCCLUDED:** Rendered at `main.jsx:2341-2349` inside the collapsed `<details>` element. |
| **Estimated Effort (Energy Proxy)** | Route Plan Trigger | `active.summary` | None (derived metric) | `POST /api/v1/routes/plan` | `cost_model.compute_minetti_relative_effort_factor()` | `summary.estimated_relative_effort` | `setResult(data)` | **TERMINOLOGY MISMATCH:** Labeled as `Est. Relative Effort: XXX eq-m (slope_penalty)` (`main.jsx:2253`). Not labeled "Energy" or "Work". |
| **Physical Chemical Fuel** | N/A | None | None | None | None | None | None | **NOT SPECIFIED / NOT APPLICABLE:** Mars rovers use MMRTG / solar panels; no liquid chemical fuel system exists. |
| **Walking Duration** | Route Plan Trigger | `active.summary` | None (derived metric) | `POST /api/v1/routes/plan` | `cost_model.calculate_edge_duration()` | `summary.estimated_duration_hours` | `setResult(data)` | **VERIFIED:** Immediately visible in primary summary pill (`main.jsx:2020`) as "Estimated Travel Time". |
| **Turnaround & Sunset** | Route Plan Trigger | `active.turnaround` | `eva_budget_hours` | `POST /api/v1/routes/plan` | `conditions/mars24.py`, `turnaround` | `turnaround.turnaround_ltst_hms`, `sunset_ltst_hms` | `setResult(data)` | **VERIFIED:** Displayed in turnaround metric card (`main.jsx:2240-2270`) when `analysisTab === 'overview'`. |
| **Return Margin** | Route Plan Trigger | `active.summary` | `eva_budget_hours` | `POST /api/v1/routes/plan` | `return_constraint.py` | `summary.max_return_time_minutes` | `setResult(data)` | **VERIFIED:** Highlighted in red (`text-warn`) if return exceeds EVA budget. |

---

### 2.3 Route Selection, Alternatives & Algorithm Benchmarks

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Route Line** | Map Canvas Layer | `result.routes[0]` | `start`, `end` | `POST /api/v1/routes/plan` | `astar.py` | `routes[0].geometry` | `MapView.jsx:450-520` | **VERIFIED:** Rendered immediately as cyan polyline on OpenLayers map. |
| **Alternative Corridors** | Comparison Table Rows (`main.jsx:2189-2230`) | `selected` (route ID) | None (backend generates up to 3) | `POST /api/v1/routes/plan` | `alternatives.generate_alternative_corridors()` | `routes[1..2]` | `setSelected(r.route_id)` | **PARTIALLY OCCLUDED:** Clickable rows switch active route and map highlight, but located in Right Drawer (`analysisTab === 'overview'`). |
| **A* vs Dijkstra Benchmark** | Select `algorithm: "compare"` | `result.algorithm_comparison` | `algorithm: "compare"` | `POST /api/v1/routes/plan` | `route_service._run_benchmark_comparison()` | `algorithm_comparison` | `main.jsx:2094-2138` | **VERIFIED:** Renders 2x4 comparison table showing 25.77x node expansion speedup and cost parity. |
| **Elevation Cross-Section** | Bottom Profile Drawer Toggle | `activeProfileTab`, `active` | None | Client-side interpolation from route steps | None | `active.steps[].elevation_m` | `Profile.jsx:50-250` | **VERIFIED:** Canvas area chart showing terrain elevation profile along route distance. |
| **Slope Cross-Section** | Profile Tab Switcher (`Profile.jsx`) | `activeProfileTab = 'slope'` | None | Client-side interpolation from route steps | None | `active.steps[].slope_deg` | `Profile.jsx:50-250` | **VERIFIED:** Line chart showing slope spikes and hazard threshold lines. |

---

### 2.4 MARSPath 2.0 Advanced Differentiation Features

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Uncertainty Stress Testing** | Tab `analysisTab === 'robustness'` | `result.robustness` | `robustness_scenarios` | `POST /api/v1/routes/plan` | `robustness_service.assess_robustness()` | `robustness.scenarios` | `main.jsx:2579-2670` | **VERIFIED:** Displays probability distribution of distance, slope, and cost under perturbation. |
| **Scientific Reliability Score** | Tab `analysisTab === 'robustness'` | `result.robustness.scientific_reliability` | None | `POST /api/v1/routes/plan` | `robustness_service.compute_scientific_reliability()` | `scientific_reliability.*` ($R$, score, multiplier) | `main.jsx:2610-2660` | **VERIFIED:** Renders score badge (`HIGH`, `MEDIUM`, `LOW`), formula breakdown, and penalty disclaimers. |
| **Next-Best Reconnaissance** | Tab `analysisTab === 'evidence'` | `result.provenance.reconnaissance_recommendations` | None | `POST /api/v1/routes/plan` | `evidence_service.generate_recon_recommendations()` | `reconnaissance_recommendations` | `main.jsx:2490-2520` | **VERIFIED:** Lists prioritized orbital acquisitions for unmapped NoData footprints. |
| **Science Return per EVA Hour** | Tab `analysisTab === 'science'` | `active.science_return` | `science_waypoints` | `POST /api/v1/routes/plan` | `cost_model.evaluate_science_return()` | `science_return.points_per_eva_hour` | `main.jsx:2515-2535` | **VERIFIED:** Quantifies geological return rate based on visited features and duration. |
| **7 Martian Failure Scenarios** | Conditions Modal (`ConditionsPanel.jsx`) | `stressTestResults` | Scenario trigger | `POST /api/v1/conditions/stress-test` | `conditions/stress_testing.py` | `scenarios[].outcome` | `ConditionsPanel.jsx` | **VERIFIED:** Evaluates dust storms, solar eclipses, steep slope stalls, communication dropouts. |

---

### 2.5 Planetary Data Ingestion & Live Intelligence

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NASA Data Catalog** | Top Bar "NASA Data" Button (`main.jsx:1340`) | `catalogData`, `isNasaDataOpen` | None | `GET /api/v1/data-sources/catalog` | `catalog_service.get_catalog_summary()` | `sources[]`, `total_sources` | `NasaDataPanel.jsx` | **VERIFIED:** Modal opens displaying all 8 NASA connectors, versions, and sync status. |
| **High-Speed Data Sync** | "Sync All Sources" Button | `isSyncing` | None | `POST /api/v1/data-sources/sync` | `sync_service.sync_all_sources()` (asyncio.gather) | `sync_duration_seconds`, `results` | `NasaDataPanel.jsx` | **VERIFIED:** Completes parallel sync in 2.57 seconds (accelerated from 7.14s). |
| **Mars24 Solar Time** | Top Bar "Live Intel" Button | `liveConditions`, `isConditionsOpen` | `sol: int`, `site: "jezero"` | `GET /api/v1/conditions/live` | `conditions/mars24.py` | `local_solar_time`, `solar_elevation_deg` | `ConditionsPanel.jsx` | **VERIFIED:** Real-time LTST clock and sub-solar latitude calculation. |
| **Terrain Shadow Masking** | Conditions Modal Toggle | `shadowOverlayActive` | `sun_azimuth`, `sun_elevation` | `GET /api/v1/conditions/shadows` | `conditions/terrain_shadows.py` | `shadow_raster_url` | `ConditionsPanel.jsx` | **VERIFIED:** Ray-traced shadow overlay rendered over Jezero DEM. |
| **Rover Telemetry Replay** | Sol Slider in Conditions Modal | `selectedSol` | `sol: int` | `GET /api/v1/conditions/rover-track` | `conditions/rover_replay.py` | `sol_position`, `heading`, `odometer_km` | `ConditionsPanel.jsx` | **VERIFIED:** Renders sol-by-sol Perseverance traverse playback. |

---

### 2.6 Mission Export & Cloud Security

| Feature Name | Control Element | React State Variable | Request Payload Field | Backend Endpoint & Handler | Domain Service Function | Response JSON Field | Frontend State Handler | User Visibility & Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **GeoJSON Route Export** | Top Export Dropdown -> "GeoJSON" (`export.js`) | `active` | None | Client-side export | None | GeoJSON FeatureCollection | Native browser download | **VERIFIED:** Downloads valid RFC 7946 GeoJSON file with elevation steps. |
| **CSV Traversal Export** | Top Export Dropdown -> "CSV" (`export.js`) | `active` | None | Client-side export | None | CSV waypoint table | Native browser download | **VERIFIED:** Generates comma-separated coordinate, slope, and elevation table. |
| **Markdown Mission Brief** | Top Export Dropdown -> "Briefing" (`export.js`) | `result`, `active` | None | Client-side export | None | Markdown dossier string | Native browser download | **VERIFIED:** Exports executive summary with route metrics and data provenance. |
| **Server-Side PDF Dossier** | Top Export Dropdown -> "Export PDF" (`export.js`) | `active`, `isExportingPdf` | `RouteExportPdfRequest` | `POST /api/v1/routes/export/pdf` | `pdf_export_service.build_mission_dossier_pdf()` | `application/pdf` binary stream | Blob URL download trigger | **VERIFIED:** Streams publication-quality multi-page PDF generated via ReportLab. |
| **Cloud Storage Token Guard** | Backend Signed URL Download | None | `token: str` | `GET /api/v1/cloud/storage/download` | `cloud_router._verify_signed_token()` | File stream or 401 Unauthorized | N/A | **VERIFIED:** Rejects invalid/forged tokens with HTTP 401; HMAC-SHA256 enforced. |
