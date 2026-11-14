"""
Phase 7.2.1 — Trust Manifest & Immutable Runtime Hardening Regression Suite.

Covers all required test sections:
Section 2: Manifest Immutability Tests (5 tests)
- Environment variables cannot override manifest checksums.
- Official USGS upstream MD5 constant is unchanged.
- Official Jezero window array SHA-256 digest is unchanged.
- Arbitrary local raster cannot become verified_source via env vars.
- Official endpoint extract remains official_endpoint_retrieved_checksum_unverified.

Section 3: Build-Time DEM Provisioning Tests (8 tests)
- Build provisioning creates both GeoTIFF and .provenance.json sidecar.
- Missing or unreachable upstream source causes build provisioning failure.
- Build provisioning fails closed against synthetic fallback.
- Existing valid artifact is reused without re-ingesting (idempotency).
- Existing artifact with modified/tampered bytes fails integrity verification.
- Missing provenance sidecar fails verification.
- Unverified numerical terrain (valid_numeric_raster_unverified_source) is rejected.
- Official endpoint extract with local_integrity_verified=True remains acceptable.

Section 4: Runtime Verification-Only Tests (10 tests)
- Runtime startup (start_render.sh) reuses valid build artifact without remote requests.
- Runtime startup fails before launching Uvicorn when artifact is absent or invalid.
- Reachable mocked upstream source test: zero network requests during failed runtime startup.
- Runtime verification fails when DEM artifact is missing.
- Runtime verification fails when provenance sidecar is missing.
- Runtime verification fails when local SHA-256 integrity mismatch occurs.
- Runtime verification fails when provenance validation status is unacceptable.
- Synthetic development mode (MARSPATH_USE_REAL_DEM=false) succeeds and reports healthy.
- /health reports HTTP 200 for acceptable real terrain.
- /health and /api/v1/data/status preserve Phase 7.1.1 readiness classifications.
"""

import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from backend.app.core.config import get_settings
from backend.app.data.ingestion import (
    USGS_MOLA_HRSC_MD5,
    USGS_MOLA_HRSC_PRODUCT_ID,
    compute_file_md5,
    provision_runtime_dem,
    verify_local_integrity,
    verify_runtime_dem,
)
from backend.app.data.manifest import (
    DATA_CATALOG_MANIFEST,
    USGS_JEZERO_WINDOW_ARRAY_SHA256,
    _compute_raster_array_sha256,
    verify_manifest_provenance,
)
from backend.app.main import app
from backend.app.services.data_catalog import (
    ACCEPTABLE_REAL_VALIDATION_STATUSES,
    evaluate_terrain_readiness,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "backend" / "scripts" / "provision_build_dem.sh"
START_SCRIPT = REPO_ROOT / "backend" / "scripts" / "start_render.sh"
GENUINE_DEM_PATH = (
    REPO_ROOT
    / "backend"
    / "app"
    / "data"
    / "rasters"
    / "jezero_mola_hrsc_blended.tif"
)
GENUINE_SIDECAR_PATH = Path(f"{GENUINE_DEM_PATH}.provenance.json")


def _write_sample_geotiff(
    path: str,
    height: int = 90,
    width: int = 120,
    offset: float = -2565.0,
    min_lon: float = 77.0,
    max_lat: float = 18.80,
    res_lon: float = 0.01,
    res_lat: float = 0.008,
) -> tuple[str, str]:
    """Writes a valid numerical Mars 2000 GeoTIFF over Jezero Crater and returns (file_sha256, array_sha256)."""
    y_idx, x_idx = np.meshgrid(
        np.linspace(0.0, 1.0, height), np.linspace(0.0, 1.0, width), indexing="ij"
    )
    elev = (offset + 35.0 * x_idx + 20.0 * y_idx).astype(np.int16)
    transform = from_origin(min_lon, max_lat, res_lon, res_lat)
    crs_str = "+proj=longlat +R=3396190 +no_defs"

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="int16",
        crs=crs_str,
        transform=transform,
        nodata=-32768,
    ) as dst:
        dst.write(elev, 1)

    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    digest = sha256_hash.hexdigest()
    arr_sha = _compute_raster_array_sha256(path)
    return digest, arr_sha


