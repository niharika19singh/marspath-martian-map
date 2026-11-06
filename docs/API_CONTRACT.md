# MARSPath API Integration Contract (for Kunal & Frontend)

This document specifies the complete REST API contract between Niharika's geospatial/routing backend and Kunal's React frontend.

---

## 🪐 Planetary Coordinate Convention (CRITICAL)

Mars geodesy differs fundamentally from Earth mapping:

1. **Geographic Coordinate Reference System (CRS):** `IAU2000:49900` (Mars 2000 Sphere, volumetric mean radius $R = 3,396,190\text{ m}$).
2. **Analysis Projection:** Local Equirectangular Metric Projection centered on Jezero Crater ($R = 3,396,190\text{ m}$).
3. **Longitude Convention:** **Positive East**, in range `[0°, 360°)` or `[-180°, +180°)`.
   - The backend accepts both and auto-normalizes to `[0°, 360°)`.
4. **Latitude Convention:** **Planetocentric latitude**, in range `[-90.0°, +90.0°]`.
5. **Active Pilot Region (Jezero Crater):**
   - Center: `~77.58° E, ~18.38° N`
   - East Longitude Bounds: `77.15° E` to `78.00° E` (`77.20° E` to `77.95° E` in synthetic mode)
   - Latitude Bounds: `18.10° N` to `18.70° N` (`18.15° N` to `18.65° N` in synthetic mode)
6. **Earth CRS Rejection:** Sending Earth CRS identifiers (such as `EPSG:4326` or `EPSG:3857`) is rejected with HTTP `422 Unprocessable Entity`.

---

## 📡 Endpoints Specification

### 1. Health & Scientific Readiness

- **Method:** `GET`
- **Path:** `/health`
- **Description:** Returns service operational status, version, and scientific terrain readiness. Separates API uptime from scientific DEM availability.

#### Response Example (200 OK — Official USGS Endpoint DEM Loaded)
```json
{
  "status": "healthy",
  "service": "MARSPath — Mars Exploration Route Intelligence and Science Planner",
  "version": "0.1.0",
  "environment": "production",
  "planetary_target": "Mars",
  "pilot_region": "Jezero Crater",
  "data_readiness": {
    "dem_loaded": true,
    "real_dem_requested": true,
    "real_dem_loaded": true,
    "is_synthetic": false,
    "data_mode": "real_official_endpoint_unverified_checksum",
    "real_data_validation_status": "official_endpoint_retrieved_checksum_unverified",
    "local_integrity_verified": true,
    "source_checksum_verified": false,
    "dem_resolution_meters": 200.0,
    "grid_shape": [178, 252],
    "spatial_coverage": {
      "min_lon": 77.1485,
      "max_lon": 77.9988,
      "min_lat": 18.1009,
      "max_lat": 18.7015
    },
    "crs": "IAU2000:49900",
    "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
    "official_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
    "official_source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
    "fallback_reason": null,
    "blocking_errors": []
  }
}
```

---

### 2. Available Map Layers

- **Method:** `GET`
- **Path:** `/api/v1/layers`
- **Description:** Lists all available layers, dynamically reporting the active DEM's physical pixel resolution and strict source attribution. Synthetic and unverified local DEMs **never** advertise an official USGS URL or product ID (`source_url: null`, `product_id: null`).

#### Response Example A (200 OK — Official USGS 200m DEM Active)
```json
{
  "count": 5,
  "pilot_region": "Jezero Crater, Mars",
  "layers": [
    {
      "id": "mars_elevation_jezero",
      "name": "Martian Digital Elevation Model (Topography)",
      "category": "elevation",
      "layer_type": "analysis_derived",
      "description": "Numerical surface elevation relative to the Mars reference datum. Internal analysis layer queried via /api/v1/routes/plan.",
      "units": "meters",
      "resolution_meters": 200.0,
      "bounds": {
        "min_lon": 77.148497,
        "min_lat": 18.100859,
        "max_lon": 77.998775,
        "max_lat": 18.701453
      },
      "crs": {
        "identifier": "IAU2000:49900",
        "name": "Mars 2000 Sphere (IAU/IAG Working Group)",
        "ellipsoid_radius_meters": 3396190.0,
        "latitude_type": "planetocentric",
        "longitude_direction": "positive_east",
        "projection": "Geographic (Planetocentric Degrees)"
      },
      "source_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
      "source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
      "product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
      "validation_status": "official_endpoint_retrieved_checksum_unverified",
      "source_checksum_verified": false,
      "provenance_note": "Retrieved from official USGS Astrogeology HTTPS endpoint via GDAL /vsicurl/ range extraction; local GeoTIFF SHA-256 integrity verified, but full 11.38 GB upstream file MD5 checksum remains unverified.",
      "is_numerical": true,
      "is_available": true,
      "is_renderable": false,
      "render_url": null,
      "is_synthetic": false
    }
  ]
}
```

