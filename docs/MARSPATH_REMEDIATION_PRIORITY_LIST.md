# MARSPath Remediation Priority List & Action Roadmap

**Document ID:** `MARSPATH-REM-ROD-001`  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Date:** November 15, 2026  
**Auditor:** Principal Software Architect & Release Manager  
**Scope:** Actionable, Prioritized Engineering Roadmap with Root Causes, Dependencies, and Acceptance Criteria  

---

## 1. Prioritization Taxonomy

* **Priority 0 (P0) — Production Deployment & Release Parity:** Immediate release-blocking items. The code is complete, tested, and green, but unmerged to production `main`.
* **Priority 1 (P1) — Critical Visibility & Terminology Alignment:** Capabilities exist in code and APIs, but are occluded, collapsed, or mislabeled, directly causing the project owner's reported missing features.
* **Priority 2 (P2) — Functional Enhancements & Cartographic Overlays:** Operational extensions that elevate existing scalar data to interactive map visualizations.
* **Priority 3 (P3) — UX Polish & Onboarding Guidance:** First-run empty states, help tooltips, and document styling.

---

## 2. Prioritized Remediation Roadmap

### Priority 0: Production Release Parity

#### `REM-P0-01`: Merge PR #10 into Production `main` and Deploy
* **Root Cause:** All map feathering, NoData transparency, A* vs Dijkstra benchmark, PDF export, accelerated parallel sync, and HMAC security fixes reside on feature branch `fix/marspath-map-transparency-feathering`. Production `main` remains on legacy commit `4aa1ab2`.
* **Affected Components:**
  - Entire repository: `backend/`, `mission-ui/`, `docs/`, Docker build.
* **Dependencies:** GitHub branch protection approval from `@Kunal-Dafuq` or admin override.
* **Acceptance Criteria:**
  1. PR #10 is merged cleanly into `main` via merge commit.
  2. GitHub Actions CI on `main` passes 100%.
  3. Render backend auto-deploys successfully from `main`.
  4. Vercel frontend auto-deploys successfully from `main`.
  5. Live production URL (`https://marspath.vercel.app/mission-control/`) reflects seamless feathering and benchmark tools.

---

### Priority 1: Critical Visibility & Terminology Alignment (Addressing Owner Concerns)

#### `REM-P1-01`: Elevate Cost & Terrain Breakdown to Always-Visible Section
* **Root Cause:** In `mission-ui/src/main.jsx:338`, `const [detailsOpen, setDetailsOpen] = useState(false)`. The itemized cost breakdown (`base_distance_cost`, `slope_penalty`, `roughness_penalty`, `hazard_penalty`, `extra_penalty`) is collapsed inside `<details className="analysis-details">` (`main.jsx:2320`), making it invisible unless explicitly expanded.
* **Affected Components:**
  - `mission-ui/src/main.jsx:338`, `main.jsx:2320-2350`, `mission-ui/src/style.css`.
* **Dependencies:** None (Pure frontend UI change).
* **Acceptance Criteria:**
  1. Change default state to `useState(true)` or remove the `<details>` wrapper in favor of a permanent "Mission Cost & Terrain Breakdown" card.
  2. Display "Total Routing Cost" and penalty shares prominently with visual horizontal progress bars.
  3. Cost values are clearly annotated as mathematical graph cost units.

#### `REM-P1-02`: Re-label "Est. Relative Effort" to "Energy Index / Work" with Nuclear/Solar Rover Tooltip
* **Root Cause:** The Minetti mechanical work model is labeled `Est. Relative Effort: XXX eq-m (slope_penalty)` (`main.jsx:2253`). The user expected "Energy" or "Fuel" and failed to recognize this metric.
* **Affected Components:**
  - `mission-ui/src/main.jsx:2250-2255`, `main.jsx:2194`, `mission-ui/src/Profile.jsx`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  1. Rename table header and card label to "Energy Index (Work)".
  2. Render a permanent informative pill: *"Nuclear / Solar Powered — Mars rovers do not use liquid fuel; energy index represents path-integrated mechanical work against gravity and rolling friction."*
  3. Display estimated electrical battery consumption in kWh alongside equivalent meters (`eq-m`).

