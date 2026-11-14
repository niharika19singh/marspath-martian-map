from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

from backend.app.integrations.google_cloud.storage.base import BaseStorageAdapter
from backend.app.integrations.google_cloud.storage.metadata import ObjectMetadata, StorageStatus


class LocalStorageAdapter(BaseStorageAdapter):
    """
    Local filesystem implementation of BaseStorageAdapter.
    Mimics Google Cloud Storage bucket structure locally for development, CI testing,
    and offline scientific operation without cloud egress charges.
    """

    def __init__(self, root_dir: str | Path = "backend/app/data/storage", bucket_name: str = "marspath-data") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.bucket_name = bucket_name
        self.bucket_root = self.root_dir / self.bucket_name
        self.bucket_root.mkdir(parents=True, exist_ok=True)

        # Initialize canonical bucket directory architecture
        for section in [
            "raw/nasa/hirise",
            "raw/nasa/ctx",
            "raw/nasa/meda",
            "raw/nasa/themis",
            "raw/nasa/crism",
            "raw/nasa/spice",
            "processed/imagery",
            "processed/dem",
            "processed/thermal",
            "processed/mineralogy",
            "processed/environmental",
            "tiles/regional",
            "tiles/hirise",
            "tiles/ctx",
            "tiles/terrain",
            "catalog/datasets",
            "catalog/observations",
            "catalog/provenance",
            "exports/missions",
            "exports/routes",
        ]:
            (self.bucket_root / section).mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, object_name: str) -> Path:
        """Resolves an object name within the bucket, sanitizing against directory traversal."""
        clean_name = object_name.lstrip("/").replace("\\", "/")
        path = (self.bucket_root / clean_name).resolve()
        if not str(path).startswith(str(self.bucket_root)):
            raise ValueError(f"Invalid path traversal attempt for object: '{object_name}'")
        return path

    def _meta_path(self, file_path: Path) -> Path:
        """Returns the sidecar path for metadata persistence."""
        return file_path.with_name(f"{file_path.name}.meta.json")

    def _calculate_hashes(self, data: bytes) -> tuple[str, str]:
        """Calculates MD5 and SHA-256 hex digests."""
        md5 = hashlib.md5(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()
        return md5, sha256

    def _save_metadata_sidecar(self, target_file: Path, meta: ObjectMetadata) -> None:
        """Saves metadata sidecar to disk."""
        meta_file = self._meta_path(target_file)
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta.model_dump(mode="json"), f, indent=2)

    def _read_metadata_sidecar(self, target_file: Path, object_name: str) -> ObjectMetadata | None:
        """Reads metadata sidecar if present, otherwise constructs default from filesystem attributes."""
        if not target_file.exists() or target_file.is_dir():
            return None

        meta_file = self._meta_path(target_file)
        if meta_file.exists():
            try:
                with open(meta_file, encoding="utf-8") as f:
                    data = json.load(f)
                    return ObjectMetadata.model_validate(data)
            except Exception:
                pass

        # Fallback to computing on the fly
        stat = target_file.stat()
        content, _ = mimetypes.guess_type(target_file.name)
        with open(target_file, "rb") as f:
            raw = f.read(65536)
            md5 = hashlib.md5(raw).hexdigest()
            sha256 = hashlib.sha256(raw).hexdigest()

        return ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=stat.st_size,
            content_type=content or "application/octet-stream",
            md5_hash=md5,
            sha256_hash=sha256,
            created_at=datetime.fromtimestamp(stat.st_ctime, tz=UTC),
            updated_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            custom_metadata={},
            storage_class="STANDARD",
        )

    async def upload_bytes(
        self,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        target_path = self._resolve_path(object_name)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        with open(target_path, "wb") as f:
            f.write(data)

        md5, sha256 = self._calculate_hashes(data)
        now = datetime.now(UTC)
        meta = ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=len(data),
            content_type=content_type,
            md5_hash=md5,
            sha256_hash=sha256,
            created_at=now,
            updated_at=now,
            custom_metadata=metadata or {},
            source_id=source_id,
            dataset_provenance=dataset_provenance,
            etag=f"W/'{md5}'",
            storage_class="STANDARD",
        )
        self._save_metadata_sidecar(target_path, meta)
        return meta

    async def upload_file(
        self,
        object_name: str,
        file_path: str | Path,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
        source_id: str | None = None,
        dataset_provenance: str | None = None,
    ) -> ObjectMetadata:
        src = Path(file_path).resolve()
        if not src.exists() or not src.is_file():
            raise FileNotFoundError(f"Source file not found for upload: '{src}'")

        target_path = self._resolve_path(object_name)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, target_path)

        with open(target_path, "rb") as f:
            data = f.read()

        guessed_type, _ = mimetypes.guess_type(src.name)
        c_type = content_type or guessed_type or "application/octet-stream"

        md5, sha256 = self._calculate_hashes(data)
        now = datetime.now(UTC)
        meta = ObjectMetadata(
            object_name=object_name,
            bucket=self.bucket_name,
            size_bytes=len(data),
            content_type=c_type,
            md5_hash=md5,
            sha256_hash=sha256,
            created_at=now,
            updated_at=now,
            custom_metadata=metadata or {},
            source_id=source_id,
            dataset_provenance=dataset_provenance,
            etag=f"W/'{md5}'",
            storage_class="STANDARD",
        )
        self._save_metadata_sidecar(target_path, meta)
        return meta

    async def download_bytes(self, object_name: str) -> bytes:
        target_path = self._resolve_path(object_name)
        if not target_path.exists() or target_path.is_dir():
            raise FileNotFoundError(f"Object not found in local storage: '{object_name}'")

        with open(target_path, "rb") as f:
            return f.read()

    async def download_file(self, object_name: str, destination_path: str | Path) -> Path:
        target_path = self._resolve_path(object_name)
        if not target_path.exists() or target_path.is_dir():
            raise FileNotFoundError(f"Object not found in local storage: '{object_name}'")

        dest = Path(destination_path).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, dest)
        return dest

    async def get_metadata(self, object_name: str) -> ObjectMetadata | None:
        target_path = self._resolve_path(object_name)
        return self._read_metadata_sidecar(target_path, object_name)

    async def generate_signed_url(
        self,
        object_name: str,
        expiration_seconds: int = 3600,
        method: str = "GET",
    ) -> str:
        """Simulates a short-lived signed access URL pointing to the local static/download endpoint."""
        target_path = self._resolve_path(object_name)
        if not target_path.exists():
            raise FileNotFoundError(f"Object not found for signed URL: '{object_name}'")

        token = hashlib.sha256(f"{object_name}:{expiration_seconds}:{target_path.stat().st_mtime}".encode()).hexdigest()[:16]
        return f"/api/v1/cloud/storage/download?object={object_name}&token={token}&expires={expiration_seconds}"

    async def list_objects(
        self,
        prefix: str = "",
        limit: int = 100,
    ) -> list[ObjectMetadata]:
        clean_prefix = prefix.lstrip("/").replace("\\", "/")
        results: list[ObjectMetadata] = []

        if not self.bucket_root.exists():
            return results

        for root, _, files in os.walk(self.bucket_root):
            for file in files:
                if file.endswith(".meta.json"):
                    continue
                full_path = Path(root) / file
                rel_path = full_path.relative_to(self.bucket_root).as_posix()

                if clean_prefix and not rel_path.startswith(clean_prefix):
                    continue

                meta = self._read_metadata_sidecar(full_path, rel_path)
                if meta:
                    results.append(meta)
                    if len(results) >= limit:
                        return results

        return results

    async def delete_object(self, object_name: str) -> bool:
        target_path = self._resolve_path(object_name)
        if not target_path.exists():
            return False

        meta_file = self._meta_path(target_path)
        if meta_file.exists():
            meta_file.unlink()

        target_path.unlink()
        return True

    async def exists(self, object_name: str) -> bool:
        target_path = self._resolve_path(object_name)
        return target_path.exists() and target_path.is_file()

    async def get_status(self) -> StorageStatus:
        total_objects = 0
        total_bytes = 0

        if self.bucket_root.exists():
            for root, _, files in os.walk(self.bucket_root):
                for file in files:
                    if file.endswith(".meta.json"):
                        continue
                    p = Path(root) / file
                    try:
                        total_bytes += p.stat().st_size
                        total_objects += 1
                    except OSError:
                        pass

        return StorageStatus(
            provider="local_filesystem",
            is_connected=True,
            bucket=self.bucket_name,
            total_objects=total_objects,
            total_bytes=total_bytes,
            root_path=str(self.bucket_root),
            public_access_prevention="enforced_local_sandbox",
            lifecycle_rules_count=3,
            details={
                "storage_backend": "LocalStorageAdapter (POSIX filesystem)",
                "root_directory": str(self.root_dir),
                "isolated_architecture": True,
                "supported_instruments": ["HiRISE", "CTX", "MEDA", "THEMIS", "CRISM", "SPICE"],
            },
        )