#### Response Example B (200 OK — Synthetic Terrain Active)
```json
{
  "id": "mars_elevation_jezero",
  "name": "Martian Digital Elevation Model (Topography)",
  "category": "elevation",
  "layer_type": "analysis_derived",
  "description": "Numerical surface elevation relative to the Mars reference datum. Internal analysis layer queried via /api/v1/routes/plan.",
  "units": "meters",
  "resolution_meters": 118.5,
  "source_name": "Synthetic Jezero Crater Terrain Model",
  "source_url": null,
  "product_id": null,
  "validation_status": "synthetic_test_fixture",
  "source_checksum_verified": false,
  "provenance_note": "Internal deterministic procedural terrain model for Jezero Crater; not derived from NASA or USGS observation data.",
  "is_numerical": true,
  "is_available": true,
  "is_renderable": false,
  "render_url": null,
  "is_synthetic": true
}
```

---

### 3. Data Readiness & Catalog Status

- **Method:** `GET`
- **Path:** `/api/v1/data/status`
- **Description:** Detailed telemetry on active datasets, resolution, spatial coverage fraction, provenance verification status, optional HiRISE local DTM readiness, and the reference planetary product catalog (`products` includes runtime readiness fields `is_loaded` and `runtime_status`).
- **HiRISE Status Fields (`DataStatusResponse`):**
  - `hirise_enabled` (`bool`): Whether `MARSPATH_USE_HIRISE_DEM` is enabled.
  - `hirise_loaded` (`bool`): Whether a validated local HiRISE DTM is loaded and available for localized corridor selection.
  - `hirise_validation_status` (`str`): One of `"disabled"`, `"incomplete_missing_hirise_dem"`, `"invalid_hirise_dem"`, `"valid_numeric_raster_unverified_source"`, or `"verified_source"`.
  - `hirise_resolution_meters` (`float | null`): Native effective resolution of the loaded HiRISE DTM in meters/pixel.
  - `hirise_coverage` (`BoundingBox | null`): Geographic bounds (`min_lon`, `min_lat`, `max_lon`, `max_lat`) of the loaded HiRISE DTM.
  - `hirise_dataset_name` (`str | null`): Dataset title of the loaded HiRISE DTM when available.
  - `hirise_fallback_reason` (`str | null`): Diagnostic reason when HiRISE is disabled, missing, or invalid.

---

### 4. Route Planning, Terrain Source Selection & Terrain Evidence Passport

- **Method:** `POST`
- **Path:** `/api/v1/routes/plan`
- **Description:** Selects a single consistent elevation source (`source_selection`: HiRISE local ~1 m/px DTM when enabled, valid, and 100% containing the padded corridor; otherwise regional MOLA–HRSC ~200 m/px DEM), optimizes traversable routes between two planetary coordinates, and attaches a structured **Terrain Evidence & Route Confidence Passport** (`evidence_passport`) to every route alternative.

#### Multi-Resolution Source Selection Report (`source_selection`)
Every `RoutePlanResponse` includes a top-level `source_selection` (`TerrainSourceSelectionReport`) object:
```json
{
  "source_selection": {
    "selected_source_id": "dem_mola_hrsc_jezero_200m",
    "selected_dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
    "selection_reason": "Selected regional MOLA-HRSC 200 m/px DEM because optional HiRISE local DTM is disabled (MARSPATH_USE_HIRISE_DEM=false).",
    "hirise_candidate_evaluated": false,
    "hirise_enabled": false,
    "hirise_loaded": false,
    "hirise_corridor_status": "disabled",
    "hirise_rejection_reason": "HiRISE local DTM integration is disabled via configuration (MARSPATH_USE_HIRISE_DEM=false).",
    "single_source_invariant_enforced": true,
    "native_resolution_meters": 200.0,
    "effective_resolution_meters": 200.0,
    "resolution_mode": "native",
    "aggregation_applied": false,
    "aggregation_factor": 1,
    "aggregation_method": null,
    "native_corridor_dimensions": [41, 55],
    "effective_corridor_dimensions": [41, 55]
  }
}
```
- **Single-Source Invariant (`single_source_invariant_enforced: true`):** MARSPath uses one elevation source and one consistent analysis grid per route request, never mosaicking partially overlapping DEMs or patching HiRISE `NoData` cells with MOLA–HRSC values.
- **Native vs. Effective Resolution & Aggregation Metadata:** Both `source_selection` and each route's `evidence_passport.source` and `evidence_passport.resolution_assessment` report `native_pixel_resolution_x_meters`, `native_pixel_resolution_y_meters`, `native_resolution_meters`, `effective_resolution_meters`, `resolution_mode` (`"native"` or `"aggregated_block"`), `aggregation_applied` (`bool`), `aggregation_factor` (`int >= 1`), and `aggregation_method` (`"mean_elevation_strict_nodata_max_subgrid_slope_roughness"` when aggregated).

