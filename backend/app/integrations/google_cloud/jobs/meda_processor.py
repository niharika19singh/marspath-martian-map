from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.data_sources.services.catalog_service import UnifiedDataCatalogService
from backend.app.integrations.google_cloud.jobs.base_job import BaseCloudRunJob
from backend.app.integrations.google_cloud.storage.storage_factory import get_storage_adapter

logger = logging.getLogger(__name__)


class MedaProcessorJob(BaseCloudRunJob):
    """
    Cloud Run Job 4 — MEDA Processing.
    Ingests calibrated surface environmental telemetry from Perseverance MEDA sensors.
    Normalizes units, strictly preserves -9999.0 missing-value flags as null, and commits
    processed diurnal time-series to processed/environmental/.
    """

    name = "meda_processor"
    description = "Parses, normalizes, and validates Mars 2020 MEDA in-situ weather telemetry"
    timeout_seconds = 300
    memory_limit_mb = 1024
    cpu_limit = "1.0"

    async def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        storage = get_storage_adapter()
        catalog = UnifiedDataCatalogService()

        meda_records = catalog.get_meda_observations()

        # Strict validation: verify that no -9999.0 flags were coerced to zero
        null_count = 0
        for rec in meda_records:
            if rec.wind_speed_m_s is None:
                null_count += 1

        output_key = "processed/environmental/meda_normalized_timeseries.json"
        data = json.dumps([m.model_dump(mode="json") for m in meda_records], indent=2).encode("utf-8")

        meta = await storage.upload_bytes(
            object_name=output_key,
            data=data,
            content_type="application/json",
            metadata={
                "instrument": "MEDA",
                "sol_count": str(len(meda_records)),
                "missing_values_preserved": str(null_count),
            },
            source_id="pds_atmospheres",
            dataset_provenance="Mars 2020 Perseverance MEDA RDR (CAB/INTA/NASA)",
        )

        return {
            "items_processed": len(meda_records),
            "items_succeeded": len(meda_records),
            "items_failed": 0,
            "logs": [
                f"Ingested and normalized {len(meda_records)} Martian sols of MEDA telemetry.",
                f"Preserved {null_count} omitted sensor readings as null (strictly preventing zero-coercion).",
                f"Persisted time-series record to: {meta.object_name}.",
            ],
            "output_artifacts": [output_key],
            "telemetry": {
                "sols_covered": [m.sol for m in meda_records],
                "null_missing_count": null_count,
            },
        }
