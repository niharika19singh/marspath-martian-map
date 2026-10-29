import os
import tempfile
import numpy as np
import pytest
from backend.app.core.exceptions import TerrainDataUnavailableError
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider


def test_real_data_disabled_uses_synthetic():
    provider = MOLAHRSCRasterProvider(dem_path="nonexistent.tif")
    provider.use_real_dem = False
    raster = provider.get_dem_raster()
    assert raster.metadata.is_synthetic is True
    prov = provider.get_provenance()
    assert prov["data_mode"] == "synthetic_test_fixture"
    assert prov["real_dem_requested"] is False


def test_real_data_requested_missing_without_fallback_raises():
    provider = MOLAHRSCRasterProvider(dem_path="definitely_missing_file_xyz.tif")
    provider.use_real_dem = True
    provider.allow_fallback = False

    with pytest.raises(TerrainDataUnavailableError) as exc_info:
        provider.get_dem_raster()
    assert "Real DEM requested" in str(exc_info.value)


def test_real_data_requested_missing_with_fallback_reports_fallback():
    provider = MOLAHRSCRasterProvider(dem_path="definitely_missing_file_xyz.tif")
    provider.use_real_dem = True
    provider.allow_fallback = True

    raster = provider.get_dem_raster()
    assert raster.metadata.is_synthetic is True
    prov = provider.get_provenance()
    assert prov["data_mode"] == "synthetic_fallback"
    assert prov["real_dem_requested"] is True
    assert prov["real_dem_loaded"] is False
    assert "not found" in prov["fallback_reason"]


def test_real_data_loads_and_reports_real():
    with tempfile.NamedTemporaryFile(suffix=".npz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        elev = np.full((30, 30), -2550.0, dtype=np.float32)
        np.savez(tmp_path, elevation=elev, min_lon=77.2, min_lat=18.15, max_lon=77.95, max_lat=18.65)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        raster = provider.get_dem_raster()
        assert raster.metadata.is_synthetic is False
        prov = provider.get_provenance()
        assert prov["data_mode"] == "real"
        assert prov["is_synthetic"] is False
        assert prov["file_path"] == tmp_path
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