def _create_source_geotiff_for_ingestion(path: str) -> tuple[str, str]:
    """Writes a source GeoTIFF covering Jezero Crater that can be clipped by ingestion.py."""
    return _write_sample_geotiff(
        path,
        height=180,
        width=240,
        offset=-2565.0,
        min_lon=76.8,
        max_lat=19.0,
        res_lon=0.006,
        res_lat=0.006,
    )


def _setup_fake_uvicorn(tmp_dir: str) -> tuple[str, str]:
    """Creates a fake python3 binary in bin/ that intercepts '-m uvicorn' without daemonizing."""
    bin_dir = os.path.join(tmp_dir, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    fake_python = os.path.join(bin_dir, "python3")
    marker_file = os.path.join(tmp_dir, "uvicorn_marker.txt")
    real_python = sys.executable

    with open(fake_python, "w", encoding="utf-8") as f:
        f.write(
            "#!/usr/bin/env bash\n"
            'if [[ "$*" == *"-m uvicorn"* ]]; then\n'
            f'    echo "uvicorn_started" > "{marker_file}"\n'
            "    exit 0\n"
            "fi\n"
            f'exec "{real_python}" "$@"\n'
        )
    os.chmod(fake_python, 0o755)
    return bin_dir, marker_file


def _build_test_env(
    tmp_dir: str,
    dem_path: str,
    source_path: str | None = None,
    allow_fallback: str = "false",
    extra_bin_dir: str | None = None,
    use_real_dem: str = "true",
) -> dict[str, str]:
    """Constructs environment dict with correct PYTHONPATH and isolation."""
    env = os.environ.copy()
    if extra_bin_dir:
        env["PATH"] = f"{extra_bin_dir}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}:{REPO_ROOT}/backend:{REPO_ROOT}/.deps:{env.get('PYTHONPATH', '')}"
    )
    env["MARSPATH_ENV"] = "production"
    env["MARSPATH_USE_REAL_DEM"] = use_real_dem
    env["MARSPATH_DEM_PATH"] = dem_path
    env["MARSPATH_ALLOW_SYNTHETIC_FALLBACK"] = allow_fallback
    if source_path:
        env["MARSPATH_INGESTION_SOURCE"] = source_path
    else:
        env.pop("MARSPATH_INGESTION_SOURCE", None)
    return env


def _copy_genuine_jezero_dem(target_path: str | Path) -> tuple[str, str]:
    """Copies the genuine Jezero DEM raster and sidecar to target_path."""
    t_path = Path(target_path)
    t_path.parent.mkdir(parents=True, exist_ok=True)
    if not GENUINE_DEM_PATH.exists() or not GENUINE_SIDECAR_PATH.exists():
        provision_runtime_dem(
            dem_path=GENUINE_DEM_PATH,
            use_real_dem=True,
            allow_fallback=False,
        )
    shutil.copy(GENUINE_DEM_PATH, t_path)
    shutil.copy(GENUINE_SIDECAR_PATH, f"{t_path}.provenance.json")

    with open(f"{t_path}.provenance.json", encoding="utf-8") as f:
        sidecar = json.load(f)
    return sidecar["local_file_sha256"], sidecar["extracted_array_sha256"]


# ==============================================================================
# SECTION 2: AUTHORITATIVE MANIFEST IMMUTABILITY TESTS (5 tests)
# ==============================================================================


def test_manifest_env_vars_cannot_override_checksums(monkeypatch):
    """Test 2.1: Setting MARSPATH_MANIFEST_* env vars cannot override catalog checksums."""
    monkeypatch.setenv(
        "MARSPATH_MANIFEST_SHA256_OVERRIDE", "deadbeef111122223333444455556666"
    )
    monkeypatch.setenv(
        "MARSPATH_MANIFEST_UPSTREAM_MD5_OVERRIDE", "deadbeefdeadbeefdeadbeefdeadbeef"
    )
    monkeypatch.setenv(
        "MARSPATH_MANIFEST_JEZERO_WINDOW_ARRAY_SHA256",
        "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
    )

    # Re-evaluate or inspect catalog item
    usgs_item = next(
        p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
    )
    assert (
        usgs_item["upstream_md5"] == "e98092a06bea74d5ec9a704dcd1fe318"
    ), "upstream_md5 must remain authoritative regardless of env vars"
    assert (
        USGS_JEZERO_WINDOW_ARRAY_SHA256
        == "e9a823c7ee00f68e6b5985425b90e574e30638f6223d07010bc75f98214f3074"
    ), "USGS_JEZERO_WINDOW_ARRAY_SHA256 must remain constant"
    assert (
        usgs_item.get("jezero_window_array_sha256")
        == "e9a823c7ee00f68e6b5985425b90e574e30638f6223d07010bc75f98214f3074"
    )


