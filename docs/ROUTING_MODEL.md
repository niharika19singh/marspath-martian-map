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
3. **Heuristic Risk Scoring & Incomplete-Observation Disclosure:** Route cost weights, slope/roughness penalties, `hazard_exposure_meters`, and categorical risk classifications are **deterministic multi-criteria decision heuristics** for comparative corridor trade-offs. They are **not** empirically calibrated probabilities of mechanical rover failure or mission loss.
   - When 100% of route steps have valid elevation, slope, and roughness observations (`risk_assessment_status = "complete_observed"`), `risk_category` is one of `"nominal"`, `"moderate"`, or `"high"`.
   - When any route step lacks valid elevation, slope, or roughness observations (`risk_assessment_status = "incomplete_partial_observations"` or `"unverified_no_valid_observations"`), complete `estimated_duration_hours`, `energy_index`, `hazard_exposure_meters`, and `surface_3d_distance_meters` are returned as `null` (with partial observed aggregates reported in dedicated fields), and `risk_category` explicitly discloses incomplete data (`"unverified_incomplete_terrain_data"`, `"moderate_observed_incomplete_data"`, `"high_observed_incomplete_data"`, or `"unverified_no_valid_terrain_data"`) rather than ever claiming `"nominal"`.

---

## 7. Terrain Evidence Quality vs. Physical Traversal Risk

MARSPath explicitly separates **physical terrain traversal heuristics** (`summary.risk_category`, `summary.hazard_exposure_meters`) from **data evidence quality** (`evidence_passport.quality_tier`):

- **Physical Traversal Risk (`summary.risk_category`):** Measures the relative topographic severity along a route (slope angles, roughness index, elevation change) over observed cells, explicitly disclosing incomplete observations (`unverified_incomplete_terrain_data`, `moderate_observed_incomplete_data`, `high_observed_incomplete_data`, `unverified_no_valid_terrain_data`) whenever any step lacks valid terrain data.
- **Terrain Evidence Quality (`evidence_passport.quality_tier`):** Measures how trustworthy and complete the underlying raster observations are (`high`, `moderate`, `low`, `unverified`) for the declared **regional corridor assessment scope** based on:
  1. **Source Provenance & Cryptographic Integrity:** Independent verification of the full upstream archive checksum (`validation_status == "verified_source"`, `source_checksum_verified == True`) AND local file SHA-256 integrity (`local_integrity_verified == True`), established Mars CRS, and known vertical datum; versus direct official USGS endpoint retrieval of a subset extract (`official_endpoint_retrieved_checksum_unverified`), unverified local numeric raster (`valid_numeric_raster_unverified_source`), or procedural synthetic terrain (`synthetic_fallback` / `synthetic_test_fixture`).
  2. **Spatial Resolution Suitability (`<= 250 m/px` for regional assessment):** `high` means authoritative, verified, complete terrain evidence suitable for regional corridor assessment (`effective_resolution_meters <= 250.0`). It does **not** mean metre-scale resolution and does **not** imply local obstacle detection capability. `obstacle_detection_capable` remains an independent resolution property (`True` only at `<= 1.0 m/px`). Thus, a fully verified `200 m/px` dataset with complete regional evidence qualifies as `high` for regional assessment while `obstacle_detection_capable` remains `False`.
  3. **Route & Corridor Observation Coverage:** Requires 100% valid route sample coverage (`route_data_coverage_fraction == 1.0`), 100% valid cropped corridor coverage (`corridor_data_coverage_fraction == 1.0`), and zero segments near nodata boundaries (`near_nodata_segment_count == 0`) for `high`.

> **Scientific Integrity Rule:** A route on smooth synthetic terrain may have `risk_category = "nominal"` (flat geometry) while simultaneously receiving `evidence_passport.quality_tier = "unverified"` (procedural terrain). Conversely, a route on the default USGS HRSC/MOLA 200 m/px HTTP Range subset extract receives `evidence_passport.quality_tier = "moderate"` because the streamed sub-window does not verify the full 11.38 GB upstream archive MD5 over all source bytes (`source_checksum_verified = False`). `quality_tier` is **never** a probability of rover survival or mission success.

---

## 8. Route Robustness Stress Testing (`robustness_assessment`)

When `robustness_config.enabled = true`, MARSPath evaluates the sensitivity of each baseline route alternative to plausible spatially correlated elevation perturbations.

