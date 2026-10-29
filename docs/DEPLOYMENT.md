# MARSPath Deployment & Operations Guide

This guide describes how to configure, containerize, and deploy the MARSPath FastAPI backend on Render or Docker.

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

# Planetary Data
MARSPATH_DATA_DIR=backend/app/data
MARSPATH_USE_REAL_DEM=false
MARSPATH_DEM_PATH=backend/app/data/rasters/jezero_mola_hrsc_blended.tif
MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true

# Safety Ceilings
MARSPATH_MAX_GRID_CELLS=250000
MARSPATH_MAX_SEARCH_RADIUS_METERS=50000.0
MARSPATH_ROUTING_TIMEOUT_SECONDS=10.0
```

---

## 2. Render Cloud Deployment

Render deployment is pre-configured via the Infrastructure-as-Code blueprint [`render.yaml`](../render.yaml):

1. **Connect GitHub:** Link the repository `niharika19singh/marspath-martian-map` in your Render dashboard.
2. **Create Web Service from Blueprint:**
   - Name: `marspath-backend`
   - Runtime: Python 3.11+
   - Build Command: `pip install -r backend/requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --app-dir backend`
   - Health Check Path: `/health`
3. **Environment Variables:** Set in Render dashboard or allow `render.yaml` defaults.
4. **Data Handling on Cloud:**
   - Render free tier does not accommodate committing multi-gigabyte rasters.
   - The backend runs by default in `synthetic_test_fixture` mode with zero external storage requirements.
   - For real DEM usage on Render, configure an S3/GCS download script in the build phase or mount a persistent disk at `MARSPATH_DATA_DIR`.

---

## 3. Docker Deployment

Build and run locally or on any container platform:

```bash
# Build the Docker image
docker build -t marspath-backend -f backend/Dockerfile .

# Run the container
docker run -p 8000:8000 \
  -e MARSPATH_ENV=production \
  -e MARSPATH_CORS_ORIGINS="*" \
  marspath-backend
```

Verify container operation:
```bash
curl http://localhost:8000/health
```

---

## 4. Large Dataset Policy

**NEVER commit raw NASA GeoTIFFs, IMG files, or VICAR labels to Git.**
- Large rasters are excluded via `.gitignore`.
- Provide download links or automated ingestion scripts rather than tracking multi-hundred-megabyte files in version control.