#### `REM-P1-03`: Elevate Alternative Route Comparison to High-Visibility HUD Card
* **Root Cause:** `<table className="route-compare-table">` is located inside the Right Analysis Drawer under `analysisTab === 'overview'`. If the user does not open or scroll through the drawer, they cannot see or switch between alternative routes.
* **Affected Components:**
  - `mission-ui/src/main.jsx:2189-2230`, `mission-ui/src/MapView.jsx`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  1. Surface a floating "Route Candidates" pill selector on the top-left map HUD showing:
     - `[Primary Route]`
     - `[Alternative Corridor]`
     - `[Safety-First Backup]`
  2. Clicking any pill immediately switches the active route, updates the OpenLayers highlight polyline, and refreshes the profile cross-section.
  3. Include an "Optimal" badge on the route with lowest total cost.

---

### Priority 2: Functional Enhancements & Cartographic Overlays

#### `REM-P2-01`: 2D Return-to-Base Safe Isochrone Map Visualization
* **Root Cause:** The return-time constraint is computed numerically (`max_return_time_minutes`, `exceeds_return_budget`), but is not rendered as a geographic polygon on the OpenLayers map.
* **Affected Components:**
  - `backend/app/routing/return_constraint.py`, `backend/app/schemas/routes.py`, `mission-ui/src/MapView.jsx`.
* **Dependencies:** `routes[].summary.max_return_time_minutes`.
* **Acceptance Criteria:**
  1. Backend generates a convex hull or isochrone contour representing the maximum safe operating radius for the configured EVA budget.
  2. OpenLayers renders a translucent green/amber dashed perimeter ring around the mission base/landing site.
  3. Any route segment extending beyond this boundary is highlighted in red.

#### `REM-P2-02`: High-Resolution HiRISE DTM Direct Ingestion Pipeline
* **Root Cause:** In the standard repository, HiRISE 1m DTM falls back to MOLA/HRSC blend DEM unless the optional 1.2 GB local GeoTIFF is manually downloaded into `backend/app/data/rasters/`.
* **Affected Components:**
  - `backend/app/data/providers/hirise.py`, `backend/scripts/download_sample_rasters.py`.
* **Dependencies:** Storage bandwidth.
* **Acceptance Criteria:**
  1. Provide a lightweight automated provisioning script using USGS/PDS Cloud Storage to stream or download the Jezero Delta HiRISE DTM GeoTIFF on demand.
  2. Provider automatically flags `hirise_selected = true` when querying within the Jezero Western Fan boundary.

---

### Priority 3: UX Polish & Onboarding Guidance

#### `REM-P3-01`: First-Run Empty State Guidance Card
* **Root Cause:** When the application first loads, state variables are empty, displaying dashes (`—`) across the HUD. First-time users perceive the application as unresponsive or unpopulated.
* **Affected Components:**
  - `mission-ui/src/main.jsx:1450-1480`.
* **Dependencies:** None.
* **Acceptance Criteria:**
  1. When `result === null`, display a friendly overlay card: *"Welcome to MARSPath Mission Control. Select a mission preset above or click anywhere on Jezero Crater to plan an optimal traversal route."*
  2. Highlight the "Jezero Delta Fan" preset button with a subtle pulse animation.

#### `REM-P3-02`: PDF Mission Dossier Styling Parity
* **Root Cause:** The server-side ReportLab PDF export uses standard publication white backgrounds, whereas the web UI uses dark mode aerospace styling.
* **Affected Components:**
  - `backend/app/services/pdf_export_service.py`.
* **Dependencies:** ReportLab 4.0+.
* **Acceptance Criteria:**
  1. Offer a toggle for "Dark Flight Operations Briefing" vs "Archival Clean Print" PDF styling.
  2. Include mission patch logos and high-resolution OpenLayers map snapshot embeddings in the PDF.
