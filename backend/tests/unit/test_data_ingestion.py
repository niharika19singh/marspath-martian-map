import hashlib
import json
import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.data.ingestion import (
    USGS_MOLA_HRSC_MD5,
    USGS_MOLA_HRSC_PRODUCT_ID,
    compute_file_md5,
    compute_file_sha256,
    ingest_jezero_dem,
    verify_local_integrity,
    verify_local_provenance,
)
from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider


def test_compute_file_sha256_and_md5():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        payload = b"Mars Exploration Route Intelligence"
        tmp.write(payload)
        tmp_path = tmp.name

    try:
        sha_digest = compute_file_sha256(tmp_path)
        md5_digest = compute_file_md5(tmp_path)
        assert len(sha_digest) == 64
        assert len(md5_digest) == 32
        assert sha_digest == hashlib.sha256(payload).hexdigest()
        assert md5_digest == hashlib.md5(payload).hexdigest()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_verify_local_provenance_missing_file():
    valid, reason, sidecar = verify_local_provenance("nonexistent_path_abc123.tif")
    assert valid is False
    assert reason == "raster_file_not_found"
    assert sidecar is None


def test_verify_local_provenance_missing_sidecar():
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(b"fake geotiff data")
        tmp_path = tmp.name

    try:
        valid, reason, sidecar = verify_local_provenance(tmp_path)
        assert valid is False
        assert reason == "provenance_sidecar_missing"
        assert sidecar is None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_regression_1_synthetic_local_geotiff_cannot_become_authoritative_via_ingestion():
    """
    Regression Test 1: A synthetic local GeoTIFF passed through `ingest_jezero_dem`
    must NEVER be assigned the official USGS product ID, USGS MD5, or `verified_source` status.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as src_tmp:
        source_path = src_tmp.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as out_tmp:
        out_path = out_tmp.name

    try:
        data = np.full((100, 100), -2400.0, dtype=np.int16)
        data[20:40, 20:40] = -2600
        transform = from_origin(77.0, 18.8, 0.012, 0.008)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            source_path,
            "w",
            driver="GTiff",
            height=100,
            width=100,
            count=1,
            dtype="int16",
            crs=crs_str,
            transform=transform,
            nodata=-32768,
        ) as dst:
            dst.write(data, 1)

        actual_source_md5 = compute_file_md5(source_path)
        assert actual_source_md5 != USGS_MOLA_HRSC_MD5

        sub_bounds = (77.20, 18.20, 77.80, 18.60)
        record = ingest_jezero_dem(
            output_path=out_path,
            source_url_or_path=source_path,
            bounds=sub_bounds,
            force=True,
        )

        # Must NOT be marked verified_source or assigned USGS product identity
        assert record["validation_status"] == "valid_numeric_raster_unverified_source"
        assert record["validation_status"] != "verified_source"
        assert record["source_checksum_verified"] is False
        assert record["source_product_id"] is None
        assert record["computed_source_md5"] == actual_source_md5
        assert record["published_upstream_md5"] is None

        # Local integrity of the generated extract is valid, but source provenance is unverified
        integrity_ok, int_reason, _ = verify_local_integrity(out_path)
        assert integrity_ok is True
        assert int_reason == "local_sha256_integrity_verified"

        prov_ok, prov_reason, _ = verify_local_provenance(out_path)
        assert prov_ok is False
        assert prov_reason == "local_sha256_valid_but_source_unverified"

        # Loading via provider must also report unverified source
        provider = MOLAHRSCRasterProvider(dem_path=out_path)
        provider.use_real_dem = True
        provider.allow_fallback = False
        prov = provider.get_provenance()
        assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
        assert prov["official_product_id"] is None
        assert prov["local_integrity_verified"] is True
        assert prov["source_checksum_verified"] is False
    finally:
        for p in [source_path, out_path, f"{out_path}.provenance.json"]:
            if os.path.exists(p):
                os.remove(p)


def test_regression_2_manually_forged_sidecar_cannot_authenticate_synthetic_file():
    """
    Regression Test 2: A manually forged sidecar claiming the official USGS product ID,
    known catalog MD5, and `verified_source` cannot authenticate a synthetic file.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    sidecar_path = f"{tmp_path}.provenance.json"

    try:
        data = np.full((30, 30), -2500.0, dtype=np.float32)
        transform = from_origin(77.3, 18.6, 0.01, 0.01)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=30,
            width=30,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        file_sha = compute_file_sha256(tmp_path)
        forged_record = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_md5": USGS_MOLA_HRSC_MD5,
            "published_upstream_md5": USGS_MOLA_HRSC_MD5,
            "source_checksum_verified": True,
            "validation_status": "verified_source",
            "local_file_sha256": file_sha,
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(forged_record, f)

        # Local SHA-256 matches, so local integrity passes, but source provenance MUST fail
        integrity_ok, _, _ = verify_local_integrity(tmp_path)
        assert integrity_ok is True

        prov_ok, reason, _ = verify_local_provenance(tmp_path)
        assert prov_ok is False
        assert reason == "local_sha256_valid_but_source_unverified"
    finally:
        for p in [tmp_path, sidecar_path]:
            if os.path.exists(p):
                os.remove(p)


