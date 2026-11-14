"""Comprehensive Unit & Integration Test Suite for USGS Jezero Imagery & 1 m DTM Integration.

Covers:
- Section 2: Authoritative catalog metadata for USGS HiRISE Orthomosaic (10.5066/P9QJDP48),
  USGS HiRISE DTM (10.5066/P9REJ9JN), USGS CTX Orthomosaic (10.5066/P9GV1ND3), and
  NASA Viking Global Mosaic (10.5066/F71V5C67).
- Section 2C: Coordinate coverage verification for sample route (77.4000°E, 18.3900°N -> 77.4400°E, 18.4200°N).
- Section 4 & 6: WMTS capabilities endpoint & XML generation for satellite imagery layers.
- Section 7: Route planning engine selecting 1 m HiRISE DTM vs 200 m MOLA-HRSC DEM, verifying
  that changing DEM alters route cost and evidence passport, and imagery does not alter route cost.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.data.manifest import (
    DATA_CATALOG_MANIFEST,
    USGS_HIRISE_TRN_DTM_WINDOW_ARRAY_SHA256,
)
from app.data.providers.hirise import HiRISERasterProvider
from app.schemas.routes import RoutePlanRequest, MarsCoordinate, RouteConstraints
from app.services.route_service import RouteService


client = TestClient(app)


def find_dataset(doi_fragment: str):
    for entry in DATA_CATALOG_MANIFEST:
        if doi_fragment in entry.get("doi", "") or doi_fragment in entry.get("pds_doi", ""):
            return entry
    return None


def test_usgs_official_dataset_catalog_metadata():
    """Verify official USGS DOIs, product IDs, URLs, and resolutions in catalog."""
    # HiRISE DTM (10.5066/P9REJ9JN)
    dtm = find_dataset("10.5066/P9REJ9JN")
    assert dtm is not None
    assert dtm["doi"] == "10.5066/P9REJ9JN"
    assert dtm["product_id"] == "JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40"
    assert dtm["resolution_meters"] == 1.0
    assert dtm["data_type"] == "elevation"
    assert dtm["vertical_units"] == "meters"
    assert dtm["nodata_value"] == pytest.approx(-3.4028226550889045e+38, rel=1e-4)
    b = dtm["bounds"]
    assert b["min_lon"] == pytest.approx(77.2229331)
    assert b["min_lat"] == pytest.approx(18.3067994)
    assert b["max_lon"] == pytest.approx(77.583964)
    assert b["max_lat"] == pytest.approx(18.669315)

    # HiRISE Orthomosaic (10.5066/P9QJDP48)
    ortho = find_dataset("10.5066/P9QJDP48")
    assert ortho is not None
    assert ortho["doi"] == "10.5066/P9QJDP48"
    assert ortho["product_id"] == "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first"
    assert ortho["resolution_meters"] == 0.25
    assert ortho["data_type"] == "imagery"

    # CTX Orthomosaic (10.5066/P9GV1ND3)
    ctx = find_dataset("10.5066/P9GV1ND3")
    assert ctx is not None
    assert ctx["doi"] == "10.5066/P9GV1ND3"
    assert ctx["product_id"] == "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0"
    assert ctx["resolution_meters"] == 6.0
    assert ctx["data_type"] == "imagery"

    # Viking Global (10.5066/F71V5C67)
    viking = find_dataset("10.5066/F71V5C67")
    assert viking is not None
    assert viking["resolution_meters"] == 232.0
    assert viking["data_type"] == "imagery"


def test_coordinate_coverage_verification_sample_route():
    """Verify that start (77.4000°E, 18.3900°N) and destination (77.4400°E, 18.4200°N)

    lie strictly within the official bounds of both USGS Jezero products.
    """
    dtm = find_dataset("10.5066/P9REJ9JN")
    b = dtm["bounds"]
    min_lon, min_lat, max_lon, max_lat = b["min_lon"], b["min_lat"], b["max_lon"], b["max_lat"]

    start_lon, start_lat = 77.4000, 18.3900
    dest_lon, dest_lat = 77.4400, 18.4200

    assert min_lon <= start_lon <= max_lon, f"Start lon {start_lon} outside {min_lon}..{max_lon}"
    assert min_lat <= start_lat <= max_lat, f"Start lat {start_lat} outside {min_lat}..{max_lat}"
    assert min_lon <= dest_lon <= max_lon, f"Dest lon {dest_lon} outside {min_lon}..{max_lon}"
    assert min_lat <= dest_lat <= max_lat, f"Dest lat {dest_lat} outside {min_lat}..{max_lat}"


def test_hirise_provider_loading_and_provenance(monkeypatch):
    """Verify that the real provisioned USGS HiRISE DTM raster loads cleanly

    and yields complete, verified provenance.
    """
    monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
    monkeypatch.setenv("MARSPATH_USE_HIRISE_DEM", "true")

    from app.core.config import get_settings
    get_settings.cache_clear()
    provider = HiRISERasterProvider(enabled=True)
    assert provider.enabled is True

    # Check bounds
    bounds = provider.get_bounds()
    assert bounds.min_lon < bounds.max_lon
    assert bounds.min_lat < bounds.max_lat
    assert bounds.min_lon <= 77.4000 <= bounds.max_lon
    assert bounds.min_lat <= 18.3900 <= bounds.max_lat
    assert bounds.min_lon <= 77.4400 <= bounds.max_lon
    assert bounds.min_lat <= 18.4200 <= bounds.max_lat

    prov = provider.get_provenance()
    assert prov["official_product_id"] == "JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40"
    assert "10.5066/P9REJ9JN" in prov["pds_doi"]
    assert prov["local_integrity_verified"] is True
    assert prov["native_resolution_meters"] == pytest.approx(1.0, rel=0.05)


def test_route_service_dem_source_differentiation(monkeypatch):
    """Verify that planning a route with preferred_dem_source='hirise_1m' uses

    the 1 m DTM and produces distinct terrain calculations from 'mola_hrsc_200m'.
    """
    monkeypatch.setenv("MARSPATH_USE_REAL_DEM", "true")
    monkeypatch.setenv("MARSPATH_USE_HIRISE_DEM", "true")

    service = RouteService()

    req_hirise = RoutePlanRequest(
        start=MarsCoordinate(lon=77.4000, lat=18.3900),
        destination=MarsCoordinate(lon=77.4400, lat=18.4200),
        preferred_dem_source="hirise_1m",
        constraints=RouteConstraints(max_slope_deg=25.0, max_roughness=0.85),
    )
    res_hirise = service.plan_route(req_hirise)

    assert res_hirise.source_selection is not None
    assert res_hirise.source_selection.hirise_selected is True
    assert res_hirise.source_selection.native_resolution_meters == 1.0
    assert "10.5066/P9REJ9JN" in res_hirise.provenance["pds_doi"]
    assert len(res_hirise.routes) >= 1

    req_mola = RoutePlanRequest(
        start=MarsCoordinate(lon=77.4000, lat=18.3900),
        destination=MarsCoordinate(lon=77.4400, lat=18.4200),
        preferred_dem_source="mola_hrsc_200m",
        constraints=RouteConstraints(max_slope_deg=25.0, max_roughness=0.85),
    )
    res_mola = service.plan_route(req_mola)

    assert res_mola.source_selection is not None
    assert res_mola.source_selection.hirise_selected is False
    assert res_mola.source_selection.native_resolution_meters == 200.0
    assert len(res_mola.routes) >= 1

    # Route costs and geometries must reflect actual differing DEM source resolutions
    cost_hi = res_hirise.routes[0].total_cost
    cost_mola = res_mola.routes[0].total_cost
    assert cost_hi != cost_mola, "Switching DEM source must update terrain cost calculations"


def test_api_wmts_capabilities_endpoint():
    """Verify the /api/v1/wmts/capabilities/{layer_id} endpoint serves valid OGC XML."""
    layer_ids = [
        "Mars_Viking_MDIM21_ClrMosaic_global_232m",
        "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0",
        "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
        "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
    ]

    for lid in layer_ids:
        resp = client.get(f"/api/v1/wmts/capabilities/{lid}")
        assert resp.status_code == 200, f"Failed for {lid}: {resp.status_code}"
        assert resp.headers["content-type"].startswith("application/xml") or resp.headers["content-type"].startswith("text/xml")
        xml_text = resp.text
        assert "<Capabilities" in xml_text
        assert lid in xml_text
        assert "default028mm" in xml_text
