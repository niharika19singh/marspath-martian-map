# MARSPath Deployment & Operations Guide

This guide describes how to configure, containerize, provision planetary DEM data, and deploy the MARSPath FastAPI backend on Render or Docker.

---

## 1. Environment Configuration

All environment variables use the prefix `MARSPATH_`. A template is provided in `.env.example`:

```bash
# Server Environment
MARSPATH_ENV=production
MARSPATH_HOST=0.0.0.0
MARSPATH_PORT=8000
MARSPATH_LOG_LEVEL=INFO

# Security & CORS
# In production (e.g. Render), only known hosted frontend origins are permitted (no localhost or loopback):
MARSPATH_CORS_ORIGINS=https://marspath.vercel.app
# Note: For local development, config defaults include localhost/127.0.0.1.
# If a hosted staging URL is created in the future, it must be explicitly appended here.

# Planetary Data & Provenance Policy
MARSPATH_DATA_DIR=backend/app/data
MARSPATH_DEM_PATH=backend/app/data/rasters/jezero_mola_hrsc_blended.tif
MARSPATH_USE_REAL_DEM=false
MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true

# Safety Ceilings
MARSPATH_MAX_GRID_CELLS=250000
MARSPATH_MAX_SEARCH_RADIUS_METERS=50000.0
MARSPATH_ROUTING_TIMEOUT_SECONDS=10.0
```

### Data Mode & Readiness Semantics
- **`MARSPATH_USE_REAL_DEM=false` (Default Synthetic Development Mode):**
  - Does not require any `.tif` file on disk.
  - `/health` reports `"dem_loaded": false`, `"real_dem_requested": false`, `"real_dem_loaded": false`, `"data_mode": "synthetic_test_fixture"`, `"real_data_validation_status": "synthetic_test_fixture"`.
  - `/api/v1/data/status` reports `"is_synthetic": true` and `"data_mode": "synthetic_test_fixture"`.
- **`MARSPATH_USE_REAL_DEM=true` with `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true`:**
  - Attempts to load `MARSPATH_DEM_PATH`. If the file is missing or invalid, falls back to synthetic terrain and explicitly reports `"dem_loaded": false`, `"real_dem_requested": true`, `"real_dem_loaded": false`, `"data_mode": "synthetic_fallback"`, `"real_data_validation_status": "incomplete_missing_genuine_dem"`, and records the failure in `blocking_errors`. It **never** silently claims real-data readiness when fallback occurs.
- **`MARSPATH_USE_REAL_DEM=true` with `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false` (Mandatory Real-DEM Mode):**
  - Requires a valid Mars DEM at `MARSPATH_DEM_PATH`. Raises `TerrainDataUnavailableError` (HTTP `503 Service Unavailable`) if the file is missing or invalid.
  - Do **not** enable mandatory real-DEM mode in cloud deployments until the raster has been provisioned via one of the workflows below.

---

## 2. Render Cloud Deployment & Idempotent Runtime DEM Provisioning

Render deployment is configured via [`render.yaml`](../render.yaml) and uses [`backend/scripts/start_render.sh`](../backend/scripts/start_render.sh) as its `startCommand`.

### Why Runtime Provisioning is Used on Render
- `.gitignore` excludes `backend/app/data/rasters/*.tif` so binary rasters are never committed to Git.
- On Render's standard web service tier, container filesystems are ephemeral across deployments and restarts, and persistent disks (when attached) are not mounted during `buildCommand`.
- The Jezero Crater sub-window (`77.15°E–78.00°E, 18.10°N–18.70°N`) from the USGS `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2` Cloud-Optimized GeoTIFF is only `178 × 252` pixels (~90 KB).
- Therefore, [`backend/scripts/start_render.sh`](../backend/scripts/start_render.sh) runs `python3 -m backend.app.data.ingestion --provision-runtime` (`provision_runtime_dem`) immediately before starting Uvicorn:
  1. **Idempotent Reuse:** Checks whether `MARSPATH_DEM_PATH` and its `.provenance.json` sidecar already exist, validates the local GeoTIFF SHA-256 against the sidecar, and verifies the raster metadata and elevation array. When valid local data is already present (e.g., on warm restarts or a mounted Persistent Disk), it skips remote re-ingestion.
  2. **HTTP Range Sub-Window Extraction:** When the raster is missing or fails integrity checks, it streams only the `178 × 252` Jezero Crater window via GDAL `/vsicurl/` HTTP Range requests from the official USGS Astrogeology S3 endpoint (`https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif`, with automatic fallback to `https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif`), never downloading the full 11.38 GB global file.
  3. **Post-Ingestion Verification & Cleanup:** Verifies the written GeoTIFF and sidecar SHA-256. If ingestion fails, any partial file is immediately deleted so failed ingestion can never masquerade as genuine data readiness.