#### Request Schema
```json
{
  "start": {
    "lon": 77.40,
    "lat": 18.39
  },
  "destination": {
    "lon": 77.44,
    "lat": 18.42
  },
  "crs_identifier": "IAU2000:49900",
  "mode": "balanced",
  "constraints": {
    "max_slope_deg": 20.0,
    "max_roughness": 0.85,
    "avoid_unobserved_terrain": true
  },
  "science_waypoints": [
    {
      "lon": 77.42,
      "lat": 18.405
    }
  ],
  "num_alternatives": 2
}
```

---

## 🪪 Terrain Evidence & Route Confidence Passport (`evidence_passport`)

Every `RouteAlternative` includes an `evidence_passport` (`RouteEvidencePassport`) that communicates the evidentiary basis of the route.

> **Scientific Integrity Requirement:** `quality_tier` is a deterministic measure of **terrain evidence quality** (provenance authenticity, observation completeness, and regional grid resolution). It is **NOT** a probability of rover survival, probability of mission success, or calibrated probability of mechanical failure.

### Quality Tier Definitions (`quality_tier`)
The backend applies the most conservative applicable tier:
1. **`unverified`**:
   - Assigned when the active terrain is synthetic (`Synthetic Jezero Crater Terrain Model`), loaded from an unverified local numerical raster (`valid_numeric_raster_unverified_source`), fails local SHA-256 integrity (`local_integrity_verified: false`), or lacks an authenticated NASA/ESA/USGS product identity.
2. **`low`**:
   - Assigned when an official planetary source is established, but material evidence degradation exists: incomplete route coverage (`route_data_coverage_fraction < 1.0`), material corridor nodata gaps (`corridor_data_coverage_fraction < 0.95`), route segments passing along a nodata boundary (`near_nodata_segment_count > 0`), missing CRS/vertical datum metadata, or coarse resolution (`> 500 m/px`).
3. **`moderate`**:
   - Assigned when an official planetary dataset is established with verified local file SHA-256 integrity, valid Mars CRS and vertical datum, and 100% route observation coverage away from nodata boundaries, **but** the full upstream archive checksum was not verified over all upstream source bytes (e.g. `official_endpoint_retrieved_checksum_unverified` from USGS `/vsicurl/` HTTP Range extraction) or minor non-adjacent corridor nodata exists (`0.95 <= corridor_data_coverage_fraction < 1.0`).
   - *Note:* Partial HTTP Range extractions from the official USGS endpoint can at most receive `moderate` and **never** receive `high`.
4. **`high`**:
   - Assigned **only** when `validation_status == "verified_source"`, the full upstream source checksum (`source_checksum_verified: true`) AND local file SHA-256 integrity (`local_integrity_verified: true`) are independently verified against the catalog manifest, an established Mars CRS and known vertical datum are present, `route_data_coverage_fraction == 1.0`, `corridor_data_coverage_fraction == 1.0`, `near_nodata_segment_count == 0`, and effective resolution meets the regional assessment contract (`<= 250 m/px`).
   - *Regional Scope vs. Obstacle Detection:* `high` means authoritative, verified, complete terrain evidence suitable for the declared **regional corridor assessment scope**. It does **not** mean wheel-scale obstacle clearance and does **not** imply flight-grade obstacle detection capability (`obstacle_detection_capable` is always `false`, even on ~1 m/px HiRISE DTMs, because sub-meter rocks, sharp boulders, and soil bearing capacity remain unresolved).

