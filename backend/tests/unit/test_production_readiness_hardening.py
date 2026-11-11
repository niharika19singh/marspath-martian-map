"""
Phase 7.1.1 — Provenance Readiness Gate & Evidence Corrections Regression Suite.

Covers all 10 required readiness regression cases:
1. Official endpoint extract, local integrity true, upstream checksum false: HTTP 200 and healthy.
2. Verified source, local integrity true: HTTP 200 and healthy.
3. Non-synthetic raster with local integrity false: HTTP 503 and degraded.
4. Non-synthetic raster with local integrity null (missing sidecar): HTTP 503 and degraded.
5. Non-synthetic raster with valid_numeric_raster_unverified_source: HTTP 503 and degraded.
6. Synthetic fallback while real DEM requested: HTTP 503 and degraded.
7. Real DEM unavailable with fallback disabled: preserve existing 503 exception behavior.
8. Local synthetic development mode with real DEM disabled: HTTP 200 and explicitly synthetic.
9. /api/v1/data/status mirrors readiness classification for all relevant cases.
10. Real official-endpoint route planning and provenance remain functional.
Extra:
11. Startup fail-closed verification:
    - MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false: provisioning failure exits nonzero and Uvicorn is not executed.
    - MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true: provisioning continues with synthetic fallback, but /health returns 503/degraded.
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


def _write_sample_geotiff(
    path: str, height: int = 90, width: int = 120, offset: float = -2565.0
) -> tuple[str, str]:
    """Writes a valid numerical Mars 2000 GeoTIFF over Jezero Crater and returns (file_sha256, array_sha256)."""
    y_idx, x_idx = np.meshgrid(
        np.linspace(0.0, 1.0, height), np.linspace(0.0, 1.0, width), indexing="ij"
    )
    elev = (offset + 35.0 * x_idx + 20.0 * y_idx).astype(np.int16)
    transform = from_origin(77.0, 18.80, 0.01, 0.008)
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


def _create_official_unverified_checksum_dem_fixture(tmp_dir: str, monkeypatch) -> str:
    """Case 1 & 10: Official endpoint extract, local integrity True, upstream checksum False."""
    dem_path = os.path.join(tmp_dir, "jezero_mola_hrsc_blended.tif")
    digest, arr_sha = _write_sample_geotiff(dem_path, height=90, width=120, offset=-2565.0)

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
        "file_size_bytes": os.path.getsize(dem_path),
        "crs": "+proj=longlat +R=3396190 +no_defs",
        "window_bounds": {
            "min_lon": 77.0,
            "min_lat": 18.08,
            "max_lon": 78.2,
            "max_lat": 18.8,
        },
        "width": 120,
        "height": 90,
        "nodata": -32768.0,
        "ingested_at_utc": "2026-11-10T13:15:46.303771+00:00",
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path


def _create_verified_source_dem_fixture(tmp_dir: str, monkeypatch) -> str:
    """Case 2: Full source verified via manifest SHA-256 match, local integrity True."""
    dem_path = os.path.join(tmp_dir, "jezero_verified_source.tif")
    digest, _ = _write_sample_geotiff(dem_path, height=91, width=121, offset=-2560.0)

    usgs_entry = next(
        p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
    )
    monkeypatch.setitem(usgs_entry, "sha256", digest)

    provenance_record = {
        "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
        "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "source_checksum_verified": True,
        "local_integrity_verified": True,
        "validation_status": "verified_source",
        "local_file_sha256": digest,
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path


def _create_local_integrity_false_fixture(tmp_dir: str) -> str:
    """Case 3: Non-synthetic raster with tampered bytes or mismatched sidecar (local_integrity_verified=False)."""
    dem_path = os.path.join(tmp_dir, "jezero_integrity_fail.tif")
    _write_sample_geotiff(dem_path, height=92, width=122, offset=-2555.0)

    provenance_record = {
        "source_product_id": USGS_MOLA_HRSC_PRODUCT_ID,
        "source_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "local_file_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "validation_status": "verified_source",
        "source_checksum_verified": True,
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path


def _create_local_integrity_null_fixture(tmp_dir: str) -> str:
    """Case 4: Non-synthetic raster with missing sidecar (local_integrity_verified=None/null)."""
    dem_path = os.path.join(tmp_dir, "jezero_no_sidecar.tif")
    _write_sample_geotiff(dem_path, height=93, width=123, offset=-2550.0)
    return dem_path


def _create_unverified_source_raster_fixture(tmp_dir: str) -> str:
    """Case 5: Non-synthetic raster with valid local sidecar but unverified source provenance."""
    dem_path = os.path.join(tmp_dir, "jezero_unverified_source.tif")
    digest, _ = _write_sample_geotiff(dem_path, height=94, width=124, offset=-2545.0)

    provenance_record = {
        "source_product_id": "unverified_local_model",
        "source_url": "arbitrary_unauthenticated_file.tif",
        "local_file_sha256": digest,
        "source_checksum_verified": False,
        "validation_status": "valid_numeric_raster_unverified_source",
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path

    provenance_record = {
        "source_product_id": "unverified_local_model",
        "source_url": "arbitrary_unauthenticated_file.tif",
        "local_file_sha256": digest,
        "source_checksum_verified": False,
        "validation_status": "valid_numeric_raster_unverified_source",
    }
    with open(f"{dem_path}.provenance.json", "w", encoding="utf-8") as pf:
        json.dump(provenance_record, pf, indent=2)

    return dem_path


# ==============================================================================
# Case 1: Official endpoint extract, local integrity True, upstream checksum False -> 200 & healthy
# ==============================================================================
def test_case_1_official_endpoint_extract_local_integrity_true_returns_200_healthy(monkeypatch):
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
            assert body["blocking_errors"] == []

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "healthy"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["data_mode"] == "real_official_endpoint_unverified_checksum"
            assert st["local_integrity_verified"] is True
            assert st["source_checksum_verified"] is False
            assert st["blocking_errors"] == []
        finally:
            get_settings.cache_clear()


# ==============================================================================
# Case 2: Verified source, local integrity True -> 200 & healthy
# ==============================================================================
def test_case_2_verified_source_local_integrity_true_returns_200_healthy(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_verified_source_dem_fixture(tmp_dir, monkeypatch)
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
            assert body["data_mode"] == "real"
            assert body["real_data_validation_status"] == "verified_source"
            assert body["local_integrity_verified"] is True
            assert body["source_checksum_verified"] is True
            assert body["blocking_errors"] == []

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "healthy"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["data_mode"] == "real"
            assert st["real_data_validation_status"] == "verified_source"
            assert st["local_integrity_verified"] is True
            assert st["source_checksum_verified"] is True
            assert st["blocking_errors"] == []
        finally:
            get_settings.cache_clear()


# ==============================================================================
# Case 3: Non-synthetic raster with local integrity False -> 503 & degraded
# ==============================================================================
def test_case_3_non_synthetic_raster_local_integrity_false_returns_503_degraded(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_local_integrity_false_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["real_dem_requested"] is True
            assert body["real_dem_loaded"] is True
            assert body["dem_loaded"] is True
            assert body["is_synthetic"] is False
            assert body["local_integrity_verified"] is False
            assert len(body["blocking_errors"]) >= 1
            assert any("integrity" in err.lower() for err in body["blocking_errors"])

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "degraded"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["local_integrity_verified"] is False
            assert len(st["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()


# ==============================================================================
# Case 4: Non-synthetic raster with local integrity null -> 503 & degraded
# ==============================================================================
def test_case_4_non_synthetic_raster_local_integrity_null_returns_503_degraded(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_local_integrity_null_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["real_dem_requested"] is True
            assert body["real_dem_loaded"] is True
            assert body["dem_loaded"] is True
            assert body["is_synthetic"] is False
            assert body["local_integrity_verified"] is None
            assert len(body["blocking_errors"]) >= 1

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "degraded"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["local_integrity_verified"] is None
            assert len(st["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()


# ==============================================================================
# Case 5: Non-synthetic raster with valid_numeric_raster_unverified_source -> 503 & degraded
# ==============================================================================
def test_case_5_non_synthetic_raster_unverified_source_returns_503_degraded(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_unverified_source_raster_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
            resp = client.get("/health")
            assert resp.status_code == 503
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["real_dem_requested"] is True
            assert body["real_dem_loaded"] is True
            assert body["dem_loaded"] is True
            assert body["is_synthetic"] is False
            assert body["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
            assert body["local_integrity_verified"] is True
            assert len(body["blocking_errors"]) >= 1
            assert any("provenance" in err.lower() or "validation status" in err.lower() for err in body["blocking_errors"])

            status_resp = client.get("/api/v1/data/status")
            assert status_resp.status_code == 200
            st = status_resp.json()
            assert st["status"] == "degraded"
            assert st["real_dem_requested"] is True
            assert st["real_dem_loaded"] is True
            assert st["dem_loaded"] is True
            assert st["is_synthetic"] is False
            assert st["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
            assert len(st["blocking_errors"]) >= 1
        finally:
            get_settings.cache_clear()


# ==============================================================================
# Case 6: Synthetic fallback while real DEM requested -> 503 & degraded
# ==============================================================================
def test_case_6_synthetic_fallback_while_real_dem_requested_returns_503_degraded(monkeypatch):
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


# ==============================================================================
# Case 7: Real DEM unavailable with fallback disabled -> 503 exception
# ==============================================================================
def test_case_7_real_dem_unavailable_fallback_disabled_raises_503(monkeypatch):
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


# ==============================================================================
# Case 8: Local synthetic development mode (USE_REAL_DEM=false) -> 200 & explicitly synthetic
# ==============================================================================
def test_case_8_local_synthetic_development_mode_returns_200_healthy(monkeypatch):
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
        assert body["real_data_validation_status"] == "synthetic_test_fixture"
        assert body["local_integrity_verified"] is None
        assert body["source_checksum_verified"] is False
        assert body["fallback_reason"] is None
        assert body["blocking_errors"] == []

        status_resp = client.get("/api/v1/data/status")
        assert status_resp.status_code == 200
        st = status_resp.json()
        assert st["status"] == "healthy"
        assert st["real_dem_requested"] is False
        assert st["is_synthetic"] is True
        assert st["data_mode"] == "synthetic_test_fixture"
        assert st["real_data_validation_status"] == "synthetic_test_fixture"
        assert st["blocking_errors"] == []
    finally:
        get_settings.cache_clear()


# ==============================================================================
# Case 9: /api/v1/data/status mirrors readiness classification across all states
# ==============================================================================
def test_case_9_data_status_mirrors_readiness_classification_for_all_cases(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == USGS_MOLA_HRSC_PRODUCT_ID
        )

        # State A: Acceptable official extract -> healthy
        dem_a = _create_official_unverified_checksum_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_a)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()
        client = TestClient(app)
        assert client.get("/api/v1/data/status").json()["status"] == "healthy"

        # State B: Verified source -> healthy
        dem_b = _create_verified_source_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_b)
        get_settings.cache_clear()
        assert client.get("/api/v1/data/status").json()["status"] == "healthy"

        # Reset manifest sha256 so it cannot match non-verified states
        monkeypatch.setitem(usgs_entry, "sha256", None)

        # State C: Integrity False -> degraded
        dem_c = _create_local_integrity_false_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_c)
        get_settings.cache_clear()
        assert client.get("/api/v1/data/status").json()["status"] == "degraded"

        # State D: Integrity null -> degraded
        dem_d = _create_local_integrity_null_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_d)
        get_settings.cache_clear()
        assert client.get("/api/v1/data/status").json()["status"] == "degraded"

        # State E: Unverified source -> degraded
        dem_e = _create_unverified_source_raster_fixture(tmp_dir)
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_e)
        get_settings.cache_clear()
        assert client.get("/api/v1/data/status").json()["status"] == "degraded"

        # State F: Synthetic development mode -> healthy
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "false")
        get_settings.cache_clear()
        assert client.get("/api/v1/data/status").json()["status"] == "healthy"


# ==============================================================================
# Case 10: Real official-endpoint route planning and provenance remain functional
# ==============================================================================
def test_case_10_real_official_endpoint_route_planning_and_provenance_functional(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp_dir:
        dem_path = _create_official_unverified_checksum_dem_fixture(tmp_dir, monkeypatch)
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", dem_path)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "false")
        get_settings.cache_clear()

        try:
            client = TestClient(app)
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


# ==============================================================================
# Startup fail-closed behavior test: tests both explicit fallback values
# ==============================================================================
def test_startup_fail_closed_behavior_both_fallback_values(monkeypatch):
    import sys

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

        # Fake 'python3' binary that intercepts '-m uvicorn' without leaving a hung daemon
        fake_bin_dir = os.path.join(tmp_dir, "bin")
        os.makedirs(fake_bin_dir, exist_ok=True)
        fake_python = os.path.join(fake_bin_dir, "python3")
        real_python = sys.executable
        with open(fake_python, "w", encoding="utf-8") as f:
            f.write(
                f"#!/usr/bin/env bash\n"
                f'if [[ "$*" == *"-m uvicorn"* ]]; then\n'
                f'    echo "launched" > "{uvicorn_marker}"\n'
                f"    exit 0\n"
                f"fi\n"
                f'exec "{real_python}" "$@"\n'
            )
        os.chmod(fake_python, 0o755)

        base_env = os.environ.copy()
        base_env.pop("MARSPATH_SKIP_UVICORN", None)
        base_env.update(
            {
                "PATH": f"{fake_bin_dir}:{base_env.get('PATH', '')}",
                "MARSPATH_USE_REAL_DEM": "true",
                "MARSPATH_DEM_PATH": missing_dem,
                "MARSPATH_INGESTION_SOURCE": missing_source,
            }
        )

        # 1. Fallback disabled (default unset, or explicitly "false"): exits non-zero and Uvicorn NEVER launched
        for fb_val in (None, "false"):
            env = base_env.copy()
            if fb_val is None:
                env.pop("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", None)
            else:
                env["MARSPATH_ALLOW_SYNTHETIC_FALLBACK"] = fb_val

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

        # 2. Fallback explicitly enabled ("true"): provisioning continues, reaches Uvicorn execution, and /health returns 503/degraded
        env_fallback = base_env.copy()
        env_fallback["MARSPATH_ALLOW_SYNTHETIC_FALLBACK"] = "true"
        proc_fallback = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(repo_root),
            env=env_fallback,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_fallback.returncode == 0
        assert os.path.exists(uvicorn_marker), "Uvicorn execution should be reached when fallback is enabled"

        # Verify that in this fallback state, /health indeed returns 503 and degraded
        monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
        monkeypatch.setenv("MARSPATH_DEM_PATH", missing_dem)
        monkeypatch.setenv("MARSPATH_ALLOW_SYNTHETIC_FALLBACK", "true")
        get_settings.cache_clear()
        client = TestClient(app)
        health_resp = client.get("/health")
        assert health_resp.status_code == 503
        assert health_resp.json()["status"] == "degraded"
        assert health_resp.json()["data_mode"] == "synthetic_fallback"
