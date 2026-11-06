FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY backend/ ./backend/
COPY docs/ ./docs/

ENV PYTHONPATH=/app:/app/backend
ENV MARSPATH_ENV=production
ENV MARSPATH_HOST=0.0.0.0
ENV MARSPATH_PORT=8000
ENV MARSPATH_USE_REAL_DEM=true
ENV MARSPATH_DEM_PATH=backend/app/data/rasters/jezero_mola_hrsc_blended.tif
ENV MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true

EXPOSE 8000

CMD ["bash", "backend/scripts/start_render.sh"]
