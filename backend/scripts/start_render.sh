#!/usr/bin/env bash
# ==============================================================================
# MARSPath — Render Runtime Startup & Strict Verification Script (Phase 7.2.1)
# ==============================================================================
# 1. Configures PYTHONPATH so both `backend.app.*` and `app.*` imports resolve.
# 2. Runs strict read-only runtime DEM verification:
#    - Verifies that pre-built DEM artifact and provenance sidecar created during
#      build time exist and pass SHA-256 local integrity and readiness checks.
#    - ZERO remote network calls, ZERO downloading, ZERO re-ingestion,
#      ZERO file mutations, ZERO sidecar regeneration.
# 3. Enforces fallback policy (`MARSPATH_ALLOW_SYNTHETIC_FALLBACK`, default `false`):
#    - If `false`: exits non-zero and aborts startup immediately if verification fails.
#    - If `true`: logs a warning and starts Uvicorn in degraded synthetic fallback mode.
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
export MARSPATH_ALLOW_SYNTHETIC_FALLBACK="${MARSPATH_ALLOW_SYNTHETIC_FALLBACK:-false}"
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

# Execute strict read-only runtime DEM verification
echo "[MARSPath Startup] Running strict runtime DEM verification..."
"${PYTHON_BIN}" -m backend.app.data.ingestion --verify-runtime --output "${MARSPATH_DEM_PATH}"

if [ "${MARSPATH_SKIP_UVICORN:-false}" = "true" ]; then
    echo "[MARSPath Startup] MARSPATH_SKIP_UVICORN=true; pre-launch verification finished."
    exit 0
fi

UVICORN_LOG_LEVEL=$(echo "${MARSPATH_LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')
echo "[MARSPath Startup] Starting Uvicorn server on 0.0.0.0:${PORT} (log-level: ${UVICORN_LOG_LEVEL})..."
exec "${PYTHON_BIN}" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}" --log-level "${UVICORN_LOG_LEVEL}"
