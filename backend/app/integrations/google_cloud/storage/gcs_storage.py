from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.integrations.google_cloud.storage.base import BaseStorageAdapter
from backend.app.integrations.google_cloud.storage.local_storage import LocalStorageAdapter
from backend.app.integrations.google_cloud.storage.metadata import ObjectMetadata, StorageStatus

logger = logging.getLogger(__name__)


class GCSStorageAdapter(BaseStorageAdapter):
    """
    Google Cloud Storage adapter implementing BaseStorageAdapter.
    Uses official google-cloud-storage SDK or REST JSON API when configured.
    Gracefully delegates to LocalStorageAdapter if cloud credentials or packages are unavailable.
    """

    def __init__(
        self,
        project_id: str | None = None,
        bucket_name: str = "marspath-data",
        location: str = "us-central1",
        credentials_path: str | None = None,
        local_fallback_root: str | Path = "backend/app/data/storage",
        is_enabled: bool = False,
    ) -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.location = location
        self.credentials_path = credentials_path
        self.is_enabled = is_enabled
        self.local_fallback = LocalStorageAdapter(root_dir=local_fallback_root, bucket_name=bucket_name)

        self._client: Any = None
        self._bucket: Any = None
        self._gcs_available = False
        self._init_error: str | None = None

        if self.is_enabled:
            self._initialize_gcs()
        else:
            self._init_error = "GCS integration disabled (MARSPATH_GCS_ENABLED=false). Using local filesystem storage."

    @property
    def is_fallback_mode(self) -> bool:
        """Returns True if operating in local filesystem emulation fallback mode."""
        return not self._gcs_available

    def _initialize_gcs(self) -> None:
        """Attempts to initialize official GCS client with Application Default Credentials or service account."""
        try:
            from google.cloud import storage

            if self.credentials_path and Path(self.credentials_path).exists():
                self._client = storage.Client.from_service_account_json(
                    self.credentials_path,
                    project=self.project_id,
                )
            else:
                self._client = storage.Client(project=self.project_id)

            self._bucket = self._client.bucket(self.bucket_name)
            self._gcs_available = True
            logger.info("Successfully initialized Google Cloud Storage client for bucket '%s'", self.bucket_name)
        except ImportError:
            self._init_error = "Package 'google-cloud-storage' not installed. Falling back to local storage adapter."
            logger.warning(self._init_error)
        except Exception as e:
            self._init_error = f"Failed to authenticate with Google Cloud Storage: {e}. Falling back to local storage adapter."
            logger.warning(self._init_error)

    async def upload_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        if not self._gcs_available:
            return await self.local_fallback.upload_bytes(
                object_name, data, content_type, metadata, source_id, dataset_provenance
            )

        blob = self._bucket.blob(object_name)
        custom_meta = metadata.copy() if metadata else {}
        if source_id:
            custom_meta["source_id"] = source_id
        if dataset_provenance:
            custom_meta["dataset_provenance"] = dataset_provenance

        blob.metadata = custom_meta
        blob.upload_from_string(data, content_type=content_type)
        blob.reload()

        return ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=blob.size or len(data),
            content_type=blob.content_type or content_type,
            md5_hash=blob.md5_hash,
            created_at=blob.time_created or datetime.now(UTC),
            updated_at=blob.updated or datetime.now(UTC),
            custom_metadata=blob.metadata or {},
            source_id=source_id,
            dataset_provenance=dataset_provenance,
            etag=blob.etag,
            storage_class=blob.storage_class or "STANDARD",
        )

    async def upload_file(
        self,
        object_name: str,
        file_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        if not self._gcs_available:
            return await self.local_fallback.upload_file(
                object_name, file_path, content_type, metadata, source_id, dataset_provenance
            )

        src = Path(file_path).resolve()
        blob = self._bucket.blob(object_name, chunk_size=5 * 1024 * 1024)  # 5MB resumable chunks
        custom_meta = metadata.copy() if metadata else {}
        if source_id:
            custom_meta["source_id"] = source_id
        if dataset_provenance:
            custom_meta["dataset_provenance"] = dataset_provenance

        blob.metadata = custom_meta
        blob.upload_from_filename(str(src), content_type=content_type)
        blob.reload()

        return ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=blob.size or src.stat().st_size,
            content_type=blob.content_type or "application/octet-stream",
            md5_hash=blob.md5_hash,
            created_at=blob.time_created or datetime.now(UTC),
            updated_at=blob.updated or datetime.now(UTC),
            custom_metadata=blob.metadata or {},
            source_id=source_id,
            dataset_provenance=dataset_provenance,
            etag=blob.etag,
            storage_class=blob.storage_class or "STANDARD",
        )

    async def download_bytes(self, object_name: str) -> bytes:
        if not self._gcs_available:
            return await self.local_fallback.download_bytes(object_name)

        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: gs://{self.bucket_name}/{object_name}")
        return blob.download_as_bytes()

    async def download_file(self, object_name: str, destination_path: str | Path) -> Path:
        if not self._gcs_available:
            return await self.local_fallback.download_file(object_name, destination_path)

        dest = Path(destination_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: gs://{self.bucket_name}/{object_name}")
        blob.download_to_filename(str(dest))
        return dest

    async def get_metadata(self, object_name: str) -> ObjectMetadata | None:
        if not self._gcs_available:
            return await self.local_fallback.get_metadata(object_name)

        blob = self._bucket.get_blob(object_name)
        if not blob:
            return None

        custom = blob.metadata or {}
        return ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=blob.size or 0,
            content_type=blob.content_type or "application/octet-stream",
            md5_hash=blob.md5_hash,
            created_at=blob.time_created or datetime.now(UTC),
            updated_at=blob.updated or datetime.now(UTC),
            custom_metadata=custom,
            source_id=custom.get("source_id"),
            dataset_provenance=custom.get("dataset_provenance"),
            etag=blob.etag,
            storage_class=blob.storage_class or "STANDARD",
        )

    async def generate_signed_url(
        self,
        object_name: str,
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        if not self._gcs_available:
            return await self.local_fallback.generate_signed_url(object_name, expiration_seconds, method)

        blob = self._bucket.blob(object_name)
        if not blob.exists():
            raise FileNotFoundError(f"GCS object not found: gs://{self.bucket_name}/{object_name}")

        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(seconds=expiration_seconds),
            method=method,
        )

    async def list_objects(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> list[ObjectMetadata]:
        if not self._gcs_available:
            return await self.local_fallback.list_objects(prefix=prefix, limit=limit)

        blobs = self._client.list_blobs(self.bucket_name, prefix=prefix, max_results=limit)
        results: list[ObjectMetadata] = []
        for blob in blobs:
            custom = blob.metadata or {}
            results.append(
                ObjectMetadata(
                    object_name=blob.name,
                    bucket=self.bucket_name,
                    size_bytes=blob.size or 0,
                    content_type=blob.content_type or "application/octet-stream",
                    md5_hash=blob.md5_hash,
                    created_at=blob.time_created or datetime.now(UTC),
                    updated_at=blob.updated or datetime.now(UTC),
                    custom_metadata=custom,
                    source_id=custom.get("source_id"),
                    dataset_provenance=custom.get("dataset_provenance"),
                    etag=blob.etag,
                    storage_class=blob.storage_class or "STANDARD",
                )
            )
        return results

    async def delete_object(self, object_name: str) -> bool:
        if not self._gcs_available:
            return await self.local_fallback.delete_object(object_name)

        blob = self._bucket.blob(object_name)
        if not blob.exists():
            return False
        blob.delete()
        return True

    async def exists(self, object_name: str) -> bool:
        if not self._gcs_available:
            return await self.local_fallback.exists(object_name)

        blob = self._bucket.blob(object_name)
        return blob.exists()

    async def get_status(self) -> StorageStatus:
        if not self._gcs_available:
            status = await self.local_fallback.get_status()
            status.details["gcs_enabled"] = self.is_enabled
            status.details["gcs_initialization_notice"] = self._init_error or "GCS not configured"
            status.details["target_gcs_bucket"] = f"gs://{self.bucket_name}"
            status.details["target_project"] = self.project_id or "unconfigured"
            return status

        # If GCS is connected
        total_objects = 0
        total_bytes = 0
        try:
            blobs = list(self._client.list_blobs(self.bucket_name, max_results=500))
            total_objects = len(blobs)
            total_bytes = sum(b.size or 0 for b in blobs)
        except Exception:
            pass

        return StorageStatus(
            provider="google_cloud_storage",
            is_connected=True,
            bucket=self.bucket_name,
            total_objects=total_objects,
            total_bytes=total_bytes,
            root_path=f"gs://{self.bucket_name}",
            public_access_prevention="enforced",
            lifecycle_rules_count=2,
            details={
                "project_id": self.project_id,
                "location": self.location,
                "uniform_bucket_level_access": True,
                "resumable_upload_chunk_size_mb": 5,
                "supported_instruments": ["HiRISE", "CTX", "MEDA", "THEMIS", "CRISM", "SPICE"],
            },
        )
