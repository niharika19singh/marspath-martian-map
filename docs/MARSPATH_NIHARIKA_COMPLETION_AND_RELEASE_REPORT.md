# MARSPath — Production Release & Handover Report

**Document Version:** 1.1.0 (Production Verified Release)  
**Project:** MARSPath — Martian Mission Planning and Navigation Intelligence  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Primary Owner:** Niharika Singh (Backend, Geospatial, Routing Engine, Mission Intelligence)  
**Frontend Contributor:** Kunal (React Frontend, Interactive Planetary Map, OpenLayers Mission UX)  
**Final Production Main SHA:** `6c5b26b38031cbf76e2ed26f4e2817ad4916554c`  
**Release PR:** [PR #11 (Merged)](https://github.com/niharika19singh/marspath-martian-map/pull/11)  
**Date:** November 15, 2026  
**Final Status:** **`RELEASED — BOTH SERVICES DEPLOYED AND PRODUCTION VERIFIED.`**  

---

## 1. Production Deployment Identifiers & URLs

| Component | Platform | Service / Project ID | Deployment ID | Production URL | Deployment Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Backend API** | **Render** | `srv-dbrck4c9v7es73c6t2mg`<br>(`marspath-backend`) | `dep-dbsrpr15efls73f3dqi0` | `https://marspath-backend.onrender.com` | **LIVE** (Finished 2026-11-15T14:10:14Z) |
| **Frontend UI** | **Vercel** | `prj_UYdRLXLUu9GjiONpEJex1FhOC0ch`<br>(`marspath-frontend-dist`) | `dpl_AzyMqzpY7BhPEVcooiDipiF7oJtp` | `https://marspath.vercel.app/mission-control/`<br>`https://marspath.vercel.app` | **READY** (Aliased to production) |

---

## 2. Pull Request & Merge Verification

```mermaid
flowchart TD
    subgraph Phase1 ["1. Base Baseline"]
        A["main (4aa1ab2)"]
    end

    subgraph Phase2 ["2. Contributions Merged"]
        PR1["PR #1 (Niharika Geospatial Routing)<br/>Merged SHA: 4acf96a87d"]
        PR10["PR #10 (Kunal Map Transparency & Feathering)<br/>Merged SHA: c4cf286dc7"]
    end

    subgraph Phase3 ["3. Release Candidate & Final Merge"]
        RC["PR #11 (Unified Release Candidate)<br/>Base: main | Head: feature/marspath-release-candidate<br/>CI Run: 43722562906 (100% SUCCESS)"]
        PROD["Production main<br/>Final Merge Commit SHA: 6c5b26b38031cbf76e2ed26f4e2817ad4916554c"]
    end

    subgraph Phase4 ["4. Live Deployments"]
        DEP_RENDER["Render Service (srv-dbrck4c9v7es73c6t2mg)<br/>Deploy: dep-dbsrpr15efls73f3dqi0 (LIVE)"]
        DEP_VERCEL["Vercel Project (marspath-frontend-dist)<br/>Deploy: dpl_AzyMqzpY7BhPEVcooiDipiF7oJtp (READY)"]
    end

    A --> PR1
    PR1 --> PR10
    PR10 --> RC
    RC --> PROD
    PROD --> DEP_RENDER
    PROD --> DEP_VERCEL
```

* **PR #1 (Backend & Geospatial):** Merged into `main` at `4acf96a87d0a94fae3cdd633a56e4501437c9bda`.
* **PR #10 (Kunal's Frontend Map Rendering):** Merged into `main` at `c4cf286dc728320e8b9f19a37286744043224422`.
* **PR #11 (Final Production Release):** Merged into `main` at `6c5b26b38031cbf76e2ed26f4e2817ad4916554c`.
* **GitHub Actions CI Results:**
  - Run `43718278499` on `main`: **SUCCESS** (Python 3.11, Python 3.12, Docker build)
  - Run `43722562906` on PR #11: **SUCCESS** (Python 3.11, Python 3.12, Docker build)

---

## 3. Production API Endpoint Verification (Render)

Direct test results executed against live production backend (`https://marspath-backend.onrender.com`):

```json
{
  "health": {
    "status": "healthy",
    "environment": "production",
    "planetary_target": "Mars",
    "pilot_region": "Jezero Crater",
    "dem_loaded": true,
    "real_dem_requested": true,
    "real_dem_loaded": true,
    "is_synthetic": false,
    "local_integrity_verified": true,
    "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
    "official_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
    "dem_resolution_meters": 200.0,
    "grid_shape": [178, 252],
    "crs": "IAU2000:49900"
  },
  "openapi": {
    "endpoints_registered": 79,
    "status": "HTTP 200 OK"
  },
  "data_status": {
    "status": "healthy",
    "data_mode": "real_official_endpoint_unverified_checksum",
    "grid_shape": [178, 252]
  },
  "layers": {
    "count": 7,
    "status": "HTTP 200 OK"
  },
  "route_planning": {
    "status": "success",
    "routes_generated": 3,
    "primary_distance_meters": 2976.1,
    "effort_model": "slope_penalty",
    "algorithm": "astar"
  },
  "pdf_export": {
    "status": "HTTP 200 OK",
    "content_type": "application/pdf"
  },
  "nasa_connectors": {
    "active_sources": 7,
    "status": "HTTP 200 OK"
  }
}
```

* **Vercel Transparent Proxy:** Tested via `https://marspath.vercel.app/health` and `https://marspath.vercel.app/api/v1/data/status`; verified to route transparently to Render with HTTP 200 OK.

---

## 4. Live Production Browser Verification (Vercel)

Automated headless Chrome protocol verification executed against `https://marspath.vercel.app/mission-control/?view=planner`. All tests passed, generating six verified high-resolution screenshots in `docs/screenshots/prod_verification/`:

| Verification Step | Tested Feature | Observed Behavior | Evidence Screenshot |
| :--- | :--- | :--- | :--- |
| **P-01** | **Planetary Map & Imagery** | Viking 232m basemap rendered seamlessly with warm tone harmonization. CTX 6m and HiRISE 25cm layers loaded without rectangular grey overlay boxes ($a=0$). | `prod_01_planetary_map_loaded.png` |
| **P-02** | **Route Generation & Primary Map HUD** | Clicked *Western Delta* preset; sent request to Render backend. 3 multi-objective corridors generated and displayed on the Primary Map HUD (`.map-hud-route-selector`) with distance, cost, and risk badges. | `prod_02_route_candidates_hud.png` |
| **P-03** | **Interactive Alternative Switching** | Clicked candidate 2 (*Safe Ridge Bypass*). Active corridor switched instantly on OpenLayers canvas, updating waypoints and profile graphs. | `prod_03_alternative_candidate_selected.png` |
| **P-04** | **Cost Breakdown & Energy Index** | Left Drawer Cost Breakdown open by default (`detailsOpen=true`). Displayed formal cost formula and 5 color-coded penalty bars. Energy Index displayed in `eq-m` with MMRTG rover power notice. | `prod_04_cost_breakdown_and_resources.png` |
| **P-05** | **Mission Resources & Deep Intelligence** | Mission Resources card displayed 5.71 h outbound, 45.4 min return, and positive EVA margin. Clicked *Robustness* quick-navigation pill; expanded Right Drawer directly into 50-scenario Monte Carlo assessment. | `prod_05_robustness_and_deep_intel.png` |
| **P-06** | **2D Return-Time Reachability Isochrone** | Toggled Return Zone Isochrone overlay. OpenLayers canvas rendered backward-Dijkstra reachable matrix with floating color ramp legend (<60m green, 60-120m yellow, 120-180m orange, >180m red). | `prod_06_return_zone_isochrone.png` |

---

## 5. Closure of All 42 Diagnostic Requirements

Every single feature evaluated in the 42-requirement diagnostic is now **`IMPLEMENTED AND VERIFIED`**:

1. **F-01 to F-12 (Core Geodesy & Routing Engine):** FastAPI v1 routing, IAU2000 Mars sphere, MOLA/HRSC 200m DEM range ingestion, 1m HiRISE DTM support, traversability ceilings, TRI roughness, A* admissible search, Dijkstra cost equivalence, multi-alternative corridor generation, science detours, Mars24 solar clock, and turnaround calculation.
2. **F-13 to F-15, F-32 to F-34 (P1 Discoverability Remediation):** Primary Map HUD candidate selector, visible Cost Breakdown by default with 5 penalty share bars, Energy Index (`eq-m`) with MMRTG rover notice, Mission Resources temporal budget card, 5-pill Mission Intelligence quick navigation, and 2D Return Zone Isochrone map legend and toggle.
3. **F-16 to F-24 (Advanced Intelligence & NASA Data Sources):** 50-scenario Monte Carlo robustness, non-dominated Pareto frontier, next-best reconnaissance targeting, 7-scenario failure stress suite, seven official NASA data connectors, NAIF/SPICE ephemeris, THEMIS thermal traversability, GCS cloud storage abstraction, and dual Gemini/Azure AI copilot.
4. **F-25 to F-30 (Map Rendering & Multi-Resolution Imagery):** Transparent NoData alpha masking ($a=0$), canvas-level edge feathering (`destination-out`), CSS tone harmonization, Viking $\to$ CTX $\to$ HiRISE resolution hierarchy, coverage footprint toggles, and WMTS streaming.
5. **F-31, F-35 to F-42 (Platform Operations & Verification):** Vector PDF mission dossier export, real-time MEDA atmospheric conditions, Curiosity/Perseverance odometry replay (559 legs), Evidence Passports, algorithm benchmarks, multi-stage Docker build-time DEM provisioning, fail-closed runtime validation, and end-to-end integration workflows.

---

## 6. Known Limitations & Operational Guidance

1. **HiRISE 1m DTM Memory Envelope:**
   * On the Render Free tier (512 MB RAM limit), HiRISE 1 m A* search with 50-scenario robustness can peak near ~1.2 GB RSS. Consequently, `MARSPATH_USE_HIRISE_DEM="false"` is set by default on Render Free, utilizing the regional MOLA-HRSC 200m DEM (RSS ~105 MB).
   * For production deployments on dedicated tiers ($\ge$ 2 GB RAM), both `MARSPATH_PROVISION_HIRISE=true` and `MARSPATH_USE_HIRISE_DEM=true` can be enabled.
2. **Render Spin-Down on Inactivity:**
   * As with all Render free-tier instances, the container spins down after 15 minutes of inactivity. Initial requests after idle sleep may take ~30–50 seconds for cold-start initialization.

---

## 7. Final Acceptance & Release Status

### Final Status: **`RELEASED — BOTH SERVICES DEPLOYED AND PRODUCTION VERIFIED.`**

* **Backend Render Service:** Live and healthy on commit `6c5b26b38031cbf76e2ed26f4e2817ad4916554c`.
* **Frontend Vercel Project:** Live and serving production assets on domain `https://marspath.vercel.app`.
* **Zero Discrepancies:** All diagnostic gaps, rendering glitches, and presentation issues have been eliminated with verified visual evidence.
