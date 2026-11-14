from __future__ import annotations

import logging
from typing import Any

from backend.app.data_sources.registry import DataSourceRegistry
from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService
from backend.app.data_sources.services.sync_service import DataSourceSyncService
from backend.app.integrations.google_cloud.jobs.base_job import BaseCloudRunJob
from backend.app.integrations.google_cloud.storage.storage_factory import get_storage_adapter

logger = logging.getLogger(__name__)


class NasaCatalogSyncJob(BaseCloudRunJob):
    """
    Cloud Run Job 1 — NASA Catalogue Synchronization.
    Periodically queries configured NASA/PDS data catalogues, detects new products,
    deduplicates against the existing database, and commits updates to storage and catalog.
    """

    name = "nasa_catalog_sync"
    description = "Synchronizes MARSPath planetary catalog with upstream NASA PDS registries"
    timeout_seconds = 600
    memory_limit_mb = 1024
    cpu_limit = "1.0"

    async def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        registry = DataSourceRegistry()
        catalog = UnifiedDataCatalogService()
        sync_service = DataSourceSyncService(registry, catalog)
        storage = get_storage_adapter()

        force = params.get("force_refresh", False) if params else False
        sync_res = await sync_service.synchronize_all(force_refresh=force)

        # Store sync report artifact in catalog/provenance/
        report_data = sync_res.model_dump_json(indent=2).encode("utf-8")
        timestamp_slug = sync_res.sync_timestamp_utc.strftime("%Y%m%d_%H%M%S")
        object_key = f"catalog/provenance/sync_report_{timestamp_slug}.json"
        meta = await storage.upload_bytes(
            object_name=object_key,
            data=report_data,
            content_type="application/json",
            metadata={"job": self.name},
            source_id="pds_releases",
            dataset_provenance="MARSPath Scheduled Catalog Sync Engine",
        )

        all_products = await catalog.get_all_products()

        return {
            "items_processed": len(sync_res.sources_updated),
            "items_succeeded": len(sync_res.sources_updated) - len(sync_res.errors),
            "items_failed": len(sync_res.errors),
            "records_synced": len(all_products),
            "logs": [
                f"Synchronized {len(sync_res.sources_updated)} NASA planetary data sources.",
                f"Identified {sync_res.new_products_indexed} new or updated science products.",
                f"Active indexed catalog count: {len(all_products)} products.",
                f"Sync audit log persisted to storage: {meta.object_name} ({meta.size_bytes} bytes).",
            ],
            "output_artifacts": [object_key],
            "telemetry": {
                "active_catalog_size": len(all_products),
                "sources_verified": len(sync_res.sources_updated),
                "errors_count": len(sync_res.errors),
            },
        }