### Missing / Invalid Elevation & Incomplete Measurement Integrity (No Fabricated Zeros or Optimistic Complete Metrics)
- **3D vs. 2D GeoJSON `LineString` (`geometry.coordinates`):** When 100% of route vertices have valid elevation observations (`elevation_sample_coverage_fraction == 1.0`), `geometry.coordinates` emits 3D `[lon, lat, elevation_m]` tuples. If any route vertex lacks a valid elevation observation, `geometry.coordinates` emits a standards-compliant 2D RFC 7946 `LineString` (`[[lon, lat], ...]`) rather than fabricating `0.0` Z values.
- **Horizontal vs. 3D Surface Distance (`summary`):** `horizontal_distance_meters` always reports 2D great-circle distance on the Mars sphere. `surface_3d_distance_meters` is populated only when 100% of step elevation transitions are valid (`distance_measurement_basis == "complete_3d_surface"`), and is `null` when any elevation sample is missing (`distance_measurement_basis == "horizontal_2d_only_incomplete_elevation"`).
- **Complete vs. Partial Duration, Energy, and Hazard Exposure (`summary`):**
  - `estimated_duration_hours` is `null` if any step lacks valid elevation or slope (never substituting `0°` slope for an unobserved step); `observed_duration_hours_partial` reports the partial duration over observed steps only.
  - `energy_index` is `null` if any step elevation transition is incomplete (never treating missing transitions as zero energy); `observed_energy_index_partial` reports the partial energy index over valid elevation transitions.
  - `hazard_exposure_meters` is `null` if any step lacks valid elevation, slope, or roughness (never allowing missing data to understate hazard exposure); `observed_hazard_exposure_meters_min` reports the lower-bound hazard distance observed on valid steps alongside `unobserved_step_distance_meters`.
- **Incomplete Risk Disclosure (`summary.risk_category` & `summary.risk_assessment_status`):** Partial route observations (`is_complete_measurement == false`) are never classified as `"nominal"`. Instead, `risk_assessment_status` is `"incomplete_partial_observations"` (or `"unverified_no_valid_observations"`) and `risk_category` explicitly discloses incomplete data (`"unverified_incomplete_terrain_data"`, `"moderate_observed_incomplete_data"`, `"high_observed_incomplete_data"`, or `"unverified_no_valid_terrain_data"`).
- **Strict Mars Metadata Validation (`evidence_passport`):** Only explicitly supported Mars CRS identifiers, validated Mars sphere PROJ/WKT definitions ($R = 3{,}396{,}190\text{ m}$), and registered Mars vertical datums (`MOLA Areoid`, etc.) pass the `high`-tier metadata gate; arbitrary strings containing `"Mars"` or arbitrary non-empty datum labels are rejected.

### Route Coverage vs. Corridor Coverage (`coverage`)
These two measurements are computed independently from the active cropped raster and nodata masks and are never combined:
- **`route_data_coverage_fraction`** (`valid_route_sample_count / route_sample_count`): Proportion of discrete grid cells directly traversed by the route that contain valid numerical elevation, slope, and roughness observations. Also populates `RouteSummary.data_coverage_fraction`.
- **`corridor_data_coverage_fraction`** (`corridor_valid_cells / corridor_total_cells`): Proportion of all grid cells inside the cropped mission bounding box that contain valid elevation observations. A route that navigates cleanly around a nodata hole will have `route_data_coverage_fraction = 1.0` while `corridor_data_coverage_fraction < 1.0`.

