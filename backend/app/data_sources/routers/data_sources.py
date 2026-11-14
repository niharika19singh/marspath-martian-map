from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.data_sources.registry.registry import DataSourceRegistry
from backend.app.data_sources.schemas.models import (
    DataProduct,
    DataRelease,
    DataSourceEntry,
    GlobalSourcesStatus,
    MedaObservation,
    ProductSearchQuery,
    ProductSearchResponse,
    SpiceGeometryResult,
    SyncResponse,
    ThemisObservation,
)
from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService
from backend.app.data_sources.services.sync_service import DataSourceSyncService

router = APIRouter(tags=["NASA Data Sources & Intelligence"])

_registry = DataSourceRegistry()
_catalog = UnifiedDataCatalogService()
_sync = DataSourceSyncService(_registry, _catalog)


# --- 1. DATA SOURCES ENDPOINTS ---


@router.get(
    "/data-sources",
    response_model=list[DataSourceEntry],
    summary="List all seven official NASA data sources",
)
async def list_data_sources() -> list[DataSourceEntry]:
    """Returns registry entries for all seven official NASA planetary data sources."""
    return _registry.list_sources()


@router.get(
    "/data-sources/status",
    response_model=GlobalSourcesStatus,
    summary="Global status summary across all NASA data sources",
)
async def get_data_sources_status() -> GlobalSourcesStatus:
    """Returns high-level status metrics: connected count, metadata availability, and ingested status."""
    return await _sync.get_global_status()


@router.get(
    "/data-sources/{source_id}",
    response_model=DataSourceEntry,
    summary="Retrieve details for a single NASA data source",
)
async def get_data_source(source_id: str) -> DataSourceEntry:
    """Retrieves authoritative registry entry, capabilities, and connection status for a specific source."""
    entry = _registry.get_source(source_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NASA data source '{source_id}' not found in registry.",
        )
    return entry


# --- 2. AUXILIARY SCIENTIFIC SPECIALIST ENDPOINTS ---


@router.get(
    "/data-sources/meda/observations",
    response_model=list[MedaObservation],
    summary="Retrieve in-situ atmospheric telemetry from Perseverance MEDA",
)
async def get_meda_observations() -> list[MedaObservation]:
    """Retrieves calibrated timeseries observations (ATS, PS, RDS, RHS, TIRS, WIND) from Perseverance."""
    return _catalog.get_meda_observations()


@router.get(
    "/data-sources/themis/observations",
    response_model=list[ThemisObservation],
    summary="Retrieve calibrated thermal observations and thermal inertia",
)
async def get_themis_observations() -> list[ThemisObservation]:
    """Retrieves THEMIS Day IR, Night IR, and derived thermal inertia observations for the Jezero region."""
    return _catalog.get_themis_observations()


@router.get(
    "/data-sources/naif/geometry",
    response_model=SpiceGeometryResult,
    summary="Compute SPICE spacecraft observation and illumination geometry",
)
async def compute_spice_geometry(
    spacecraft_id: str = Query("mro", description="Spacecraft ID (e.g. mro, ody, m2020)"),
) -> SpiceGeometryResult:
    """Calculates sub-spacecraft point, sub-solar point, solar incidence angle, and local solar time."""
    return _catalog.compute_spice_geometry(spacecraft_id)


# --- 3. UNIFIED DATA CATALOGUE ENDPOINTS ---


