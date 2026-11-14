# MARSPath Methodology — Stage 1 Safety Core

This document defines the mathematical models, routing algorithms, temporal feasibility checks, provenance schema, and configurable constants implemented in MARSPath (Stage 1: Safety Core).

> **Framing Notice:** All scores, traversal times, and effort values computed by MARSPath are **planning indicators** (`relative route score`, `estimated relative effort`), never probabilities of mission success, physiological caloric expenditures, or safety certifications.

---

## 1. Terrain Ingestion and Provenance Separation

1. **Strict Elevation Separation:** Route graphs, slopes, surface roughness, and return/rescue grids are computed exclusively from numerical Digital Elevation Model (DEM) rasters (USGS HiRISE 1 m/px DTM when intersecting the provisioned Jezero delta corridor; USGS MOLA-HRSC 200 m/px blended DEM globally/regionally across Jezero Crater; or labeled synthetic terrain only when real rasters are unavailable and permitted). Visual mosaics (Viking MDIM 2.1, CTX 6 m ortho, HiRISE 25 cm ortho) are strictly visualization-only and never enter routing calculations.
2. **Grid Aggregation Safeguard:** When a local raster crop exceeds `MAX_GRID_CELLS` (default `250,000`), MARSPath aggregates blocks conservatively using block-maximum slope and block-maximum roughness rather than smoothing peaks away, and reports both the **native DEM resolution** (e.g., `1.0 m/px`) and the **effective routing grid resolution** (e.g., `8.0 m/px`).
3. **No-Data Handling:** Any DEM cell marked as `NoData` or non-finite is expanded with a 3x3 safety dilation mask and treated as **non-traversable**. Returned overlay grids (`return_zone`, `rescue_zone`) serialize non-traversable or unreachable cells as `null` (`None`), never as `0` or invented numbers.
4. **Provenance Fields:** Every route summary carries `kind` (`computed` | `modeled` | `measured` | `historical` | `derived`), `source`, `resolution`, and `as_of`, alongside the route metrics.

---

## 2. Directional Slope Geometry & Cost Modes

On a Cartesian-scaled local grid with zonal spacing $\Delta x$ and meridional spacing $\Delta y$, centered finite differences (falling back to one-sided differences near valid edges/NoData borders) compute the easting and northing elevation gradients $(\partial z / \partial x, \partial z / \partial y)$.

For each directed 8-connected step from pixel $(r_1, c_1)$ to $(r_2, c_2)$ with horizontal unit step vector $\hat{u} = (u_x, u_y)$:

- **Along-track slope** ($\theta_{\text{along}}$):
  $$\theta_{\text{along}} = \arctan\!\left(\frac{z_2 - z_1}{d_{2\text{D}}}\right)$$
  Positive values represent uphill climbs; negative values represent descents.
- **Cross-track slope** ($\theta_{\text{cross}}$): Computed from the directional gradient vector projected onto the perpendicular unit vector $\hat{u}_\perp = (-u_y, u_x)$, quantifying side-slope roll hazard:
  $$\theta_{\text{cross}} = \arctan\!\left(\left|\nabla z \cdot \hat{u}_\perp\right|\right)$$

MARSPath supports two explicit cost modes (`cost_mode`):

1. **`directional` (Stage 1 default):** Uphill slopes incur substantially greater traversal penalty than equal-magnitude downhill slopes (while steep descents still penalize braking/slip), plus an explicit roll penalty proportional to `cross_slope_weight` $\times |\theta_{\text{cross}}|$.
2. **`legacy_magnitude` (Comparison mode):** Symmetric absolute-slope cost model preserved for side-by-side comparison in the UI (`Route Comparison Table`).

All cost breakdowns preserve the five canonical additive components whose sum equals `total_cost`:
- `base_distance_cost`
- `slope_penalty` (includes directional along-track + cross-slope penalties)
- `roughness_penalty`
- `hazard_penalty`
- `extra_penalty`