### Response Example 1 (Official USGS Endpoint Extraction — `quality_tier: "moderate"`)
```json
{
  "mission_id": "mission_9f8e7d6c5b4a",
  "status": "success",
  "crs": {
    "identifier": "IAU2000:49900",
    "name": "Mars 2000 Sphere (IAU/IAG Working Group)",
    "ellipsoid_radius_meters": 3396190.0,
    "latitude_type": "planetocentric",
    "longitude_direction": "positive_east",
    "projection": "Geographic (Planetocentric Degrees)"
  },
  "pilot_region": "Jezero Crater, Mars",
  "data_mode": "real_official_endpoint_unverified_checksum",
  "provenance": {
    "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
    "official_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
    "official_source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
    "local_integrity_verified": true,
    "source_checksum_verified": false,
    "real_data_validation_status": "official_endpoint_retrieved_checksum_unverified"
  },
  "routes": [
    {
      "route_id": "route_primary_opt",
      "name": "Primary Route (Balanced)",
      "mode": "balanced",
      "score_rank": 1,
      "total_cost": 3184.25,
      "cost_breakdown": {
        "base_distance_cost": 2976.1,
        "slope_penalty": 142.8,
        "roughness_penalty": 65.35,
        "hazard_penalty": 0.0,
        "extra_penalty": 0.0
      },
      "summary": {
        "total_distance_meters": 2976.1,
        "elevation_gain_meters": 31.0,
        "elevation_loss_meters": 4.0,
        "min_elevation_meters": -2561.0,
        "max_elevation_meters": -2534.0,
        "max_slope_deg": 2.41,
        "average_slope_deg": 1.18,
        "average_roughness": 0.048,
        "data_coverage_fraction": 1.0,
        "estimated_duration_hours": 5.51,
        "motion_profile": "rover_slope_derated_0.15mps",
        "energy_index": 3.6,
        "science_score": 45.0,
        "hazard_exposure_meters": 0.0,
        "risk_category": "nominal"
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [77.4000, 18.3900, -2561.0],
          [77.4200, 18.4050, -2548.0],
          [77.4400, 18.4200, -2534.0]
        ]
      },
      "waypoints_visited": [],
      "science_targets_visited": ["poi_delta_front"],
      "science_targets_nearby": ["poi_kodiak_butte"],
      "warnings": [],
      "evidence_passport": {
        "schema_version": "1.0.0",
        "assessment_scope": "regional_terrain_evidence_assessment_not_mission_survival_probability",
        "scientific_disclaimer": "Terrain evidence quality measures the provenance, spatial resolution, and observation completeness of the underlying elevation data. It is NOT a probability of rover survival, probability of mission success, or calibrated probability of mechanical failure.",
        "quality_tier": "moderate",
        "tier_explanation": "Assigned 'moderate' tier for official dataset 'Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2' (Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2) with 100% valid route observation coverage and verified local file integrity because the Jezero Crater sub-window was extracted from the official USGS HTTPS endpoint with verified local SHA-256 integrity, but the full 11.38 GB upstream archive MD5 checksum remains unverified over all source bytes.",
        "quality_flags": [
          "source_checksum_unverified",
          "coarse_resolution_for_obstacle_detection"
        ],
        "source": {
          "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
          "product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
          "publisher": "USGS Astrogeology Science Center",
          "official_source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
          "data_mode": "real_official_endpoint_unverified_checksum",
          "validation_status": "official_endpoint_retrieved_checksum_unverified",
          "verification_method": "official_endpoint_retrieved_checksum_unverified",
          "is_synthetic": false,
          "local_integrity_verified": true,
          "source_checksum_verified": false,
          "file_sha256": "03845eeebd5965a288d8835c414632773d18ee3b392b38cf40d0467154c0f029",
          "pixel_resolution_x_meters": 189.79,
          "pixel_resolution_y_meters": 200.0,
          "nominal_resolution_meters": 200.0,
          "raster_width": 252,
          "raster_height": 178,
          "crs_identifier": "ESRI:104971",
          "vertical_datum": "Mars Areoid (MOLA 0m reference datum)",
          "spatial_coverage": {
            "min_lon": 77.148497,
            "min_lat": 18.100859,
            "max_lon": 77.998775,
            "max_lat": 18.701453
          },
          "source_limitations": [
            "Retrieved from official USGS/PDS HTTPS endpoint via GDAL /vsicurl/ HTTP Range extraction; local GeoTIFF SHA-256 integrity is verified.",
            "Full 11.38 GB upstream file MD5 checksum (e98092a06bea74d5ec9a704dcd1fe318) was NOT independently verified over all source bytes because only the Jezero Crater sub-window was streamed."
          ]
        },
        "coverage": {
          "route_sample_count": 3,
          "valid_route_sample_count": 3,
          "invalid_route_sample_count": 0,
          "route_data_coverage_fraction": 1.0,
          "corridor_total_cells": 2255,
          "corridor_valid_cells": 2255,
          "corridor_invalid_cells": 0,
          "corridor_data_coverage_fraction": 1.0,
          "near_nodata_segment_count": 0
        },
        "resolution_assessment": {
          "actual_x_meters_per_pixel": 189.79,
          "actual_y_meters_per_pixel": 200.0,
          "effective_resolution_meters": 200.0,
          "nominal_dataset_resolution_meters": 200.0,
          "suitability_classification": "regional_corridor_assessment_only",
          "obstacle_detection_capable": false,
          "limitation_statement": "Actual metric cell resolution at corridor latitude is 189.79 m (X) × 200.0 m (Y) per pixel (effective 200.0 m/px) (nominal equatorial resolution 200.0 m/px; zonal width compressed by cos(lat) at Jezero Crater). Supports regional corridor topographic screening only; does NOT resolve metre-scale boulders, local scarps, sand ripples, or flight-grade rover obstacles."
        },
        "known_limitations": [
          "Actual metric cell resolution at corridor latitude is 189.79 m (X) × 200.0 m (Y) per pixel (effective 200.0 m/px) (nominal equatorial resolution 200.0 m/px; zonal width compressed by cos(lat) at Jezero Crater). Supports regional corridor topographic screening only; does NOT resolve metre-scale boulders, local scarps, sand ripples, or flight-grade rover obstacles.",
          "Route cost weights, hazard penalties, and categorical risk levels are deterministic multi-criteria decision heuristics, not empirically calibrated probabilities of rover failure or mission survival.",
          "USGS warns of HRSC/MOLA blending seam inconsistencies and notes the global blended DEM (200 m/px nominal) was originally constructed for global thermal-modelling (THEMIS thermal inertia) rather than precision local surface navigation.",
          "Retrieved via HTTP range extraction from the official USGS endpoint; local GeoTIFF SHA-256 integrity is verified, but the full 11.38 GB upstream file MD5 checksum was not computed over all upstream source bytes."
        ],
        "segments": [
          {
            "segment_index": 0,
            "from_coord": {"lon": 77.4, "lat": 18.39},
            "to_coord": {"lon": 77.42, "lat": 18.405},
            "step_distance_meters": 1488.05,
            "elevation_start_m": -2561.0,
            "elevation_end_m": -2548.0,
            "delta_elevation_m": 13.0,
            "slope_deg": 1.12,
            "roughness": 0.044,
            "is_valid_data": true,
            "segment_cost": 1582.1,
            "quality_flags": [
              "source_checksum_unverified",
              "coarse_resolution_for_obstacle_detection"
            ]
          },
          {
            "segment_index": 1,
            "from_coord": {"lon": 77.42, "lat": 18.405},
            "to_coord": {"lon": 77.44, "lat": 18.42},
            "step_distance_meters": 1488.05,
            "elevation_start_m": -2548.0,
            "elevation_end_m": -2534.0,
            "delta_elevation_m": 14.0,
            "slope_deg": 1.24,
            "roughness": 0.052,
            "is_valid_data": true,
            "segment_cost": 1602.15,
            "quality_flags": [
              "source_checksum_unverified",
              "coarse_resolution_for_obstacle_detection"
            ]
          }
        ]
      }
    }
  ],
  "stats": {
    "algorithm_used": "A* (with admissible Euclidean heuristic)",
    "search_duration_seconds": 0.038,
    "nodes_expanded": 84,
    "grid_rows": 41,
    "grid_cols": 55,
    "cell_size_meters": 194.9
  },
  "limitations": [
    "Elevation resolution (200.0m/px) supports regional corridor terrain assessment, not metre-scale obstacle detection or flight-grade rover navigation.",
    "Route cost weights, hazard penalties, and categorical risk levels are deterministic multi-criteria decision heuristics, not empirically calibrated probabilities of failure.",
    "USGS warns of HRSC/MOLA blending seam inconsistencies and notes the global blended DEM (200m/px nominal) was originally generated for thermal-modelling (THEMIS thermal inertia) rather than precision local navigation.",
    "Retrieved via HTTP range extraction from official USGS endpoint; local GeoTIFF SHA-256 integrity is verified, but full 11.38 GB upstream file checksum was not computed over all upstream source bytes."
  ]
}
```

