# MARSPath Master Feature Inventory & Requirements Register

**Document ID:** `MARSPATH-REQ-INV-001`  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Target Branches:** `main` (Production), `fix/marspath-map-transparency-feathering` (Release Candidate PR #10), `kunal` (Frontend Baseline)  
**Date:** November 15, 2026  
**Auditor:** Principal Software Architect & Mission Planning Systems Engineer  
**Audit Scope:** Complete System Requirements Traceability, Backend Capabilities, Frontend Implementation, and Production Exposure  

---

## 1. Requirements Discovery & Specification Lineage

To establish an authoritative requirements baseline, this audit synthesized all historical and active specification documents across the project's evolution:

1. **`MARSPath_Website_Architecture_and_Team_Plan` (Baseline v1.0):** Defined team roles (Niharika: Backend/Geospatial/Routing; Kunal: Frontend/UI/Map Integration; Shared: Integration & Deployment). Specified core routing in Jezero Crater, interactive Mars map, profile viewer, and multi-criteria optimization.
2. **`MARSPath_Martian_Map_Track_Research_Brief` (Research Spec):** Outlined planetary coordinate reference systems (IAU2000 Mars Sphere / Web Mercator projection), USGS Astrogeology WMTS tile pyramids (Viking MDIM2.1, CTX, HiRISE), and MOLA/HRSC blend DEM products.
3. **`MARSPath_Backend_Functionality_and_Frontend_Integration_Handover` (API Contract v1.0):** Established the `/api/v1/routes/plan` contract, slope/roughness penalty formulations, route summary schemas, and GeoJSON export schemas.
4. **`MARSPath 2.0 — Advanced Mission Intelligence & Competitive Differentiation` (v2.0 Spec):** Added five advanced capabilities:
   - Uncertainty-Aware Route Planning (Monte Carlo / Gaussian perturbation)
   - Pareto-Optimal Mission Trade-off Engine (Multi-objective candidate generation)
   - Next-Best-Reconnaissance Planner (Targeted orbital acquisition recommendations)
   - Scientific Return per EVA Hour (Quantitative geological value optimization)
   - Mission Stress-Testing Centre (7 deterministic Martian environmental failure modes)
5. **NASA Data Intelligence Handover (`NASA_DATA_SOURCE_INTEGRATION_MATRIX.md`):** Defined connectors for Mars Trek, NAIF SPICE, PDS Atmospheres (MEDA), PDS Geosciences, PDS Releases, Planetary Notebook, and THEMIS thermal inertia.
6. **Live Intelligence Architecture (`LIVE_MARS_INTELLIGENCE_ARCHITECTURE.md`):** Real-time Mars24 solar geometry, shadow simulation, and Perseverance/Curiosity telemetry ingestion.

### 1.1 Document Conflict Resolution & Authoritative Precedence

Where specifications diverged over time, the following authoritative rules were enforced:

* **Energy Model vs Fuel Model:** Baseline brief colloquially mentioned "fuel/energy", but the formal Handover Spec (`API_CONTRACT.md` §3.2) explicitly clarifies:
  > *"Martian surface rovers (Perseverance, Curiosity) utilize Radioisotope Thermoelectric Generators (MMRTG) or solar arrays, not liquid propellant or combustion fuel. The physical metric is mechanical work and battery energy (kWh / state-of-charge), while the routing model computes a dimensionless `energy_index`. No physical chemical propellant model exists or was designed."*
  **Authoritative Spec:** Dimensionless `energy_index` representing path-integrated mechanical work against gravity and rolling friction.
* **Coordinate Systems:** Early drafts referenced Equirectangular coordinates (`EPSG:4326` equivalent); the production mapping engine utilizes Spherical Mercator (`EPSG:3857`) for OpenLayers tile compatibility with explicit forward/inverse transformations to aerocentric lat/lon (`EPSG:4997`).
  **Authoritative Spec:** Map rendering in `EPSG:3857`; routing, elevation grids, and scientific coordinates strictly in Planetocentric Decimal Degrees.
* **Algorithm Selection:** Baseline spec referenced A* as the sole production engine; Phase 6 requested Dijkstra comparison capability.
  **Authoritative Spec:** A* is the primary operational planner; Dijkstra is the rigorous unguided baseline, selectable via `algorithm="dijkstra"` or `algorithm="compare"`.

---

## 2. Master Requirements Register

Requirements are classified under stable identifiers:
- `REQ-CORE-xxx`: Original Core Mission Requirements
- `REQ-KUNAL-xxx`: Kunal Frontend & UI Requirements
- `REQ-GEO-xxx`: Backend, Terrain & Geospatial Requirements
- `REQ-INT-xxx`: Full-Stack Integration Requirements
- `REQ-ADV-xxx`: MARSPath 2.0 Advanced Differentiation Requirements
- `REQ-OPS-xxx`: Cloud, AI & Operational Telemetry Requirements
- `REQ-NEW-xxx`: Newly Discovered Documented Requirements

### 2.1 Category Classification Key
- **MANDATORY:** Core operational requirement necessary for mission feasibility.
- **OPTIONAL / BENCHMARK:** Reference mode, analytical comparison, or secondary tool.
- **PROTOTYPE / EXTENSION:** Advanced research capability or cloud extension.

---

### Category A: Planetary Map & Imagery

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-CORE-001` | Map Research Brief | Global Mars Basemap (Viking MDIM 2.1 Color) | MANDATORY | USGS WMTS Endpoint | `MapView.jsx:200-240` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-002` | Map Research Brief | Regional High-Res CTX Mosaic (Jezero Crater, 6m/px) | MANDATORY | USGS WMTS Endpoint | `MapView.jsx:245-280` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-003` | Map Research Brief | Ultra-High-Res HiRISE Orthomosaic (Jezero Delta, 25cm/px) | MANDATORY | USGS WMTS Endpoint | `MapView.jsx:285-320` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-004` | Handover Spec v1 | NoData Transparency (Alpha = 0 for unmapped pixels) | MANDATORY | Canvas Raster Pipeline | `MapView.jsx:130-160` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-005` | Map Fix PR #10 | Seamless Edge Feathering (48–64px gradient mask) | MANDATORY | Destination-Out Compositing | `MapView.jsx:165-240` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-006` | Map Fix PR #10 | Multi-Resolution Layer CSS Classes & Tone Harmonization | MANDATORY | None | `style.css:320-335`, `MapView.jsx` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-007` | Map Research Brief | MOLA / HRSC Shaded Relief & Color Elevation Overlay | MANDATORY | USGS WMTS Endpoint | `MapView.jsx:325-360` | **VERIFIED** | **Visible via Toggle** |
| `REQ-CORE-008` | Architecture Plan | Interactive Map Pan, Zoom, and Coordinate Readout | MANDATORY | None | `MapView.jsx:80-120` | **VERIFIED** | **Immediately Visible** |
| `REQ-CORE-009` | Architecture Plan | Rover Traverse Overlays (Perseverance & Curiosity) | MANDATORY | GeoJSON Fixtures | `MapView.jsx:400-440` | **VERIFIED** | **Visible via Toggle** |

---

### Category B: Mission Configuration & Input Controls

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-KUNAL-001` | Architecture Plan | Pre-configured Mission Presets (Jezero Delta, Crater Rim, etc.) | MANDATORY | None | `main.jsx:350-410` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-002` | Architecture Plan | Interactive Start & Goal Pin Placement on Map | MANDATORY | None | `MapView.jsx:450-490` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-003` | Architecture Plan | Manual Latitude/Longitude Decimal Degree Coordinate Input | MANDATORY | None | `main.jsx:1530-1580` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-004` | Architecture Plan | Science Target & Waypoint Coordinate Specification | MANDATORY | `schemas/routes.py` | `main.jsx:1630-1670` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-005` | Handover Spec v1 | Routing Profile Mode Selector (`balanced`, `safety_first`, `shortest_distance`) | MANDATORY | `cost_model.py` | `main.jsx:1590-1610` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-006` | PR #10 Handover | Algorithm Selector (`astar`, `dijkstra`, `compare`) | MANDATORY | `route_service.py` | `main.jsx:1614-1628` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-007` | Handover Spec v1 | Traversal Constraints (Max slope threshold: 5° to 30°) | MANDATORY | `schemas/routes.py` | `main.jsx:1675-1710` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-008` | Handover Spec v1 | EVA Mission Time Budget Configuration (hours) | MANDATORY | `schemas/routes.py` | `main.jsx:1715-1740` | **VERIFIED** | **Immediately Visible** |
| `REQ-KUNAL-009` | MARSPath 2.0 | Robustness Stress-Test Scenario Count (3 to 200) | MANDATORY | `robustness_service.py` | `main.jsx:1867-1880` | **VERIFIED** | **Immediately Visible** |

---

### Category C: Route Planning & Path Optimization

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-GEO-001` | Handover Spec v1 | 3D Octile/Euclidean A* Heuristic Path Planning | MANDATORY | `routing/astar.py` | `main.jsx:750-890` | **VERIFIED** | **Immediately Visible** |
| `REQ-GEO-002` | PR #10 Handover | Uniform-Cost Dijkstra Reference Search | BENCHMARK | `routing/dijkstra.py` | `main.jsx:750-890` | **VERIFIED** | **Visible via Selector** |
| `REQ-GEO-003` | PR #10 Handover | A* vs Dijkstra Benchmark Performance Matrix | BENCHMARK | `route_service.py:350-450` | `main.jsx:2094-2138` | **VERIFIED** | **Immediately Visible (under Benchmark)** |
| `REQ-GEO-004` | Handover Spec v1 | Multi-Resolution Terrain Source Auto-Selection | MANDATORY | `terrain_source_service.py` | `main.jsx:2460-2495` | **VERIFIED** | **Visible in Details Tab** |
| `REQ-GEO-005` | Handover Spec v1 | HiRISE 1m DTM Query with MOLA/HRSC Fallback | MANDATORY | `hirise_provider.py` | `main.jsx:2474-2483` | **VERIFIED** | **Visible in Details Tab** |
| `REQ-GEO-006` | Handover Spec v1 | Slope & Roughness Continuous Terramechanics Cost Model | MANDATORY | `routing/cost_model.py` | `main.jsx:2540-2565` | **VERIFIED** | **Visible in Details Tab** |
| `REQ-GEO-007` | Handover Spec v1 | Multi-Alternative Route Generation (up to 3 corridors) | MANDATORY | `routing/alternatives.py` | `main.jsx:2140-2250` | **VERIFIED** | **Visible in Comparison Tab** |
| `REQ-GEO-008` | Handover Spec v1 | Active Candidate Route Selection & Map Highlighting | MANDATORY | None | `main.jsx:2160-2180`, `MapView.jsx` | **VERIFIED** | **Visible in Comparison Tab** |
| `REQ-GEO-009` | Architecture Plan | Interactive Elevation & Slope Profile Cross-Section Chart | MANDATORY | `route_service.py` | `Profile.jsx:50-250` | **VERIFIED** | **Visible via Bottom Drawer** |

---

### Category D: Cost, Energy, EVA & Feasibility Estimation

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-COST-001` | Handover Spec v1 | Path-Integrated Total Cost & Itemized Penalty Breakdown | MANDATORY | `cost_model.py:250-320` | `main.jsx:2540-2565` | **VERIFIED** | **Visible in Details Tab** |
| `REQ-COST-002` | Handover Spec v1 | Dimensionless Mechanical Energy Index Computation | MANDATORY | `cost_model.py:330-380` | `main.jsx:2572-2580` | **VERIFIED** | **Visible in Details Tab** |
| `REQ-COST-003` | Handover Spec v1 | Physical Chemical Fuel / Propellant Estimation Model | NOT SPECIFIED | None | None | **NOT APPLICABLE** | **N/A (Rovers are Nuclear/Solar)** |
| `REQ-EVA-001` | Handover Spec v1 | Terramechanics Slope-Derated Walking Duration (hours) | MANDATORY | `cost_model.py:390-440` | `main.jsx:2020-2035` | **VERIFIED** | **Immediately Visible (Primary HUD)** |
| `REQ-EVA-002` | Handover Spec v1 | EVA Mission Feasibility & Remaining Time Margin Check | MANDATORY | `schemas/routes.py` | `Profile.jsx:120-150` | **VERIFIED** | **Visible in Bottom Drawer** |
| `REQ-EVA-003` | Architecture Plan | Return-to-Base Safe Operating Radius / Margin Analysis | MANDATORY | `return_constraint.py` | `main.jsx:2585-2605` | **VERIFIED** | **Visible in Details Tab** |

---

### Category E: Advanced MARSPath 2.0 Capabilities

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-ADV-001` | MARSPath 2.0 Spec | Uncertainty-Aware Monte Carlo Stress Testing (3–200 runs) | MANDATORY | `robustness_service.py` | `main.jsx:2600-2670` | **VERIFIED** | **Visible in Robustness Tab** |
| `REQ-ADV-002` | MARSPath 2.0 Spec | Multi-Factor Scientific Reliability Score Formula | MANDATORY | `robustness_service.py:550-640` | `main.jsx:2610-2660` | **VERIFIED** | **Visible in Robustness Tab** |
| `REQ-ADV-003` | MARSPath 2.0 Spec | Synthetic Terrain Reliability Penalty Capping ($\le 40\%$) | MANDATORY | `robustness_service.py:615-625` | `main.jsx:2620-2635` | **VERIFIED** | **Visible in Robustness Tab** |
| `REQ-ADV-004` | MARSPath 2.0 Spec | Pareto-Optimal Multi-Objective Trade-Off Evaluator | MANDATORY | `routing/alternatives.py` | `main.jsx:2140-2250` | **VERIFIED** | **Visible in Comparison Tab** |
| `REQ-ADV-005` | MARSPath 2.0 Spec | Next-Best-Reconnaissance Targeted Acquisition Engine | MANDATORY | `evidence_service.py` | `main.jsx:2490-2520` | **VERIFIED** | **Visible in Source Tab** |
| `REQ-ADV-006` | MARSPath 2.0 Spec | Scientific Return per EVA Hour Metric | MANDATORY | `cost_model.py:445-480` | `main.jsx:2515-2535` | **VERIFIED** | **Visible in Source Tab** |
| `REQ-ADV-007` | MARSPath 2.0 Spec | Mission Stress Testing (7 Martian Failure Scenarios) | MANDATORY | `conditions/stress_testing.py` | `ConditionsPanel.jsx` | **VERIFIED** | **Visible in Conditions Panel** |

---

### Category F: Planetary Data Ingestion & Live Intelligence

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-DATA-001` | Data Ingestion Spec | PDS Atmospheres MEDA Jezero Weather Ingestion | MANDATORY | `connectors/pds_atmospheres` | `NasaDataPanel.jsx` | **VERIFIED** | **Visible in NASA Data Modal** |
| `REQ-DATA-002` | Data Ingestion Spec | THEMIS Infrared Thermal Inertia Connector | MANDATORY | `connectors/themis` | `NasaDataPanel.jsx` | **VERIFIED** | **Visible in NASA Data Modal** |
| `REQ-DATA-003` | Data Ingestion Spec | NAIF SPICE Planetary Ephemerides & Rover Position | MANDATORY | `connectors/naif_spice` | `NasaDataPanel.jsx` | **VERIFIED** | **Visible in NASA Data Modal** |
| `REQ-DATA-004` | Data Ingestion Spec | NASA Data Source Catalogue & Health Status Registry | MANDATORY | `registry/registry.py` | `NasaDataPanel.jsx` | **VERIFIED** | **Visible in NASA Data Modal** |
| `REQ-DATA-005` | Data Ingestion Spec | Asynchronous High-Speed Connector Synchronization | MANDATORY | `services/sync_service.py` | `NasaDataPanel.jsx` | **VERIFIED** | **Visible in NASA Data Modal** |
| `REQ-LIVE-001` | Live Intel Spec | Real-Time Mars24 Solar Time & Sub-Solar Point Engine | MANDATORY | `conditions/mars24.py` | `ConditionsPanel.jsx` | **VERIFIED** | **Visible in Conditions Panel** |
| `REQ-LIVE-002` | Live Intel Spec | Dynamic Sun Elevation & Terrain Ray-Traced Shadow Mask | MANDATORY | `conditions/terrain_shadows.py` | `ConditionsPanel.jsx` | **VERIFIED** | **Visible in Conditions Panel** |
| `REQ-LIVE-003` | Live Intel Spec | Rover Telemetry Replay (Sol-by-Sol Position & Heading) | MANDATORY | `conditions/rover_replay.py` | `ConditionsPanel.jsx` | **VERIFIED** | **Visible in Conditions Panel** |

---

### Category G: Cloud, AI Copilot & Mission Export

| Requirement ID | Specification Source | Description | Class | Backend Component | Frontend Component | Implementation Status | User Visibility |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `REQ-EXP-001` | Architecture Plan | GeoJSON Route Geometry Export | MANDATORY | None | `export.js:1-36` | **VERIFIED** | **Immediately Visible (Export Bar)** |
| `REQ-EXP-002` | Architecture Plan | CSV Route Waypoints & Terrain Data Export | MANDATORY | None | `export.js:38-70` | **VERIFIED** | **Immediately Visible (Export Bar)** |
| `REQ-EXP-003` | Architecture Plan | Markdown Mission Briefing Document Export | MANDATORY | None | `export.js:72-120` | **VERIFIED** | **Immediately Visible (Export Bar)** |
| `REQ-EXP-004` | PR #10 Handover | ReportLab Server-Side Mission Dossier PDF Export | MANDATORY | `services/pdf_export_service.py` | `export.js:125-180` | **VERIFIED** | **Immediately Visible (Export Bar)** |
| `REQ-OPS-001` | Cloud Architecture | Cloud Storage Signed URL Token Verification (HMAC) | MANDATORY | `cloud_router.py:45-90` | None | **VERIFIED** | **Backend Security Guard** |
| `REQ-AI-001` | Cloud & AI Spec | Multimodal Martian Imagery Context Builder | PROTOTYPE | `orchestration/context_builder.py` | `CloudAiPanel.jsx` | **VERIFIED** | **Visible in AI Modal** |
| `REQ-AI-002` | Cloud & AI Spec | Azure AI Foundry & Gemini Science Copilot Chat | PROTOTYPE | `providers/azure_foundry.py` | `CloudAiPanel.jsx` | **VERIFIED** | **Visible in AI Modal** |
