# Google Cloud Storage (GCS) Integration & Data Lake Specification

## 1. Overview

MARSPath establishes a unified planetary data lake on Google Cloud Storage (`gs://marspath-data`). To ensure deterministic testing, offline research capability, and complete protection against unexpected egress costs, MARSPath uses an abstract adapter architecture:

- `BaseStorageAdapter`: Abstract contract defining all storage operations.
- `GCSStorageAdapter`: Connects to live GCP buckets using `google-cloud-storage` and ADC credentials.
- `LocalStorageAdapter`: Emulates bucket layout, SHA-256 integrity verification, and signed URLs using local POSIX storage.
- `storage_factory.py`: Instantiates `GCSStorageAdapter` or gracefully falls back to `LocalStorageAdapter`.

---

## 2. Canonical Bucket Directory Architecture

All stored planetary data is strictly organized into canonical directories within `gs://marspath-data`:

```text
gs://marspath-data/
├── raw/                               # Unmodified upstream NASA/PDS primary archives
│   └── nasa/
│       ├── hirise/                    # High-resolution imaging science experiment products (.IMG, .JP2, .tif)
│       ├── ctx/                       # Context Camera regional mosaics and strips
│       ├── meda/                      # Mars 2020 MEDA calibrated surface environmental tables
│       ├── themis/                    # 2001 Mars Odyssey calibrated thermal infrared bands
│       ├── crism/                     # MRO CRISM hyperspectral targeted cubes
│       └── spice/                     # NAIF SPICE planetary ephemeris kernel archives
├── processed/                         # Scientifically validated derivatives
│   ├── imagery/                       # Cloud-Optimized GeoTIFFs (COG) with internal tiling
│   ├── dem/                           # Elevation mosaics, continuous slope, roughness, and hillshades
│   ├── thermal/                       # Thermal inertia ($I$) rasters and wheel-sinkage risk tags
│   ├── mineralogy/                    # Mineral ratio maps (carbonates, clays, ferric oxides)
│   └── environmental/                 # Normalized diurnal weather time-series (nulls preserved)
├── tiles/                             # Multiresolution XYZ map pyramids
│   ├── regional/                      # Mars Trek regional context tiles (z0 - z8)
│   ├── hirise/                        # 0.25 m/pixel localized traverse pyramids (z9 - z14)
│   ├── ctx/                           # 6 m/pixel intermediate contextual pyramids
│   └── terrain/                       # Colorized slope and elevation overlay tiles
├── catalog/                           # Search metadata and provenance registries
│   ├── datasets/                      # Registered NASA data source profiles
│   ├── observations/                  # Indexed orbital and surface observation records
│   └── provenance/                    # Cryptographic sync logs, audit reports, and DOI mappings
└── exports/                           # User-generated mission planning outputs
    ├── missions/                      # Mission summary bundles
    └── routes/                        # Planned traverse corridors in GeoJSON format
```

---

## 3. Storage Operations & API Contract

### Methods Supported by BaseStorageAdapter:

```python
async def upload_bytes(object_name: str, data: bytes, content_type: str, ...) -> ObjectMetadata: ...
async def upload_file(object_name: str, file_path: Path, ...) -> ObjectMetadata: ...
async def download_bytes(object_name: str) -> bytes: ...
async def download_file(object_name: str, destination_path: Path) -> Path: ...
async def get_metadata(object_name: str) -> ObjectMetadata | None: ...
async def generate_signed_url(object_name: str, expiration_seconds: int = 900) -> str: ...
async def list_objects(prefix: str = "", limit: int = 100) -> list[ObjectMetadata]: ...
async def delete_object(object_name: str) -> bool: ...
async def exists(object_name: str) -> bool: ...
async def get_status() -> StorageStatus: ...
```

---

## 4. Metadata Tagging & Provenance Preservation

Every stored asset carries strict metadata headers matching `ObjectMetadata`:
- `sha256_hash`: 64-character hex digest computed over binary contents to detect tampering or transmission corruption.
- `md5_hash`: Base64 or hex digest for GCS integrity check.
- `source_id`: Formal NASA source identifier (`pds_geosciences`, `mars_trek`, `themis_viewer`, `pds_atmospheres`).
- `dataset_provenance`: Archival attribution citation.
- `custom_metadata`: Scientific attributes (e.g. `sol`, `instrument`, `resolution_m_per_px`, `product_id`).

In `LocalStorageAdapter`, metadata is preserved in a companion JSON sidecar file (`.meta.json`) adjacent to the asset.

---

## 5. Signed URLs & Secure Access

- When GCS is enabled, `generate_signed_url` creates official **Google Cloud V4 Signed URLs** with time-limited read access (default 15 minutes), preventing public bucket exposure.
- In local fallback mode, `generate_signed_url` generates an authenticated internal stream endpoint (`/api/v1/cloud/storage/download?object_name=...`).
