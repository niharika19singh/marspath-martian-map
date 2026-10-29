# MARSPath API Integration Contract (for Kunal & Frontend)

This document specifies the complete REST API contract between Niharika's backend and Kunal's React frontend.

---

## 🪐 Planetary Coordinate Convention (CRITICAL)

Mars geodesy differs fundamentally from Earth mapping:

1. **Coordinate Reference System (CRS):** `IAU2000:49900` (Mars 2000 Sphere, volumetric mean radius $R = 3,396,190\text{ m}$).
2. **Longitude Convention:** **Positive East**, in range `[0°, 360°)` or `[-180°, +180°)`.
   - The backend accepts both and auto-normalizes to `[0°, 360°)`.
3. **Latitude Convention:** **Planetocentric latitude**, in range `[-90.0°, +90.0°]`.
4. **Active Pilot Region (Jezero Crater):**
   - Center: `~77.58° E, ~18.38° N`
   - East Longitude Bounds: `77.20° E` to `77.95° E`
   - Latitude Bounds: `18.15° N` to `18.65° N`
5. **Earth CRS Rejection:** Sending Earth CRS identifiers (such as `EPSG:4326` or `EPSG:3857`) will be rejected with HTTP `422 Unprocessable Entity`.

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
- **Description:** Lists all available numerical raster layers (elevation, slope, roughness, traversability) and visual basemaps for map rendering.

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
      "description": "Numerical surface elevation relative to the Mars areoid datum.",
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
        "projection": "Equirectangular Metric (Plate Carree centered at reference)"
      },
      "source_name": "Synthetic Jezero Pilot Model",
      "source_url": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
      "is_numerical": true,
      "is_available": true,
      "is_synthetic": true
    },
    {
      "id": "mars_trek_imagery_basemap",
      "name": "NASA Mars Trek Visible Basemap",
      "category": "imagery",
      "description": "Global orthorectified multi-mission visible mosaic for frontend display.",
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
        "projection": "Equirectangular Metric (Plate Carree centered at reference)"
      },
      "source_name": "NASA Solar System Treks (JPL)",
      "source_url": "https://trek.nasa.gov/mars/",
      "is_numerical": false,
      "is_available": true,
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
- **Description:** Optimizes traversable routes between two planetary coordinates with explainable scores, terrain breakdowns, and GeoJSON coordinates.

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
  "science_waypoints": [],
  "num_alternatives": 2
}
```

#### Optimization Modes:
- `safety_first`: Strict 14° slope limit, heavy roughness aversion, prioritizes minimum mechanical risk.
- `balanced`: 20° slope limit, balanced tradeoff between ground distance and slope penalty.
- `science_first`: 22° slope limit, routes through or near key geological POIs (delta front, Belva crater, Séítah formation).

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
    "projection": "Equirectangular Metric (Plate Carree centered at reference)"
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
      "route_id": "route_primary_opt",
      "name": "Primary Route (Balanced)",
      "mode": "balanced",
      "score_rank": 1,
      "total_cost": 3208.15,
      "cost_breakdown": {
        "base_distance_cost": 3014.0,
        "slope_penalty": 128.4,
        "roughness_penalty": 65.7,
        "hazard_penalty": 0.0
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
        "energy_index": 3.58,
        "science_score": 30.0
      },
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [77.4000, 18.3900, -2558.1],
          [77.4080, 18.3960, -2552.0],
          [77.4400, 18.4200, -2529.6]
        ]
      },
      "waypoints_visited": [],
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

---

## 🚀 Frontend Quickstart with Mock Fixture

If Kunal starts frontend work before running the backend locally:
- A complete mock response matching this schema is available at:  
  `backend/app/data/fixtures/sample_route_response.json`
- In React, Kunal can import this JSON directly into map state to test OpenLayers / Leaflet rendering.
