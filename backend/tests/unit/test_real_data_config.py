import hashlib
import os
import tempfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from backend.app.core.exceptions import TerrainDataUnavailableError
from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider


def test_real_data_disabled_uses_synthetic():
    """When real DEM is disabled, provider operates in synthetic test mode."""
    provider = MOLAHRSCRasterProvider(dem_path="nonexistent.tif")
    provider.use_real_dem = False
    raster = provider.get_dem_raster()

    assert raster.metadata.is_synthetic is True
    prov = provider.get_provenance()
    assert prov["data_mode"] == "synthetic_test_fixture"
    assert prov["real_dem_requested"] is False
    assert prov["real_dem_loaded"] is False
    assert prov["real_data_validation_status"] == "synthetic_test_fixture"
    assert "deterministic" in prov["provenance_verification_method"]


def test_real_data_requested_missing_without_fallback_raises():
    """When real DEM is requested, missing, and fallback is disabled, raise clear error."""
    provider = MOLAHRSCRasterProvider(dem_path="definitely_missing_file_xyz.tif")
    provider.use_real_dem = True
    provider.allow_fallback = False

    with pytest.raises(TerrainDataUnavailableError) as exc_info:
        provider.get_dem_raster()
    assert "Real DEM requested" in str(exc_info.value)


def test_real_data_requested_missing_with_fallback_reports_incomplete():
    """When real DEM is missing with fallback enabled, status must report incomplete."""
    provider = MOLAHRSCRasterProvider(dem_path="definitely_missing_file_xyz.tif")
    provider.use_real_dem = True
    provider.allow_fallback = True

    raster = provider.get_dem_raster()
    assert raster.metadata.is_synthetic is True

    prov = provider.get_provenance()
    assert prov["data_mode"] == "synthetic_fallback"
    assert prov["real_dem_requested"] is True
    assert prov["real_dem_loaded"] is False
    assert prov["real_data_validation_status"] == "incomplete_missing_genuine_dem"
    assert "not found" in prov["fallback_reason"].lower()
    assert prov["provenance_verification_method"] == "none_file_missing_or_invalid"