def test_manifest_official_usgs_upstream_md5_constant():
    """Test 2.2: Official USGS upstream MD5 constant is strictly preserved."""
    usgs_item = next(
        p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
    )
    assert usgs_item["upstream_md5"] == "e98092a06bea74d5ec9a704dcd1fe318"
    assert USGS_MOLA_HRSC_MD5 == "e98092a06bea74d5ec9a704dcd1fe318"


def test_manifest_official_jezero_window_array_sha256_constant():
    """Test 2.3: Official Jezero Crater window array SHA-256 digest is strictly preserved."""
    assert (
        USGS_JEZERO_WINDOW_ARRAY_SHA256
        == "e9a823c7ee00f68e6b5985425b90e574e30638f6223d07010bc75f98214f3074"
    )


def test_arbitrary_local_raster_cannot_become_verified_source_via_env(monkeypatch):
    """Test 2.4: An arbitrary local raster cannot become verified_source via env vars."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dummy_tif = os.path.join(tmp_dir, "fake_mars_dem.tif")
        digest, _ = _write_sample_geotiff(dummy_tif, height=90, width=120)

        # Set malicious env vars attempting to override manifest
        monkeypatch.setenv("MARSPATH_MANIFEST_SHA256_OVERRIDE", digest)
        monkeypatch.setenv(
            "MARSPATH_MANIFEST_UPSTREAM_MD5_OVERRIDE",
            "fake_md5_string_1234567890abcdef",
        )
        monkeypatch.setenv(
            "MARSPATH_MANIFEST_JEZERO_WINDOW_ARRAY_SHA256",
            "fake_arr_sha256_1234567890abcdef",
        )

        # Sidecar claiming to be verified
        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "validation_status": "verified_source",
            "source_checksum_verified": True,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
        }
        with open(f"{dummy_tif}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        is_verified, method, matched_item = verify_manifest_provenance(
            file_sha256=digest,
            metadata_tags={"PRODUCT_ID": USGS_MOLA_HRSC_PRODUCT_ID},
            file_path=dummy_tif,
        )
        assert is_verified is False
        assert method == "unverified_sidecar_source_not_authenticated"
        assert matched_item is None


def test_official_endpoint_extract_remains_unverified_checksum_without_full_source():
    """Test 2.5: Path 2b extract returns honest unverified status when full source is absent."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_copy = os.path.join(tmp_dir, "jezero_test_extract.tif")
        digest, arr_sha = _copy_genuine_jezero_dem(dem_copy)

        is_verified, method, matched = verify_manifest_provenance(
            file_sha256=digest,
            metadata_tags={},
            file_path=dem_copy,
        )
        # Never claims full source checksum verified without the full 11.38 GB archive
        assert is_verified is False
        assert method == "official_endpoint_retrieved_checksum_unverified"
        assert matched is not None
        assert matched["id"] == USGS_MOLA_HRSC_PRODUCT_ID


# ==============================================================================
# SECTION 3: BUILD-TIME DEM PROVISIONING TESTS (8 tests)
# ==============================================================================


