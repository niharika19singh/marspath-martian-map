# MARSPath — Prioritized Remediation Roadmap & Implementation Guide

**Date:** November 15, 2026  
**Auditor:** Senior Software Architect, Planetary GIS Specialist & Security Auditor  
**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Audited Branch:** `fix/marspath-map-transparency-feathering`  
**Base Commit (`origin/main`):** `4aa1ab269a11ea3a0e37aba93166406d6394f98e` (PR #9 Merge)  
**Pull Request:** [PR #10](https://github.com/niharika19singh/marspath-martian-map/pull/10) (Open)

---

## 1. Executive Remediation Strategy

This roadmap details the concrete engineering tasks required to transition MARSPath from its current state into a fully hardened, reliable, production-ready planetary mission control system.

The work packages are strictly structured in descending order of operational criticality:
- **Phase 1: P0 Blockers (Crashes, Security, Broken Contracts & Release Parity)**
- **Phase 2: P1 Major Functional Gaps & Performance Optimization**
- **Phase 3: P2 Architectural Hygiene & Technical Debt Liquidation**
- **Phase 4: P3 Verification, E2E Test Hardening & Deployment Certification**

---

## 2. Phase 1 — P0 Critical Blocker Work Packages

### Work Package WP-01: Fix Unhandled 500 Crash in AI Imagery Analysis
- **Severity:** P0 (Crash / Blocker)
- **Affected Component:** Backend AI Orchestration
- **Affected Files:**
  - `backend/app/integrations/ai/orchestration/context_builder.py`
  - `backend/app/integrations/ai/services/mars_science_assistant.py`
- **Root Cause:**
  `context_builder.py` accesses attributes (`product.target_name`, `product.spatial_resolution_m_per_px`, `product.acquisition_utc`, `product.doi`, `product.processing_status`) that do not exist on `DataProduct` (`backend/app/data_sources/schemas/models.py`).
- **Required Changes:**
  Update `build_observation_context` to safely extract properties from `DataProduct`:
  ```python
  return {
      "product_id": product.product_id,
      "instrument": product.instrument,
      "spacecraft": product.spacecraft,
      "title": product.title,
      "target_name": getattr(product, "mission", "Mars"),
      "spatial_resolution_m_per_px": product.spatial_resolution_m,
      "martian_sol": product.martian_sol,
      "acquisition_utc": product.acquisition_timestamp.isoformat() if product.acquisition_timestamp else None,
      "doi": product.citation.doi if product.citation else None,
      "archive_url": product.archive_url,
      "download_url": product.download_url,
      "processing_status": getattr(product, "processing_level", "CALIBRATED"),
  }
  ```
- **Dependencies:** None.
- **Acceptance Criteria:**
  - `curl -X POST http://127.0.0.1:8005/api/v1/ai/imagery/analyze -d '{"product_id": "TREK_HRSC_MOLA_BLEND_DEM"}'` returns HTTP 200 with valid `interpretation_summary`.
  - Add automated test `test_interpret_imagery_with_real_catalog_product` in `backend/tests/unit/test_ai_copilot.py`.
- **Estimated Effort:** 0.5 Engineering Days.

---

### Work Package WP-02: Reconcile Frontend NASA Data Contracts & Eliminate Static Overrides
- **Severity:** P0 (Functional Contract Failure)
- **Affected Component:** Frontend Data Ingestion Client
- **Affected File:** `mission-ui/src/nasa_data.js`
- **Root Cause:**
  Endpoint URLs are mismatched against backend routes, and lines 759–763 and 771–775 explicitly discard live backend responses to return static canned fallback constants.
- **Required Changes:**
  1. Fix `fetchMedaObservations`:
     Change `${apiUrl}/api/v1/environmental/meda` $\to$ `${apiUrl}/api/v1/data-sources/meda/observations`.
     Remove line returning `FALLBACK_MEDA_OBSERVATIONS` on 200; return `data` directly.
  2. Fix `fetchThemisObservations`:
     Change `${apiUrl}/api/v1/thermal/themis` $\to$ `${apiUrl}/api/v1/data-sources/themis/observations`.
     Remove line returning `FALLBACK_THEMIS_OBSERVATIONS` on 200; return `data` directly.
  3. Fix `computeSpiceGeometry`:
     Change `${apiUrl}/api/v1/ephemeris/geometry` $\to$ `${apiUrl}/api/v1/data-sources/naif/geometry`.
  4. Fix `fetchCatalogueProduct`:
     Change `${apiUrl}/api/v1/data-catalogue/products/${productId}` $\to$ `${apiUrl}/api/v1/data-catalogue/${productId}`.
- **Dependencies:** None.
- **Acceptance Criteria:**
  - Mission Intelligence and conditions panel display live calibrated MEDA air temperature, pressure, and THEMIS thermal inertia fetched from backend.
  - Browser network tab verifies HTTP 200 across all NASA data source requests.
- **Estimated Effort:** 0.5 Engineering Days.

---

### Work Package WP-03: Implement Token Authentication on Cloud Storage Download
- **Severity:** P0 (Security Vulnerability)
- **Affected Component:** Backend Cloud Storage Router
- **Affected File:** `backend/app/integrations/routers/cloud_router.py`
- **Root Cause:**
  `download_storage_object` accepts `token: str = Query(...)` as a mandatory parameter but never verifies it against any secret or session hash.
- **Required Changes:**
  1. Add token verification logic in `backend/app/core/config.py` using HMAC or an environment secret (`MARSPATH_STORAGE_SECRET`):
     ```python
     def verify_storage_token(object_key: str, token: str) -> bool:
         expected = hmac.new(settings.SECRET_KEY.encode(), object_key.encode(), hashlib.sha256).hexdigest()
         return hmac.compare_digest(expected, token)
     ```
  2. Enforce check in `download_storage_object`:
     ```python
     if not verify_storage_token(object, token):
         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired storage access token.")
     ```
- **Dependencies:** None.
- **Acceptance Criteria:**
  - Arbitrary tokens (`?token=1`) return HTTP 401 Unauthorized.
  - Valid HMAC-signed download links stream the requested artifact.
- **Estimated Effort:** 0.5 Engineering Days.

---

### Work Package WP-04: Merge PR #10 & Deploy Unified Map Fixes to Production
- **Severity:** P0 (Production Parity)
- **Affected Component:** Deployment Infrastructure (Vercel & Render)
- **Affected Repository:** `niharika19singh/marspath-martian-map`
- **Actions Required:**
  1. Obtain human code review approval from `@Kunal-Dafuq` on [PR #10](https://github.com/niharika19singh/marspath-martian-map/pull/10).
  2. Complete controlled squash-merge into `main`.
  3. Verify automatic Vercel production build completes on `main`.
  4. Perform smoke test on `https://marspath.vercel.app/mission-control/` to verify:
     - No rectangular NoData boundary.
     - Smooth canvas feathering between CTX and Viking basemap.
     - Sepia tone harmonization active.
- **Dependencies:** PR #10 approval.
- **Acceptance Criteria:** Production URL renders seamless multi-resolution imagery without visual artifacts.
- **Estimated Effort:** 0.25 Engineering Days.

---

## 3. Phase 2 — P1 Major Functional Gaps & Performance Optimization

### Work Package WP-05: High-Resolution HiRISE Routing Memory Optimization for Free Tier
- **Severity:** P1 (Production Capability Gap)
- **Affected Component:** Geospatial & Graph Engine
- **Affected Files:**
  - `backend/app/geospatial/raster_loader.py`
  - `backend/app/routing/graph_builder.py`
  - `render.yaml`
- **Problem Statement:**
  Loading 1m HiRISE DTM into memory for the entire Jezero Delta requires ~1.2 GB RAM, exceeding Render free-tier (512 MB).
- **Required Changes:**
  1. Implement spatial corridor windowing: Read only the bounding box covering `start` to `destination` (with 500m margin) using `rasterio.windows.from_bounds()`, rather than allocating the entire raster array.
  2. Downsample corridor dynamically if corridor area exceeds memory budget.
  3. Re-enable `MARSPATH_USE_HIRISE_DEM="true"` in `render.yaml`.
- **Dependencies:** WP-04.
- **Acceptance Criteria:**
  - HiRISE 1m route execution runs within <250 MB RSS.
  - Render production backend successfully serves 1m route requests without OOM restarts.
- **Estimated Effort:** 1.5 Engineering Days.

---

### Work Package WP-06: Asynchronous Non-Blocking NASA Data Synchronization
- **Severity:** P1 (Performance / Latency)
- **Affected Component:** Data Sources Sync Engine
- **Affected File:** `backend/app/data_sources/services/sync_service.py`
- **Problem Statement:**
  `synchronize_all` sequentially awaits 7 external NASA HTTP requests, taking 7.14s up to 35s when connections stall.
- **Required Changes:**
  Replace sequential loop with concurrent execution:
  ```python
  async def check_source(s):
      conn = connector_map.get(s.source_id)
      if conn:
          return s.source_id, await conn.check_connection()
      return s.source_id, (ConnectionState.CONNECTED, None)

  results = await asyncio.gather(*[check_source(s) for s in sources], return_exceptions=True)
  ```
- **Dependencies:** None.
- **Acceptance Criteria:**
  - Endpoint latency reduced from 7.14s to <1.5s.
  - Failures in single remote NASA endpoints do not block or delay other connectors.
- **Estimated Effort:** 0.5 Engineering Days.

---

### Work Package WP-07: Harmonize Default Development Proxy Port (8000 vs 8005)
- **Severity:** P1 (Developer Experience)
- **Affected Files:**
  - `mission-ui/vite.config.js`
  - `backend/app/core/config.py`
- **Required Changes:**
  Standardize on port 8000 across all components:
  - In `mission-ui/vite.config.js`, change default target to `'http://127.0.0.1:8000'`.
  - Update `mission-ui/package.json` dev script if necessary.
- **Dependencies:** None.
- **Acceptance Criteria:** Running `npm run dev` in `mission-ui` connects out-of-the-box with default backend on port 8000.
- **Estimated Effort:** 0.25 Engineering Days.

---

### Work Package WP-08: Transparent Offline Indication for AI Assistant
- **Severity:** P1 (Scientific Integrity / Truth in Advertising)
- **Affected Files:**
  - `backend/app/integrations/ai/providers/gemini.py`
  - `backend/app/integrations/ai/services/mars_science_assistant.py`
- **Required Changes:**
  When `GEMINI_API_KEY` is not present:
  - Set `provider_used: "Offline Heuristic Simulator (API Key Not Configured)"`.
  - Add explicit boolean field `is_simulated: true` in response models.
  - Ensure UI displays an "Offline Simulation" badge next to answers.
- **Dependencies:** None.
- **Acceptance Criteria:** Operator clearly sees when answers are generated by live LLMs vs offline fallback heuristics.
- **Estimated Effort:** 0.5 Engineering Days.

---

## 4. Phase 3 — P2 Architectural Hygiene & Technical Debt

### Work Package WP-09: Deprecate Redundant Top-Level `frontend/` Directory
- **Severity:** P2 (Code Cleanliness)
- **Affected Directory:** `/Users/user/Documents/TeleSol-mac-release/marspath-unified-wt/frontend/`
- **Actions Required:**
  1. Remove empty stub `frontend/` directory.
  2. Update `docs/TEAM_OWNERSHIP.md` to reference `mission-ui/` as the sole canonical frontend codebase.
- **Estimated Effort:** 0.25 Engineering Days.

---

### Work Package WP-10: Clean Unused Defective Code in `context_builder.py`
- **Severity:** P2 (Dead Code)
- **Affected File:** `backend/app/integrations/ai/orchestration/context_builder.py`
- **Actions Required:**
  Refactor `build_themis_context()` to use correct `ThemisObservation` fields (`t.product_id`, `t.thermal_inertia_tiu`, `t.brightness_temp_k`) or delete if superseded.
- **Estimated Effort:** 0.25 Engineering Days.

---

## 5. Phase 4 — P3 Test Hardening & Production Release Certification

### Work Package WP-11: Expand Automated E2E Regression Playwright Suite
- **Severity:** P3 (Quality Assurance)
- **Affected Files:** `scripts/capture_e2e_screenshots.mjs`, `backend/tests/`
- **Actions Required:**
  1. Create headless Playwright test suite validating all 4 tabs:
     - Route Planner tab (Route calculation, elevation chart, 3D view toggle).
     - Mission Intel tab (MEDA weather display, THEMIS thermal risk, PDS releases).
     - AI Copilot tab (Chat inquiry, citation validation).
     - Map layers (Multi-resolution feathering at zoom levels 2, 7, 12).
  2. Integrate into GitHub Actions CI workflow.
- **Estimated Effort:** 1.0 Engineering Days.

---

## 6. Implementation Schedule & Milestone Roadmap

```
+---------------------------------------------------------------------------------------+
| SPRINT 1 (Days 1–2): Phase 1 P0 Blocker Resolution & Parity                           |
| - WP-01: Fix AI imagery analyze 500 crash in context_builder.py                       |
| - WP-02: Fix nasa_data.js contract URLs and remove static fallback overrides           |
| - WP-03: Implement HMAC/secret token check on storage download                         |
| - WP-04: Approve & merge PR #10; verify Vercel live map feathering                    |
+---------------------------------------------------------------------------------------+
| SPRINT 2 (Days 3–4): Phase 2 P1 Performance & Capability Optimization                 |
| - WP-05: Spatial corridor raster cropping for 1m HiRISE RAM optimization              |
| - WP-06: Asyncio.gather concurrent NASA sources synchronization                        |
| - WP-07: Vite proxy port harmonization to 8000                                        |
| - WP-08: Transparent AI simulation flags in responses and UI                         |
+---------------------------------------------------------------------------------------+
| SPRINT 3 (Day 5): Phase 3 & 4 Hardening & Release Handover                            |
| - WP-09: Cleanup redundant frontend/ directory & update documentation                 |
| - WP-10: Refactor defective ThemisObservation code in context_builder.py               |
| - WP-11: Final end-to-end Playwright certification suite & release sign-off           |
+---------------------------------------------------------------------------------------+
```