---

## 3. Effort Models (`effort_model`)

MARSPath supports two configurable effort models on top of slope geometry:

1. **`slope_penalty` (Default planning indicator):** Cost-weighted terrain impedance scaled for rover/EVA corridor planning.
2. **`minetti_effort` (Mars-gravity Minetti-style relative effort):** Applies a Mars-gravity-scaled 5th-order walking cost polynomial inspired by Minetti et al. (2002), scaled by the Martian gravity ratio $g_{\text{Mars}} / g_{\text{Earth}} = 3.72076 / 9.80665 \approx 0.3794$ and multiplied by `suit_load_factor` (level baseline `1.0` on flat terrain, floored at `0.45` on downhill savings; `calculate_edge_cost` enforces step routing cost $\ge \text{distance}_{3\text{D}}$ so the Euclidean A* heuristic stays admissible). Output is explicitly labeled **"estimated relative effort"** (dimensionless planning indicator, not physiological energy/oxygen consumption).

---

## 4. Return-to-Habitat Constraint (Backward Dijkstra)

To guarantee that an outbound plan does not strand the crew or rover beyond their remaining return budget:

- `compute_backward_time_grid` executes **reverse-edge Dijkstra** starting from the `habitat` node (defaulting to the route origin when no separate habitat coordinate is specified) using directional uphill/downhill walking speeds along the **reverse** traversal direction (`target -> habitat`).
- Traversal modes (`return_constraint_mode`):
  - **`block`**: Rejects outbound destinations whose backward return time exceeds the EVA budget (raising `UnreachableDestinationError` with diagnostic guidance) and blocks cells exceeding budget during A* expansion.
  - **`flag`**: Computes the route while annotating segments exceeding budget and setting `exceeds_return_budget = true`.
  - **`off`**: Disables return-budget pruning/blocking (still computes baseline diagnostics when habitat is present).
- Serialized `return_zone` grid overlays report minutes required to return to habitat per grid cell (`null` for NoData or unreachable cells).

---

## 5. Hard Turnaround Time (Mars24 Sunset + Daylight Buffer)

Using the canonical NASA GISS Mars24 solar geometry model (Allison & McEwen, 2000), MARSPath computes Local True Solar Time (LTST) and solar sunset (`sunset_utc`, `sunset_ltst_hms`) at the route start coordinate for the configured `departure_utc`.

Given an EVA time budget (`eva_budget_hours`) and a safety margin (`daylight_buffer_minutes`), the hard turnaround time (`must_turn_around_by_utc` / `must_turn_around_by_ltst_hms`) is governed by whichever arrives earlier:
1. Half of the EVA budget from departure (for symmetric out-and-back planning), or
2. Sufficient margin before local sunset minus `daylight_buffer_minutes` and expected return duration.

When departure occurs after sunset, pre-dawn, or during polar night, `feasible_before_sunset` is marked `false` and surfaced immediately in both the Hard Turnaround card and elevation profile. Stale client route requests during rapid UI parameter edits are automatically canceled via `AbortController`.

---

## 6. Rescue-Time Map (Drivable Support Vehicle Reachability)

To assess unassisted-return contingency coverage, `compute_backward_time_grid` is run a second time from `habitat` with vehicle constraints:
- Maximum drivable slope limit: `rescue_max_slope_deg` (default `12.0°`; cells steeper than this limit in the vehicle return direction are non-traversable for wheeled rescue).
- Rescue vehicle speed: `rescue_speed_m_s` (configurable).
- Alert threshold: `rescue_threshold_minutes` (segments whose rescue access time exceeds this threshold are flagged in segment telemetry and highlighted on the `Rescue time map` overlay).

---

## 7. Configurable Constants Reference

