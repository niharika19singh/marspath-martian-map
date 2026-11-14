from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ObjectMetadata(BaseModel):
    """Metadata describing a stored scientific object in GCS or local storage."""

    object_name: str = Field(description="Logical object key in bucket, e.g. 'raw/nasa/hirise/ESP_069176_1985.tif'")
    bucket: str = Field(default="marspath-data", description="Storage bucket identifier")
    size_bytes: int = Field(default=0, ge=0, description="Size of object in bytes")
    content_type: str = Field(default="application/octet-stream", description="MIME content type")
    md5_hash: str | None = Field(default=None, description="MD5 hash hex digest for integrity verification")
    sha256_hash: str | None = Field(default=None, description="SHA-256 hash hex digest for provenance authentication")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    custom_metadata: dict[str, str] = Field(default_factory=dict, description="Custom scientific key-value attributes")
    source_id: str | None = Field(default=None, description="NASA source ID, e.g. 'pds_geosciences', 'mars_trek'")
    dataset_provenance: str | None = Field(default=None, description="DOI, mission, or instrument provenance string")
    etag: str | None = None
    storage_class: str = Field(default="STANDARD", description="GCS storage tier, e.g. STANDARD, NEARLINE, COLDLINE")


class StorageStatus(BaseModel):
    """Operational status and metrics of the storage subsystem."""

    provider: str = Field(description="'google_cloud_storage' or 'local_filesystem'")
    is_connected: bool = Field(description="True if storage backend is accessible and operational")
    bucket: str = Field(description="Active bucket name or root namespace")
    total_objects: int = Field(default=0, ge=0)
    total_bytes: int = Field(default=0, ge=0)
    root_path: str = Field(description="Local path or gs:// URI")
    public_access_prevention: str = Field(default="enforced", description="Bucket security posture")
    lifecycle_rules_count: int = Field(default=0, ge=0)
    details: dict[str, Any] = Field(default_factory=dict)
