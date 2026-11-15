# MARSPath — Kunal Frontend Ownership Completion Tracker

**Assigned Frontend Owner:** Kunal  
**Geospatial & Backend Owner:** Niharika Singh  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Active Working Branch:** `feature/astronaut-survival-frontend`  
**Target Merge PR:** `main`  
**Date of Audit & Verification:** November 15, 2026  
**Automated Verification Suite:** 13/13 test suites passing (`check-astronaut-survival.mjs`, `check-kunal-completion.mjs`, etc.)

---

## Complete Ownership & Verification Matrix

The table below documents all 30 frontend features and responsibilities under Kunal's ownership, formatted in the mandatory 5-column schema:
1. `Feature / Responsibility`
2. `Implementation Status` (`VERIFIED`, `IMPLEMENTED`, `BLOCKED BY BACKEND`)
3. `Verification Evidence / Screenshots`
4. `API Integration Status`
5. `Notes / Dependencies`

| Feature / Responsibility | Implementation Status | Verification Evidence / Screenshots | API Integration Status | Notes / Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| **1. Main Planetary Map Workspace** | `VERIFIED` | Clean continuous Mars Trek Viking basemap; no tile gaps, square masks, or debug outlines. Automated test: `check-map-fix-traverse-window.mjs`. | Local / WMTS Static | OpenLayers 10.7 viewport with custom Martian equirectangular projection (`EPSG:49900`, radius 3,396,190 m). |
| **2. Viking Global Imagery** | `VERIFIED` | `wmtsVikingGlobal` tile layer connected to USGS/NASA Mars Trek WMTS endpoint with fallback to validated tiles. | WMTS GetCapabilities Validated | Smooth zoom and pan; default basemap. |
| **3. CTX Regional Imagery** | `VERIFIED` | Multi-resolution CTX mosaic layer with edge feathering and opacity control. Bounds: `[77.16, 18.21, 77.70, 18.72]`. | WMTS / Local GeoTIFF | Layer toggle in Layers popover; soft alpha feathering removes rectangular seams. |
| **4. HiRISE Local Imagery** | `VERIFIED` | 25 cm/px local ortho mosaic (`DOI: 10.5066/P9QJDP48`) with resolution-dependent display (<35 m/px). | WMTS / High-Res TileSource | Off by default to keep clean road-map view; optional in Layers popover. |
| **5. MOLA/HRSC Shaded Relief Terrain** | `VERIFIED` | 200 m/px USGS blended hillshade layer (`DOI: 10.5066/P907276M`). | Local DEM / WMTS | Powers deterministic elevation and slope lookups via `terrain.js`. |
| **6. Map Zoom, Pan, and Layer Transitions** | `VERIFIED` | Smooth OpenLayers transitions, scale line in metric units, 3D tilt toggle, and bookmark selector (Jezero, Gale, Olympus Mons, Valles Marineris). | Client State | Extent clamped to global Martian boundaries. |
| **7. Start and Destination Selection** | `VERIFIED` | Interactive map pin dropping ('Pick on map' mode) and coordinate row swap button. | Client State | Validates coordinates within Jezero coverage boundaries. |
| **8. Manual Coordinate Entry** | `VERIFIED` | Latitude/Longitude text inputs with instant parsing, validation, and error notice on out-of-bounds inputs. | Client State | Formats to 5 decimal places (~1 m on Mars). |
| **9. Mission Waypoint Selection** | `VERIFIED` | Science target waypoints selector (e.g. Neretva Vallis, Kodiak Mesa, Hawksbill Gap) with science value scores. | Client / Enricher | Stored in `scienceWaypoints` array and passed to routing engine. |
| **10. Route Visualization** | `VERIFIED` | High-contrast mint-green polyline (`#5cffb0`, zIndex 20) with start/destination markers and waypoint pins. | GeoJSON Vector Layer | Fully unclipped, distinct from muted taupe passive traverse (`#9c9489`). |
| **11. Route Alternatives Comparison Cards** | `VERIFIED` | Displays up to 3 candidate routes (Primary, Alt 1, Alt 2) with distance, duration, and Marswalk Survivability Score badges. | Full Integration (`POST /routes/plan`) | Shows actual count when fewer alternatives are feasible (`shortfall-banner`). |
| **12. Active Route Selection** | `VERIFIED` | Radio-button card selection synchronizing map highlight, elevation profile, resource summary, and export dossier. | Client State | Keyboard accessible; updates `selected` route ID. |
| **13. Elevation and Slope Profiles** | `VERIFIED` | Interactive SVG chart drawer displaying distance, elevation gain/loss, max slope, and hover cursor synchronized with map crosshair. | Local Terrain Engine | Minetti biomechanical metabolic effort displayed on profile header. |
| **14. Mission Configuration Controls** | `VERIFIED` | Routing algorithm (A*, Dijkstra), cost mode (Balanced, Safety First, Distance First), max slope slider, max roughness, departure time, and EVA budget. | Request Payload | Fully validated before submission. |
| **15. Loading and Error States** | `VERIFIED` | Shimmer calculating notices, backend timeout alerts, CORS origin configuration guidance, and retry buttons. | Client State | Graceful offline fallback to bundled DEM and local A* planner. |
| **16. Provenance & Evidence Passport** | `VERIFIED` | Route provenance strip showing data kind, source authority, resolution, DEM checksums, and USGS DOIs. | Full Integration (`GET /provenance/summary`) | Suppressed when in synthetic mode to prevent misleading claims. |
| **17. Backend API Integration** | `VERIFIED` | FastAPI connection manager supporting `health`, `status`, and `/routes/plan` with degraded-mode notification and reconnect. | Connected / Validated | Tested against local FastAPI and mock endpoints. |
| **18. Frontend Presentation of Mission Metrics** | `VERIFIED` | Distance (km), travel duration (hrs), Energy Index (dimensionless ratio $\times\text{ flat}$, no fake kWh/fuel), and surface 3D distance. | Full Integration | Complies with planetary rover and astronaut EVA physics standards. |
| **19. Export Controls & Route Synchronization** | `VERIFIED` | Multi-format export (PDF Mission Dossier, GeoJSON, CSV segments, Markdown brief, JSON manifest) strictly synchronized to selected route. | Client / PDF Service | Automated test: `check-kunal-completion.mjs` Pass 7. |
| **20. Responsive Mission Control Interface** | `VERIFIED` | Glassmorphic floating drawers (left planner, right analysis, bottom timeline/profile) with mobile auto-collapse (<850px). | CSS Media Queries | Tested across desktop (1920x1080) and mobile (768x1024) viewports. |
| **21. Astronaut Visor HUD (Field Execution Mode)** | `VERIFIED` | High-contrast astronaut tactical visor overlay (`ASTRONAUT VISOR HUD` button in topbar); includes 360° digital compass ribbon, PLSS suit O₂ reserve meter, EMU battery power draw, Minetti specific energy and metabolic watts, central target reticle with bearing arrows to target & base, countdown clock, and clear ESC exit button. | `[SIMULATED SUIT TELEMETRY]` & `[ASSUMED BATTERY CAPACITY]` | Full client interactive component `VisorHUD.jsx`. Clear notice distinguishing authentic Mars GIS from simulated suit life support telemetry. |
| **22. Marswalk Survivability Score Engine** | `VERIFIED` | 0–100 composite safety index combining Terrain Mobility (28%), Resource Margin (26%), Return Feasibility (24%), Environmental Radiation (14%), and RF Comms (8%). Prominently displayed next to candidate routes and in dedicated analysis card. | Deterministic Client Model (coordinates with backend `/stress/evaluate`) | Drops from nominal 96/100 to 45/100 during active Solar Particle Events (SPE). |
| **23. Solar Particle Event (SPE) Simulation** | `VERIFIED` | Interactive scenario simulator with S1–S4 severity selector ($2.5–100.0\text{ mSv/h}$), nearest terrain shelter beacon (Kodiak Mesa, Neretva Vallis, Belva Crater with $>70\%$ shielding factor), baseline vs scenario comparison, and one-click Reset button. | Scenario Simulation Engine | Nearest shelter navigator dynamically sets emergency destination. |
| **24. Dual-Radius Walk-Back Safety Map** | `VERIFIED` | Concentric safety envelopes centered on Habitat Base: primary Rover-Assisted Envelope (cyan `#00d4ff`, 5.2 km radius) and secondary On-Foot Astronaut Return Envelope (mint `#5cffb0`, 1.8 km radius). Evaluates walk-back feasibility at $1.0\text{ m/s}$ ($3.6\text{ km/h}$) and displays prominent warning if route exceeds on-foot limit. | Deterministic Geodesic Buffer (`getDualRadiusWalkBackGeoJSON`) | Integrated in `MapView.jsx` OpenLayers vector layer and Route Analysis drawer. |
| **25. Planetary Protection Special Regions** | `VERIFIED` | Catalog and interactive map polygons for COSPAR Category IVc zones: `PPZ-JEZ-01` (Neretva Vallis Delta, Red `#ef4444`), `PPZ-JEZ-02` (Candidate Sensitive, Amber `#f59e0b`), and `PPZ-JEZ-03` (Demo, Purple `#a855f7`). Point-in-polygon intersection detector warns when route traverses restricted region. | COSPAR Astrobiology Policy Catalog | Displays sterilization mandate (bioburden $<0.03\text{ spores/m}^2$) and human boots-on-the-ground exclusion notice. |
| **26. Scout Rover Conceptual Handoff Dialog** | `VERIFIED` | Interactive modal offering `DISPATCH SCOUT ROVER (SIMULATION)` to dispatch an uncrewed sterilized robotic rover (Perseverance Scout SC-01) with SHERLOC-lite and Raman micro-coring payload into Category IVc Special Regions. | Conceptual Robotic Handoff (`[SIMULATED RECONNAISSANCE REQUEST]`) | Confirmed dispatch updates mission log and displays confirmation notice. |
| **27. RF Communications & Line-of-Sight Analysis** | `VERIFIED` | Evaluates UHF radio line-of-sight to Base Habitat antenna mast, identifies terrain shadow zones, and displays active orbiter relay schedule (MRO Electra, TGO, Mars Odyssey). | Client Geometric Analysis | Predicts next orbiter pass window (e.g. T-42 min MRO Electra pass). |
| **28. Authentic NASA Surface POV Imagery** | `VERIFIED` | Map markers and photo lightbox viewer for authentic Perseverance Mastcam-Z and SuperCam ground photos: PIA24424 (Octavia E. Butler Landing, Sol 4), PIA24838 (Kodiak Mesa Delta Clinoforms, Sol 78), and PIA25325 (Hawksbill Gap Mudstones, Sol 482). | Official NASA/JPL Photojournal PDS | Links directly to authoritative NASA Photojournal catalog entries with camera, sol, and geological context. |
| **29. Multi-Hazard Compound Risk Fusion** | `VERIFIED` | Non-linear compound risk model combining slope, roughness, acute SPE radiation, and communications loss with hazard interaction penalties. Evaluates 0–100 risk index and assigns tier (Low, Moderate, Critical). | Algorithmic Risk Fusion (`survivability.js`) | Displayed in Visor HUD, Route Analysis, and injected into Copilot. |
| **30. Mars Science Copilot Smart Context Injection** | `VERIFIED` | Google Gemini Mars Science Copilot panel enhanced with quick prompt chips ("🧑‍🚀 Survivability & Minetti", "☀️ SPE Radiation & Shelters", "🚶 Walk-Back Safety", "🪐 Planetary Protection") and automatic injection of live active route distance, slope, survivability score, radiation state, and walk-back status. | Gemini / Cloud AI Client (`cloud_ai.js`) | Provides grounded planetary science and EVA tactical advice. |