def test_regression_3_sidecar_with_correct_local_sha256_but_unverified_source_md5_is_insufficient():
    """
    Regression Test 3: A sidecar containing a valid local SHA-256 but an unverified
    source MD5 is insufficient to establish authoritative provenance.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(b"simulated raster bytes")
        tmp_path = tmp.name
    sidecar_path = f"{tmp_path}.provenance.json"

    try:
        file_sha = compute_file_sha256(tmp_path)
        record = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_md5": "11111111111111111111111111111111",
            "local_file_sha256": file_sha,
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(record, f)

        integrity_ok, _, _ = verify_local_integrity(tmp_path)
        assert integrity_ok is True

        valid, reason, _ = verify_local_provenance(tmp_path)
        assert valid is False
        assert reason == "local_sha256_valid_but_source_unverified"
    finally:
        for p in [tmp_path, sidecar_path]:
            if os.path.exists(p):
                os.remove(p)


def test_regression_4_tampered_local_file_fails_integrity_verification():
    """
    Regression Test 4: Modifying a local raster file after sidecar creation causes
    both `verify_local_integrity` and `verify_local_provenance` to fail with `sha256_mismatch`.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(b"original data")
        tmp_path = tmp.name
    sidecar_path = f"{tmp_path}.provenance.json"

    try:
        file_sha = compute_file_sha256(tmp_path)
        record = {
            "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
            "source_md5": USGS_MOLA_HRSC_MD5,
            "local_file_sha256": file_sha,
        }
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(record, f)

        # Tamper with file bytes
        with open(tmp_path, "ab") as f:
            f.write(b"corrupted additions")

        int_ok, int_reason, _ = verify_local_integrity(tmp_path)
        assert int_ok is False
        assert "sha256_mismatch" in int_reason

        valid, reason, _ = verify_local_provenance(tmp_path)
        assert valid is False
        assert "sha256_mismatch" in reason
    finally:
        for p in [tmp_path, sidecar_path]:
            if os.path.exists(p):
                os.remove(p)


