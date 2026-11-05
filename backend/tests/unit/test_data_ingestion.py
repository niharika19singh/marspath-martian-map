import json
import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.data.ingestion import (
    USGS_MOLA_HRSC_MD5,
    USGS_MOLA_HRSC_PRODUCT_ID,
    compute_file_sha256,
    ingest_jezero_dem,
    verify_local_provenance,
)


def test_compute_file_sha256():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"Mars Exploration Route Intelligence")
        tmp_path = tmp.name

    try:
        digest = compute_file_sha256(tmp_path)
        assert len(digest) == 64
        # Known SHA-256 for the string above
        import hashlib

        expected = hashlib.sha256(b"Mars Exploration Route Intelligence").hexdigest()
        assert digest == expected
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


def test_verify_local_provenance_valid_sidecar():
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(b"valid simulated dem bytes")
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

        valid, reason, loaded_sidecar = verify_local_provenance(tmp_path)
        assert valid is True
        assert reason == "authoritative_provenance_verified"
        assert loaded_sidecar is not None
        assert loaded_sidecar["local_file_sha256"] == file_sha
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(sidecar_path):
            os.remove(sidecar_path)


def test_verify_local_provenance_tampered_file():
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

        # Tamper with file
        with open(tmp_path, "ab") as f:
            f.write(b"corrupted additions")

        valid, reason, _ = verify_local_provenance(tmp_path)
        assert valid is False
        assert "sha256_mismatch" in reason
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        if os.path.exists(sidecar_path):
            os.remove(sidecar_path)


def test_ingest_jezero_dem_from_local_source():
    """
    Tests the ingestion windowing pipeline using a local synthetic source GeoTIFF
    covering a broad domain around Jezero Crater.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as src_tmp:
        source_path = src_tmp.name
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as out_tmp:
        out_path = out_tmp.name

    try:
        # Create a source GeoTIFF spanning 77.0 to 78.2 E, 18.0 to 18.8 N
        # with Mars 2000 CRS and 200m equivalent pixels
        data = np.full((100, 100), -2400.0, dtype=np.int16)
        data[20:40, 20:40] = -2600  # Crater floor
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

        # Ingest a subwindow (77.2 to 77.8 E, 18.2 to 18.6 N)
        sub_bounds = (77.20, 18.20, 77.80, 18.60)
        record = ingest_jezero_dem(
            output_path=out_path,
            source_url_or_path=source_path,
            bounds=sub_bounds,
            force=True,
        )

        assert record["validation_status"] == "verified_source"
        assert record["local_file_path"] == out_path
        assert os.path.exists(out_path)
        assert os.path.exists(f"{out_path}.provenance.json")
        assert record["min_elevation_meters"] <= -2400.0
        assert record["raster_shape"][0] > 0
        assert record["raster_shape"][1] > 0

        # Verify through verify_local_provenance
        valid, reason, sidecar = verify_local_provenance(out_path)
        assert valid is True
        assert reason == "authoritative_provenance_verified"
        assert sidecar["source_md5"] == USGS_MOLA_HRSC_MD5
    finally:
        for p in [source_path, out_path, f"{out_path}.provenance.json"]:
            if os.path.exists(p):
                os.remove(p)