### Configured Render Environment (`render.yaml`)
```yaml
startCommand: "bash backend/scripts/start_render.sh"
envVars:
  - key: MARSPATH_DEM_PATH
    value: "backend/app/data/rasters/jezero_mola_hrsc_blended.tif"
  - key: MARSPATH_USE_REAL_DEM
    value: "true"
  - key: MARSPATH_ALLOW_SYNTHETIC_FALLBACK
    value: "true"
```

- **Default Demo Resilience Policy (`MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true`):**
  - When runtime USGS provisioning succeeds, `/health` and `/api/v1/data/status` report:
    - `real_dem_requested: true`
    - `real_dem_loaded: true`
    - `dem_loaded: true`
    - `is_synthetic: false`
    - `data_mode: "real_official_endpoint_unverified_checksum"`
    - `real_data_validation_status: "official_endpoint_retrieved_checksum_unverified"`
    - `local_integrity_verified: true`
    - `source_checksum_verified: false`
  - If the upstream USGS endpoint is temporarily unreachable during cold start, the service stays online in `synthetic_fallback` mode and explicitly reports:
    - `real_dem_requested: true`
    - `real_dem_loaded: false`
    - `dem_loaded: false`
    - `is_synthetic: true`
    - `data_mode: "synthetic_fallback"`
    - `real_data_validation_status: "incomplete_missing_genuine_dem"`
    - `fallback_reason` and `blocking_errors` populated with the provisioning error.
- **Alternative Strict Policy (`MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false`):**
  - Set `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false` in Render Environment Variables to require real DEM provisioning on startup. If the USGS endpoint is unreachable and no valid local DEM exists, `start_render.sh` exits with code `1` and aborts container startup.
- **Optional Paid Persistent Disk:**
  - You may optionally mount a Render Persistent Disk (e.g. at `/var/data/marspath`) and set `MARSPATH_DEM_PATH=/var/data/marspath/jezero_mola_hrsc_blended.tif`. `start_render.sh` will provision the DEM onto the disk on first boot and reuse the SHA-256-verified file on all subsequent deploys and restarts.

---

## 3. Docker Deployment

```bash
# Build the Docker image
docker build -t marspath-backend -f backend/Dockerfile .

# Run in default synthetic mode
docker run -p 8000:8000 \
  -e MARSPATH_ENV=production \
  -e MARSPATH_USE_REAL_DEM=false \
  marspath-backend

# Or mount a local rasters directory with an ingested DEM
docker run -p 8000:8000 \
  -v $(pwd)/backend/app/data/rasters:/app/backend/app/data/rasters \
  -e MARSPATH_ENV=production \
  -e MARSPATH_USE_REAL_DEM=true \
  -e MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false \
  marspath-backend
```

---

## 4. Operational Smoke-Test Procedure

Run these curl commands to verify complete operational readiness after process or container startup:

### Step 1: Health & Scientific Terrain Readiness
```bash
curl -s http://localhost:8000/health | jq '{status, environment, data_readiness: {dem_loaded, data_mode, real_data_validation_status, local_integrity_verified, source_checksum_verified, crs, dem_resolution_meters}}'
```
**Expected Output (Real MOLA-HRSC Mode):**
```json
{
  "status": "healthy",
  "environment": "production",
  "data_readiness": {
    "dem_loaded": true,
    "data_mode": "real_official_endpoint_unverified_checksum",
    "real_data_validation_status": "official_endpoint_retrieved_checksum_unverified",
    "local_integrity_verified": true,
    "source_checksum_verified": false,
    "crs": "IAU2000:49900",
    "dem_resolution_meters": 200.0
  }
}
```

### Step 2: Layer Catalog
```bash
curl -s http://localhost:8000/api/v1/layers | jq '{count, layers: [.layers[].id]}'
```
**Expected Output:**
```json
{
  "count": 5,
  "layers": [
    "mars_elevation_jezero",
    "mars_slope_degrees",
    "mars_roughness_tri",
    "mars_trek_imagery_basemap",
    "mars_hirise_delta_dtm"
  ]
}
```

### Step 3: Planetary Data Status
```bash
curl -s http://localhost:8000/api/v1/data/status | jq '{active_pilot_region, is_synthetic, data_mode, crs: .crs.identifier, valid_data_fraction}'
```
**Expected Output:**
```json
{
  "active_pilot_region": "Jezero Crater, Mars",
  "is_synthetic": false,
  "data_mode": "real_official_endpoint_unverified_checksum",
  "crs": "IAU2000:49900",
  "valid_data_fraction": 1.0
}
```