---

## Backend Coordination & Pending Dependencies

As established in the Master Scope definition, FastAPI architecture, raw planetary DEM ingestion, backend Dijkstra/A* solver binaries, and scientific model weights remain under Niharika Singh's ownership.

The following potential endpoints have been architected and integrated on the frontend with deterministic client engines, ready for direct backend hookup when Niharika provisions the corresponding server-side routes:

1. `POST /eva/survivability`: Client currently calculates deterministic 0–100 composite score based on 5 sub-factors. Can bind to authoritative backend server model when available.
2. `POST /eva/scout-dispatch`: Client manages local state and conceptual dialog (`[SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST]`).
3. `GET /telemetry/plss`: Client renders simulated suit telemetry (`[SIMULATED SUIT TELEMETRY]`, `[ASSUMED BATTERY CAPACITY]`) adhering strictly to real astronaut metabolic physics (Minetti equations).

---

## Verification Summary

- **Automated Test Suites:** 13 out of 13 automated test suites pass with 100% success rate:
  - `check-engine.mjs` — PASS
  - `check-traverse.mjs` — PASS
  - `check-integration.mjs` — PASS
  - `check-intelligence.mjs` — PASS
  - `check-nasa-data.mjs` — PASS
  - `check-cloud-ai.mjs` — PASS
  - `check-usgs-imagery-dem.mjs` — PASS
  - `check-mars-now-conditions.mjs` — PASS
  - `check-mission-intelligence.mjs` — PASS
  - `check-map-rendering-fixes.mjs` — PASS
  - `check-kunal-completion.mjs` — PASS
  - `check-map-fix-traverse-window.mjs` — PASS
  - `check-astronaut-survival.mjs` — PASS (All 10 modules verified)
- **Production Bundle:** Verified clean build via `npx vite build` (`dist/mission-control/index.html`, `dist/mission-control/assets/index-_xz_L6p3.js`, `assets/index-BnZ-T9Rv.css`).
- **Live Browser Acceptance Verification:** Executed by autonomous browser subagent covering all 8 acceptance steps.
