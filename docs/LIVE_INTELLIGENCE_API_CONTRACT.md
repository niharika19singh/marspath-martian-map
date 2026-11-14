# Live Mars Intelligence API Contract Specification

## Base URL
`/api/v1/intelligence`

All endpoints return standard `application/json`, adhere to the IAU2000 Mars coordinate standard (`IAU2000:49900`), and provide explicit provenance records and data freshness states.

---

## 1. System Health & Operational Status

### `GET /status`
Returns subsystem health, synchronized tracking counts, and active upstream provider status.

**Response `200 OK`:**
```json
{
  "subsystem": "live_mars_intelligence",
  "status": "OPERATIONAL",
  "active_orbiters_count": 5,
  "active_rovers_count": 2,
  "indexed_observations_count": 3,
  "last_sync_utc": "2026-11-14T09:00:00Z",
  "primary_coordinate_system": "IAU2000:49900",
  "data_state": "LATEST AVAILABLE",
  "sources": [
    { "source_name": "NASA/JPL NAIF SPICE", "status": "CONNECTED" },
    { "source_name": "NASA PDS Imaging Node", "status": "SYNCHRONIZED" },
    { "source_name": "ESA Planetary Science Archive", "status": "CONNECTED" }
  ]
}
```

---

## 2. Spacecraft Ephemerides & Ground Tracks

### `GET /spacecraft`
Lists all tracked Mars orbiters with orbital parameters and latest propagated positions.

**Response `200 OK`:**
```json
[
  {
    "spacecraft_id": "mro",
    "name": "Mars Reconnaissance Orbiter",
    "agency": "NASA / JPL",
    "mission": "Mars Exploration Program",
    "orbit_type": "Sun-Synchronous Polar",
    "semi_major_axis_km": 3656.0,
    "eccentricity": 0.0085,
    "inclination_deg": 93.0,
    "orbital_period_minutes": 111.8,
    "primary_instruments": ["HiRISE", "CTX", "CRISM", "MCS", "MARCI", "SHARAD"],
    "ephemeris_source": "NASA/JPL NAIF SPICE Kernel MRO_RECON_CORRECTED",
    "current_position": {
      "spacecraft_id": "mro",
      "epoch_utc": "2026-11-14T09:00:00Z",
      "lon": 11.80214,
      "lat": 78.53912,
      "altitude_km": 291.4,
      "velocity_kms": 3.42,
      "heading_deg": 194.2,
      "state": "PREDICTED",
      "coordinate_system": "IAU2000:49900"
    }
  }
]
```

### `GET /spacecraft/{spacecraft_id}/position`
Calculates real-time propagated position for the specified orbiter.

- **Path Parameters:**
  - `spacecraft_id` (string, required): `mro`, `ody`, `maven`, `mex`, `tgo`.
- **Query Parameters:**
  - `epoch_utc` (string, optional): ISO-8601 target timestamp (defaults to current server time).

### `GET /spacecraft/{spacecraft_id}/ground-track`
Generates a future ground track trajectory sampled at uniform time steps.

- **Query Parameters:**
  - `duration_minutes` (integer, default: 120, min: 10, max: 1440): Total propagation window.
  - `step_seconds` (integer, default: 60, min: 10, max: 300): Step sampling frequency.

**Response `200 OK`:**
```json
{
  "spacecraft_id": "mro",
  "spacecraft_name": "Mars Reconnaissance Orbiter",
  "start_epoch_utc": "2026-11-14T09:00:00Z",
  "duration_minutes": 120,
  "step_seconds": 60,
  "points": [
    { "epoch_utc": "2026-11-14T09:00:00Z", "lon": 11.802, "lat": 78.539, "altitude_km": 291.4, "velocity_kms": 3.42, "heading_deg": 194.2 }
  ],
  "provenance": {
    "source_name": "NASA/JPL",
    "dataset_id": "MRO_GROUND_TRACK_PREDICTED",
    "data_state": "PREDICTED"
  }
}
```

---

## 3. Surface Rover Telemetry

### `GET /rovers`
Returns telemetry records for all active Martian rovers.

### `GET /rovers/{rover_id}/position`
Returns the latest validated position for a specific rover (`perseverance` or `curiosity`).

**Response `200 OK`:**
```json
{
  "rover_id": "perseverance",
  "name": "Perseverance (Mars 2020)",
  "mission": "NASA Mars 2020 Exploration Mission",
  "landing_site": "Octavia E. Butler Landing, Jezero Crater",
  "sol": 2022,
  "earth_date_utc": "2026-11-06T13:46:52Z",
  "lon": 77.23322,
  "lat": 18.43559,
  "elevation_m": -1936.37,
  "total_odometry_meters": 45245.71,
  "last_drive_distance_meters": 22.06,
  "heading_deg": 284.5,
  "active_instruments": ["Mastcam-Z", "SuperCam", "PIXL", "SHERLOC", "MEDA", "RIMFAX", "MOXIE"],
  "state": "LATEST AVAILABLE",
  "uncertainty_meters": 0.15,
  "provenance": {
    "source_name": "NASA/JPL-Caltech Mars 2020 Operations",
    "dataset_id": "M20_WAYPOINTS_SOL2022",
    "data_state": "LATEST AVAILABLE",
    "citation_url": "https://mars.nasa.gov/mars2020/"
  }
}
```

### `GET /rovers/{rover_id}/traverse`
Retrieves drive legs and waypoints up to an optional Sol limit (`sol_limit`).

### `GET /rovers/{rover_id}/observations`
Retrieves surface science observations (e.g., Mastcam-Z panoramas, ChemCam LIBS spectra).

---

## 4. Planetary Observations & Timeline

### `GET /observations`
Returns cataloged orbital remote sensing observation footprints.

- **Query Parameters:**
  - `spacecraft_id` (string, optional): Filter by spacecraft (`mro`, `mex`).
  - `instrument` (string, optional): Filter by instrument (`HiRISE`, `CTX`, `HRSC`).
  - `min_lon`, `max_lon`, `min_lat`, `max_lat` (float, optional): Spatial bounding box filter.

### `GET /timeline`
Assembles an event stream ordered chronologically or reverse-chronologically across rovers and orbiters.

- **Query Parameters:**
  - `limit` (integer, default: 20, min: 1, max: 100).
  - `reverse` (boolean, default: true).

---

## 5. Operations & Synchronization

### `POST /sync`
Forces an operational re-synchronization with upstream mission catalogs.

**Request Body:**
```json
{
  "force_refresh": true
}
```

**Response `200 OK`:**
```json
{
  "success": true,
  "sync_timestamp_utc": "2026-11-14T09:05:00Z",
  "updated_sources": ["NASA_PDS_M20", "NASA_PDS_MSL", "NASA_JPL_HORIZONS", "ESA_PSA_MEX"],
  "new_observations_count": 3,
  "rover_updates_count": 2,
  "spacecraft_propagated_count": 5,
  "message": "Live Mars Intelligence synchronized successfully."
}
```
