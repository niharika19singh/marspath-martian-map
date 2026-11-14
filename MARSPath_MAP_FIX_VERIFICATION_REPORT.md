# MARSPath — Planetary GIS Map Rendering Fix & Visual Regression Report

**Repository:** `https://github.com/niharika19singh/marspath-martian-map`  
**Working Branch:** `fix/marspath-map-transparency-feathering`  
**Pushed Remote URL:** [https://github.com/niharika19singh/marspath-martian-map/tree/fix/marspath-map-transparency-feathering](https://github.com/niharika19singh/marspath-martian-map/tree/fix/marspath-map-transparency-feathering)  
**Commit SHA:** `42eabc1ad55af2db0fabbd5f2bb59b236bb01cf4`  
**Base Commit:** `4aa1ab269a11ea3a0e37aba93166406d6394f98e` (`origin/main`)  
**Status:** ✅ **ALL 10 TASKS IMPLEMENTED, TESTED, VERIFIED, AND PUSHED TO GITHUB**

---

## 1. Executive Summary

This report documents the resolution of the Mars map's rectangular grey overlay and abrupt resolution-boundary cutouts. The fixes have been implemented on a clean branch branched directly from `origin/main` (`4aa1ab2`), validated through 10 automated frontend test suites and 262 backend unit tests, visually verified across all 8 mandatory Playwright capture scenarios at 1440×900 viewport, and pushed to GitHub `origin`.

### Strict Operational Boundary Compliance
1. **No Merging into Main:** Main branch remains untouched at `4aa1ab2`.
2. **No Production Deployment:** Production Vercel and Render deployments were not touched.
3. **Workspace Isolation:** Baseline `/Users/user/Documents/TeleSol-mac-release/marspath-martian-map` (`kunal`) was strictly preserved and untouched.
4. **Independent Branch Push:** `fix/marspath-map-transparency-feathering` exists and is up to date on GitHub `origin`.

---

## 2. Root Cause Analysis

An audit of `mission-ui/src/MapView.jsx` in `main` identified four interconnected defects responsible for the visual anomalies:

1. **Slate-Grey NoData / Unreachable Cell Initialization:**
   In `buildTimeOverlayCanvas`:
   ```javascript
   let rgb = [105, 118, 128];
   let a = 70; // NoData / unreachable never shown as safe
   ```
   Every pixel in the return-time and rescue-time raster bounding box initialized with slate-grey RGB and alpha 70. Any unreached cell, out-of-budget area, or DEM null value was rendered as a semi-transparent slate-grey rectangle obscuring the underlying Viking basemap.
2. **Knife-Edge Rectangular Layer Boundaries:**
   USGS CTX (6 m/px) and HiRISE (0.25 m/px) orthomosaics were rendered directly onto OpenLayers' shared canvas with hard coordinate clipping (`ctx.clip()` at `ctxExtent` and `hiriseOrthoExtent`), creating harsh knife-edge borders against the global Viking color mosaic (`[76, 60, 44]`).
3. **Shared Canvas vs. Layer Erasing:**
   In OpenLayers 10, all TileLayers render to a single shared canvas by default. Attempting `globalCompositeOperation = 'destination-out'` without layer isolation erases all underlying basemap layers down to DOM transparency.
4. **DEM Footprint Polygon Style:**
   The `demPoly` footprint feature was rendering a bounding box fill by default even when the user had not toggled the Coverage layer.

---

## 3. Concrete Code Changes Implemented

### A. Modular Map Rendering Engine (`mission-ui/src/map_rendering.js`)
Created a standalone, testable module containing:
- **`computeTimeOverlayPixels(zone, kind)`**:
  - Initializes all pixels to `[0, 0, 0, 0]` (100% transparent).
  - Explicitly checks `val !== null && val !== undefined && Number.isFinite(val) && val >= 0`.
  - Assigns calibrated color and opacity (`a = 48..82` for return within budget, `a = 55` for return beyond budget, `a = 88..110` for rescue tiers).
  - Guarantees `a = 0` for all NoData, unreachable, nonfinite, or negative cells, letting the underlying Mars basemap shine through.
- **`calculateEdgeFeatherGradients(pixelBounds, featherPx = 54)`**:
  - Computes top, bottom, left, and right linear gradient geometries using dynamic screen-pixel clamping `fp = Math.min(featherPx, w/4, h/4)`.
  - Restores canvas composite state after execution.

### B. MapView Integration (`mission-ui/src/MapView.jsx`)
- **Layer Canvas Isolation:**
  Configured `className: 'ol-layer-ctx'` on `wmtsCtxRegional` and `className: 'ol-layer-hirise'` on `wmtsHiriseLocal`. This instructs OpenLayers to render these layers into dedicated `<div class="ol-layer-*"><canvas>` containers.
- **Dynamic Linear Alpha Edge Feathering (`applyEdgeFeathering`):**
  Attached `postrender` listeners to CTX (64 px feather) and HiRISE (48 px feather):
  ```javascript
  ctx.save();
  ctx.globalCompositeOperation = 'destination-out';
  // Top, Bottom, Left, Right linear alpha gradients (rgba(0,0,0,1) -> rgba(0,0,0,0))
  ctx.restore();
  ```
  Because the layers reside on isolated canvases, `destination-out` feathers only the edges of the high-resolution insets, revealing the underlying Viking basemap seamlessly.
- **Deterministic Resolution Hierarchy:**
  - Viking Global: Active across all zoom levels (`maxResolution` uncapped, down to `28000 / M_PER_DEG`).
  - CTX Regional: `maxResolution: 800 / M_PER_DEG` (activates when viewport resolution is $\le 800\text{ m/px}$).
  - HiRISE Local: `maxResolution: 25 / M_PER_DEG` (activates when viewport resolution is $\le 25\text{ m/px}$).
- **Coverage Boundary Gating:**
  `demPoly.setStyle` returns `null` unless `callbacks.current.props.coverage === true`, ensuring coverage boxes remain invisible by default.

### C. Tone Harmonization (`mission-ui/src/style.css`)
Added CSS tone harmonization filter targeting dedicated layer canvases:
```css
.ol-layer-ctx canvas,
.ol-layer-hirise canvas {
  transition: opacity 0.35s ease-in-out;
  filter: contrast(1.05) brightness(0.97) sepia(0.12) hue-rotate(-12deg);
}
```
This harmonizes panchromatic grayscale insets with Mars albedo color space without modifying raw pixel numbers or altering analytical overlays.

### D. Documentation Updates
- Updated `METHODOLOGY.md` (Section 9: Multi-Resolution Planetary GIS Display & Seamless Inset Model).
- Updated `LIMITATIONS.md` (Section 7: Multi-Resolution Imagery Hierarchy & Boundary Feathering).
- Updated `README.md` (Core Features: Multi-Resolution Planetary GIS Hierarchy & Seamless Inset Engine).

---

## 4. Automated Test Verification

### Frontend Suite (`npm test` in `mission-ui/`)
All 10 test suites passed:
```text
✓ check-engine.mjs                     (A* vs Dijkstra optimal-cost equivalence, route constraints)
✓ check-traverse.mjs                   (559 segments, 36,661 vertices, sol filtering)
✓ check-integration.mjs                (API synthetic vs official attribution, shortfall handling)
✓ check-intelligence.mjs               (Astrodynamics propagator, rover telemetry, SPICE ground tracks)
✓ check-nasa-data.mjs                  (7 official NASA sources, THEMIS thermal inertia, NAIF SPICE)
✓ check-cloud-ai.mjs                   (GCS assets, Gemini Mars Copilot, Azure Foundry dual-model)
✓ check-usgs-imagery-dem.mjs           (WMTS GetCapabilities z=0..17, HiRISE 1m DTM vs MOLA 200m)
✓ check-mars-now-conditions.mjs        (Mars24 clock, seasonal Ls, solar elevations)
✓ check-mission-intelligence.mjs       (Knowledge graph, causal risk propagation, what-if scenarios)
✓ check-map-rendering-fixes.mjs        (NoData alpha=0, edge feathering math, resolution hierarchy)
```

### Production Build (`npm run build` in `mission-ui/`)
- Built in **1.36s**. Generated `dist/mission-control/assets/index-B2X4xqMC.js` (881 kB) and `index-BL7qW-bJ.css` (88.5 kB).

### Backend Test Suite (`pytest backend/tests/unit/ -v`)
- **262 passed**, 1 skipped (official multi-GB HiRISE PDS3 file test), 0 failures in **69.23s**.

### Code Quality (`ruff check backend/app/`)
- **All checks passed!**

---

## 5. Visual Regression & Mandatory Screenshot Evidence

All screenshots were captured at standard **1440×900** resolution and saved in the artifact directory:

| Screenshot | File Path | Verification Objective | Result |
| :--- | :--- | :--- | :--- |
| **Shot 1** | `shot_01_global_mars.png` | Global Mars view (NASA Viking MDIM 2.1 mosaic) | ✅ Full continuous planet surface, no grey rectangles |
| **Shot 2** | `shot_02_jezero_overview.png` | Jezero Crater basin overview (CTX 6 m/px) | ✅ Seamless transition from Viking to CTX |
| **Shot 3** | `shot_03_hirise_local.png` | HiRISE local corridor (0.25 m/px orthomosaic) | ✅ Sub-meter crater morphology clearly resolved |
| **Shot 4** | `shot_04_feathered_boundaries.png` | Zoomed-in feathered boundary transition | ✅ 48–64 px soft alpha dissolve, no knife-edge seams |
| **Shot 5** | `shot_05_returntime_nodata.png` | Reachable return-time overlay with NoData | ✅ NoData cells 100% transparent; basemap visible |
| **Shot 6** | `shot_06_coverage_disabled.png` | Coverage layer disabled | ✅ No footprint outlines or grey bounding boxes |
| **Shot 7** | `shot_07_coverage_enabled.png` | Coverage layer enabled | ✅ Thin dashed green vector outline, non-occluding |
| **Shot 8** | `shot_08_zoom_pan_stability.png` | Map after multiple zoom and pan operations | ✅ Smooth rendering, no canvas accumulation |

### Before vs. After Comparison
- **Before (`before_map_rendering_fix.png`):** An opaque/semi-transparent slate-grey rectangular box obscured Jezero Crater, with sharp knife-edge cutouts between grayscale and color imagery.
- **After (`after_map_rendering_fix.png`):** The grey box is completely eliminated. The Mars terrain is 100% visible across the entire Jezero basin, with high-resolution insets feathering smoothly into the surrounding Viking global basemap.

---

## 6. Exact Files Modified & Git Metadata

```text
Commit SHA: 42eabc1ad55af2db0fabbd5f2bb59b236bb01cf4
Branch: fix/marspath-map-transparency-feathering
Tracking: origin/fix/marspath-map-transparency-feathering

Modified Files:
- README.md
- METHODOLOGY.md
- LIMITATIONS.md
- mission-ui/package.json
- mission-ui/src/MapView.jsx
- mission-ui/src/map_rendering.js (new)
- mission-ui/src/style.css
- mission-ui/check-map-rendering-fixes.mjs (new)
- dist/mission-control/index.html
- dist/mission-control/assets/index-B2X4xqMC.js
- dist/mission-control/assets/index-BL7qW-bJ.css
```

---

## 7. Remaining Limitations

1. **Analytical vs. Optical Separation:** As documented in `METHODOLOGY.md`, terrain slopes and routing graphs are computed strictly on DEM elevation arrays, never on visual imagery. Tone harmonization and edge feathering are strictly viewport rendering transformations and do not alter numerical elevations.
2. **Sub-Pixel Hazards:** HiRISE 1 m DTM cannot resolve sub-meter hazards (boulders < 0.5 m, wheel slip sand).
3. **PDS3 Archive Scale:** In local testing, the full multi-gigabyte PDS3 DTM download is skipped when absent, using the validated local bundled 1 m corridor fixture.
