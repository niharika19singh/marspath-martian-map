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
# 3. Enforces fallback policy (`MARSPATH_ALLOW_SYNTHETIC_FALLBACK`, default `false`):
#    - If `false`: exits non-zero and aborts startup if real terrain cannot be
#      provisioned and verified.
#    - If `true`: logs a warning on ingestion failure and continues startup in
#      degraded `synthetic_fallback` mode (`GET /health` returns HTTP 503 with
#      `status="degraded"`, `real_dem_loaded=false`, `dem_loaded=false`, and `blocking_errors`).
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

# Execute idempotent runtime DEM provisioning check / extraction
"${PYTHON_BIN}" -m backend.app.data.ingestion --provision-runtime \
    --output "${MARSPATH_DEM_PATH}" \
    ${MARSPATH_INGESTION_SOURCE:+--source "${MARSPATH_INGESTION_SOURCE}"}

if [ "${MARSPATH_SKIP_UVICORN:-false}" = "true" ] && [ "${MARSPATH_VERIFY_READINESS:-false}" != "true" ]; then
    echo "[MARSPath Startup] MARSPATH_SKIP_UVICORN=true; startup provisioning check finished."
    exit 0
fi

# Defense-in-depth runtime verification: when real DEM is required and fallback is forbidden,
# strictly verify the build artifact exists, passes SHA-256 integrity, and meets the readiness gate
# before launching Uvicorn.
if [ "${MARSPATH_USE_REAL_DEM}" = "true" ] && [ "${MARSPATH_ALLOW_SYNTHETIC_FALLBACK}" = "false" ]; then
    echo "[MARSPath Startup] Running defense-in-depth pre-launch DEM integrity and readiness verification..."
    "${PYTHON_BIN}" - << 'EOF'
import sys
import os
from pathlib import Path

dem_path_str = os.environ.get("MARSPATH_DEM_PATH", "backend/app/data/rasters/jezero_mola_hrsc_blended.tif")
dem_path = Path(dem_path_str)
sidecar_path = Path(f"{dem_path_str}.provenance.json")

if not dem_path.is_file():
    print(f"CRITICAL: Real DEM raster missing at '{dem_path}'. Aborting startup.", file=sys.stderr)
    sys.exit(1)

if not sidecar_path.is_file():
    print(f"CRITICAL: Provenance sidecar missing at '{sidecar_path}'. Aborting startup.", file=sys.stderr)
    sys.exit(1)

from backend.app.data.ingestion import verify_local_integrity
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.services.data_catalog import evaluate_terrain_readiness, ACCEPTABLE_REAL_VALIDATION_STATUSES

ok, reason, sidecar = verify_local_integrity(dem_path)
if not ok:
    print(f"CRITICAL: Local SHA-256 integrity verification failed: {reason}. Aborting startup.", file=sys.stderr)
    sys.exit(1)

try:
    prov = MOLAHRSCRasterProvider(dem_path=str(dem_path))
    raster = prov.get_dem_raster()
    provenance = prov.get_provenance()
    readiness = evaluate_terrain_readiness(
        is_synthetic=raster.metadata.is_synthetic,
        provenance=provenance,
        default_use_real_dem=True,
        dem_path=str(dem_path),
    )

    if readiness.get("status") != "healthy":
        print(f"CRITICAL: Pre-launch readiness gate failed: {readiness.get('blocking_errors')}. Aborting startup.", file=sys.stderr)
        sys.exit(1)

    if readiness.get("is_synthetic") is not False:
        print("CRITICAL: Pre-launch terrain is marked as synthetic. Aborting startup.", file=sys.stderr)
        sys.exit(1)

    if readiness.get("local_integrity_verified") is not True:
        print(f"CRITICAL: Pre-launch local_integrity_verified is not True: {readiness.get('local_integrity_verified')}. Aborting startup.", file=sys.stderr)
        sys.exit(1)

    val_status = readiness.get("real_data_validation_status")
    if val_status not in ACCEPTABLE_REAL_VALIDATION_STATUSES:
        print(f"CRITICAL: Pre-launch validation status '{val_status}' unacceptable. Aborting startup.", file=sys.stderr)
        sys.exit(1)

except Exception as exc:
    print(f"CRITICAL: Pre-launch DEM provider validation failed: {exc}. Aborting startup.", file=sys.stderr)
    sys.exit(1)

print(f"[MARSPath Startup] Real DEM artifact and provenance verified successfully ({dem_path}).")
EOF
fi

if [ "${MARSPATH_SKIP_UVICORN:-false}" = "true" ]; then
    echo "[MARSPath Startup] MARSPATH_SKIP_UVICORN=true; pre-launch verification finished."
    exit 0
fi

UVICORN_LOG_LEVEL=$(echo "${MARSPATH_LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')
echo "[MARSPath Startup] Starting Uvicorn server on 0.0.0.0:${PORT} (log-level: ${UVICORN_LOG_LEVEL})..."
exec "${PYTHON_BIN}" -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}" --log-level "${UVICORN_LOG_LEVEL}"