### Response Example 2 (Synthetic Terrain — `quality_tier: "unverified"`, Zero USGS Attribution)
```json
{
  "evidence_passport": {
    "schema_version": "1.0.0",
    "assessment_scope": "regional_terrain_evidence_assessment_not_mission_survival_probability",
    "scientific_disclaimer": "Terrain evidence quality measures the provenance, spatial resolution, and observation completeness of the underlying elevation data. It is NOT a probability of rover survival, probability of mission success, or calibrated probability of mechanical failure.",
    "quality_tier": "unverified",
    "tier_explanation": "Assigned 'unverified' tier because the route was computed on procedurally synthesized terrain ('Synthetic Jezero Crater Terrain Model') rather than verified spacecraft observation data.",
    "quality_flags": [
      "synthetic_terrain",
      "coarse_resolution_for_obstacle_detection"
    ],
    "source": {
      "dataset_name": "Synthetic Jezero Crater Terrain Model",
      "product_id": null,
      "publisher": "MARSPath Internal Synthetic Generator",
      "official_source_url": null,
      "data_mode": "synthetic_test_fixture",
      "validation_status": "synthetic_test_fixture",
      "verification_method": "deterministic_synthetic_procedural_generator",
      "is_synthetic": true,
      "local_integrity_verified": null,
      "source_checksum_verified": false,
      "file_sha256": null,
      "pixel_resolution_x_meters": 108.53,
      "pixel_resolution_y_meters": 118.55,
      "nominal_resolution_meters": 112.5,
      "raster_width": 375,
      "raster_height": 250,
      "crs_identifier": "IAU2000:49900",
      "vertical_datum": "Synthetic Reference Datum (Mars Sphere R=3,396,190m)"
    }
  }
}
```

---