| Parameter / Constant | Default Value | Scope / Config Location | Purpose |
| :--- | :--- | :--- | :--- |
| `cost_mode` | `"directional"` (`"legacy_magnitude"` optional) | `RoutePlanRequest` / `cost_model.py` | Uphill/downhill asymmetry + cross-slope vs symmetric magnitude |
| `effort_model` | `"slope_penalty"` (`"minetti_effort"` optional) | `RoutePlanRequest` / `cost_model.py` | Slope penalty vs Mars-gravity Minetti-style relative effort |
| `cross_slope_weight` | `0.35` | `RoutePlanRequest` / `cost_model.py` | Roll/side-slope penalty weight on $\theta_{\text{cross}}$ |
| `gravity_ratio` | `3.72076 / 9.80665` ($\approx 0.3794$) | `cost_model.py` | Mars-to-Earth surface gravity scaling for Minetti curve |
| `suit_load_factor` | `1.0` | `RoutePlanRequest` / `cost_model.py` | Dimensionless payload/suit multiplier for effort indicator |
| `return_constraint_mode` | `"flag"` (`"block"`, `"off"`) | `RoutePlanRequest` / `route_service.py` | Backward-Dijkstra return budget enforcement |
| `daylight_buffer_minutes` | `0.0` (UI default configurable) | `RoutePlanRequest` / `mission_clock.py` | Pre-sunset margin subtracted from turnaround window |
| `rescue_enabled` | `true` | `RoutePlanRequest` / `route_service.py` | Enables drivable-slope rescue reachability map |
| `rescue_speed_m_s` | Configurable | `RoutePlanRequest` / `route_service.py` | Rescue vehicle nominal traverse speed |
| `rescue_max_slope_deg` | `12.0`° | `RoutePlanRequest` / `route_service.py` | Drivable slope ceiling for rescue vehicle |
| `rescue_threshold_minutes` | Configurable | `RoutePlanRequest` / `route_service.py` | Segment flagging threshold for extended rescue access |
| `DEFAULT_MAX_SLOPE_DEG` | `20.0`° | `backend/app/core/config.py` | Nominal traverse slope limit |
| `STRICT_MAX_SLOPE_DEG` | `14.0`° | `backend/app/core/config.py` | Conservative traverse slope limit |
| `MAX_GRID_CELLS` | `250000` | `backend/app/core/config.py` | Cap before conservative DEM block aggregation |
| `ROUTING_TIMEOUT_SECONDS` | `10.0` s | `backend/app/core/config.py` | A* traversal compute timeout |
| `MARS_RADIUS_METERS` | `3396190.0` m | `backend/app/core/config.py` | IAU Mars 2000 reference sphere radius |
| `MARS_SOL_RATIO` | `1.0274912517` | `backend/app/conditions/mars24.py` | Sidereal/synodic Earth-day to Mars-sol conversion ratio |
| `MARS_SOL_SECONDS` | `88775.244147` s | `backend/app/conditions/mars24.py` | Mean solar day on Mars in SI seconds |

---

## 8. Mission Intelligence & Risk Fusion Subsystem

Inspired by multi-source data fusion architectures (e.g. Aureum AI / Verity), the **MARSPath Mission Intelligence & Risk Fusion Engine** evolves MARSPath from a static terrain routing tool into a provenance-traceable planetary decision-support platform.

### 8.1 Multi-Source Evidence Fusion & Normalization
All incoming observations from orbital sensors (HiRISE, CTX, THEMIS, MOLA-HRSC), in-situ instruments (Perseverance MEDA, SuperCam, Mastcam-Z), and ancillary models (SPICE ephemerides, MCD climatology) are normalized into canonical evidence structures (`NormalizedObservation`):
- **Quality Tiers:** `GOLD` (peer-reviewed / calibrated PDS archives with cryptographic integrity), `SILVER` (standard processed mission telemetry), `BRONZE` (preliminary unvalidated products), and `UNVALIDATED` (provisional or experimental inputs).
- **Provenance Kinds:** `MEASURED` (direct instrument readings), `MODELED` (numerical simulations / climatology), `DERIVED` (computed terrain metrics, slope, TRI), `HISTORICAL` (prior traverse logs), and `INFERRED` (multi-spectral proxies).
- **Quantified Uncertainty:** Retains $1\sigma$ / $2\sigma$ error bars, resolution thresholds, and missing-value flags (preserving `-9999.0` sentinel representations as strictly unavailable data).