def test_regression_5_genuinely_verified_upstream_source_recognised_when_bytes_match_catalog():
    """
    Regression Test 5: When a local full-product source file has its actual byte MD5
    independently matching the catalog's `upstream_md5` and the extracted window pixels
    match that verified source file, `ingest_jezero_dem` and `verify_local_provenance`
    recognise it as `verified_source`.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as src_tmp:
        source_path = src_tmp.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as out_tmp:
        out_path = out_tmp.name

    try:
        rng = np.random.default_rng(42)
        data = rng.integers(-2800, -1600, size=(80, 80), dtype=np.int16)
        transform = from_origin(77.0, 18.8, 0.012, 0.008)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            source_path,
            "w",
            driver="GTiff",
            height=80,
            width=80,
            count=1,
            dtype="int16",
            crs=crs_str,
            transform=transform,
            nodata=-32768,
        ) as dst:
            dst.write(data, 1)

        actual_src_md5 = compute_file_md5(source_path)

        # Register the source file's actual MD5 in the catalog entry for this test
        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )
        original_md5 = usgs_entry.get("upstream_md5")
        usgs_entry["upstream_md5"] = actual_src_md5

        try:
            sub_bounds = (77.20, 18.20, 77.80, 18.60)
            record = ingest_jezero_dem(
                output_path=out_path,
                source_url_or_path=source_path,
                bounds=sub_bounds,
                force=True,
            )

            assert record["validation_status"] == "verified_source"
            assert record["source_checksum_verified"] is True
            assert record["source_product_id"] == USGS_MOLA_HRSC_PRODUCT_ID
            assert record["computed_source_md5"] == actual_src_md5

            valid, reason, _ = verify_local_provenance(out_path)
            assert valid is True
            assert reason == "authoritative_full_source_bytes_verified"

            provider = MOLAHRSCRasterProvider(dem_path=out_path)
            provider.use_real_dem = True
            provider.allow_fallback = False
            prov = provider.get_provenance()
            assert prov["real_data_validation_status"] == "verified_source"
            assert prov["source_checksum_verified"] is True
            assert prov["local_integrity_verified"] is True
            assert prov["provenance_verification_method"] == "authoritative_full_source_bytes_verified"
        finally:
            usgs_entry["upstream_md5"] = original_md5
    finally:
        for p in [source_path, out_path, f"{out_path}.provenance.json"]:
            if os.path.exists(p):
                os.remove(p)


def test_render_startup_reuses_already_provisioned_valid_dem():
    """
    Requirement 6: Render startup (`provision_runtime_dem` and `start_render.sh`)
    correctly detects and reuses an already provisioned valid DEM without re-ingesting.
    """
    import subprocess
    from pathlib import Path

    from backend.app.data.ingestion import provision_runtime_dem

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as src_tmp:
        source_path = src_tmp.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as out_tmp:
        out_path = out_tmp.name

    try:
        data = np.full((80, 80), -2450.0, dtype=np.int16)
        transform = from_origin(77.0, 18.8, 0.012, 0.008)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            source_path,
            "w",
            driver="GTiff",
            height=80,
            width=80,
            count=1,
            dtype="int16",
            crs=crs_str,
            transform=transform,
            nodata=-32768,
        ) as dst:
            dst.write(data, 1)

        # Provision initially
        ingest_jezero_dem(
            output_path=out_path,
            source_url_or_path=source_path,
            bounds=(77.20, 18.20, 77.80, 18.60),
            force=True,
        )
        initial_mtime = os.path.getmtime(out_path)
        initial_sha = compute_file_sha256(out_path)

        # Remove source_path to prove `provision_runtime_dem` does NOT re-read the source
        os.remove(source_path)

        res = provision_runtime_dem(
            dem_path=out_path,
            use_real_dem=True,
            allow_fallback=False,
            source_url_or_path="nonexistent_source_should_not_be_called.tif",
            force=False,
        )
        assert res["status"] == "already_provisioned_valid"
        assert res["action"] == "reused_existing_valid_dem"
        assert res["real_dem_provisioned"] is True
        assert res["local_file_sha256"] == initial_sha
        assert os.path.getmtime(out_path) == initial_mtime

        # Also verify `backend/scripts/start_render.sh` shell execution with MARSPATH_SKIP_UVICORN=true
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "backend" / "scripts" / "start_render.sh"
        env = os.environ.copy()
        env.update(
            {
                "MARSPATH_USE_REAL_DEM": "true",
                "MARSPATH_DEM_PATH": out_path,
                "MARSPATH_ALLOW_SYNTHETIC_FALLBACK": "false",
                "MARSPATH_INGESTION_SOURCE": "nonexistent_source_should_not_be_called.tif",
                "MARSPATH_SKIP_UVICORN": "true",
            }
        )
        proc = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
        assert "already_provisioned_valid" in proc.stdout
    finally:
        for p in [source_path, out_path, f"{out_path}.provenance.json", f"{out_path}.provision_error.json"]:
            if os.path.exists(p):
                os.remove(p)


def test_render_startup_provisions_missing_dem():
    """
    Requirement 7: Render startup (`provision_runtime_dem` and `start_render.sh`)
    correctly provisions a missing DEM from the configured source and verifies its SHA-256.
    """
    import subprocess
    from pathlib import Path

    from backend.app.data.ingestion import provision_runtime_dem

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as src_tmp:
        source_path = src_tmp.name
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = os.path.join(tmp_dir, "jezero_provisioned.tif")

        try:
            data = np.full((90, 120), -2510.0, dtype=np.int16)
            transform = from_origin(77.0, 18.8, 0.01, 0.008)
            crs_str = "+proj=longlat +R=3396190 +no_defs"

            with rasterio.open(
                source_path,
                "w",
                driver="GTiff",
                height=90,
                width=120,
                count=1,
                dtype="int16",
                crs=crs_str,
                transform=transform,
                nodata=-32768,
            ) as dst:
                dst.write(data, 1)

            assert not os.path.exists(out_path)

            res = provision_runtime_dem(
                dem_path=out_path,
                use_real_dem=True,
                allow_fallback=False,
                source_url_or_path=source_path,
                force=False,
            )
            assert res["status"] == "provisioned_from_source"
            assert res["real_dem_provisioned"] is True
            assert os.path.exists(out_path)
            assert os.path.exists(f"{out_path}.provenance.json")

            integrity_ok, _, _ = verify_local_integrity(out_path)
            assert integrity_ok is True

            # Test via start_render.sh on a fresh missing path
            out_path_2 = os.path.join(tmp_dir, "jezero_script_provisioned.tif")
            repo_root = Path(__file__).resolve().parents[3]
            script_path = repo_root / "backend" / "scripts" / "start_render.sh"
            env = os.environ.copy()
            env.update(
                {
                    "MARSPATH_USE_REAL_DEM": "true",
                    "MARSPATH_DEM_PATH": out_path_2,
                    "MARSPATH_ALLOW_SYNTHETIC_FALLBACK": "false",
                    "MARSPATH_INGESTION_SOURCE": source_path,
                    "MARSPATH_SKIP_UVICORN": "true",
                }
            )
            proc = subprocess.run(
                ["bash", str(script_path)],
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert proc.returncode == 0, f"stderr: {proc.stderr}\nstdout: {proc.stdout}"
            assert "provisioned_from_source" in proc.stdout
            assert os.path.exists(out_path_2)
        finally:
            if os.path.exists(source_path):
                os.remove(source_path)


def test_render_startup_fallback_and_strict_failure_reflected_in_health_and_data_status(monkeypatch):
    """
    Requirement 8: When ingestion fails during Render startup:
    - With `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true`: startup succeeds in fallback mode,
      and `/health` + `/api/v1/data/status` report `real_dem_requested=true`,
      `real_dem_loaded=false`, `dem_loaded=false`, `is_synthetic=true`,
      `data_mode="synthetic_fallback"`, and populate `fallback_reason` & `blocking_errors`.
    - With `MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false`: `provision_runtime_dem` raises
      `RuntimeError` and `start_render.sh` exits non-zero to abort startup.
    """
    import subprocess
    from pathlib import Path

    import pytest
    from fastapi.testclient import TestClient

    from backend.app.core.config import get_settings
    from backend.app.data.ingestion import provision_runtime_dem
    from backend.app.main import app

    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_dem_path = os.path.join(tmp_dir, "missing_jezero.tif")
        unusable_source = os.path.join(tmp_dir, "does_not_exist_upstream.tif")

        # 1. Strict mode (allow_fallback=False) must fail startup
        with pytest.raises(RuntimeError, match="Mandatory real DEM provisioning failed"):
            provision_runtime_dem(
                dem_path=missing_dem_path,
                use_real_dem=True,
                allow_fallback=False,
                source_url_or_path=unusable_source,
            )

        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "backend" / "scripts" / "start_render.sh"
        strict_env = os.environ.copy()
        strict_env.update(
            {
                "MARSPATH_USE_REAL_DEM": "true",
                "MARSPATH_DEM_PATH": missing_dem_path,
                "MARSPATH_ALLOW_SYNTHETIC_FALLBACK": "false",
                "MARSPATH_INGESTION_SOURCE": unusable_source,
                "MARSPATH_SKIP_UVICORN": "true",
            }
        )
        strict_proc = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(repo_root),
            env=strict_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert strict_proc.returncode != 0

        # 2. Fallback mode (allow_fallback=True) must succeed startup and accurately report fallback in /health and /api/v1/data/status
        res = provision_runtime_dem(
            dem_path=missing_dem_path,
            use_real_dem=True,
            allow_fallback=True,
            source_url_or_path=unusable_source,
        )
        assert res["status"] == "fallback_to_synthetic"
        assert res["real_dem_requested"] is True
        assert res["real_dem_provisioned"] is False

        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            health_resp = client.get("/health")
            assert health_resp.status_code == 503
            health_body = health_resp.json()
            assert health_body["status"] == "degraded"
            readiness = health_body["data_readiness"]
            assert readiness["status"] == "degraded"
            assert readiness["real_dem_requested"] is True
            assert readiness["real_dem_loaded"] is False
            assert readiness["dem_loaded"] is False
            assert readiness["is_synthetic"] is True
            assert readiness["data_mode"] == "synthetic_fallback"
            assert readiness["real_data_validation_status"] == "incomplete_missing_genuine_dem"
            assert readiness["fallback_reason"] is not None
            assert "provisioning error" in readiness["fallback_reason"].lower()
            assert len(readiness["blocking_errors"]) >= 1

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "degraded"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is False
            assert st["dem_loaded"] is False
            assert st["is_synthetic"] is True
            assert st["data_mode"] == "synthetic_fallback"
            assert st["fallback_reason"] is not None
            assert len(st["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()