def test_01_build_provisioning_creates_geotiff_and_provenance_sidecar(monkeypatch):
    """Test 3.1: Build provisioning creates both GeoTIFF and .provenance.json sidecar."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        source_tif = os.path.join(tmp_dir, "source_jezero_raw.tif")
        _create_source_geotiff_for_ingestion(source_tif)
        src_md5 = compute_file_md5(source_tif)

        out_dem = os.path.join(tmp_dir, "built_jezero_dem.tif")
        sidecar = Path(f"{out_dem}.provenance.json")

        # Isolated in-memory manifest fixture for unit test execution
        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        monkeypatch.setitem(usgs_entry, "upstream_md5", src_md5)

        record = provision_runtime_dem(
            dem_path=out_dem,
            use_real_dem=True,
            allow_fallback=False,
            source_url_or_path=source_tif,
            force=True,
        )

        assert record["status"] == "provisioned_from_source"
        assert os.path.exists(out_dem), "Provisioned DEM raster was not created"
        assert os.path.getsize(out_dem) > 0, "Provisioned DEM raster is empty"
        assert sidecar.exists(), "Provenance sidecar was not created"

        with open(sidecar, encoding="utf-8") as f:
            sidecar_data = json.load(f)

        assert sidecar_data["local_integrity_verified"] is True
        assert sidecar_data["validation_status"] in ACCEPTABLE_REAL_VALIDATION_STATUSES

        # Verify SHA-256 matches actual file
        hasher = hashlib.sha256()
        with open(out_dem, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        assert hasher.hexdigest().lower() == sidecar_data["local_file_sha256"].lower()

        # Strict runtime verification must pass
        v_res = verify_runtime_dem(
            dem_path=out_dem, use_real_dem=True, allow_fallback=False
        )
        assert v_res["status"] == "verified_valid"


def test_02_missing_or_unreachable_source_causes_build_provisioning_failure():
    """Test 3.2: Missing or unreachable upstream source causes build provisioning to fail nonzero."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "failed_build.tif")
        bad_source = os.path.join(tmp_dir, "nonexistent_source_path.tif")

        env = _build_test_env(tmp_dir, out_dem, source_path=bad_source)

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert (
            proc.returncode != 0
        ), "Build script must exit nonzero on unreachable source"
        assert not os.path.exists(out_dem), "Partial DEM must be cleaned up on failure"
        assert not os.path.exists(
            f"{out_dem}.provenance.json"
        ), "Partial sidecar must not exist"


def test_03_build_provisioning_fails_closed_against_synthetic_fallback():
    """Test 3.3: Build provisioning fails closed: synthetic fallback cannot satisfy build."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "synthetic_forbidden.tif")
        bad_source = os.path.join(tmp_dir, "unreachable_source.tif")

        env = _build_test_env(
            tmp_dir, out_dem, source_path=bad_source, allow_fallback="true"
        )

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert (
            proc.returncode != 0
        ), "Build provisioning must fail closed even if env had fallback=true"
        assert not os.path.exists(
            out_dem
        ), "Target raster must not be populated with synthetic data"


def test_04_existing_valid_artifact_reused_without_reingesting():
    """Test 3.4: Existing valid artifact is reused without re-ingesting (idempotency)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "existing_valid.tif")
        _copy_genuine_jezero_dem(out_dem)

        # Point source to an unreachable path to prove no download/ingestion is attempted
        unreachable_source = os.path.join(tmp_dir, "should_never_be_touched.tif")
        env = _build_test_env(tmp_dir, out_dem, source_path=unreachable_source)

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert (
            proc.returncode == 0
        ), f"Expected idempotency success:\n{proc.stdout}\n{proc.stderr}"
        assert (
            "already_provisioned_valid" in proc.stdout
            or "Skipping re-ingestion" in proc.stderr
        )
        assert (
            "ALL BUILD-TIME DEM ARTIFACT INTEGRITY CHECKS PASSED" in proc.stdout
        )


def test_05_tampered_artifact_bytes_fails_integrity_verification():
    """Test 3.5: Existing artifact with modified or tampered bytes fails integrity verification."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "tampered.tif")
        digest, _ = _write_sample_geotiff(out_dem, height=90, width=120)

        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "validation_status": "verified_source",
            "source_checksum_verified": True,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
        }
        with open(f"{out_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        # Tamper with file
        with open(out_dem, "ab") as f:
            f.write(b"\x00\xff\xfe\xfdGARBAGE_BYTES")

        # 1. verify_local_integrity returns False
        ok, reason, sidecar = verify_local_integrity(out_dem)
        assert not ok
        assert "sha256_mismatch" in reason

        # 2. Build script fails when tampered artifact is present without upstream source
        bad_source = os.path.join(tmp_dir, "nonexistent.tif")
        env = _build_test_env(tmp_dir, out_dem, source_path=bad_source)
        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0


def test_06_missing_provenance_sidecar_fails_verification():
    """Test 3.6: Missing provenance sidecar fails verification."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "no_sidecar.tif")
        _write_sample_geotiff(out_dem, height=90, width=120)

        ok, reason, sidecar = verify_local_integrity(out_dem)
        assert not ok
        assert reason == "provenance_sidecar_missing"

        # Build script fails
        bad_source = os.path.join(tmp_dir, "nonexistent.tif")
        env = _build_test_env(tmp_dir, out_dem, source_path=bad_source)
        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0