### 8.2 Geospatial & Temporal Indexing
- **Mars Spherical Distance:** Great-circle geodesy using the IAU 2000 Mars mean radius ($R = 3,396,190\text{ m}$) with positive-East longitude wrapping across the $[0^\circ, 360^\circ)$ and $[-180^\circ, 180^\circ)$ frames.
- **Cross-Track Distance:** Point-to-segment spherical projection for determining proximity of environmental hazards to traverse corridors.
- **Coverage Gap Detection:** Automated discovery of bounding regions lacking high-resolution DEM or in-situ atmospheric coverage, flagging fallback dependencies (e.g. falling back to 200 m MOLA-HRSC data).

### 8.3 Geospatial Mission Knowledge Graph
The mission domain is modeled as a directed property graph ($G = (V, E)$) comprising:
- **12 Node Types:** `DATASET`, `OBSERVATION`, `HAZARD`, `ROUTE_SEGMENT`, `ROUTE`, `WAYPOINT`, `TERRAIN_REGION`, `OPERATIONAL_CONSTRAINT`, `SCIENCE_TARGET`, `SPACECRAFT`, `COMM_PASS`, `WEATHER_EVENT`.
- **12 Directed Relation Types:** `DERIVED_FROM`, `OBSERVED_BY`, `AFFECTS`, `CONSTRAINS`, `LOCATED_IN`, `INTERSECTS`, `PRECEDES`, `CONTRIBUTES_TO`, `MONITORS`, `VALIDATES`, `CONFLICTS_WITH`, `SUPPORTS`.
- **Multi-Hop Traversal Algorithms:**
  - *Upstream Evidence Tracing:* Traverses backward along `DERIVED_FROM`, `OBSERVED_BY`, `AFFECTS`, and `CONSTRAINS` edges to discover authoritative NASA PDS/USGS root products and DOIs supporting any hazard or route constraint.
  - *Downstream Impact Tracing:* Traverses forward along `AFFECTS`, `CONSTRAINS`, and `PRECEDES` edges to discover which route segments, rover subsystems, and science targets are jeopardized by an observed anomaly or hazard.

### 8.4 Causal Risk Propagation Engine
Risk is propagated deterministically through traverse segments:
1. **Segment Traversability:** Segments are classified into discrete operational states: `PASSABLE`, `MARGINAL` (approaching constraints), or `IMPASSABLE` (violating strict slope ceilings or crossing critical hazards).
2. **Relative Effort Index:** A continuous planning indicator scaled from baseline terrain impedance, slope gradient, surface roughness, and localized wheel degradation factors.
3. **Hazard Exposure Score:** Sum of proximal hazard severity weights attenuated by Euclidean/spherical distance.
4. **Uncertainty Exposure:** Quantifies lack of high-resolution evidence along the corridor (e.g., segments traversing low-resolution MOLA fallback regions or uncharacterized terrain).
5. **Causal Chain Generation:** Explicit diagnostic narratives linking root evidence (e.g., high-resolution HiRISE slope or THEMIS low-thermal-inertia sand) to specific operational segment constraints.

### 8.5 What-If Contingency Scenarios
Enables operators to evaluate hypothetical or deteriorating operational conditions:
- **Modifiers:** Atmospheric dust storm opacity ($\tau$), power budget factor ($0.0 - 1.0$), slope ceiling threshold (degrees), wheel degradation multiplier, and communication blackout windows.
- **Side-by-Side Comparison:** Compares modified scenarios against primary baseline traverses, reporting deltas in traversability, effort index, hazard exposure, and identifying compromised segments.

