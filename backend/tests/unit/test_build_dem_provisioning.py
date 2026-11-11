"""
Phase 7.2 — Build-Time DEM Provisioning & Immutable Runtime Artifact Regression Suite.

Covers all 13 required test cases:
1. Build provisioning creates both GeoTIFF and .provenance.json sidecar.
2. Missing or unreachable upstream source causes build provisioning to fail with nonzero exit.
3. Build provisioning fails closed: synthetic fallback cannot satisfy build requirements.
4. Existing valid artifact is reused without re-ingesting (idempotency).
5. Existing artifact with modified or tampered bytes fails integrity verification.
6. Missing provenance sidecar fails verification.
7. Unverified numerical terrain (valid_numeric_raster_unverified_source) is rejected as degraded.
8. Official endpoint extract with local_integrity_verified=True and source_checksum_verified=False remains acceptable.
9. Runtime startup (start_render.sh) reuses valid build artifact without remote requests.
10. Runtime startup fails before Uvicorn when artifact is absent or invalid.
11. /health reports HTTP 200 for acceptable real terrain.
12. /health reports HTTP 503 for unacceptable or synthetic production terrain.
13. /api/v1/data/status preserves Phase 7.1.1 readiness classification.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from backend.app.core.config import get_settings
from backend.app.data.ingestion import (
    USGS_MOLA_HRSC_MD5,
    USGS_MOLA_HRSC_PRODUCT_ID,
    compute_file_md5,
    verify_local_integrity,
)
from backend.app.data.manifest import DATA_CATALOG_MANIFEST, _compute_raster_array_sha256
from backend.app.main import app
from backend.app.services.data_catalog import (
    ACCEPTABLE_REAL_VALIDATION_STATUSES,
    evaluate_terrain_readiness,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUILD_SCRIPT = REPO_ROOT / "backend" / "scripts" / "provision_build_dem.sh"
START_SCRIPT = REPO_ROOT / "backend" / "scripts" / "start_render.sh"


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
    manifest_jezero_win_sha: str | None = None,
    manifest_up_md5: str | None = None,
) -> dict[str, str]:
    """Constructs environment dict with correct PYTHONPATH and isolation."""
    env = os.environ.copy()
    if extra_bin_dir:
        env["PATH"] = f"{extra_bin_dir}:{env.get('PATH', '')}"
    env["PYTHONPATH"] = (
        f"{REPO_ROOT}:{REPO_ROOT}/backend:{REPO_ROOT}/.deps:{env.get('PYTHONPATH', '')}"
    )
    env["MARSPATH_ENV"] = "production"
    env["MARSPATH_USE_REAL_DEM"] = "true"
    env["MARSPATH_DEM_PATH"] = dem_path
    env["MARSPATH_ALLOW_SYNTHETIC_FALLBACK"] = allow_fallback
    if source_path:
        env["MARSPATH_INGESTION_SOURCE"] = source_path
    else:
        env.pop("MARSPATH_INGESTION_SOURCE", None)
    if manifest_jezero_win_sha:
        env["MARSPATH_MANIFEST_JEZERO_WINDOW_ARRAY_SHA256"] = manifest_jezero_win_sha
    if manifest_up_md5:
        env["MARSPATH_MANIFEST_UPSTREAM_MD5_OVERRIDE"] = manifest_up_md5
    return env


# ==============================================================================
# Test 1: Build provisioning creates both GeoTIFF and .provenance.json sidecar
# ==============================================================================
def test_01_build_provisioning_creates_geotiff_and_provenance_sidecar(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        source_tif = os.path.join(tmp_dir, "source_jezero_raw.tif")
        _create_source_geotiff_for_ingestion(source_tif)
        src_md5 = compute_file_md5(source_tif)

        out_dem = os.path.join(tmp_dir, "built_jezero_dem.tif")
        sidecar = Path(f"{out_dem}.provenance.json")

        env = _build_test_env(
            tmp_dir,
            out_dem,
            source_path=source_tif,
            manifest_up_md5=src_md5,
        )

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, f"Build script failed:\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
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


# ==============================================================================
# Test 2: Missing or unreachable upstream source causes build provisioning to fail nonzero
# ==============================================================================
def test_02_missing_or_unreachable_source_causes_build_provisioning_failure():
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

        assert proc.returncode != 0, "Build script must exit nonzero on unreachable source"
        assert not os.path.exists(out_dem), "Partial DEM must be cleaned up on failure"
        assert not os.path.exists(f"{out_dem}.provenance.json"), "Partial sidecar must not exist"


# ==============================================================================
# Test 3: Build provisioning fails closed: synthetic fallback cannot satisfy build
# ==============================================================================
def test_03_build_provisioning_fails_closed_against_synthetic_fallback():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "synthetic_forbidden.tif")
        bad_source = os.path.join(tmp_dir, "unreachable_source.tif")

        # Explicitly attempt to pass allow_fallback="true" to build script
        env = _build_test_env(tmp_dir, out_dem, source_path=bad_source, allow_fallback="true")

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode != 0, "Build provisioning must fail closed even if env had fallback=true"
        assert not os.path.exists(out_dem), "Target raster must not be populated with synthetic data"


# ==============================================================================
# Test 4: Existing valid artifact is reused without re-ingesting (idempotency)
# ==============================================================================
def test_04_existing_valid_artifact_reused_without_reingesting(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "existing_valid.tif")
        digest, arr_sha = _write_sample_geotiff(out_dem, height=90, width=120, offset=-2565.0)

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        monkeypatch.setitem(usgs_entry, "jezero_window_array_sha256", arr_sha)

        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
            "ingestion_method": "official_endpoint_vsicurl_range_extract",
            "validation_status": "official_endpoint_retrieved_checksum_unverified",
            "source_checksum_verified": False,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
            "extracted_array_sha256": arr_sha,
        }
        with open(f"{out_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        # Point source to an unreachable path to prove no download/ingestion is attempted
        unreachable_source = os.path.join(tmp_dir, "should_never_be_touched.tif")
        env = _build_test_env(
            tmp_dir,
            out_dem,
            source_path=unreachable_source,
            manifest_jezero_win_sha=arr_sha,
        )

        proc = subprocess.run(
            ["bash", str(BUILD_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, f"Expected idempotency success:\n{proc.stdout}\n{proc.stderr}"
        assert "already_provisioned_valid" in proc.stdout or "Skipping re-ingestion" in proc.stdout
        assert "ALL BUILD-TIME DEM ARTIFACT INTEGRITY CHECKS PASSED" in proc.stdout


# ==============================================================================
# Test 5: Existing artifact with modified or tampered bytes fails integrity verification
# ==============================================================================
def test_05_tampered_artifact_bytes_fails_integrity_verification():
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


# ==============================================================================
# Test 6: Missing provenance sidecar fails verification
# ==============================================================================
def test_06_missing_provenance_sidecar_fails_verification():
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


# ==============================================================================
# Test 7: Unverified numerical terrain is rejected as degraded
# ==============================================================================
def test_07_unverified_numerical_terrain_rejected_as_degraded():
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
        assert "not in acceptable statuses" in proc.stderr or proc.returncode != 0


# ==============================================================================
# Test 8: Official endpoint extract with local_integrity_verified=True remains acceptable
# ==============================================================================
def test_08_official_endpoint_extract_unverified_checksum_remains_acceptable():
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
# Test 9: Runtime startup reuses valid build artifact without remote requests
# ==============================================================================
def test_09_runtime_startup_reuses_valid_build_artifact_without_remote_requests(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dem = os.path.join(tmp_dir, "runtime_reused.tif")
        digest, arr_sha = _write_sample_geotiff(out_dem, height=90, width=120, offset=-2565.0)

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        monkeypatch.setitem(usgs_entry, "jezero_window_array_sha256", arr_sha)

        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
            "ingestion_method": "official_endpoint_vsicurl_range_extract",
            "validation_status": "official_endpoint_retrieved_checksum_unverified",
            "source_checksum_verified": False,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
            "extracted_array_sha256": arr_sha,
        }
        with open(f"{out_dem}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

        # Point source to unreachable URL to ensure no network call is made
        env = _build_test_env(
            tmp_dir,
            out_dem,
            source_path="http://127.0.0.1:9/unreachable.tif",
            manifest_jezero_win_sha=arr_sha,
        )
        env["MARSPATH_SKIP_UVICORN"] = "true"
        env["MARSPATH_VERIFY_READINESS"] = "true"

        proc = subprocess.run(
            ["bash", str(START_SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, f"Startup script failed:\n{proc.stdout}\n{proc.stderr}"
        assert "already_provisioned_valid" in proc.stdout or "Skipping re-ingestion" in proc.stdout
        assert "Real DEM artifact and provenance verified successfully" in proc.stdout


# ==============================================================================
# Test 10: Runtime startup fails before Uvicorn when artifact is absent or invalid
# ==============================================================================
def test_10_runtime_startup_fails_before_uvicorn_when_artifact_absent_or_invalid():
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
        assert not os.path.exists(uvicorn_marker), "Uvicorn must not be launched when artifact is missing"

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
        assert not os.path.exists(uvicorn_marker), "Uvicorn must not be launched when artifact is corrupted"

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
        assert not os.path.exists(uvicorn_marker), "Uvicorn must not be launched for unverified source"


# ==============================================================================
# Test 11: /health reports HTTP 200 for acceptable real terrain
# ==============================================================================
def test_11_health_reports_200_for_acceptable_real_terrain(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = os.path.join(tmp_dir, "jezero_acceptable.tif")
        digest, arr_sha = _write_sample_geotiff(dem_path, height=90, width=120, offset=-2565.0)

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        monkeypatch.setitem(usgs_entry, "jezero_window_array_sha256", arr_sha)

        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
            "published_upstream_md5": USGS_MOLA_HRSC_MD5,
            "source_checksum_verified": False,
            "local_integrity_verified": True,
            "ingestion_method": "official_endpoint_vsicurl_range_extract",
            "validation_status": "official_endpoint_retrieved_checksum_unverified",
            "local_file_sha256": digest,
            "extracted_array_sha256": arr_sha,
        }
        with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

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


# ==============================================================================
# Test 12: /health reports HTTP 503 for unacceptable or synthetic production terrain
# ==============================================================================
def test_12_health_reports_503_for_unacceptable_or_synthetic_production_terrain(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = TestClient(app)

        # 1. Synthetic fallback mode in production
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

        # 2. Unverified numerical terrain
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


# ==============================================================================
# Test 13: /api/v1/data/status preserves Phase 7.1.1 readiness classification
# ==============================================================================
def test_13_data_status_preserves_phase_7_1_1_readiness_classification(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        client = TestClient(app)

        # 1. Acceptable real terrain
        dem_path = os.path.join(tmp_dir, "jezero_ok.tif")
        digest, arr_sha = _write_sample_geotiff(dem_path, height=90, width=120, offset=-2565.0)

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        monkeypatch.setitem(usgs_entry, "jezero_window_array_sha256", arr_sha)

        sidecar_data = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
            "ingestion_method": "official_endpoint_vsicurl_range_extract",
            "validation_status": "official_endpoint_retrieved_checksum_unverified",
            "source_checksum_verified": False,
            "local_integrity_verified": True,
            "local_file_sha256": digest,
            "extracted_array_sha256": arr_sha,
        }
        with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as f:
            json.dump(sidecar_data, f, indent=2)

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
        assert body["real_data_validation_status"] == "official_endpoint_retrieved_checksum_unverified"

        # 2. Unverified numerical terrain
        unverified_dem = os.path.join(tmp_dir, "unverified_data_status.tif")
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

        monkeypatch.setenv("MARSPATH_DEM_PATH", unverified_dem)
        get_settings.cache_clear()

        status_resp = client.get("/api/v1/data/status")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["status"] == "degraded"
        assert body["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
        assert len(body["blocking_errors"]) > 0
