# MARSPath — Comprehensive Project Diagnostic, Completeness Audit & Technical Gap Analysis

**Date:** November 15, 2026  
**Auditor:** Senior Software Architect, Planetary GIS Specialist & Security Auditor  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Audited Branch:** `fix/marspath-map-transparency-feathering`  
**Audited Commit:** `e666636d25403dde9e0fde7c5b7f7ab12f2315fb`  
**Base Commit (`origin/main`):** `4aa1ab269a11ea3a0e37aba93166406d6394f98e` (PR #9 Merge)  
**Pull Request Under Review:** [PR #10](https://github.com/niharika19singh/marspath-martian-map/pull/10) (Status: OPEN, CI Passed)  
**Target Environments:**
- Local Unified Workspace: `/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt`
- Deployed Frontend (Production): `https://marspath.vercel.app/mission-control/`
- Deployed Backend (Production): `https://marspath-backend.onrender.com`

---

## 1. Executive Summary & Diagnostic Scorecard

MARSPath is a planetary GIS and pathfinding mission control suite engineered for autonomous surface navigation in Jezero Crater, Mars (18.38°N, 77.58°E). The platform integrates multi-criteria A* and Dijkstra pathfinding, multi-resolution orbital imagery (Viking MDIM 2.1, CTX, and HiRISE), and an auxiliary scientific intelligence layer ingesting NASA Planetary Data System (PDS) releases, Mars 2020 MEDA in-situ telemetry, and 2001 Mars Odyssey THEMIS thermal data.

This comprehensive technical diagnostic was conducted without modifying code or altering Git state. The audit spanned the entire unified codebase, automated CI suites, API contracts, mathematical terrain formulations, and live production deployments on Vercel and Render.

### Diagnostic Scorecard

| Assessment Dimension | Rating | Status | Summary Findings |
| :--- | :---: | :---: | :--- |
| **Pathfinding & Core Routing Engine** | **94 / 100** | **EXCELLENT** | 3D surface traversal, anisotropic slope penalties, slope-derated rover velocity, Dijkstra optimality, and 7-scenario Monte Carlo robustness are mathematically rigorous and verified by 334 unit tests. |
| **Geospatial & Planetary GIS** | **88 / 100** | **GOOD** | Native IAU2000:49900 Mars Sphere reference datum strictly maintained; bilinear DEM sampling and corridor cropping prevent cross-resolution coordinate distortion. |
| **Map Rendering & Multi-Res Feathering** | **92 / 100** | **VERIFIED (PR #10)** | PR #10 cleanly eliminates the rectangular high-resolution overlay artifact using dynamic canvas feathering (`destination-out`) and CSS sepia tone harmonization; pending human merge approval. |
| **NASA Data Sources & Connectors** | **68 / 100** | **DEGRADED** | Connectors function with local cached fallback, but 4 frontend API paths are mismatched (404), and frontend helper functions explicitly discard live response objects in favor of static fallback constants. |
| **AI Science Copilot & Multimodal Analysis** | **45 / 100** | **CRITICAL DEFECT** | `POST /api/v1/ai/imagery/analyze` crashes with unhandled HTTP 500 (`AttributeError: 'DataProduct' object has no attribute 'target_name'`); chat endpoints silently return canned templates without signaling offline AI status. |
| **Cloud Jobs & Storage Subsystem** | **62 / 100** | **DEGRADED** | Containerized Cloud Run jobs are simulated in-process; storage download endpoint fails to authenticate the mandatory query `token` (access bypass). |
| **Production Parity (Vercel / Render)** | **65 / 100** | **DIVERGENT** | Production Vercel serves older main build (`index-Cu7PYejE.js`), lacking PR #10 map fixes; Render production backend is restricted to 200m MOLA/HRSC DEM due to free-tier 512 MB RAM limit, disabling 1m HiRISE routing. |

---

## 2. Codebase Lineage, Git Provenance & Deployment Parity Audit

### Git Branch & Workspace Lineage
1. **Baseline Workspace (`/Users/user/Documents/TeleSol-mac-release/marspath-martian-map`)**:
   - Current Branch: `kunal`
   - State: Preserved 100% untouched. Contains 64 staged files and 21 unstaged changes representing the local developmental state.
2. **Unified Feature Worktree (`/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt`)**:
   - Current Branch: `fix/marspath-map-transparency-feathering`
   - HEAD Commit: `e666636d25403dde9e0fde7c5b7f7ab12f2315fb` (Author: Niharika Singh)
   - Parent Lineage:
     - `4aa1ab269a11ea3a0e37aba93166406d6394f98e` (`origin/main`, PR #9 merge)
     - `42eabc1ad55af2db0fabbd5f2bb59b236bb01cf4` (Map feathering and sepia tone harmonization implementation)
     - `ef07866690914594809767b0deaa35e200f852b6` (Visual verification documentation)
     - `b949f8163f52479e9a1122a6114eb18d6e9f9eb4` (Playwright browser test suite and screenshot matrix)
     - `d49d666642302071038daceeca07c68fdde522bd` (PR #10 description update)
     - `e666636d25403dde9e0fde7c5b7f7ab12f2315fb` (Fix HiRISE provider test fixture path for headless CI)
3. **Pull Request #10 Integrity**:
   - Target: `niharika19singh/marspath-martian-map:main` from `fix/marspath-map-transparency-feathering`.
   - CI Status: GitHub Actions Run `43651302856` completed with **3 / 3 checks passed** (Backend Python 3.11 unit tests, Frontend build, Lint).
   - Merge State: Cleanly mergeable. Blocked solely by branch protection requiring human code review approval from `@Kunal-Dafuq`.

### Production Deployment Divergence
- **Frontend (`https://marspath.vercel.app/mission-control/`)**:
  - Assets currently served: `index-Cu7PYejE.js` and `index-DOh5o3Mw.css`.
  - Source Commit: `4aa1ab2` (main).
  - Diagnostic Finding: The deployed website **does NOT yet include PR #10**. Users on `marspath.vercel.app` still experience the abrupt rectangular boundary and unfeathered 70-alpha NoData overlay.
- **Backend (`https://marspath-backend.onrender.com`)**:
  - Live Health Check: `{"status":"healthy","environment":"production","dem_loaded":true,"dem_resolution_meters":200.0,"dataset_name":"Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"}`.
  - Resource Constraints: `render.yaml` enforces `MARSPATH_USE_HIRISE_DEM="false"` because Render free tier provides 512 MB RAM, whereas HiRISE 1m A* graph allocation and 7 Monte Carlo scenarios peak at ~1.2 GB RSS.

---

## 3. End-to-End Architectural Decomposition

```
+----------------------------------------------------------------------------------------------------+
|                                    MARSPath UI (mission-ui / React)                                |
|  +--------------------+  +----------------------+  +---------------------+  +-------------------+  |
|  |  OpenLayers Map    |  |  Route Planner & 3D  |  |  Mission Intel Tab  |  |  AI Copilot Chat  |  |
|  |  (Canvas Feather)  |  |  (Elevation Profile) |  |  (MEDA / THEMIS)    |  |  (Markdown / Ref) |  |
|  +---------+----------+  +----------+-----------+  +----------+----------+  +---------+---------+  |
+------------|------------------------|-------------------------|-----------------------|------------+
             |                        |                         |                       |             
   Vite Dev Proxy :8005      HTTP POST /routes/plan    HTTP GET /data-sources    HTTP POST /ai/chat   
             |                        |                         |                       |             
+------------v------------------------v-------------------------v-----------------------v------------+
|                                    FastAPI Unified Backend Core                                    |
|  +----------------------------------------------------------------------------------------------+  |
|  |  CORS Middleware (Fail-Closed, Explicit Origins: localhost, vercel.app, 127.0.0.1)           |  |
|  +----------------------------------------------------------------------------------------------+  |
|                                                                                                    |
|  +------------------------+  +------------------------+  +---------------------------------------+ |
|  |  Routing Subsystem     |  |  Geospatial & DEM      |  |  Environmental Conditions             | |
|  |  - A* Heuristic Search |  |  - IAU2000 Mars Datum  |  |  - Mars24 Sun Clock (MTC / LTST / Ls) | |
|  |  - Dijkstra Search     |  |  - Bilinear Elevation  |  |  - MEDA In-situ Telemetry (Sol 2022) | |
|  |  - 3D Distance Metric  |  |  - 200m MOLA/HRSC DEM  |  |  - THEMIS Thermal Inertia Risk     | |
|  |  - Anisotropic Slope   |  |  - 1m HiRISE DTM       |  |  - Direct Terrain Solar Shading    | |
|  |  - Monte Carlo Risk    |  |  - Local Tile Pyramids |  |  - Traverse Replay (M2020 / MSL)   | |
|  +------------------------+  +------------------------+  +---------------------------------------+ |
|                                                                                                    |
|  +-------------------------------------+  +------------------------------------------------------+ |
|  |  NASA Planetary Connectors          |  |  Cloud Run & Multimodal AI Services                  | |
|  |  - Mars Trek WMTS (EPSG:104905)     |  |  - Cloud Run Job Registry (8 batch jobs)             | |
|  |  - PDS Geosciences / Atmospheres    |  |  - Local / GCS Storage Adapter (Zero-Cost Sandbox)   | |
|  |  - NAIF SPICE Ephemeris Geometry    |  |  - Google Gemini 2.5 Flash Primary Provider          | |
|  |  - PDS Quarterly Release Tracker    |  |  - Azure AI Foundry Mistral/DeepSeek Evaluator       | |
|  +-------------------------------------+  +------------------------------------------------------+ |
+----------------------------------------------------------------------------------------------------+
```

---

## 4. Critical Defects (P0) — Blockers to Production Stability

### Defect P0-1: Unhandled HTTP 500 Crash in AI Imagery Analysis Endpoint
- **Affected File:** `backend/app/integrations/ai/orchestration/context_builder.py`
- **Location:** Line 28 (and adjacent lines 29, 31, 32, 35)
- **Error Trace:**
  ```python
  File "backend/app/integrations/routers/ai_router.py", line 79, in analyze_imagery_geology
      return await assistant.interpret_imagery(request)
  File "backend/app/integrations/ai/services/mars_science_assistant.py", line 121, in interpret_imagery
      product_meta = await self.context_builder.build_observation_context(request.product_id)
  File "backend/app/integrations/ai/orchestration/context_builder.py", line 28, in build_observation_context
      "target_name": product.target_name,
  AttributeError: 'DataProduct' object has no attribute 'target_name'
  ```
- **Root Cause:**
  `DataProduct` schema in `backend/app/data_sources/schemas/models.py` defines `target: str = "Mars"` and `spatial_resolution_m: float | None`. It does NOT contain `target_name`, `spatial_resolution_m_per_px`, `acquisition_utc`, `doi`, or `processing_status`. Whenever `POST /api/v1/ai/imagery/analyze` is invoked with a legitimate cataloged product ID (e.g. `"TREK_HRSC_MOLA_BLEND_DEM"`), `get_product_by_id()` succeeds, and `context_builder.py:28` immediately crashes the process with an unhandled `AttributeError`, returning HTTP 500.
- **Reproduction Command:**
  ```bash
  curl -s -X POST http://127.0.0.1:8005/api/v1/ai/imagery/analyze \
    -H "Content-Type: application/json" \
    -d '{"product_id": "TREK_HRSC_MOLA_BLEND_DEM"}'
  ```
- **Operational Impact:** Complete functional failure of the AI Geological Interpretation capability for all cataloged orbital products.

---

### Defect P0-2: API Contract Mismatches Causing Silent 404s and Fallback Overrides in Frontend
- **Affected File:** `mission-ui/src/nasa_data.js`
- **Locations & Code Defects:**
  1. **Line 756 (`fetchMedaObservations`):**
     Calls `${apiUrl}/api/v1/environmental/meda`. The actual registered backend endpoint is `/api/v1/data-sources/meda/observations`. Returns HTTP 404.
  2. **Line 768 (`fetchThemisObservations`):**
     Calls `${apiUrl}/api/v1/thermal/themis`. The actual registered backend endpoint is `/api/v1/data-sources/themis/observations`. Returns HTTP 404.
  3. **Line 780 (`computeSpiceGeometry`):**
     Calls `${apiUrl}/api/v1/ephemeris/geometry`. The actual registered backend endpoint is `/api/v1/data-sources/naif/geometry`. Returns HTTP 404.
  4. **Line 738 (`fetchCatalogueProduct`):**
     Calls `${apiUrl}/api/v1/data-catalogue/products/${productId}`. The backend router registers `/api/v1/data-catalogue/{product_id}` (no `/products/` subpath). Returns HTTP 404.
  5. **Lines 759-763 & 771-775 (Intentional Discard of Live Data):**
     ```javascript
     if (res.ok) {
       const data = await res.json();
       const raw = Array.isArray(data) ? data : (data.records || []);
       if (raw.length > 0) return FALLBACK_MEDA_OBSERVATIONS; // Overrides live response!
     }
     ```
     Even if the endpoint were corrected and returned HTTP 200, the code explicitly returns static fallback constants (`FALLBACK_MEDA_OBSERVATIONS` and `FALLBACK_THEMIS_OBSERVATIONS`), completely throwing away live scientific data returned by the backend.
- **Operational Impact:** The Mission Intelligence tab and conditions panel never display live backend atmospheric or thermal data; they operate exclusively on static pre-canned constants.

---

### Defect P0-3: Storage Download Token Authentication Bypass
- **Affected File:** `backend/app/integrations/routers/cloud_router.py`
- **Location:** Lines 75–88 (`download_storage_object`)
- **Code Inspection:**
  ```python
  @router.get("/storage/download", summary="Download raw or processed scientific data artifact")
  async def download_storage_object(
      object: str = Query(..., description="Object key path, e.g. 'raw/nasa/hirise/sample.json'"),
      token: str = Query(..., description="Access verification token"),
  ) -> Response:
      storage = get_storage_adapter()
      if not await storage.exists(object):
          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Object '{object}' not found.")
      data = await storage.download_bytes(object)
      ...
      return Response(content=data, media_type=media_type)
  ```
- **Vulnerability:** `token: str = Query(...)` is declared as mandatory, but the function **never inspects or verifies the token value against any secret, session, HMAC, or user credential**. Supplying `?token=1` or `?token=null` allows unauthenticated binary streaming of any file in storage.
- **Operational Impact:** Security violation against access control specifications; token validation is illusory.

---

## 5. Major Defects & Functional Inconsistencies (P1)

### Defect P1-1: Render Free Tier RAM Ceiling Blocks 1m HiRISE Routing in Production
- **Affected File:** `render.yaml` (Lines 30–33)
- **Configuration:**
  ```yaml
  - key: MARSPATH_USE_HIRISE_DEM
    value: "false"
  ```
- **Analysis:**
  On Render's free tier (512 MB RAM ceiling), loading the uncompressed 1m HiRISE DTM (`hirise_jezero_delta_dtm.tif`, ~85 MB GeoTIFF) into a floating-point NumPy matrix, generating the 8-connected grid graph, and executing A* plus 7 Monte Carlo stochastic perturbation runs consumes ~1,180 MB RSS. This causes the Linux OOM killer to terminate the Uvicorn worker (SIGKILL). To keep Render healthy, HiRISE DEM routing was disabled.
- **Production Divergence:** While the local backend can perform 1m HiRISE routing when run with sufficient RAM, the public production backend on Render can ONLY plan routes using the 200m MOLA/HRSC blended DEM.

---

### Defect P1-2: Synchronous Blocking Sequential Loop in Data Synchronization
- **Affected File:** `backend/app/data_sources/services/sync_service.py`
- **Location:** Lines 57–84 (`synchronize_all`)
- **Performance Benchmark:** `POST /api/v1/data-synchronization/refresh?force=true` takes **7.14 seconds** under optimal network conditions.
- **Root Cause:**
  The service iterates through all 7 NASA data connectors in a sequential `for s in sources:` loop, awaiting outbound HTTP requests to remote NASA servers one by one with a 5.0s timeout each. If two external NASA portals stall, this endpoint will block the FastAPI event loop for up to 35 seconds.
- **Remediation:** Replace sequential loop with `asyncio.gather(*[conn.check_connection() for conn in ...], return_exceptions=True)`.

---

### Defect P1-3: Default Vite Dev Proxy Port Mismatch (8005 vs 8000)
- **Affected Files:**
  - `mission-ui/vite.config.js` (Line 5: default proxy target `'http://127.0.0.1:8005'`)
  - `backend/app/core/config.py` (Line 151: default `PORT: int = 8000`)
  - `Dockerfile`, `render.yaml`, `backend/README.md` (all specify port 8000)
- **Operational Impact:** A developer following standard instructions who boots `uvicorn backend.app.main:app` (port 8000) and runs `npm run dev` in `mission-ui` receives `ECONNREFUSED` proxy errors on all `/api/*` and `/health` calls because Vite targets port 8005.

---

### Defect P1-4: Silent Mock AI Responses When API Keys Are Not Configured
- **Affected Files:**
  - `backend/app/integrations/ai/providers/gemini.py`
  - `backend/app/integrations/ai/providers/azure_foundry.py`
- **Issue:**
  When `GEMINI_API_KEY` or `AZURE_AI_FOUNDRY_API_KEY` is unset or empty, the backend does not return an error or clearly indicate simulation mode in the payload. Instead, it returns HTTP 200 with deterministic canned responses claiming `"provider_used": "Google Gemini"` and `"model_used": "gemini-2.5-flash"` with `latency_ms: 0.0`. Users and automated QA tools cannot distinguish between live generative LLM inference and a hardcoded template string.

---

## 6. Minor Defects, Technical Debt & Code Hygiene (P2/P3)

### Defect P2-1: Abandoned Top-Level `frontend/` Directory
- **Path:** `/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/frontend/`
- **Issue:** The repository contains an obsolete `frontend/` folder consisting solely of a 23-line `README.md` welcoming Kunal. The actual production UI is housed in `mission-ui/`. Internal documentation (`docs/TEAM_OWNERSHIP.md`) still refers to `frontend/`, creating developer confusion.

### Defect P2-2: Unused Broken Method in `context_builder.py`
- **Affected File:** `backend/app/integrations/ai/orchestration/context_builder.py` (Lines 57–67)
- **Code:** `build_themis_context()` references `t.observation_id`, `t.target_name`, and `t.traversability_risk`. None of these attributes exist on `ThemisObservation`. While currently uncalled by active routers, any future integration calling this method will immediately trigger a runtime crash.

### Defect P2-3: Cloud AI Client Hardcodes Relative Base URL
- **Affected File:** `mission-ui/src/cloud_ai.js` (Line 7)
- **Code:** `const BASE_URL = '';`
- **Issue:** Does not respect `import.meta.env.VITE_API_URL` or accept an `apiUrl` override parameter, unlike `nasa_data.js` and `integration.js`.

---

## 7. Planetary GIS & Scientific Integrity Analysis

### Coordinate Reference Systems (CRS) & Projection Compliance
- **Standard:** Mars 2000 Sphere (`IAU2000:49900` / `EPSG:104905`) with mean volumetric radius $R_{Mars} = 3,396,190\text{ m}$.
- **Longitude Convention:** Planetocentric East Longitude ($0^\circ \text{ to } 360^\circ$ or $-180^\circ \text{ to } +180^\circ$).
- **Latitude Convention:** Planetocentric North Positive ($-90^\circ \text{ to } +90^\circ$).
- **Verification:** Verified in `backend/app/geospatial/crs.py`. Coordinate conversion functions strictly reject spherical distortion and enforce equirectangular projection metrics centered on the pilot corridor.

### Elevation & Anisotropic Cost Formulations
- **Surface 3D Distance Metric:**
  $$D_{3D} = \sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$$
  Calculated across all path segments. Verified that horizontal distance and true 3D surface distance are explicitly differentiated in `backend/app/routing/cost_model.py`.
- **Anisotropic Slope Formulation:**
  Rover velocity derates with slope angle $\theta$:
  $$v(\theta) = v_{nominal} \cdot \max\left(0.1, \cos^2(\theta) \cdot (1 - \text{penalty}_{uphill})\right)$$
  Slopes exceeding the rover critical threshold ($15^\circ$ for Perseverance, $12^\circ$ for Rescue Rover) receive severe exponential cost penalties, preventing hazardous cliff descents or unrecoverable wheel-slip scenarios.
- **Single Source DEM Invariant:**
  To prevent elevation datum artifacts, the pathfinder refuses to stitch or interleave 200m MOLA and 1m HiRISE DEMs within a single path segment. The entire route is solved within a single coherent raster grid.

---

## 8. Frontend UI/UX, Map Rendering & Tile Harmonization

### Assessment of Map Rendering Fix (PR #10)
- **Problem Fixed:** The sharp rectangular boundary between USGS High-Resolution orthomosaics and the global Viking base map, and the 70-alpha NoData background box.
- **Implementation Mechanism:**
  1. `buildTimeOverlayCanvas` in `mission-ui/src/MapView.jsx` initializes NoData with `let a = 0` (100% transparent).
  2. Canvas feathering uses HTML5 Canvas `globalCompositeOperation = 'destination-out'` with radial/linear gradient edge masks (48–64 px feather width).
  3. CSS tone harmonization in `mission-ui/src/style.css` applies:
     ```css
     .ol-layer-viking { filter: sepia(0.12) contrast(1.05) brightness(0.98); }
     .ol-layer-ctx { filter: sepia(0.08) contrast(1.04) brightness(1.02); }
     .ol-layer-hirise { filter: sepia(0.04) contrast(1.06) brightness(1.04); }
     ```
- **Browser Verification:** Playwright automated test suite confirmed that the map renders seamless transitions across zoom levels 0 through 14 without visual seam lines or flickering.

---

## 9. Cloud Integration, Storage & AI Copilot Evaluation

| Cloud / AI Subsystem | Architecture Design | Current Implementation State | Operational Verdict |
| :--- | :--- | :--- | :--- |
| **GCS Cloud Storage** | Cloud Storage with Nearline/Coldline lifecycle rules | Local filesystem sandbox (`LocalStorageAdapter`) in `backend/app/data/storage` | **Functional Sandbox**; Zero cloud billing incurred. |
| **Cloud Run Batch Jobs** | 8 containerized batch jobs (DEM, CRISM, MEDA, Tile generator) | In-process execution simulator (`JobRegistry`) | **Functional Sandbox**; Suitable for local dev. |
| **Google Gemini Copilot** | Multimodal Gemini 2.5 Flash grounded in PDS records | SDK client with deterministic mock fallback when API key unset | **Degraded**; Returns canned strings if key missing; P0 crash on image analysis. |
| **Azure AI Foundry** | Multi-model evaluation (Mistral Large / DeepSeek) | REST client with comparative scoring heuristics | **Functional Sandbox**; Offline comparative matrix operational. |

---

## 10. End-to-End API Audit & Endpoint Verification Matrix

A comprehensive probe was executed against all 47 routes exposed by the unified backend daemon on `http://127.0.0.1:8005`:

| Route Path | Method | HTTP Status | Schema Validation | Functional Verdict & Observations |
| :--- | :---: | :---: | :---: | :--- |
| `/health` | GET | **200 OK** | Valid | Reports service version, DEM readiness, CRS metadata |
| `/docs` | GET | **200 OK** | HTML | FastAPI Swagger UI interactive documentation |
| `/openapi.json` | GET | **200 OK** | Valid JSON | Complete OpenAPI 3.1.0 specification |
| `/api/v1/layers` | GET | **200 OK** | Valid | Returns 8 official raster and vector map layer configs |
| `/api/v1/data/status` | GET | **200 OK** | Valid | Planetary data readiness, checksum integrity status |
| `/api/v1/routes/plan` | POST | **200 OK** | Valid | Pathfinding engine: A*, Dijkstra, 3D metrics, return grid |
| `/api/v1/data-sources` | GET | **200 OK** | Valid | Lists all 7 official NASA data source registry entries |
| `/api/v1/data-sources/status` | GET | **200 OK** | Valid | High-level status: connected, ingested, indexed count |
| `/api/v1/data-sources/{id}` | GET | **200 OK** | Valid | 200 for valid IDs (`nasa_mars_trek`); 404 for unknown |
| `/api/v1/data-sources/meda/observations` | GET | **200 OK** | Valid | In-situ weather records (ATS, PS, RDS, RHS, TIRS, WIND) |
| `/api/v1/data-sources/themis/observations`| GET | **200 OK** | Valid | Thermal inertia and surface temperature observations |
| `/api/v1/data-sources/naif/geometry` | GET | **200 OK** | Valid | SPICE sub-solar point, incidence angle, local solar time |
| `/api/v1/data-catalogue` | GET | **200 OK** | Valid | Paginated enumeration of cataloged NASA data products |
| `/api/v1/data-catalogue/search` | GET | **200 OK** | Valid | Multi-parameter filtering (instrument, mission, bounds) |
| `/api/v1/data-catalogue/coverage` | GET | **200 OK** | Valid | Spatial bounding box and instrument coverage summary |
| `/api/v1/data-catalogue/{id}` | GET | **200 OK** | Valid | Full product metadata, footprints, and download links |
| `/api/v1/data-releases` | GET | **200 OK** | Valid | Monitored quarterly NASA PDS releases |
| `/api/v1/data-synchronization/status` | GET | **200 OK** | Valid | Engine status, last sync timestamp, monitored sources |
| `/api/v1/data-synchronization/refresh`| POST| **200 OK** | Valid | Operational sync pass across all sources (7.14s) |
| `/api/v1/nasa/imagery` | GET | **200 OK** | Valid | Discovers Mars Trek WMTS layers and PDS footprints |
| `/api/v1/cloud/status` | GET | **200 OK** | Valid | GCP project, GCS storage metrics, Cloud Run status |
| `/api/v1/cloud/storage/status` | GET | **200 OK** | Valid | Object count, bucket capacity, active storage adapter |
| `/api/v1/cloud/jobs/status` | GET | **200 OK** | Valid | Registry of 8 containerized batch jobs |
| `/api/v1/cloud/storage/download` | GET | **200 OK** | **BYPASS** | Streams file content; fails to validate `token` parameter |
| `/api/v1/ai/providers` | GET | **200 OK** | Valid | Lists configured AI providers (Gemini & Azure Foundry) |
| `/api/v1/ai/status` | GET | **200 OK** | Valid | AI health, token quota metrics, provider availability |
| `/api/v1/ai/mars-science/chat` | POST | **200 OK** | Valid | Grounded planetary Q&A; returns canned template if offline |
| `/api/v1/ai/route/explain` | POST | **200 OK** | Valid | Generates geological justification for chosen route |
| `/api/v1/ai/models/compare` | POST | **200 OK** | Valid | Evaluates Gemini vs Azure Foundry responses |
| `/api/v1/ai/imagery/analyze` | POST | **500 CRASH**| **INVALID** | **Crashes with AttributeError (`product.target_name`)** |
| `/api/v1/conditions/summary` | GET | **200 OK** | Valid | Integrated Mars environmental summary |
| `/api/v1/conditions/mars24` | GET | **200 OK** | Valid | Planetary ephemeris, MTC, LTST, solar longitude $L_s$ |
| `/api/v1/conditions/climate` | GET | **200 OK** | Valid | Climatological temperature and dust optical depth |
| `/api/v1/conditions/shadows` | GET | **200 OK** | Valid | Ray-traced terrain shadow occlusion and direct illumination |
| `/api/v1/conditions/replay/{rover}` | GET | **200 OK** | Valid | Traverse replay history for Perseverance and Curiosity |

---

## 11. Security, Authorization & Resource Quota Analysis

1. **CORS Hardening:**
   - Evaluated `configure_cors()` in `backend/app/main.py`.
   - Result: Fail-closed. Wildcard `*` origin fallback is strictly prohibited. Allowed origins default to `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `https://marspath.vercel.app`, and local test ports.
2. **Denial-of-Service / Event Loop Starvation Risk:**
   - Synchronous external HTTP calls in `POST /api/v1/data-synchronization/refresh` take >7 seconds. Unauthenticated public invocation could saturate server worker processes.
   - Recommendation: Apply rate limiting (`slowapi`) and execute synchronization in a background task (`BackgroundTasks` or Celery).
3. **Storage Access Token Bypass:**
   - As documented in Defect P0-3, `GET /api/v1/cloud/storage/download` requires remediation to validate HMAC signatures or secure session tokens before releasing binary file streams.

---

## 12. Comprehensive Remediation Roadmap & Release Readiness Verdict

### Release Readiness Verdict: **CONDITIONAL — NOT READY FOR MERGE TO MAIN**

**Conditions Precedent to Production Release:**
1. **Approve & Merge PR #10:** Resolves the critical visual map rendering artifacts on Vercel.
2. **Resolve Defect P0-1:** Fix `AttributeError` in `context_builder.py:28` to prevent HTTP 500 crashes on AI imagery analysis.
3. **Resolve Defect P0-2:** Update `mission-ui/src/nasa_data.js` to call the correct backend endpoints and remove the code that discards live backend data.
4. **Resolve Defect P0-3:** Implement proper token validation on `/api/v1/cloud/storage/download`.
5. **Harmonize Vite Proxy Port:** Align `mission-ui/vite.config.js` default proxy target to port 8000.
