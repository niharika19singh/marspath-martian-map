# MARSPath API Integration Contract (for Kunal & Frontend)

This document specifies the complete REST API contract between Niharika's backend and Kunal's React frontend.

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
   - East Longitude Bounds: `77.20° E` to `77.95° E`
   - Latitude Bounds: `18.15° N` to `18.65° N`
6. **Earth CRS Rejection:** Sending Earth CRS identifiers (such as `EPSG:4326` or `EPSG:3857`) is rejected with HTTP `422 Unprocessable Entity`.

---

## 📡 Endpoints Specification

### 1. Health & Scientific Readiness

- **Method:** `GET`
- **Path:** `/health`
- **Description:** Returns service operational status, version, and whether the scientific terrain engine is loaded.

#### Response Example (200 OK)
```json
{
  "status": "healthy",
  "service": "MARSPath — Mars Exploration Route Intelligence and Science Planner",
  "version": "0.1.0",
  "environment": "development",
  "planetary_target": "Mars",
  "pilot_region": "Jezero Crater",
  "data_readiness": {
    "dem_loaded": true,
    "data_mode": "synthetic_test_fixture",
    "is_synthetic": true,
    "crs": "IAU2000:49900"
  }
}
```

---

### 2. Available Map Layers

- **Method:** `GET`
- **Path:** `/api/v1/layers`
- **Description:** Lists all available layers. Clearly differentiates between directly renderable tile services and analysis-only matrices.

#### Response Example (200 OK)
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
      "description": "Numerical surface elevation relative to the Mars areoid datum. Internal analysis layer queried via /api/v1/routes/plan.",
      "units": "meters",
      "resolution_meters": 112.5,
      "bounds": {
        "min_lon": 77.2,
        "min_lat": 18.15,
        "max_lon": 77.95,
        "max_lat": 18.65
      },
      "crs": {
        "identifier": "IAU2000:49900",
        "name": "Mars 2000 Sphere (IAU/IAG Working Group)",
        "ellipsoid_radius_meters": 3396190.0,
        "latitude_type": "planetocentric",
        "longitude_direction": "positive_east",
        "projection": "Geographic (Planetocentric Degrees)"
      },
      "source_name": "Synthetic Jezero Pilot Model",
      "source_url": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
      "is_numerical": true,
      "is_available": true,
      "is_renderable": false,
      "render_url": null,
      "is_synthetic": true
    },
    {
      "id": "mars_trek_imagery_basemap",
      "name": "NASA Mars Trek Visible Basemap",
      "category": "imagery",
      "layer_type": "tile_service",
      "description": "Global orthorectified multi-mission visible mosaic for direct frontend display via XYZ/WMTS tile services.",
      "units": "reflectance RGB",
      "resolution_meters": 6.0,
      "bounds": {
        "min_lon": 0.0,
        "min_lat": -90.0,
        "max_lon": 360.0,
        "max_lat": 90.0
      },
      "crs": {
        "identifier": "IAU2000:49900",
        "name": "Mars 2000 Sphere (IAU/IAG Working Group)",
        "ellipsoid_radius_meters": 3396190.0,
        "latitude_type": "planetocentric",
        "longitude_direction": "positive_east",
        "projection": "Geographic (Planetocentric Degrees)"
      },
      "source_name": "NASA Solar System Treks (JPL)",
      "source_url": "https://trek.nasa.gov/mars/",
      "is_numerical": false,
      "is_available": true,
      "is_renderable": true,
      "render_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
      "is_synthetic": false
    }
  ]
}
```

---

### 3. Data Readiness & Catalog Status

- **Method:** `GET`
- **Path:** `/api/v1/data/status`
- **Description:** Detailed telemetry on active datasets, resolution, spatial coverage fraction, and verified NASA product catalog.

---

### 4. Route Planning

- **Method:** `POST`
- **Path:** `/api/v1/routes/plan`
- **Description:** Optimizes traversable routes between two planetary coordinates, evaluating local slope, roughness, and scientific waypoints with fully reconciled cost breakdowns.

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

#### Optimization Modes:
- `safety_first`: Strict 14° slope limit, heavy roughness aversion, prioritizes minimum mechanical risk.
- `balanced`: 20° slope limit, balanced tradeoff between ground distance and slope penalty.
- `science_first`: 22° slope limit; if no intermediate waypoints are given, autonomously evaluates candidate detours to sample high-priority science POIs (delta front, Belva crater, Séítah formation).

#### Response Example (200 OK)
```json
{
  "mission_id": "mission_a1b2c3d4e5f6",
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
  "data_mode": "synthetic_test_fixture",
  "provenance": {
    "mode": "synthetic_test_fixture",
    "pilot_region": "Jezero Crater, Mars",
    "nominal_resolution_meters": 112.5
  },
  "routes": [
    {
      "route_id": "route_primary_waypoint_guided",
      "name": "Primary Route via 1 Science Waypoint(s)",
      "mode": "balanced",
      "score_rank": 1,
      "total_cost": 3208.15,
      "cost_breakdown": {
        "base_distance_cost": 3014.0,
        "slope_penalty": 128.45,
        "roughness_penalty": 65.7,
        "hazard_penalty": 0.0,
        "extra_penalty": 0.0
      },
      "summary": {
        "total_distance_meters": 3014.0,
        "elevation_gain_meters": 28.5,
        "elevation_loss_meters": 8.2,
        "min_elevation_meters": -2558.1,
        "max_elevation_meters": -2529.6,
        "max_slope_deg": 1.39,
        "average_slope_deg": 0.94,
        "average_roughness": 0.022,
        "data_coverage_fraction": 1.0,
        "estimated_duration_hours": 5.58,
        "motion_profile": "rover_slope_derated_0.15mps",
        "energy_index": 3.58,
        "science_score": 45.0
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [77.4000, 18.3900, -2558.1],
          [77.4200, 18.4050, -2542.0],
          [77.4400, 18.4200, -2529.6]
        ]
      },
      "waypoints_visited": [
        { "lon": 77.42, "lat": 18.405 }
      ],
      "science_targets_visited": ["poi_delta_front"],
      "science_targets_nearby": ["poi_kodiak_butte"],
      "warnings": []
    }
  ],
  "stats": {
    "algorithm_used": "A* (with admissible Euclidean heuristic)",
    "search_duration_seconds": 0.038,
    "nodes_expanded": 84,
    "grid_rows": 82,
    "grid_cols": 76,
    "cell_size_meters": 112.5
  },
  "limitations": [
    "Operating on deterministic synthetic test fixture; routing results must NOT be used for flight operations."
  ]
}
```

---

## ⚠️ Error Responses

| Code | Cause | Sample Response |
|---|---|---|
| `422 Unprocessable Entity` | Coordinates out of pilot bounds | `{"error": "Coordinates (150.0000°E, 10.0000°N) are outside supported pilot bounds..."}` |
| `422 Unprocessable Entity` | Unsupported CRS (e.g. Earth EPSG:4326) | `{"error": "Coordinate Reference System 'EPSG:4326' is not supported. Mars requires planetary CRS."}` |
| `404 Not Found` | Unreachable destination (cliff/obstacle) | `{"error": "Unreachable destination: No traversable Martian corridor exists..."}` |
| `413 Payload Too Large` | Mission corridor exceeds cell budget | `{"error": "Computational bounds exceeded: corridor window requires 320,000 cells..."}` |