@router.get(
    "/data-catalogue",
    response_model=list[DataProduct],
    summary="Enumerate all cataloged NASA data products",
)
async def list_data_catalogue(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[DataProduct]:
    """Lists cataloged scientific products across all seven sources with pagination."""
    all_products = await _catalog.get_all_products()
    return all_products[offset : offset + limit]


@router.get(
    "/data-catalogue/search",
    response_model=ProductSearchResponse,
    summary="Search unified NASA data catalogue with multi-parameter filtering",
)
async def search_data_catalogue(
    query: str | None = Query(None, description="Free-text search query across title, description, product ID"),
    instrument: str | None = Query(None, description="Filter by instrument (HiRISE, CTX, CRISM, SHARAD, MEDA, THEMIS)"),
    spacecraft: str | None = Query(None, description="Filter by spacecraft (MRO, Mars 2020, MSL, Odyssey)"),
    source_id: str | None = Query(None, description="Filter by originating NASA source ID"),
    product_type: str | None = Query(None, description="Filter by product type (IMAGERY_RDR, TERRAIN_DTM, ATMOSPHERIC_TIMESERIES, etc.)"),
    min_sol: int | None = Query(None, description="Minimum Martian sol"),
    max_sol: int | None = Query(None, description="Maximum Martian sol"),
    min_lon: float | None = Query(None, description="Bounding box min longitude (East)"),
    max_lon: float | None = Query(None, description="Bounding box max longitude (East)"),
    min_lat: float | None = Query(None, description="Bounding box min latitude (North)"),
    max_lat: float | None = Query(None, description="Bounding box max latitude (North)"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ProductSearchResponse:
    """Searches and filters products across all seven NASA sources with spatial and instrument constraints."""
    search_q = ProductSearchQuery(
        query=query,
        instrument=instrument,
        spacecraft=spacecraft,
        source_id=source_id,
        product_type=product_type,
        min_sol=min_sol,
        max_sol=max_sol,
        min_lon=min_lon,
        max_lon=max_lon,
        min_lat=min_lat,
        max_lat=max_lat,
        limit=limit,
        offset=offset,
    )
    return await _catalog.search_products(search_q)


@router.get(
    "/data-catalogue/coverage",
    response_model=dict[str, Any],
    summary="Retrieve spatial and instrument coverage statistics",
)
async def get_catalogue_coverage() -> dict[str, Any]:
    """Returns spatial and instrument coverage summary across cataloged NASA datasets."""
    return await _catalog.get_coverage_summary()


@router.get(
    "/data-catalogue/{product_id}",
    response_model=DataProduct,
    summary="Retrieve metadata for a specific data product",
)
async def get_catalogue_product(product_id: str) -> DataProduct:
    """Retrieves full scientific metadata, spatial footprint, and download links for a specific product."""
    prod = await _catalog.get_product_by_id(product_id)
    if not prod:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Data product '{product_id}' not found in unified NASA catalogue.",
        )
    return prod


# --- 4. NASA DATA RELEASES ENDPOINTS ---


@router.get(
    "/data-releases",
    response_model=list[DataRelease],
    summary="List official NASA PDS data releases",
)
async def list_data_releases() -> list[DataRelease]:
    """Returns monitored quarterly and major PDS data release records for MRO, Mars 2020, MSL, and Odyssey."""
    return _catalog.get_pds_releases()


# --- 5. SYNCHRONIZATION ENDPOINTS ---


@router.get(
    "/data-synchronization/status",
    response_model=dict[str, Any],
    summary="Get data synchronization engine status",
)
async def get_sync_status() -> dict[str, Any]:
    """Returns status of the multi-source synchronization engine and last execution timestamp."""
    global_status = await _sync.get_global_status()
    return {
        "engine": "NASA Data Sources Synchronization Engine",
        "status": "OPERATIONAL",
        "last_sync_utc": global_status.last_sync_utc.isoformat(),
        "total_sources_monitored": global_status.total_sources,
        "connected_sources": global_status.connected_count,
        "total_indexed_products": global_status.total_indexed_products,
        "active_map_layers": global_status.active_map_layers_count,
    }


@router.post(
    "/data-synchronization/refresh",
    response_model=SyncResponse,
    summary="Trigger operational re-synchronization across all NASA sources",
)
async def refresh_synchronization(
    force: bool = Query(True, description="Force metadata cache invalidation"),
) -> SyncResponse:
    """Forces an operational re-synchronization pass across all seven NASA data sources."""
    return await _sync.synchronize_all(force_refresh=force)
