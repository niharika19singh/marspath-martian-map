FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY backend/ ./backend/
COPY docs/ ./docs/

# Set production environment configuration:
# Fail-closed policy: MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false ensures startup fails
# immediately if genuine DEM or provenance sidecar is missing or invalid.
ENV PYTHONPATH=/app:/app/backend \
    MARSPATH_ENV=production \
    MARSPATH_HOST=0.0.0.0 \
    MARSPATH_PORT=8000 \
    MARSPATH_USE_REAL_DEM=true \
    MARSPATH_DEM_PATH=backend/app/data/rasters/jezero_mola_hrsc_blended.tif \
    MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false

# Provision the official Jezero DEM artifact during image construction.
# This ensures the image contains the verified GeoTIFF and provenance sidecar
# before container runtime startup, matching the Render buildCommand specification.
RUN bash backend/scripts/provision_build_dem.sh

# Build verification: Ensure both GeoTIFF and provenance sidecar are present and non-empty
RUN test -s backend/app/data/rasters/jezero_mola_hrsc_blended.tif \
    && test -s backend/app/data/rasters/jezero_mola_hrsc_blended.tif.provenance.json

EXPOSE 8000

# Runtime startup: start_render.sh runs strict read-only runtime verification
# in <10 ms with ZERO network calls or downloading before launching Uvicorn.
CMD ["bash", "backend/scripts/start_render.sh"]

