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
MARSPATH_CORS_ORIGINS=https://marspath.vercel.app,http://localhost:3000

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

## 2. Render Cloud Deployment & DEM Provisioning

Render deployment is configured via [`render.yaml`](../render.yaml). Because `.gitignore` excludes `backend/app/data/rasters/*.tif`, a freshly cloned container does **not** contain a local raster unless explicitly provisioned.

### Mode A: Default Out-of-the-Box Deployment (`render.yaml` default)
- `MARSPATH_USE_REAL_DEM="false"`
- `MARSPATH_DEM_PATH="backend/app/data/rasters/jezero_mola_hrsc_blended.tif"`
- `MARSPATH_ALLOW_SYNTHETIC_FALLBACK="true"`
- Operates deterministically in `synthetic_test_fixture` mode with zero external storage dependencies and transparent readiness reporting.

### Mode B: Provisioning the Official USGS 200m DEM on Render
To run against the USGS `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2` Jezero Crater extract on Render:

1. **Option 1 — Build-Time HTTP Range Ingestion (~90 KB extract):**
   Update `buildCommand` in Render to run the cloud-native `/vsicurl/` window extractor during build:
   ```bash
   pip install -r backend/requirements.txt && PYTHONPATH=. python -m backend.app.data.ingestion --output backend/app/data/rasters/jezero_mola_hrsc_blended.tif
   ```
   Then set in Render Environment Variables:
   ```bash
   MARSPATH_USE_REAL_DEM=true
   MARSPATH_DEM_PATH=backend/app/data/rasters/jezero_mola_hrsc_blended.tif
   MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false
   ```
   *(Note: Because build-time `/vsicurl/` streams only the Jezero sub-window rather than hashing the full 11.38 GB upstream archive, `/api/v1/data/status` will report `real_data_validation_status: "official_endpoint_retrieved_checksum_unverified"` and `data_mode: "real_official_endpoint_unverified_checksum"`.)*

2. **Option 2 — Render Persistent Disk with FullCheck-Verified Raster:**
   Mount a Render Persistent Disk (e.g. at `/var/data/marspath`), upload the checksum-verified DEM and its provenance sidecar, and set:
   ```bash
   MARSPATH_USE_REAL_DEM=true
   MARSPATH_DEM_PATH=/var/data/marspath/jezero_mola_hrsc_blended.tif
   MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false
   ```

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

## 4. Large Dataset Policy

**NEVER commit raw NASA GeoTIFFs, IMG files, or ISIS3 cubes to Git.**
- Large rasters and local extracts under `backend/app/data/rasters/` are excluded via `.gitignore`.
- Always use `python -m backend.app.data.ingestion` to reproducibly provision the Jezero Crater DEM window.
