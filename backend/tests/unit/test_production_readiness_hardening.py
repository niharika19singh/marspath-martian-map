"""
Phase 7.1 — Production Fail-Closed Readiness Hardening Regression Suite.

Covers all 8 required regression cases:
1. Real DEM loaded, local integrity verified, upstream checksum unverified: /health returns 200 and real mode.
2. Real DEM requested, synthetic fallback active: /health returns 503 and degraded readiness.
3. Real DEM missing, fallback disabled: provider raises TerrainDataUnavailableError and the API returns 503.
4. Runtime provisioning fails with fallback disabled (and default Render config is fail-closed):
   startup provisioning exits nonzero and Uvicorn is not launched.
5. Local synthetic development mode: /health remains available (200) and reports synthetic test data honestly.
6. Data-status endpoint (/api/v1/data/status) does not report healthy when real terrain is requested but unavailable.
7. Real-data route planning and provenance remain functional after the hardening changes.
8. Real DEM mode does not require source_checksum_verified=true when official_endpoint_retrieved_checksum_unverified is present.
"""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from backend.app.core.config import get_settings
from backend.app.core.exceptions import TerrainDataUnavailableError
from backend.app.data.ingestion import USGS_MOLA_HRSC_MD5, USGS_MOLA_HRSC_PRODUCT_ID
from backend.app.data.manifest import DATA_CATALOG_MANIFEST, _compute_raster_array_sha256
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.main import app


