#!/usr/bin/env bash
# ==============================================================================
# MARSPath — Render Runtime Startup & Idempotent DEM Provisioning Script
# ==============================================================================
# 1. Configures PYTHONPATH so both `backend.app.*` and `app.*` imports resolve.
# 2. When MARSPATH_USE_REAL_DEM=true, runs idempotent runtime DEM provisioning:
#    - Reuses the local Jezero DEM (`MARSPATH_DEM_PATH`) if both the raster and
#      its provenance sidecar exist, pass SHA-256 local integrity checks, and
#      validate as a genuine numeric Mars GeoTIFF over Jezero Crater.
#    - Otherwise extracts only the 178x252 Jezero Crater sub-window (~90 KB) from
#      the official USGS 200m global blended DEM endpoint via GDAL /vsicurl/ HTTP
#      Range reads (never downloading the full 11.38 GB archive).
# 3. Enforces fallback policy (`MARSPATH_ALLOW_SYNTHETIC_FALLBACK`):
#    - If `true`: logs a warning on ingestion failure and continues startup so
#      `/health` and `/api/v1/data/status` transparently report `synthetic_fallback`,
#      `real_dem_loaded=false`, `dem_loaded=false`, and `blocking_errors`.
#    - If `false`: exits non-zero and aborts startup if real terrain cannot be
#      provisioned and verified.
# 4. Starts Uvicorn on `0.0.0.0:$PORT`.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

if [ -d "${REPO_ROOT}/.deps" ]; then
    export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/backend:${REPO_ROOT}/.deps:${PYTHONPATH:-}"
else
    export PYTHONPATH="${REPO_ROOT}:${REPO_ROOT}/backend:${PYTHONPATH:-}"
fi

export MARSPATH_ENV="${MARSPATH_ENV:-production}"
export MARSPATH_USE_REAL_DEM="${MARSPATH_USE_REAL_DEM:-true}"
export MARSPATH_DEM_PATH="${MARSPATH_DEM_PATH:-backend/app/data/rasters/jezero_mola_hrsc_blended.tif}"
export MARSPATH_ALLOW_SYNTHETIC_FALLBACK="${MARSPATH_ALLOW_SYNTHETIC_FALLBACK:-true}"
export PORT="${PORT:-${MARSPATH_PORT:-8000}}"

# Select Python binary
PYTHON_BIN="python3"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

echo "[MARSPath Startup] Repository root: ${REPO_ROOT}"
echo "[MARSPath Startup] Environment: ${MARSPATH_ENV}"
echo "[MARSPath Startup] Port: ${PORT}"
echo "[MARSPath Startup] MARSPATH_USE_REAL_DEM=${MARSPATH_USE_REAL_DEM}"
echo "[MARSPath Startup] MARSPATH_DEM_PATH=${MARSPATH_DEM_PATH}"
echo "[MARSPath Startup] MARSPATH_ALLOW_SYNTHETIC_FALLBACK=${MARSPATH_ALLOW_SYNTHETIC_FALLBACK}"

# Execute idempotent runtime DEM provisioning check / extraction
"${PYTHON_BIN}" -m backend.app.data.ingestion --provision-runtime \
    --output "${MARSPATH_DEM_PATH}" \
    ${MARSPATH_INGESTION_SOURCE:+--source "${MARSPATH_INGESTION_SOURCE}"}

if [ "${MARSPATH_SKIP_UVICORN:-false}" = "true" ]; then
    echo "[MARSPath Startup] MARSPATH_SKIP_UVICORN=true; startup provisioning check finished."
    exit 0
fi

UVICORN_LOG_LEVEL=$(echo "${MARSPATH_LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')
echo "[MARSPath Startup] Starting Uvicorn server on 0.0.0.0:${PORT} (log-level: ${UVICORN_LOG_LEVEL})..."
exec "${PYTHON_BIN}" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}" --log-level "${UVICORN_LOG_LEVEL}"