def test_arbitrary_numpy_raster_cannot_be_reported_as_verified_nasa_dem():
    """
    An arbitrary NumPy array with plausible Jezero bounds cannot be reported as
    a verified NASA DEM merely because it is numerically and spatially valid.
    It must be reported as valid_numeric_raster_unverified_source.
    """
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        elev = np.full((30, 30), -2550.0, dtype=np.float32)
        np.savez(
            tmp_path,
            elevation=elev,
            min_lon=77.2,
            min_lat=18.15,
            max_lon=77.95,
            max_lat=18.65,
        )

        # Expected SHA-256 of the generated file
        with open(tmp_path, "rb") as f:
            expected_sha256 = hashlib.sha256(f.read()).hexdigest()

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        raster = provider.get_dem_raster()
        assert raster.metadata.is_synthetic is False

        prov = provider.get_provenance()

        # Must NOT claim verified NASA/ESA/USGS provenance
        assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
        assert prov["real_data_validation_status"] != "verified_source"
        assert prov["data_mode"] == "real_unverified_source"

        # Dataset name must disclose that source is unverified
        assert "unverified" in prov["dataset_name"].lower()
        assert prov["dataset_name"] != "HRSC and MOLA Blended Digital Elevation Model (200m & 50m Jezero Mosaic)"

        # Must record actual file SHA-256 and format
        assert prov["file_sha256"] == expected_sha256
        assert "NumPy" in prov["file_format"]

        # Official IDs must be None
        assert prov["official_product_id"] is None
        assert prov["official_source_url"] is None
        assert prov["pds_doi"] is None
        assert prov["provenance_verification_method"] == "unverified_source_no_authoritative_credentials"

        # Disclose limitations
        assert any("could NOT be verified" in lim for lim in prov["provenance_limitations"])
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_synthetic_geotiff_with_mars_crs_cannot_be_reported_as_verified_nasa_dem():
    """
    A synthetic GeoTIFF with plausible Mars elevations and valid planetary CRS
    cannot claim verified NASA provenance without authoritative PDS metadata or checksums.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        data = np.full((40, 40), -2520.0, dtype=np.float32)
        transform = from_origin(77.2, 18.65, 0.01875, 0.0125)
        crs_str = "+proj=longlat +R=3396190 +no_defs"

        with rasterio.open(
            tmp_path,
            "w",
            driver="GTiff",
            height=40,
            width=40,
            count=1,
            dtype="float32",
            crs=crs_str,
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        raster = provider.get_dem_raster()
        assert raster.metadata.is_synthetic is False

        prov = provider.get_provenance()

        # Must be reported as unverified source
        assert prov["real_data_validation_status"] == "valid_numeric_raster_unverified_source"
        assert prov["real_data_validation_status"] != "verified_source"
        assert prov["data_mode"] == "real_unverified_source"
        assert prov["official_product_id"] is None
        assert prov["file_format"] == "GeoTIFF"
        assert prov["provenance_verification_method"] == "unverified_source_no_authoritative_credentials"

        # Check raster statistics
        stats = prov["raster_statistics"]
        assert stats["total_cells"] == 1600
        assert stats["valid_cells"] == 1600
        assert stats["valid_data_fraction"] == 1.0
        assert stats["min_elevation_meters"] == -2520.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_authoritative_source_via_metadata_tags_reports_verified_source():
    """
    A GeoTIFF carrying authoritative USGS/PDS product metadata tags
    is recognized and granted verified_source status.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

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
            dst.update_tags(
                PRODUCT_ID="JEZERO_HRSC_MOLA_blended_DEM",
                PDS_DOI="https://doi.org/10.5066/P9P7W018",
                VERTICAL_DATUM="Mars Areoid (MOLA MEGDR IAU2000)",
            )
            dst.write(data, 1)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        raster = provider.get_dem_raster()
        assert raster.metadata.is_synthetic is False

        prov = provider.get_provenance()

        # Provenance is authenticated!
        assert prov["real_data_validation_status"] == "verified_source"
        assert prov["data_mode"] == "real"
        assert prov["official_product_id"] == "dem_hrsc_mola_blended_50m"
        assert prov["dataset_name"] == "HRSC and MOLA Blended Digital Elevation Model (200m & 50m Jezero Mosaic)"
        assert prov["official_source_url"] == "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM"
        assert prov["provenance_verification_method"] == "authoritative_pds_metadata_tags"
        assert prov["vertical_datum"] == "Mars Areoid (MOLA MEGDR IAU2000)"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_authoritative_source_via_manifest_sha256_reports_verified_source():
    """
    A DEM whose SHA-256 checksum matches an official manifest record
    is verified and granted verified_source status.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        data = np.full((30, 30), -2480.0, dtype=np.float32)
        transform = from_origin(77.38, 18.45, 0.001, 0.001)
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

        # Compute file SHA-256
        with open(tmp_path, "rb") as f:
            actual_sha = hashlib.sha256(f.read()).hexdigest()

        # Temporarily register this checksum in the HiRISE product manifest entry
        hirise_entry = next(p for p in DATA_CATALOG_MANIFEST if p["id"] == "dem_hirise_jezero_delta_1m")
        original_sha = hirise_entry.get("sha256")
        hirise_entry["sha256"] = actual_sha

        try:
            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            prov = provider.get_provenance()

            assert prov["real_data_validation_status"] == "verified_source"
            assert prov["official_product_id"] == "dem_hirise_jezero_delta_1m"
            assert prov["provenance_verification_method"] == "authoritative_manifest_sha256_match"
            assert prov["dataset_name"] == "HiRISE Jezero Crater Western Delta Digital Terrain Model (DTM)"
        finally:
            hirise_entry["sha256"] = original_sha
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
