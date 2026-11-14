from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from backend.app.integrations.google_cloud.storage.metadata import ObjectMetadata, StorageStatus


class BaseStorageAdapter(ABC):
    """Abstract interface defining required storage operations for planetary datasets."""

    @abstractmethod
    async def upload_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        """Uploads raw binary bytes to the storage location."""
        pass

    @abstractmethod
    async def upload_file(
        self,
        object_name: str,
        file_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        """Uploads a local file to the storage location."""
        pass

    @abstractmethod
    async def download_bytes(self, object_name: str) -> bytes:
        """Retrieves object content as raw binary bytes."""
        pass

    @abstractmethod
    async def download_file(self, object_name: str, destination_path: str | Path) -> Path:
        """Downloads object content directly to a local file destination."""
        pass

    @abstractmethod
    async def get_metadata(self, object_name: str) -> ObjectMetadata | None:
        """Retrieves scientific metadata, hashes, and attributes for an object."""
        pass

    @abstractmethod
    async def generate_signed_url(
        self,
        object_name: str,
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """Generates a short-lived URL for controlled browser access without exposing credentials."""
        pass

    @abstractmethod
    async def list_objects(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> list[ObjectMetadata]:
        """Lists objects under a specific namespace/prefix in the bucket."""
        pass

    @abstractmethod
    async def delete_object(self, object_name: str) -> bool:
        """Deletes an object from the bucket."""
        pass

    @abstractmethod
    async def exists(self, object_name: str) -> bool:
        """Checks whether an object exists in storage."""
        pass

    @abstractmethod
    async def get_status(self) -> StorageStatus:
        """Retrieves overall connection status, object counts, and security metrics."""
        pass