### Step 4: Route Planning & Evidence Passport
```bash
curl -s -X POST http://localhost:8000/api/v1/routes/plan \
  -H "Content-Type: application/json" \
  -d '{
    "start": {"lon": 77.40, "lat": 18.39},
    "destination": {"lon": 77.44, "lat": 18.42},
    "crs_identifier": "IAU2000:49900",
    "mode": "balanced",
    "num_alternatives": 2
  }' | jq '{status, mission_id, routes_count: (.routes | length), primary_distance: .routes[0].summary.total_distance_meters, passport_tier: .routes[0].evidence_passport.quality_tier}'
```
**Expected Output:**
```json
{
  "status": "success",
  "mission_id": "mission_...",
  "routes_count": 2,
  "primary_distance": 2976.1,
  "passport_tier": "moderate"
}
```

### Step 5: CORS Preflight Verification
```bash
curl -s -I -X OPTIONS http://localhost:8000/api/v1/routes/plan \
  -H "Origin: https://marspath.vercel.app" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type"
```
**Expected Output:**
`HTTP/1.1 200 OK` with `access-control-allow-origin: https://marspath.vercel.app` and `access-control-allow-methods`.

---

## 5. Operational Safety Ceilings & Timeout Limits

MARSPath enforces strict computational boundaries to prevent runaway resource consumption:

| Limit Variable | Default Value | Enforcement Mechanism | Failure Response |
|---|---|---|---|
| `MARSPATH_MAX_GRID_CELLS` | `250000` | Checked during corridor cropping and block aggregation | `413 ComputationalBoundExceededError` |
| `MARSPATH_MAX_SEARCH_RADIUS_METERS` | `50000.0` (50 km) | Enforced on direct point-to-point and waypoint leg distance *before* corridor preparation | `413 ComputationalBoundExceededError` |
| `MARSPATH_ROUTING_TIMEOUT_SECONDS` | `10.0` | Active deadline checked periodically inside A* node expansions (`ASTAR_TIMEOUT_CHECK_INTERVAL_NODES = 200`) and across shared search iterations | `504 RoutingTimeoutError` |

### Timeout Scope & Lifecycle Enforcement
`MARSPATH_ROUTING_TIMEOUT_SECONDS` specifically bounds graph search (A* expansion across primary paths, multi-point waypoint legs, and alternative corridors).
- **Enforcement Interval:** Evaluated periodically every `ASTAR_TIMEOUT_CHECK_INTERVAL_NODES = 200` node expansions and before each leg / alternative search phase.
- **Scope Distinction:** It does NOT bound upstream terrain source selection, corridor cropping, or risk array calculation, which are bounded independently by spatial pilot bounds and the pre-corridor `MAX_SEARCH_RADIUS_METERS` guard.
- **Shared Deadline:** When multi-leg waypoints or alternative corridors are requested, a single shared deadline is passed across successive A* searches so cumulative graph traversal time cannot exceed the configured budget.

---

## 6. Common Startup Failure Modes & Recovery

1. **Missing `libexpat1` in Minimal Debian / Docker Slim Images:**
   - *Symptom:* `ImportError: libexpat.so.1: cannot open shared object file` on `import rasterio`.
   - *Resolution:* Added `libexpat1` to `apt-get install` in `backend/Dockerfile`.
2. **Missing SSL Certificates for GDAL `/vsicurl/` Range Extraction:**
   - *Symptom:* `[SSL: CERTIFICATE_VERIFY_FAILED]` when connecting to USGS S3 buckets.
   - *Resolution:* `backend/app/data/ingestion.py` automatically configures `CURL_CA_BUNDLE`, `GDAL_CA_BUNDLE`, and `SSL_CERT_FILE` from `certifi.where()` if present.
3. **Upstream USGS Endpoint Outage During Startup:**
   - *Symptom:* Remote range extraction fails or times out during container boot.
   - *Resilience Policy:* With `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true` (default), the server stays healthy, transitions to `synthetic_fallback` mode, transparently logs the error, and reports `is_synthetic: true`, `real_dem_loaded: false`, and `blocking_errors` on `/health`.
4. **Port Binding on Render:**
   - *Resolution:* `start_render.sh` dynamically binds Uvicorn to `0.0.0.0:${PORT}` where Render injects `PORT` (e.g. `PORT=10000`).

---

## 7. Large Dataset Policy

**NEVER commit raw NASA GeoTIFFs, IMG files, or ISIS3 cubes to Git.**
- Large rasters and local extracts under `backend/app/data/rasters/` are excluded via `.gitignore` and `.dockerignore`.
- Always use `python -m backend.app.data.ingestion` to reproducibly provision the Jezero Crater DEM window.