def _create_official_unverified_checksum_dem_fixture(tmp_dir: str, monkeypatch) -> str:
    """
    Create a valid Mars 2000 GeoTIFF and companion .provenance.json matching
    an official-endpoint window extract (local_integrity_verified=True,
    source_checksum_verified=False, validation_status='official_endpoint_retrieved_checksum_unverified').
    """
    dem_path = os.path.join(tmp_dir, "jezero_mola_hrsc_blended.tif")
    # Create gently varying elevation around Jezero landing area (-2570 m to -2510 m)
    height, width = 90, 120
    y_idx, x_idx = np.meshgrid(
        np.linspace(0.0, 1.0, height), np.linspace(0.0, 1.0, width), indexing="ij"
    )
    elev = (-2565.0 + 35.0 * x_idx + 20.0 * y_idx).astype(np.int16)

    # Covers 77.0E to 78.2E, 18.08N to 18.80N
    transform = from_origin(77.0, 18.80, 0.01, 0.008)
    crs_str = "+proj=longlat +R=3396190 +no_defs"

    with rasterio.open(
        dem_path,
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
    with open(dem_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    digest = sha256_hash.hexdigest()
    file_size = os.path.getsize(dem_path)
    arr_sha = _compute_raster_array_sha256(dem_path)

    usgs_entry = next(
        p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
    )
    monkeypatch.setitem(usgs_entry, "jezero_window_array_sha256", arr_sha)

    provenance_record = {
        "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
        "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "published_upstream_md5": USGS_MOLA_HRSC_MD5,
        "computed_source_md5": None,
        "source_checksum_verified": False,
        "local_integrity_verified": True,
        "ingestion_method": "official_endpoint_vsicurl_range_extract",
        "validation_status": "official_endpoint_retrieved_checksum_unverified",
        "local_file_sha256": digest,
        "extracted_array_sha256": arr_sha,
        "file_size_bytes": file_size,
        "crs": crs_str,
        "window_bounds": {
            "min_lon": 77.0,
            "min_lat": 18.08,
            "max_lon": 78.2,
            "max_lat": 18.8,
        },
        "width": width,
        "height": height,
        "nodata": -32768.0,
        "ingested_at_utc": "2026-11-10T13:15:46.303771+00:00",
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path


def test_case_1_real_dem_loaded_unverified_upstream_checksum_returns_200_healthy(monkeypatch):
    """
    Regression Case 1:
    Real DEM loaded, local integrity verified, upstream checksum unverified:
    /health returns 200 and real mode ('real_official_endpoint_unverified_checksum').
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_official_unverified_checksum_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "healthy"
            assert body["real_dem_requested"] is True
            assert body["real_dem_loaded"] is True
            assert body["dem_loaded"] is True
            assert body["is_synthetic"] is False
            assert body["data_mode"] == "real_official_endpoint_unverified_checksum"
            assert body["real_data_validation_status"] == "official_endpoint_retrieved_checksum_unverified"
            assert body["local_integrity_verified"] is True
            assert body["source_checksum_verified"] is False
            assert body["fallback_reason"] is None
            assert body["blocking_errors"] == []

            readiness = body["data_readiness"]
            assert readiness["status"] == "healthy"
            assert readiness["real_dem_loaded"] is True
            assert readiness["is_synthetic"] is False
            assert readiness["local_integrity_verified"] is True
            assert readiness["source_checksum_verified"] is False
        finally:
            get_settings.cache_clear()


def test_case_8_real_dem_mode_does_not_require_source_checksum_verified_for_official_endpoint(monkeypatch):
    """
    Regression Case 8:
    The real DEM mode does not require source_checksum_verified=true when the correct
    intermediate official-endpoint validation status ('official_endpoint_retrieved_checksum_unverified')
    is present.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_official_unverified_checksum_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            provider = MOLAHRSCRasterProvider(dem_path=dem_path)
            prov = provider.get_provenance()
            assert prov["is_synthetic"] is False
            assert prov["source_checksum_verified"] is False
            assert prov["local_integrity_verified"] is True
            assert prov["real_data_validation_status"] == "official_endpoint_retrieved_checksum_unverified"
            assert prov["data_mode"] == "real_official_endpoint_unverified_checksum"

            client = TestClient(app)
            health_resp = client.get("/health")
            assert health_resp.status_code == 200
            assert health_resp.json()["status"] == "healthy"
            assert health_resp.json()["source_checksum_verified"] is False

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            assert status_resp.json()["status"] == "healthy"
            assert status_resp.json()["source_checksum_verified"] is False
            assert status_resp.json()["real_dem_loaded"] is True
        finally:
            get_settings.cache_clear()


def test_case_2_real_dem_requested_synthetic_fallback_active_returns_503_degraded(monkeypatch):
    """
    Regression Case 2:
    Real DEM requested (USE_REAL_DEM=true), synthetic fallback active (ALLOW_SYNTHETIC_FALLBACK=true,
    missing real DEM): /health returns HTTP 503 and degraded readiness.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_dem = os.path.join(tmp_dir, "missing_real_dem.tif")
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["real_dem_requested"] is True
            assert body["real_dem_loaded"] is False
            assert body["dem_loaded"] is False
            assert body["is_synthetic"] is True
            assert body["data_mode"] == "synthetic_fallback"
            assert body["fallback_reason"] is not None
            assert len(body["blocking_errors"]) >= 1

            readiness = body["data_readiness"]
            assert readiness["status"] == "degraded"
            assert readiness["real_dem_requested"] is True
            assert readiness["real_dem_loaded"] is False
            assert readiness["dem_loaded"] is False
            assert readiness["is_synthetic"] is True
            assert readiness["data_mode"] == "synthetic_fallback"
            assert readiness["fallback_reason"] is not None
            assert len(readiness["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()


def test_case_3_real_dem_missing_fallback_disabled_raises_503(monkeypatch):
    """
    Regression Case 3:
    Real DEM missing, fallback disabled: provider raises TerrainDataUnavailableError
    and the API returns HTTP 503 across /health, /api/v1/data/status, /api/v1/layers, and /api/v1/routes/plan.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_dem = os.path.join(tmp_dir, "missing_real_dem.tif")
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            provider = MOLAHRSCRasterProvider(dem_path=missing_dem)
            with pytest.raises(TerrainDataUnavailableError) as exc_info:
                provider.get_dem_raster()
            assert exc_info.value.status_code == 503

            client = TestClient(app)
            health_resp = client.get("/health")
            assert health_resp.status_code == 503
            assert "Numerical Martian terrain data unavailable" in health_resp.json()["error"]

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 503
            assert "Numerical Martian terrain data unavailable" in status_resp.json()["error"]

            layers_resp = client.get("/api/v1/layers")
            assert layers_resp.status_code == 503

            route_resp = client.post(
                "/api/v1/routes/plan",
                json={
                    "start": {"lon": 77.4508, "lat": 18.4447},
                    "destination": {"lon": 77.4050, "lat": 18.4650},
                    "mode": "safety_first",
                },
            )
            assert route_resp.status_code == 503
        finally:
            get_settings.cache_clear()


def test_case_4_runtime_provisioning_fails_closed_by_default():
    """
    Regression Case 4:
    - Verify render.yaml configures MARSPATH_ALLOW_SYNTHETIC_FALLBACK="false".
    - Verify start_render.sh defaults MARSPATH_ALLOW_SYNTHETIC_FALLBACK to "false" when unset,
      exits nonzero when provisioning fails, and never launches Uvicorn.
    """
    repo_root = Path(__file__).resolve().parents[3]
    render_yaml_path = repo_root / "render.yaml"
    render_yaml_text = render_yaml_path.read_text(encoding="utf-8")
    assert "key: MARSPATH_ALLOW_SYNTHETIC_FALLBACK\n        value: \"false\"" in render_yaml_text
    assert "key: MARSPATH_ALLOW_SYNTHETIC_FALLBACK\n        value: \"true\"" not in render_yaml_text

    script_path = repo_root / "backend" / "scripts" / "start_render.sh"
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_dem = os.path.join(tmp_dir, "missing_dem.tif")
        missing_source = os.path.join(tmp_dir, "nonexistent_source.tif")
        uvicorn_marker = os.path.join(tmp_dir, "uvicorn_was_launched.txt")

        # Create a fake 'uvicorn' binary in PATH that writes a marker file if executed
        fake_bin_dir = os.path.join(tmp_dir, "bin")
        os.makedirs(fake_bin_dir, exist_ok=True)
        fake_uvicorn = os.path.join(fake_bin_dir, "uvicorn")
        with open(fake_uvicorn, "w", encoding="utf-8") as f:
            f.write(f"#!/usr/bin/env bash\necho 'launched' > '{uvicorn_marker}'\nexit 0\n")
        os.chmod(fake_uvicorn, 0o755)

        env = os.environ.copy()
        # Ensure MARSPATH_ALLOW_SYNTHETIC_FALLBACK is unset so start_render.sh uses its default ('false')
        env.pop("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", None)
        env.pop("MARSPATH_SKIP_UVICORN", None)
        env.update(
            {
                "PATH": f"{fake_bin_dir}:{env.get('PATH', '')}",
                "MARSPATH_USE_REAL_DEM": "true",
                "MARSPATH_DEM_PATH": missing_dem,
                "MARSPATH_INGESTION_SOURCE": missing_source,
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
        assert proc.returncode != 0
        assert not os.path.exists(uvicorn_marker), "Uvicorn must NOT launch when provisioning fails with fallback disabled"


def test_case_5_local_synthetic_development_mode_returns_200_healthy(monkeypatch):
    """
    Regression Case 5:
    Local synthetic development mode (USE_REAL_DEM=false): /health remains available (HTTP 200)
    and reports synthetic test data honestly (data_mode='synthetic_test_fixture').
    """
    monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "false")
    monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
    get_settings.cache_clear()

    try:
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["real_dem_requested"] is False
        assert body["real_dem_loaded"] is False
        assert body["dem_loaded"] is False
        assert body["is_synthetic"] is True
        assert body["data_mode"] == "synthetic_test_fixture"
        assert body["fallback_reason"] is None
        assert body["blocking_errors"] == []

        status_resp = client.get("/api/v1/data/status")
        assert status_resp.status_code == 200
        st = status_resp.json()
        assert st["status"] == "healthy"
        assert st["data_mode"] == "synthetic_test_fixture"
        assert st["is_synthetic"] is True
    finally:
        get_settings.cache_clear()


def test_case_6_data_status_endpoint_reports_degraded_when_real_terrain_unavailable(monkeypatch):
    """
    Regression Case 6:
    /api/v1/data/status does not report 'healthy' when real terrain is requested
    but unavailable (returns status='degraded' when synthetic fallback is active).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        missing_dem = os.path.join(tmp_dir, "missing_dem.tif")
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/api/v1/data/status")
            assert resp.status_code == 200
            st = resp.json()
            assert st["status"] == "degraded"
            assert st["status"] != "healthy"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is False
            assert st["dem_loaded"] is False
            assert st["is_synthetic"] is True
            assert st["data_mode"] == "synthetic_fallback"
            assert st["fallback_reason"] is not None
            assert len(st["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()


def test_case_7_real_data_route_planning_and_provenance_remain_functional(monkeypatch):
    """
    Regression Case 7:
    Real-data route planning and provenance remain functional after the hardening changes.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_official_unverified_checksum_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            # Check /api/v1/data/status in real mode
            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "healthy"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["data_mode"] == "real_official_endpoint_unverified_checksum"
            assert st["real_data_validation_status"] == "official_endpoint_retrieved_checksum_unverified"
            assert st["local_integrity_verified"] is True
            assert st["source_checksum_verified"] is False
            assert st["blocking_errors"] == []

            # Plan a route in real DEM mode
            route_resp = client.post(
                "/api/v1/routes/plan",
                json={
                    "start": {"lon": 77.4508, "lat": 18.4447},
                    "destination": {"lon": 77.4050, "lat": 18.4650},
                    "mode": "safety_first",
                    "num_alternatives": 2,
                },
            )
            assert route_resp.status_code == 200
            route_body = route_resp.json()
            assert route_body["status"] == "success"
            assert route_body["data_mode"] == "real_official_endpoint_unverified_checksum"
            assert len(route_body["routes"]) >= 1
            assert route_body["routes"][0]["geometry"]["type"] == "LineString"
            assert len(route_body["routes"][0]["geometry"]["coordinates"]) >= 2
            prov = route_body["provenance"]
            assert prov["is_synthetic"] is False
            assert prov["data_mode"] == "real_official_endpoint_unverified_checksum"
            assert prov["real_data_validation_status"] == "official_endpoint_retrieved_checksum_unverified"
            assert prov["local_integrity_verified"] is True
            assert prov["source_checksum_verified"] is False
            assert prov["official_product_id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        finally:
            get_settings.cache_clear()
