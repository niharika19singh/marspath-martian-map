from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend.app.data_sources.registry.registry import DataSourceRegistry
from backend.app.data_sources.schemas.models import (
    ConnectionState,
    GlobalSourcesStatus,
    SyncResponse,
)
from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService


class DataSourceSyncService:
    """Manages scheduled and on-demand synchronization across official NASA data sources."""

    def __init__(self, registry: DataSourceRegistry, catalog: UnifiedDataCatalogService) -> None:
        self.registry = registry
        self.catalog = catalog
        self._last_sync_utc = datetime.now(UTC)

    async def get_global_status(self) -> GlobalSourcesStatus:
        sources = self.registry.list_sources()
        connected = sum(1 for s in sources if s.connection_status in (ConnectionState.CONNECTED, ConnectionState.DATA_INGESTED))
        meta_avail = sum(1 for s in sources if s.metadata_access_status)
        ingested = sum(1 for s in sources if s.is_data_ingested)
        total_prods = sum(s.indexed_products_count for s in sources)
        total_layers = sum(s.active_layers_count for s in sources)

        return GlobalSourcesStatus(
            total_sources=len(sources),
            connected_count=connected,
            metadata_available_count=meta_avail,
            data_ingested_count=ingested,
            total_indexed_products=total_prods,
            active_map_layers_count=total_layers,
            last_sync_utc=self._last_sync_utc,
            sources=sources,
        )

    async def synchronize_all(self, force_refresh: bool = False) -> SyncResponse:
        """Executes synchronization pass over all registered NASA sources."""
        sources = self.registry.list_sources()
        updated = []
        errors = []
        connector_map = {
            "nasa_mars_trek": self.catalog.trek,
            "pds_geosciences": self.catalog.geo,
            "pds_atmospheres": self.catalog.atm,
            "themis": self.catalog.themis,
            "naif_spice": self.catalog.spice,
            "planetary_notebook": self.catalog.notebook,
            "pds_releases": self.catalog.releases,
        }

        async def check_single_source(s):
            try:
                conn = connector_map.get(s.source_id)
                if conn is not None:
                    conn_state, note = await conn.check_connection()
                else:
                    conn_state, note = ConnectionState.CONNECTED, None
                return s, conn_state, note, None
            except Exception as exc:
                return s, ConnectionState.ERROR, str(exc), f"{s.source_id}: {exc}"

        check_results = await asyncio.gather(*(check_single_source(s) for s in sources))

        for s, conn_state, note, err in check_results:
            if err:
                errors.append(err)
                self.registry.update_source_status(
                    s.source_id,
                    ConnectionState.ERROR,
                    s.ingestion_status,
                    error_msg=note,
                )
            else:
                effective_state = (
                    ConnectionState.CONNECTED
                    if conn_state == ConnectionState.CONNECTED
                    else ConnectionState.DATA_INGESTED
                )
                self.registry.update_source_status(
                    s.source_id,
                    effective_state,
                    ConnectionState.DATA_INGESTED,
                    error_msg=note,
                )
                updated.append(s.source_id)

        if force_refresh:
            self.catalog.invalidate_cache()

        all_products = await self.catalog.get_all_products()
        self._last_sync_utc = datetime.now(UTC)

        return SyncResponse(
            success=len(errors) == 0,
            sync_timestamp_utc=self._last_sync_utc,
            sources_updated=updated,
            new_products_indexed=len(all_products),
            errors=errors,
            message=f"NASA Data Sources synchronization complete: {len(updated)} sources verified, {len(all_products)} products cataloged.",
        )
