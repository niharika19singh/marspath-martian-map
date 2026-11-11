#!/usr/bin/env bash
# ==============================================================================
# MARSPath — Build-Time DEM Provisioning & Validation Script (Phase 7.2)
# ==============================================================================
# Executed during the Render build phase (render.yaml buildCommand).
#
# 1. Configures PYTHONPATH so both `backend.app.*` and `app.*` imports resolve.
# 2. Sets MARSPATH_USE_REAL_DEM=true and forces MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false.
# 3. Defaults MARSPATH_DEM_PATH to backend/app/data/rasters/jezero_mola_hrsc_blended.tif.
# 4. Invokes idempotent provisioning via `backend.app.data.ingestion --provision-runtime`:
#    - Reuses existing valid DEM + provenance sidecar without re-downloading if already present.
#    - Otherwise extracts the 178x252 Jezero window (~90 KB) from official USGS endpoint or override source.
# 5. Strictly validates post-conditions:
#    - Both GeoTIFF and .provenance.json sidecar exist and are non-empty.
#    - Local SHA-256 integrity verification passes (matching sidecar local_file_sha256).
#    - Provenance satisfies Phase 7.1.1 readiness gate:
#        * is_synthetic is False
#        * local_integrity_verified == True
#        * real_data_validation_status in ('verified_source', 'official_endpoint_retrieved_checksum_unverified')
#        * evaluate_terrain_readiness status is "healthy"
# 6. Exits nonzero on any failure, missing artifact, corrupted checksum, or fallback substitution.
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
export MARSPATH_USE_REAL_DEM="true"
export MARSPATH_ALLOW_SYNTHETIC_FALLBACK="false"
export MARSPATH_DEM_PATH="${MARSPATH_DEM_PATH:-backend/app/data/rasters/jezero_mola_hrsc_blended.tif}"

# Select Python binary
PYTHON_BIN="python3"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

echo "[MARSPath Build Provisioning] =========================================="
echo "[MARSPath Build Provisioning] Starting build-time DEM provisioning"
echo "[MARSPath Build Provisioning] Repository root: ${REPO_ROOT}"
echo "[MARSPath Build Provisioning] Python binary: ${PYTHON_BIN}"
echo "[MARSPath Build Provisioning] Target DEM path: ${MARSPATH_DEM_PATH}"
echo "[MARSPath Build Provisioning] MARSPATH_USE_REAL_DEM=${MARSPATH_USE_REAL_DEM}"
echo "[MARSPath Build Provisioning] MARSPATH_ALLOW_SYNTHETIC_FALLBACK=${MARSPATH_ALLOW_SYNTHETIC_FALLBACK}"
echo "[MARSPath Build Provisioning] =========================================="

# Step 1: Execute idempotent ingestion / extraction
echo "[MARSPath Build Provisioning] Invoking runtime provisioning..."
"${PYTHON_BIN}" -m backend.app.data.ingestion --provision-runtime \
    --output "${MARSPATH_DEM_PATH}" \
    ${MARSPATH_INGESTION_SOURCE:+--source "${MARSPATH_INGESTION_SOURCE}"}

# Step 2: Strict post-condition verification via runtime verification gate
echo "[MARSPath Build Provisioning] Verifying build artifact integrity and readiness gate..."
"${PYTHON_BIN}" -m backend.app.data.ingestion --verify-runtime --output "${MARSPATH_DEM_PATH}"
echo "[MARSPath Build Provisioning] ALL BUILD-TIME DEM ARTIFACT INTEGRITY CHECKS PASSED."

echo "[MARSPath Build Provisioning] Build-time DEM artifact successfully provisioned and verified at ${MARSPATH_DEM_PATH}."
exit 0
