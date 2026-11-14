from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.app.data_sources.connectors.mars_trek.connector import MarsTrekConnector
from backend.app.data_sources.connectors.naif_spice.connector import NaifSpiceConnector
from backend.app.data_sources.connectors.pds_atmospheres.connector import PdsAtmospheresConnector
from backend.app.data_sources.connectors.pds_geosciences.connector import PdsGeosciencesConnector
from backend.app.data_sources.connectors.pds_releases.connector import PdsReleasesConnector
from backend.app.data_sources.connectors.planetary_notebook.connector import PlanetaryNotebookConnector
from backend.app.data_sources.connectors.themis.connector import ThemisConnector
from backend.app.data_sources.registry.registry import OFFICIAL_NASA_SOURCES, DataSourceRegistry
from backend.app.data_sources.schemas.models import (
    ConnectionState,
    ProductSearchQuery,
)
from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService
from backend.app.data_sources.services.sync_service import DataSourceSyncService
from backend.app.main import app

client = TestClient(app)


# 1. Registry tests
def test_01_all_seven_nasa_sources_registered():
    registry = DataSourceRegistry()
    sources = registry.list_sources()
    assert len(sources) == 7

    source_ids = {s.source_id for s in sources}
    expected_ids = {
        "nasa_mars_trek",
        "pds_geosciences",
        "pds_atmospheres",
        "themis",
        "naif_spice",
        "planetary_notebook",
        "pds_releases",
    }
    assert source_ids == expected_ids

    for s in sources:
        assert s.source_name
        assert s.organization
        assert s.official_url.startswith("https://")
        assert s.connection_status in (ConnectionState.CONNECTED, ConnectionState.DATA_INGESTED)
        assert s.is_data_ingested is True
        assert s.indexed_products_count > 0
        assert "publisher" in s.citation_information or "authority" in s.citation_information


# 2. Mars Trek Connector
def test_02_mars_trek_capabilities_and_products():
    connector = MarsTrekConnector(OFFICIAL_NASA_SOURCES["nasa_mars_trek"])
    meta = asyncio.run(connector.fetch_metadata())
    assert meta["service"] == "OGC WMTS"
    assert meta["supported_layers_count"] >= 5
    assert len(meta["layers"]) >= 5

    products = asyncio.run(connector.list_products(10))
    assert len(products) >= 5

    jezero_hirise = next((p for p in products if "HiRISE" in p.title), None)
    assert jezero_hirise is not None
    assert jezero_hirise.spatial_resolution_m == 0.25
    assert jezero_hirise.map_layer_supported is True
    assert "tile_url" in jezero_hirise.map_layer_config


# 3. PDS Geosciences Connector
def test_03_pds_geosciences_mro_instruments():
    connector = PdsGeosciencesConnector(OFFICIAL_NASA_SOURCES["pds_geosciences"])
    meta = asyncio.run(connector.fetch_metadata())
    assert "HiRISE" in meta["supported_instruments"]
    assert "CRISM" in meta["supported_instruments"]

    products = asyncio.run(connector.list_products(20))
    assert len(products) >= 5

    instruments = {p.instrument for p in products}
    assert "HiRISE" in instruments
    assert "CTX" in instruments
    assert "CRISM" in instruments
    assert "SHARAD" in instruments

    dtm = next((p for p in products if p.product_type == "TERRAIN_DTM"), None)
    assert dtm is not None
    assert dtm.spatial_resolution_m == 1.0


# 4. PDS Atmospheres (MEDA)
def test_04_pds_atmospheres_meda_telemetry():
    connector = PdsAtmospheresConnector(OFFICIAL_NASA_SOURCES["pds_atmospheres"])
    meta = asyncio.run(connector.fetch_metadata())
    assert meta["instrument"] == "MEDA (Mars Environmental Dynamics Analyzer)"
    assert "scientific_constraint" in meta["observation_location"]

    observations = connector.get_observations()
    assert len(observations) >= 5

    sol2022 = next((o for o in observations if o.sol == 2022 and o.timestamp_utc.hour == 14), None)
    assert sol2022 is not None
    assert sol2022.air_temp_c == -22.4
    assert sol2022.pressure_pa == 742.6
    assert sol2022.dust_optical_depth_tau == 0.38
    assert sol2022.relative_humidity_pct is not None


# 5. THEMIS Connector
def test_05_themis_thermal_datasets():
    connector = ThemisConnector(OFFICIAL_NASA_SOURCES["themis"])
    observations = connector.get_observations()
    assert len(observations) >= 3

    ti_obs = next((o for o in observations if o.observation_type == "THERMAL_INERTIA"), None)
    assert ti_obs is not None
    assert ti_obs.thermal_inertia_tiu >= 300.0

    products = asyncio.run(connector.list_products(10))
    assert len(products) >= 3
    for p in products:
        assert p.map_layer_supported is True


# 6. NAIF SPICE Connector
def test_06_naif_spice_geometry_calculation():
    connector = NaifSpiceConnector(OFFICIAL_NASA_SOURCES["naif_spice"])
    geom = connector.compute_geometry(spacecraft_id="mro")
    assert geom.spacecraft_id == "MRO"
    assert -180.0 <= geom.sub_spacecraft_lon <= 180.0
    assert -90.0 <= geom.sub_spacecraft_lat <= 90.0
    assert 0.0 <= geom.solar_incidence_angle_deg <= 180.0
    assert ":" in geom.local_solar_time