## 🧪 Route Robustness Stress Testing (`robustness_config` & `robustness_assessment`)

MARSPath supports optional deterministic terrain perturbation stress testing via `robustness_config` on `POST /api/v1/routes/plan`.

> **Scientific Integrity Requirement:** The default USGS HRSC/MOLA blended DEM (`Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`) does **not** establish a validated per-pixel vertical error standard deviation or spatial correlation length in its provenance metadata. Therefore, MARSPath never invents DEM uncertainty parameters. When `robustness_config.enabled` is `true`, the caller must explicitly provide `vertical_sigma_m` ($> 0$) and `correlation_length_m` ($> 0$) as hypothetical stress-test assumptions; omitting either parameter returns `422 Unprocessable Entity`. When `robustness_config` is omitted or `enabled: false`, zero perturbation scenarios are generated and `robustness_assessment` is `null`.

### Optional Request Block (`robustness_config`)
```json
{
  "robustness_config": {
    "enabled": true,
    "vertical_sigma_m": 1.5,
    "correlation_length_m": 400.0,
    "scenario_count": 5,
    "seed": 42,
    "cost_regret_threshold_fraction": 0.05
  }
}
```
- `enabled` (`bool`, default `false`): Enables deterministic perturbation stress testing.
- `vertical_sigma_m` (`float > 0`, required when `enabled: true`): Assumed $1\sigma$ vertical elevation perturbation amplitude in meters over valid non-nodata cells.
- `correlation_length_m` (`float > 0`, required when `enabled: true`): Physical standard deviation $L$ (in meters) of the 2D separable Gaussian convolution filter kernel ($\sigma_x = L / \Delta x$, $\sigma_y = L / \Delta y$). Note that convolving white noise with a Gaussian kernel of standard deviation $L$ produces a theoretical infinite-plane Gaussian autocorrelation function $\rho(\Delta x, \Delta y) = \exp(-\Delta x^2 / (4L^2) - \Delta y^2 / (4L^2))$, corresponding to an autocorrelation Gaussian standard deviation of $\sqrt{2}L$ (`theoretical_autocorrelation_sigma_m`) and an $e$-folding distance ($\rho = e^{-1}$) of $2L$ (`theoretical_efolding_distance_m`), subject to finite-grid boundary reflection, nodata masking, and valid-cell sample normalization.
- `scenario_count` (`int`, bounded `3..20`, default `5`): Number of independent perturbation scenarios to evaluate.
- `seed` (`int`, default `42`): Master deterministic seed used to derive per-scenario seeds via `numpy.random.SeedSequence`.
- `cost_regret_threshold_fraction` (`float >= 0.0`, default `0.05`): Comparative reporting criterion for relative cost regret. **This is a comparative routing efficiency criterion, NOT a physical rover safety threshold.**

### Perturbation Model & Route Comparison Metrics
1. **Spatially Correlated Gaussian Elevation Perturbation (`spatially_correlated_gaussian_elevation_perturbation`):**
   - For each scenario $k$, a zero-mean unit-variance Gaussian field $W_k \sim \mathcal{N}(0, 1)$ is generated using `scenario_seed` (with nodata cells zeroed prior to convolution) and convolved with a 2D separable Gaussian filter kernel whose physical standard deviation is $L =$ `correlation_length_m` and pixel standard deviations are:
     $$\sigma_x = \frac{L}{\Delta x}, \quad \sigma_y = \frac{L}{\Delta y}$$
     where $\Delta x$ (`actual_dx_meters`) and $\Delta y$ (`actual_dy_meters`) are the actual physical cell dimensions in meters.
   - `uncertainty_assumptions` explicitly reports both the filter-kernel standard deviation (`correlation_length_m` $= L$) and the resulting theoretical infinite-plane field autocorrelation scales (`theoretical_autocorrelation_sigma_m` $= \sqrt{2}L$, `theoretical_efolding_distance_m` $= 2L$).
   - The filtered field is centered to zero mean and scaled to standard deviation `vertical_sigma_m` strictly over valid non-nodata cells, then added to a copy of the cropped elevation array while preserving the original nodata mask unchanged.
   - Slope (`compute_slope_degrees`), roughness (`compute_roughness_index`), and mode-specific traversability (`build_traversability_mask`) and `TerrainGridGraph` instances are recomputed from scratch for each scenario.
