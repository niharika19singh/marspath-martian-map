# MARSPath Limitations & Assumptions

This document records the scope boundaries, model assumptions, and data constraints of MARSPath (Stage 1: Safety Core).

---

## 1. Planning Indicators vs. Operational Certification
- **Not a Flight Certification Tool:** Outputs (`relative route score`, `estimated relative effort`, `return_zone`, `rescue_zone`, `turnaround`) are **planning indicators** for relative corridor comparison. They are **not** probabilities of vehicle survival, crew metabolic/oxygen guarantees, or flight-certified traverse clearances.
- **No Uncalibrated Absolute Risk Claims:** The directional slope cost, cross-slope penalty, and Mars-gravity Minetti-style effort curve provide unitless relative rankings between candidate routes on a given DEM, not validated human metabolic expenditure (kcal) or hardware failure rates.

---

## 2. Terrain Resolution & Footprint Boundaries
- **Sub-Pixel Hazards Invisible:** Even the `1.0 m/px` HiRISE DTM (`10.5066/P9REJ9JN`) cannot resolve sub-meter boulders, sharp ventifacts, wheel-entrapment sand ripples, or thin dust crusts overlying bedrock. When aggregated (e.g., to `8.0 m/px` effective routing grid for large bounding boxes), block-maximum aggregation preserves steep pixel maxima within the block rather than guaranteeing smooth micro-topography.
- **Outside the HiRISE Corridor:** Outside the locally provisioned `1.0 m/px` HiRISE corridor window (`77.3819891°E–77.4580081°E`, `18.3719875°N–18.4400097°N`), routing falls back to the `200.0 m/px` MOLA-HRSC blended DEM (`10.5066/P9P7W018`). At `200 m/px`, narrow scarps, crater rims, and channels inside single cells are heavily averaged out.
- **Independent DEM Selection Between Endpoints:** `/api/v1/conditions` reports terrain sampled from its configured DEM source (MOLA-HRSC 200 m where applicable), whereas `/api/v1/routes/plan` uses the active routing DEM (HiRISE 1 m native / block-aggregated effective resolution inside the Jezero delta corridor). Resolution and provenance labels are displayed separately so neither is mistaken for the other.
- **No-Data Cells Remain Blocked:** `NoData` cells (and their 3x3 safety dilation halo) are strictly excluded from routing and serialized as `null` (`None`) in return/rescue overlays; MARSPath never interpolates across `NoData` voids during Stage 1 planning.

---

## 3. Biomechanics & Traverse Assumptions
- **Directional Walking Speed & Minetti Scaling:** The Mars-gravity Minetti effort curve scales Earth biped treadmill polynomial coefficients by $g_{\text{Mars}} / g_{\text{Earth}} \approx 0.3794$ and clamps above `1.0` at flat minimum. This ignores regolith sinkage, boot-sole traction, pressurized spacesuit joint torque limits, and rover wheel slip (terrains with high cross-slope $\theta_{\text{cross}}$ are penalized linearly by `cross_slope_weight`, default `0.35`, rather than a full terramechanics model).
- **Static Surface Conditions Along Route:** Return-time and rescue-time grids assume steady speed parameters across the planned EVA window and do not couple transient wind gusts, dust devil encounters, or surface temperature extremes directly into wheel traction yet.

---

## 4. Solar Turnaround & Conditions Scope
- **Idealized Horizon Sunset:** Mars24 sunset (`sunset_ltst_hours`, `sunset_utc`) uses astronomical geometric solar depression without local crater-rim horizon ray-casting in Stage 1. Actual topographic shadowing inside steep valleys or beside the Jezero Western Delta scarp occurs earlier than astronomical sunset; operators should increase `daylight_buffer_minutes` near tall scarps.
- **Seasonal Climatology vs. Forecast:** Climatology metrics (`kind="modelled_climatology"`) reflect MCD v6.1 / MEDA Year-1 harmonic averages, not real-time meteorological telemetry beyond the released PDS MEDA archive (`urn:nasa:pds:mars2020_meda`).

---

## 5. Browser Engine vs. Backend Precision
- For instant offline/interactive preview when the FastAPI backend is absent, `mission-ui/src/engine.js` mirrors Stage 1 directional gradients, Minetti effort, backward-Dijkstra return/rescue grids, and Mars24 turnaround math on the active client terrain buffer. Authoritative multi-mode route reports and provenance metadata come from `POST /api/v1/routes/plan` when connected to the backend.