# 7. Planetary Analyst's Notebook
def test_07_planetary_notebook_rover_manifests():
    connector = PlanetaryNotebookConnector(OFFICIAL_NASA_SOURCES["planetary_notebook"])
    products = asyncio.run(connector.list_products(10))
    assert len(products) >= 4

    m20_traverse = next((p for p in products if p.product_id == "NOTEBOOK_M20_TRAVERSE_SOL2022"), None)
    assert m20_traverse is not None
    assert m20_traverse.martian_sol == 2022

    cores = next((p for p in products if p.product_id == "NOTEBOOK_M20_SEALED_CORE_SAMPLES"), None)
    assert cores is not None


# 8. PDS Data Releases
def test_08_pds_data_releases_bulletins():
    connector = PdsReleasesConnector(OFFICIAL_NASA_SOURCES["pds_releases"])
    releases = connector.get_releases()
    assert len(releases) >= 5

    rel12 = next((r for r in releases if r.release_id == "PDS_M20_REL12"), None)
    assert rel12 is not None
    assert rel12.mission == "Mars 2020"
    assert rel12.is_processed_in_marspath is True


# 9. Unified Data Catalogue
def test_09_unified_catalog_search_and_coverage():
    catalog = UnifiedDataCatalogService()
    all_prods = asyncio.run(catalog.get_all_products())
    assert len(all_prods) >= 30

    # Search by instrument
    res_hirise = asyncio.run(catalog.search_products(ProductSearchQuery(instrument="HiRISE")))
    assert res_hirise.total_matched >= 2

    # Search by query
    res_meda = asyncio.run(catalog.search_products(ProductSearchQuery(query="MEDA")))
    assert res_meda.total_matched >= 5

    # Coverage summary
    coverage = asyncio.run(catalog.get_coverage_summary())
    assert coverage["total_cataloged_products"] >= 30
    assert coverage["georeferenced_products_count"] >= 15


# 10. Synchronization Service
def test_10_synchronization_service_status():
    registry = DataSourceRegistry()
    catalog = UnifiedDataCatalogService()
    sync = DataSourceSyncService(registry, catalog)

    status = asyncio.run(sync.get_global_status())
    assert status.total_sources == 7
    assert status.connected_count == 7
    assert status.data_ingested_count == 7
    assert status.total_indexed_products >= 30

    res = asyncio.run(sync.synchronize_all(force_refresh=True))
    assert res.success is True
    assert len(res.sources_updated) == 7


# 11. FastAPI Endpoints Integration
def test_11_fastapi_endpoints_data_sources():
    # GET /api/v1/data-sources
    r = client.get("/api/v1/data-sources")
    assert r.status_code == 200
    sources = r.json()
    assert len(sources) == 7

    # GET /api/v1/data-sources/status
    r_status = client.get("/api/v1/data-sources/status")
    assert r_status.status_code == 200
    assert r_status.json()["total_sources"] == 7

    # GET /api/v1/data-sources/nasa_mars_trek
    r_trek = client.get("/api/v1/data-sources/nasa_mars_trek")
    assert r_trek.status_code == 200
    assert r_trek.json()["source_name"] == "NASA Mars Trek"

    # GET /api/v1/data-catalogue
    r_cat = client.get("/api/v1/data-catalogue?limit=10")
    assert r_cat.status_code == 200
    assert len(r_cat.json()) == 10

    # GET /api/v1/data-catalogue/search
    r_search = client.get("/api/v1/data-catalogue/search?query=Jezero")
    assert r_search.status_code == 200
    assert r_search.json()["total_matched"] >= 5

    # GET /api/v1/data-catalogue/coverage
    r_cov = client.get("/api/v1/data-catalogue/coverage")
    assert r_cov.status_code == 200
    assert r_cov.json()["total_cataloged_products"] >= 30

    # GET /api/v1/data-releases
    r_rel = client.get("/api/v1/data-releases")
    assert r_rel.status_code == 200
    assert len(r_rel.json()) >= 5

    # GET /api/v1/data-synchronization/status
    r_sync_stat = client.get("/api/v1/data-synchronization/status")
    assert r_sync_stat.status_code == 200
    assert r_sync_stat.json()["status"] == "OPERATIONAL"

    # POST /api/v1/data-synchronization/refresh
    r_refresh = client.post("/api/v1/data-synchronization/refresh?force=true")
    assert r_refresh.status_code == 200
    assert r_refresh.json()["success"] is True

    # Specialist endpoints
    r_meda = client.get("/api/v1/data-sources/meda/observations")
    assert r_meda.status_code == 200
    assert len(r_meda.json()) >= 5

    r_themis = client.get("/api/v1/data-sources/themis/observations")
    assert r_themis.status_code == 200
    assert len(r_themis.json()) >= 3

    r_spice = client.get("/api/v1/data-sources/naif/geometry?spacecraft_id=mro")
    assert r_spice.status_code == 200
    assert r_spice.json()["spacecraft_id"] == "MRO"