2. **Route-Specific Mode & Objective Preservation:**
   - Each baseline route alternative is evaluated under its own `RouteAlternative.mode` (`route_mode`) using `MODE_WEIGHTS[route_mode]` and `effective_max_slope = min(constraints.max_slope_deg, MODE_WEIGHTS[route_mode].slope_ceiling_deg)`. For example, `route_safety_backup` (`safety_first`) is evaluated under its `14.0°` slope ceiling and `SAFETY_FIRST` cost weights even when the top-level request mode is `balanced` (`20.0°`).
   - Route-specific required waypoints (`route.waypoints_visited`, reported via `required_waypoint_count`) are preserved during scenario re-optimization: `route_primary_waypoint_guided` re-optimizes leg-by-leg through all requested `science_waypoints`, and `route_science_primary` re-optimizes through its selected science target, while direct routes (`route_direct_baseline`) use the direct start-to-destination scenario optimum.
   - Scenario terrain-generation status (`terrain_generation_status`) is tracked separately from each route's scenario optimization status (`comparison_status`, `comparison_error_reason`). If one route-specific scenario search fails (e.g., `route_safety_backup` becomes unreachable under its stricter `14.0°` slope ceiling), other routes whose scenario searches succeeded retain their completed comparisons (`scenario_status = "completed_partial"`).
3. **Baseline Route Feasibility (`baseline_route_feasibility_fraction`):**
   - Checks whether every grid cell and step along the baseline route remains traversable under that route's own mode graph in the scenario, strictly enforcing the **diagonal corner-cutting constraint** (a diagonal move is infeasible if either orthogonal neighbor is untraversable).
   - When `evaluated_scenario_count == 0` for a route, `baseline_route_feasibility_fraction` and `baseline_route_retention_fraction` are returned as `null` (`None`), with `scenario_feasible_count = 0` and `scenario_infeasible_count = 0` for the completed-scenario aggregate, while preserving per-scenario statuses and `feasible` checks in `scenario_results`.
4. **Jaccard Route Overlap (`jaccard_overlap_fraction`, `mean_route_overlap_fraction`, `minimum_route_overlap_fraction`):**
   - Computed over discrete `(row, col)` grid-cell identities between the baseline route and its route-specific scenario-optimal path:
     $$\text{Jaccard Overlap} = \frac{|N_{\text{baseline}} \cap N_{\text{scenario}}|}{|N_{\text{baseline}} \cup N_{\text{scenario}}|}$$
5. **Relative Cost Regret (`cost_regret_fraction`, `mean_cost_regret_fraction`, `maximum_cost_regret_fraction`):**
   - Computed under the route's own mode cost model and waypoint objective whenever the baseline route is feasible in the scenario and the route's `scenario_optimal_cost` is valid:
     $$\text{cost\_regret\_fraction} = \frac{C_{\text{baseline in scenario}} - C_{\text{scenario optimal}}}{C_{\text{scenario optimal}}}$$
     Tiny negative values ($-10^{-9} \le \text{regret} < 0$) from floating-point rounding are clamped to `0.0`.
6. **Route Retention (`baseline_route_retention_fraction`):**
   - Fraction of **evaluated (completed) scenarios** (`evaluated_scenario_count`) for that route in which the baseline route remained traversable, had a valid scenario cost, and satisfied `cost_regret_fraction <= cost_regret_threshold_fraction` (`null` when `evaluated_scenario_count == 0`).
   - Failed scenarios (`failed_untraversable_endpoint`, `failed_unreachable`, `failed_computational_bound`, `failed_error`) are reported transparently in `scenario_results` and are never treated as positive stability evidence, nor are computational search failures conflated with physical traversability failures.
7. **Separation of Evidence Quality vs. Route Stability:**
   - `evidence_passport.quality_tier` measures the authenticity, completeness, and resolution of the source DEM.
   - `robustness_assessment` measures geometric and cost sensitivity of the route to hypothetical elevation perturbations. Neither metric is a calibrated probability of rover survival or mission success:
     > *"Results describe route stability under the specified hypothetical terrain perturbation model. They do not establish the actual probability of rover failure or mission success."*

---

## ⚠️ Error Responses

| Code | Cause | Sample Response |
|---|---|---|
| `422 Unprocessable Entity` | Coordinates out of pilot bounds | `{"error": "Coordinates (150.0000°E, 10.0000°N) are outside supported pilot bounds..."}` |
| `422 Unprocessable Entity` | Unsupported CRS (e.g. Earth EPSG:4326) | `{"error": "Coordinate Reference System 'EPSG:4326' is not supported. Mars requires planetary CRS."}` |
| `404 Not Found` | Unreachable destination (cliff/obstacle) | `{"error": "Unreachable destination: No traversable Martian corridor exists..."}` |
| `413 Payload Too Large` | Mission corridor exceeds cell budget | `{"error": "Computational bounds exceeded: corridor window requires 320,000 cells..."}` |
