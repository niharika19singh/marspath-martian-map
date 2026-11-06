# MARSPath Multi-Objective Routing Intelligence & Cost Model

This document explains the mathematical formulations, graph representation, search algorithms, mission optimization modes, and scientific limitations implemented in the MARSPath routing engine.

---

## 1. Graph Representation

- **Connectivity:** 8-connected regular grid graph over the cropped mission corridor DEM.
  - Orthogonal movements: North, South, East, West ($\Delta s_{2D} = \Delta x \text{ or } \Delta y$).
  - Diagonal movements: NW, NE, SW, SE ($\Delta s_{2D} = \sqrt{\Delta x^2 + \Delta y^2}$).
- **3D Surface Distance:**
  $$\Delta s_{3D} = \sqrt{\Delta s_{2D}^2 + (z_{\text{dest}} - z_{\text{src}})^2}$$
- **Diagonal Corner-Cutting Prevention:**
  Moving diagonally from $(r, c)$ to $(r+dr, c+dc)$ is **strictly prohibited** if either orthogonal adjacent cell $(r+dr, c)$ or $(r, c+dc)$ is untraversable (impassable cliff, severe roughness, or nodata). This prevents paths from clipping through thin cliff faces or hazardous barriers.

---

## 2. Explainable Edge Cost Formulation

Every directed edge $(u, v)$ from cell $u$ to adjacent cell $v$ is assigned an explainable, non-negative traversal cost:
$$\text{Cost}(u, v) = \Delta s_{3D} \cdot \left(1.0 + w_{\text{slope}} \cdot \hat{S}_{uv} + w_{\text{rough}} \cdot R_v + w_{\text{hazard}} \cdot H_v\right) + P_{\text{corridor}}$$

Where:
- $\Delta s_{3D} > 0$: 3D physical distance in meters.
- $\hat{S}_{uv}$: Directional slope factor. Slopes approaching the mode ceiling scale quadratically. Uphill climbs ($\Delta z > 0$) incur a $+20\%$ directional energy penalty.
- $R_v \in [0.0, 1.0]$: Local Terrain Ruggedness Index (TRI) at cell $v$.
- $H_v$: Missing data / uncertainty penalty ($4.0$ if nodata, $0.0$ if observed).
- $P_{\text{corridor}}$: Alternative route diversion penalty ($0.0$ for primary search).

### Non-Negativity & Admissibility Guarantee
Because weights $w \ge 0$, factors $\ge 0$, and multiplier $\ge 1.0$:
$$\text{Cost}(u, v) \ge \Delta s_{3D} \ge \Delta s_{2D} > 0$$
This guarantees that the Euclidean ground distance heuristic $h(u, \text{dest}) = \text{EuclideanDistance}_{2D}(u, \text{dest})$ is strictly **admissible** and **monotonic/consistent**, ensuring A* search optimality.

---

## 3. Search Algorithms: A* and Dijkstra Baseline

### A* Search (Primary Engine)
- Utilizes priority queue with $f(n) = g(n) + h(n)$.
- Early termination upon popping destination node.
- Enforces computational safety bound (`max_search_nodes = 100,000` default) to prevent runaway memory or latency.

### Reference Dijkstra Algorithm (Analytical Baseline)
- Standard uninformed Dijkstra search ($h \equiv 0$).
- Used in automated regression testing (`test_astar_dijkstra_equivalence.py`) to mathematically prove that A* achieves the exact identical minimum cost on identical terrain.

---

## 4. Optimization Priority Modes

| Mode | Slope Ceiling | $w_{\text{slope}}$ | $w_{\text{rough}}$ | Routing Priority |
|---|---|---|---|---|
| `safety_first` | 14.0° | 3.5 | 2.5 | Minimizes mechanical rollover risk, avoids fractured bedrock and dune traps. |
| `balanced` | 20.0° | 1.2 | 1.0 | Optimizes trade-off between total mission distance and elevation energy expenditure. |
| `science_first` | 22.0° | 0.7 | 0.6 | Enables steeper delta scarp ascents to visit high-priority geological science targets. |