def test_07_unverified_numerical_terrain_rejected_as_degraded():
    """Test 3.7: Unverified numerical terrain is rejected as degraded."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "unverified_numeric.tif")
        digest, _ = _write_sample_geotiff(out_dem, height=90, width=120)

        sidecar_data = {
            "source_product_id": "unverified_model",
            "validation_status": "valid_numeric_raster_unverified_source",
            "source_checksum_verified": False,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
        }
        with open(f"{out_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        # 1. evaluate_terrain_readiness marks it degraded
        readiness = evaluate_terrain_readiness(
            is_synthetic=False,
            provenance={
                "real_dem_requested": True,
                "real_dem_loaded": True,
                "data_mode": "real",
                "real_data_validation_status": "valid_numeric_raster_unverified_source",
                "local_integrity_verified": True,
                "source_checksum_verified": False,
            },
            default_use_real_dem=True,
            dem_path=out_dem,
        )
        assert readiness["status"] == "degraded"
        assert readiness["http_status_code"] == 503
        assert len(readiness["blocking_errors"]) > 0

        # 2. Build script fails because readiness gate rejects unverified source status
        bad_source = os.path.join(tmp_dir, "nonexistent.tif")
        env = _build_test_env(tmp_dir, out_dem, source_path=bad_source)
        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode != 0


def test_08_official_endpoint_extract_unverified_checksum_remains_acceptable():
    """Test 3.8: Official endpoint extract with local_integrity_verified=True remains acceptable."""
    readiness = evaluate_terrain_readiness(
        is_synthetic=False,
        provenance={
            "real_dem_requested": True,
            "real_dem_loaded": True,
            "data_mode": "real_official_endpoint_unverified_checksum",
            "real_data_validation_status": "official_endpoint_retrieved_checksum_unverified",
            "local_integrity_verified": True,
            "source_checksum_verified": False,
            "provenance_verification_method": "official_endpoint_vsicurl_range_extract",
        },
        default_use_real_dem=True,
        dem_path="backend/app/data/rasters/jezero_mola_hrsc_blended.tif",
    )
    assert readiness["status"] == "healthy"
    assert readiness["http_status_code"] == 200
    assert readiness["dem_loaded"] is True
    assert readiness["real_dem_loaded"] is True
    assert readiness["is_synthetic"] is False
    assert readiness["local_integrity_verified"] is True
    assert readiness["source_checksum_verified"] is False
    assert readiness["blocking_errors"] == []


# ==============================================================================
# SECTION 4: RUNTIME VERIFICATION-ONLY TESTS (10 tests)
# ==============================================================================


def test_09_runtime_startup_reuses_valid_build_artifact_without_remote_requests():
    """Test 4.1: Runtime startup reuses valid build artifact without remote requests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "runtime_reused.tif")
        _copy_genuine_jezero_dem(out_dem)

        # Point source to unreachable URL to ensure no network call is made
        env = _build_test_env(
            tmp_dir,
            out_dem,
            source_path="http://127.0.0.1:9/unreachable.tif",
        )
        env["MARSPATH_SKIP_UVICORN"] = "true"

        proc = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert (
            proc.returncode == 0
        ), f"Startup script failed:\n{proc.stdout}\n{proc.stderr}"
        assert "Running strict runtime DEM verification" in proc.stdout
        assert "Runtime verification status: verified_valid" in proc.stdout
        assert "MARSPATH_SKIP_UVICORN=true; pre-launch verification finished." in proc.stdout


