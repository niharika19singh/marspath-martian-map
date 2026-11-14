from __future__ import annotations

from functools import lru_cache

from backend.app.core.config import Settings, get_settings
from backend.app.integrations.google_cloud.storage.base import BaseStorageAdapter
from backend.app.integrations.google_cloud.storage.gcs_storage import GCSStorageAdapter
from backend.app.integrations.google_cloud.storage.local_storage import LocalStorageAdapter


@lru_cache
def get_storage_adapter(settings: Settings | None = None) -> BaseStorageAdapter:
    """
    Factory function returning the active storage adapter.
    If MARSPATH_GCS_ENABLED=true and credentials/project are configured, returns GCSStorageAdapter.
    Otherwise, returns LocalStorageAdapter for isolated, zero-cost execution.
    """
    s = settings or get_settings()

    if s.GCS_ENABLED and (s.GOOGLE_CLOUD_PROJECT or s.GOOGLE_APPLICATION_CREDENTIALS):
        return GCSStorageAdapter(
            project_id=s.GOOGLE_CLOUD_PROJECT,
            bucket_name=s.GCS_BUCKET,
            location=s.GOOGLE_CLOUD_LOCATION,
            credentials_path=s.GOOGLE_APPLICATION_CREDENTIALS,
            local_fallback_root=s.GCS_LOCAL_STORAGE_ROOT,
            is_enabled=True,
        )

    # Clean local filesystem fallback
    return LocalStorageAdapter(
        root_dir=s.GCS_LOCAL_STORAGE_ROOT,
        bucket_name=s.GCS_BUCKET,
    )
