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

# Step 2: Strict post-condition verification via Python validation gate
echo "[MARSPath Build Provisioning] Verifying build artifact integrity and readiness gate..."
"${PYTHON_BIN}" - << 'EOF'
import sys
import os
import json
import hashlib
from pathlib import Path

dem_path_str = os.environ.get("MARSPATH_DEM_PATH", "backend/app/data/rasters/jezero_mola_hrsc_blended.tif")
dem_path = Path(dem_path_str)
sidecar_path = Path(f"{dem_path_str}.provenance.json")

print(f"[Build Gate] Inspecting raster: {dem_path}")
print(f"[Build Gate] Inspecting sidecar: {sidecar_path}")

# Check 1: Existence of both files
if not dem_path.is_file():
    print(f"CRITICAL: Provisioned DEM raster not found at '{dem_path}'.", file=sys.stderr)
    sys.exit(1)

if not sidecar_path.is_file():
    print(f"CRITICAL: Provenance sidecar not found at '{sidecar_path}'.", file=sys.stderr)
    sys.exit(1)

# Check 2: File size non-zero
if dem_path.stat().st_size == 0:
    print(f"CRITICAL: Provisioned DEM raster is empty (0 bytes).", file=sys.stderr)
    sys.exit(1)

# Check 3: Read and parse sidecar
try:
    with open(sidecar_path, "r", encoding="utf-8") as f:
        sidecar = json.load(f)
except Exception as exc:
    print(f"CRITICAL: Failed to parse provenance sidecar JSON: {exc}", file=sys.stderr)
    sys.exit(1)

# Check 4: Local SHA-256 integrity check
expected_sha256 = sidecar.get("local_file_sha256")
if not expected_sha256 or len(expected_sha256) != 64:
    print(f"CRITICAL: Sidecar local_file_sha256 missing or malformed: {expected_sha256}", file=sys.stderr)
    sys.exit(1)

hasher = hashlib.sha256()
with open(dem_path, "rb") as f:
    for chunk in iter(lambda: f.read(65536), b""):
        hasher.update(chunk)
computed_sha256 = hasher.hexdigest()

if computed_sha256.lower() != expected_sha256.lower():
    print(
        f"CRITICAL: Local SHA-256 integrity mismatch! Computed={computed_sha256}, Expected={expected_sha256}",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"[Build Gate] Local SHA-256 integrity verified: {computed_sha256[:12]}...")

# Check 5: Run data catalog & provider integrity checks
try:
    from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
    from backend.app.services.data_catalog import (
        evaluate_terrain_readiness,
        ACCEPTABLE_REAL_VALIDATION_STATUSES,
    )

    provider = MOLAHRSCRasterProvider(dem_path=str(dem_path))
    raster = provider.get_dem_raster()
    provenance = provider.get_provenance()

    readiness = evaluate_terrain_readiness(
        is_synthetic=raster.metadata.is_synthetic,
        provenance=provenance,
        default_use_real_dem=True,
        dem_path=str(dem_path),
    )

    print(f"[Build Gate] Readiness status: {readiness.get('status')}")
    print(f"[Build Gate] Validation status: {readiness.get('real_data_validation_status')}")
    print(f"[Build Gate] Local integrity verified: {readiness.get('local_integrity_verified')}")
    print(f"[Build Gate] Is synthetic: {readiness.get('is_synthetic')}")

    if readiness.get("status") != "healthy":
        print(f"CRITICAL: Terrain readiness gate returned non-healthy status: {readiness}", file=sys.stderr)
        sys.exit(1)

    if readiness.get("is_synthetic") is not False:
        print("CRITICAL: Provisioned terrain is marked as synthetic!", file=sys.stderr)
        sys.exit(1)

    if readiness.get("local_integrity_verified") is not True:
        print(f"CRITICAL: local_integrity_verified is not True: {readiness.get('local_integrity_verified')}", file=sys.stderr)
        sys.exit(1)

    val_status = readiness.get("real_data_validation_status")
    if val_status not in ACCEPTABLE_REAL_VALIDATION_STATUSES:
        print(
            f"CRITICAL: Validation status '{val_status}' not in acceptable statuses: {sorted(ACCEPTABLE_REAL_VALIDATION_STATUSES)}",
            file=sys.stderr,
        )
        sys.exit(1)

    if readiness.get("blocking_errors"):
        print(f"CRITICAL: Readiness blocking errors present: {readiness.get('blocking_errors')}", file=sys.stderr)
        sys.exit(1)

except Exception as exc:
    print(f"CRITICAL: Provider validation or readiness check failed: {exc}", file=sys.stderr)
    sys.exit(1)

print("[Build Gate] ALL BUILD-TIME DEM ARTIFACT INTEGRITY CHECKS PASSED.")
EOF

echo "[MARSPath Build Provisioning] Build-time DEM artifact successfully provisioned and verified at ${MARSPATH_DEM_PATH}."
exit 0