def test_10_runtime_startup_fails_before_uvicorn_when_artifact_absent_or_invalid():
    """Test 4.2: Runtime startup fails before Uvicorn when artifact is absent or invalid."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        bin_dir, uvicorn_marker = _setup_fake_uvicorn(tmp_dir)

        # Case A: Missing artifact
        missing_dem = os.path.join(tmp_dir, "missing.tif")
        env_a = _build_test_env(
            tmp_dir,
            missing_dem,
            source_path=os.path.join(tmp_dir, "no_source.tif"),
            extra_bin_dir=bin_dir,
        )
        proc_a = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env_a,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_a.returncode != 0
        assert not os.path.exists(
            uvicorn_marker
        ), "Uvicorn must not be launched when artifact is missing"

        # Case B: Tampered bytes
        tampered_dem = os.path.join(tmp_dir, "tampered_runtime.tif")
        digest, _ = _write_sample_geotiff(tampered_dem, height=90, width=120)
        with open(f"{tampered_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
                    "validation_status": "verified_source",
                    "local_integrity_verified": True,
                    "local_file_sha256": digest,
                },
                f,
            )
        with open(tampered_dem, "ab") as f:
            f.write(b"CORRUPTION_BYTES")

        env_b = _build_test_env(
            tmp_dir,
            tampered_dem,
            source_path=os.path.join(tmp_dir, "no_source.tif"),
            extra_bin_dir=bin_dir,
        )
        proc_b = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env_b,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_b.returncode != 0
        assert not os.path.exists(
            uvicorn_marker
        ), "Uvicorn must not be launched when artifact is corrupted"

        # Case C: Unverified source status
        unverified_dem = os.path.join(tmp_dir, "unverified_runtime.tif")
        u_digest, _ = _write_sample_geotiff(unverified_dem, height=90, width=120)
        with open(f"{unverified_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_product_id": "unverified",
                    "validation_status": "valid_numeric_raster_unverified_source",
                    "local_integrity_verified": True,
                    "local_file_sha256": u_digest,
                },
                f,
            )

        env_c = _build_test_env(
            tmp_dir,
            unverified_dem,
            source_path=os.path.join(tmp_dir, "no_source.tif"),
            extra_bin_dir=bin_dir,
        )
        proc_c = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env_c,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_c.returncode != 0
        assert not os.path.exists(
            uvicorn_marker
        ), "Uvicorn must not be launched for unverified source"


def test_11_runtime_verification_reachable_mocked_upstream_causes_zero_requests():
    """Test 4.3: Reachable mocked upstream source experiences ZERO requests during startup failure."""

    class _CountingHTTPHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.request_count += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"MOCK_DATA")

        def do_HEAD(self):
            self.server.request_count += 1
            self.send_response(200)
            self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress server logging during tests

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _CountingHTTPHandler)
    httpd.request_count = 0
    server_port = httpd.server_address[1]

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_dem = os.path.join(tmp_dir, "missing_at_runtime.tif")
            # Point to the live reachable mock HTTP server
            source_url = (
                f"http://127.0.0.1:{server_port}/Mars_HRSC_MOLA_BlendDEM.tif"
            )

            env = _build_test_env(
                tmp_dir,
                missing_dem,
                source_path=source_url,
                allow_fallback="false",
            )

            proc = subprocess.run(
                ["bash", str(START_SCRIPT)],
                cwd=str(REPO_ROOT),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

            # Startup must fail
            assert proc.returncode != 0
            # Zero network contact must be made: the mock server request count must be exactly 0
            assert (
                httpd.request_count == 0
            ), f"Runtime startup made {httpd.request_count} network requests! Expected exactly 0."
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_12_runtime_verification_missing_artifact_fails():
    """Test 4.4: verify_runtime_dem fails directly when DEM artifact is missing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        nonexistent = os.path.join(tmp_dir, "missing_dem.tif")
        with pytest.raises(RuntimeError) as exc_info:
            verify_runtime_dem(
                dem_path=nonexistent, use_real_dem=True, allow_fallback=False
            )
        assert "Runtime DEM raster missing" in str(exc_info.value)


def test_13_runtime_verification_missing_sidecar_fails():
    """Test 4.5: verify_runtime_dem fails directly when provenance sidecar is missing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_file = os.path.join(tmp_dir, "no_sidecar.tif")
        _write_sample_geotiff(dem_file, height=90, width=120)

        with pytest.raises(RuntimeError) as exc_info:
            verify_runtime_dem(
                dem_path=dem_file, use_real_dem=True, allow_fallback=False
            )
        assert "provenance sidecar missing" in str(exc_info.value)


def test_14_runtime_verification_corrupted_local_sha256_fails():
    """Test 4.6: verify_runtime_dem fails directly on local SHA-256 integrity mismatch."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_file = os.path.join(tmp_dir, "corrupt.tif")
        _copy_genuine_jezero_dem(dem_file)

        # Corrupt file bytes
        with open(dem_file, "ab") as f:
            f.write(b"EXTRA_CORRUPT_BYTES")

        with pytest.raises(RuntimeError) as exc_info:
            verify_runtime_dem(
                dem_path=dem_file, use_real_dem=True, allow_fallback=False
            )
        assert "local SHA-256 integrity verification failed" in str(exc_info.value)