---

## 5. Alternative Route Generation

When `num_alternatives > 1` is requested:
1. **Primary Route:** Optimal path found by A* using the selected mode.
2. **Alternative Corridor:** Edges along the primary path receive an additive $+1500\text{m}$ diversion penalty. A* re-runs on the penalized graph to discover a geometrically distinct corridor (overlap threshold $< 85\%$).
3. **Safety Backup Corridor:** Re-runs under strict `safety_first` constraints to provide a conservative baseline route.

---

## 6. Scientific & Operational Limitations

1. **Regional Resolution Scale (200 m/px):** The selected USGS global blended DEM (`Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`) has a nominal resolution of 200 metres per pixel ($\sim 189.77\text{ m} \times 200.00\text{ m}$ at Jezero Crater). It supports **regional corridor terrain assessment**, not metre-scale boulder/obstacle detection, wheel-scale hazard avoidance, or flight-grade autonomous rover navigation.
2. **HRSC/MOLA Blending & Thermal-Modelling Caveat:** As documented by USGS Astrogeology (Fergason et al., 2018), this global blended DEM was originally constructed to derive global thermal inertia (for THEMIS) where smooth regional transitions were prioritized over local topographic fidelity. Blending HRSC stereo-photogrammetry with MOLA laser altimetry introduces seam artifacts, vertical registration offsets, and smoothing inconsistencies across coverage boundaries.
3. **Heuristic Risk Scoring Disclaimer:** Route cost weights, slope/roughness penalties, `hazard_exposure_meters`, and categorical risk classifications (`nominal`, `moderate`, `high`) are **deterministic multi-criteria decision heuristics** for comparative corridor trade-offs. They are **not** empirically calibrated probabilities of mechanical rover failure or mission loss.

---

## 7. Terrain Evidence Quality vs. Physical Traversal Risk

MARSPath explicitly separates **physical terrain traversal heuristics** (`summary.risk_category`, `summary.hazard_exposure_meters`) from **data evidence quality** (`evidence_passport.quality_tier`):

- **Physical Traversal Risk (`summary.risk_category`):** Measures the relative topographic severity along a route (slope angles, roughness index, elevation change) assuming the underlying raster values are true.
- **Terrain Evidence Quality (`evidence_passport.quality_tier`):** Measures how trustworthy and complete the underlying raster observations are (`high`, `moderate`, `low`, `unverified`) based on:
  1. **Source Provenance:** Cryptographic verification of the official archival file (`verified_source`), direct official USGS endpoint retrieval of a subset extract (`official_endpoint_retrieved_checksum_unverified`), unverified local numeric raster (`valid_numeric_raster_unverified_source`), or procedural synthetic terrain (`synthetic_fallback` / `synthetic_test_fixture`).
  2. **Spatial Resolution Suitability:** Actual cell dimensions in metres (`actual_x_meters_per_pixel`, `actual_y_meters_per_pixel`, `effective_resolution_meters`) and whether the grid can resolve rover-scale hazards (`obstacle_detection_capable`).
  3. **Route & Corridor Observation Coverage:** Independent measurements of valid non-nodata cells along the route (`route_data_coverage_fraction`), across the cropped mission corridor (`corridor_data_coverage_fraction`), and within a 2-cell boundary buffer around nodata gaps (`near_nodata_segment_count`).

> **Scientific Integrity Rule:** A route on smooth synthetic terrain may have `risk_category = "nominal"` (flat geometry) while simultaneously receiving `evidence_passport.quality_tier = "unverified"` (procedural terrain). Conversely, a route on the real USGS HRSC/MOLA 200 m/px Jezero extract receives `evidence_passport.quality_tier = "moderate"` because the subset extract is retrieved from the official USGS endpoint without a full-file archival MD5 match and its 200 m/px grid resolves regional corridors rather than metre-scale obstacles. `quality_tier` is **never** a probability of rover survival or mission success.