### 8.1 Mathematical Perturbation Model (`spatially_correlated_gaussian_elevation_perturbation`)
- **Explicit User Assumptions:** The active USGS MOLA-HRSC blended DEM does **not** publish a validated per-pixel vertical error standard deviation ($\sigma_z$) or spatial correlation length ($L_c$) in its provenance metadata. Therefore, `vertical_sigma_m` ($\sigma_z > 0$) and `correlation_length_m` ($L_c > 0$) must be explicitly supplied by the caller; omitting them when `enabled = true` raises a validation error.
- **Reproducible Seed Sequence:** A master integer `seed` generates `scenario_count` ($3 \le N \le 20$) deterministic per-scenario integer seeds via `numpy.random.SeedSequence(seed)`.
- **2D Separable Gaussian Spatial Filter:** For each scenario $k$:
  1. Draw an independent standard normal grid $W_k \sim \mathcal{N}(0, 1)$ using `scenario_seed`, setting $W_k[\text{nodata\_mask}] = 0$.
  2. Convert physical correlation length $L_c$ into pixel standard deviations using the actual physical cell sizes $(\Delta x, \Delta y)$:
     $$\sigma_x = \frac{L_c}{\Delta x} \text{ (columns/zonal)}, \quad \sigma_y = \frac{L_c}{\Delta y} \text{ (rows/meridional)}$$
  3. Convolve $W_k$ with a 2D separable Gaussian filter kernel:
     $$K(\Delta r, \Delta c) \propto \exp\left(-\frac{\Delta r^2}{2\sigma_y^2} - \frac{\Delta c^2}{2\sigma_x^2}\right)$$
  4. Center and normalize the filtered field strictly over valid cells $V = \neg\text{nodata\_mask}$ to zero sample mean ($\mu_V = 0$) and population standard deviation equal to `vertical_sigma_m` ($\sigma_z$):
     $$\delta Z_k[r, c] = \left(F_k[r, c] - \mu_V\right) \cdot \frac{\sigma_z}{s_V} \quad \forall (r, c) \in V, \qquad \delta Z_k[\text{nodata\_mask}] = 0$$
  5. Add $\delta Z_k$ to a copy of the cropped elevation array without mutating the original DEM or altering the nodata mask, then recompute slope, roughness, traversability, the 8-connected `TerrainGridGraph`, and `astar_search`.

### 8.2 Route Comparison Metrics & Non-Probabilistic Interpretation
- **Baseline Feasibility (`baseline_route_feasibility_fraction`):** Checks whether every baseline grid node and step remains traversable in the scenario, including the **diagonal corner-cutting constraint** (diagonal steps require both orthogonal adjacent cells to be traversable).
- **Jaccard Route Overlap (`jaccard_overlap_fraction`):** Computed over discrete `(row, col)` grid-cell sets:
  $$\text{Jaccard}(R_{\text{base}}, R_{\text{scen}}) = \frac{|R_{\text{base}} \cap R_{\text{scen}}|}{|R_{\text{base}} \cup R_{\text{scen}}|}$$
- **Relative Cost Regret (`cost_regret_fraction`):** Evaluated on the scenario graph using the same active cost model whenever the baseline route is feasible and the scenario-optimal cost is valid:
  $$\text{cost\_regret\_fraction} = \frac{C_{\text{base in scenario}} - C_{\text{scenario optimal}}}{C_{\text{scenario optimal}}}$$
  Tiny negative floating-point rounding residuals ($-10^{-9} \le \text{regret} < 0$) are clamped to `0.0`. `cost_regret_threshold_fraction` (default `0.05`) is a comparative routing efficiency reporting criterion, **not** a physical safety threshold.
- **Route Retention (`baseline_route_retention_fraction`):** Fraction of **evaluated (completed) scenarios** (`completed_scenario_count`) in which the baseline route remained traversable, had valid scenario cost, and satisfied `cost_regret_fraction <= cost_regret_threshold_fraction`.
- **Failed Scenarios:** Scenarios where start/destination became untraversable (`failed_untraversable_endpoint`), no corridor existed (`failed_unreachable`), or A* exceeded `max_search_nodes` (`failed_computational_bound`) are reported in `scenario_results` and `failed_scenario_count` and are never treated as positive stability evidence.
- **Separation of Concepts & Mandatory Disclaimer:** Terrain evidence quality (`evidence_passport.quality_tier`), physical traversal risk heuristics (`summary.risk_category`), and route perturbation stability (`robustness_assessment`) are distinct, independent dimensions. Scenario fractions are deterministic frequencies across the finite tested scenario set conditional on user-specified assumptions—they are **not** calibrated probabilities:
  > *"Results describe route stability under the specified hypothetical terrain perturbation model. They do not establish the actual probability of rover failure or mission success."*