def test_15_runtime_verification_unacceptable_provenance_fails():
    """Test 4.7: verify_runtime_dem fails directly on unverified provenance status."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_file = os.path.join(tmp_dir, "unverified_prov.tif")
        digest, _ = _write_sample_geotiff(dem_file, height=90, width=120)
        with open(f"{dem_file}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_product_id": "unverified",
                    "validation_status": "valid_numeric_raster_unverified_source",
                    "local_integrity_verified": True,
                    "local_file_sha256": digest,
                },
                f,
            )

        with pytest.raises(RuntimeError) as exc_info:
            verify_runtime_dem(
                dem_path=dem_file, use_real_dem=True, allow_fallback=False
            )
        assert (
            "Runtime DEM readiness gate failed" in str(exc_info.value)
            or "unacceptable statuses" in str(exc_info.value)
        )


def test_16_runtime_verification_synthetic_development_mode_healthy():
    """Test 4.8: Synthetic development mode (MARSPATH_USE_REAL_DEM=false) succeeds and reports healthy."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        fake_dem = os.path.join(tmp_dir, "nonexistent.tif")

        # In-process verification returns skipped status
        res = verify_runtime_dem(
            dem_path=fake_dem, use_real_dem=False, allow_fallback=False
        )
        assert res["status"] == "skipped_real_dem_disabled"
        assert res["real_dem_requested"] is False
        assert res["readiness_status"] == "healthy"

        # start_render.sh with MARSPATH_USE_REAL_DEM=false exits 0
        env = _build_test_env(tmp_dir, fake_dem, use_real_dem="false")
        env["MARSPATH_SKIP_UVICORN"] = "true"
        proc = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert "skipped_real_dem_disabled" in proc.stdout


def test_17_health_endpoint_reports_200_for_acceptable_real_terrain(
    monkeypatch,
):
    """Test 4.9: /health reports HTTP 200 for acceptable real terrain."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = os.path.join(tmp_dir, "jezero_acceptable.tif")
        _copy_genuine_jezero_dem(dem_path)

        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["real_dem_loaded"] is True
        assert body["dem_loaded"] is True
        assert body["is_synthetic"] is False
        assert body["local_integrity_verified"] is True
        assert body["source_checksum_verified"] is False
        assert body["blocking_errors"] == []


def test_18_health_and_data_status_readiness_preserved(monkeypatch):
    """Test 4.10: /health and /api/v1/data/status preserve Phase 7.1.1 readiness classifications."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = TestClient(app)

        # 1. Acceptable real terrain
        dem_path = os.path.join(tmp_dir, "jezero_ok.tif")
        _copy_genuine_jezero_dem(dem_path)

        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        status_resp = client.get("/api/v1/data/status")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["status"] == "healthy"
        assert body["dem_loaded"] is True
        assert body["local_integrity_verified"] is True
        assert (
            body["real_data_validation_status"]
            == "official_endpoint_retrieved_checksum_unverified"
        )

        # 2. Synthetic fallback mode in production -> HTTP 503 degraded
        missing_dem = os.path.join(tmp_dir, "missing.tif")
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
        get_settings.cache_clear()

        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
        assert resp.json()["data_mode"] == "synthetic_fallback"
        assert resp.json()["real_dem_loaded"] is False

        # 3. Unverified numerical terrain -> HTTP 503 degraded
        unverified_dem = os.path.join(tmp_dir, "unverified.tif")
        u_digest, _ = _write_sample_geotiff(unverified_dem, height=90, width=120)
        with open(f"{unverified_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "source_product_id": "unverified",
                    "validation_status": "valid_numeric_raster_unverified_source",
                    "local_integrity_verified": True,
                    "local_file_sha256": u_digest,
                },
                f,
            )

        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", unverified_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
        assert len(resp.json()["blocking_errors"]) > 0
