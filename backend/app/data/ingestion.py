"""
NASA / USGS Planetary Data Ingestion Pipeline for Jezero Crater DEM.

Separates local file integrity (SHA-256) from authoritative source authenticity:
1. When ingesting from a local full-product file, the source file's actual bytes are
   hashed (MD5 & SHA-256) and checked against `DATA_CATALOG_MANIFEST`. Only if the
   computed source checksum matches an official catalog entry is the extract marked
   `verified_source`. Unverified or synthetic local files are marked
   `valid_numeric_raster_unverified_source` and never receive official USGS product IDs.
2. When extracting a spatial sub-window via HTTP Range requests (`/vsicurl/`) from the
   official USGS HTTPS endpoint, full 11.38 GB archive checksumming is impractical.
   The resulting extract is honestly marked `official_endpoint_retrieved_checksum_unverified`
   with `source_checksum_verified: False` and `local_integrity_verified: True`.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.data.manifest import DATA_CATALOG_MANIFEST, verify_manifest_provenance

logger = logging.getLogger("marspath.ingestion")

# Authoritative upstream catalog metadata (Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2)
USGS_MOLA_HRSC_PRODUCT_ID = "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
USGS_MOLA_HRSC_PRODUCT_NAME = "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
USGS_MOLA_HRSC_LANDING_PAGE = (
    "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m"
)
USGS_MOLA_HRSC_GLOBAL_URL = "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif"
USGS_MOLA_HRSC_BACKUP_URL = "https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif"
USGS_MOLA_HRSC_MD5 = "e98092a06bea74d5ec9a704dcd1fe318"
USGS_MOLA_HRSC_PDS3_LBL = "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/99f5a18a-b4fb-4e87-8417-7408d8440651/download/mars_hrsc_mola_blenddem_global_200mp_v2_pds3.lbl"
USGS_MOLA_HRSC_ISIS3_LBL = "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/mars_hrsc_mola_blenddem_global_200mp_v2.lbl"

OFFICIAL_USGS_ENDPOINTS = {
    USGS_MOLA_HRSC_GLOBAL_URL,
    USGS_MOLA_HRSC_BACKUP_URL,
}

# Default Jezero Crater analysis envelope
DEFAULT_JEZERO_BOUNDS = (77.15, 18.10, 78.00, 18.70)  # min_lon, min_lat, max_lon, max_lat
DEFAULT_OUTPUT_FILENAME = "jezero_mola_hrsc_blended.tif"


def compute_file_sha256(filepath: str | Path) -> str:
    """Calculates the SHA-256 hexadecimal digest of a file in chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_file_md5(filepath: str | Path) -> str:
    """Calculates the MD5 hexadecimal digest of a file in chunks."""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_array_sha256(arr: np.ndarray) -> str:
    """Calculates deterministic SHA-256 over contiguous float32 array bytes."""
    contig = np.ascontiguousarray(arr, dtype=np.float32)
    return hashlib.sha256(contig.tobytes()).hexdigest()


def get_provenance_sidecar_path(raster_path: str | Path) -> Path:
    """Returns the expected path to the cryptographic provenance sidecar JSON."""
    rp = Path(raster_path)
    return (
        rp.with_name(f"{rp.name}.provenance.json")
        if not str(rp).endswith(".provenance.json")
        else rp
    )


def verify_local_integrity(raster_path: str | Path) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Verifies local file integrity ONLY: checks whether `raster_path` exists, its sidecar
    exists, and the file's actual SHA-256 matches `local_file_sha256` in the sidecar.
    Does NOT claim authoritative upstream source authenticity.
    """
    r_path = Path(raster_path)
    if not r_path.exists():
        return False, "raster_file_not_found", None

    sidecar_path = r_path.with_name(f"{r_path.name}.provenance.json")
    if not sidecar_path.exists():
        alt_sidecar = r_path.with_suffix(".provenance.json")
        if alt_sidecar.exists():
            sidecar_path = alt_sidecar
        else:
            return False, "provenance_sidecar_missing", None

    try:
        with open(sidecar_path, encoding="utf-8") as f:
            sidecar = json.load(f)
    except Exception as e:
        return False, f"corrupted_sidecar_json: {e}", None

    recorded_sha = str(sidecar.get("local_file_sha256", "")).strip().lower()
    actual_sha = compute_file_sha256(r_path).lower()
    if not recorded_sha or recorded_sha != actual_sha:
        return (
            False,
            f"sha256_mismatch (recorded={recorded_sha[:10]}..., actual={actual_sha[:10]}...)",
            sidecar,
        )

    return True, "local_sha256_integrity_verified", sidecar


def verify_local_provenance(raster_path: str | Path) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Verifies both:
    1. Local file SHA-256 integrity against the provenance sidecar.
    2. Independent authoritative upstream source authenticity.

    Crucial Security Invariant:
    Never trusts a sidecar merely because `local_file_sha256` matches and `source_md5`
    contains the known catalog MD5 string. Authoritative source verification (`True`)
    requires either a direct manifest hash match of `raster_path` OR an existing local
    source file whose actual full-file bytes match the catalog checksum and whose
    extracted pixel window matches `raster_path`.
    """
    integrity_ok, reason, sidecar = verify_local_integrity(raster_path)
    if not integrity_ok or sidecar is None:
        return False, reason, sidecar

    r_path = Path(raster_path)
    actual_sha = compute_file_sha256(r_path).lower()

    is_verified, method, _ = verify_manifest_provenance(
        file_sha256=actual_sha,
        metadata_tags={},
        file_path=str(r_path),
    )

    if is_verified:
        return True, method, sidecar

    if method == "official_endpoint_retrieved_checksum_unverified":
        return False, "official_endpoint_retrieved_checksum_unverified", sidecar

    return False, "local_sha256_valid_but_source_unverified", sidecar


def ingest_jezero_dem(
    output_path: str | Path | None = None,
    source_url_or_path: str | None = None,
    bounds: tuple[float, float, float, float] = DEFAULT_JEZERO_BOUNDS,
    force: bool = False,
) -> dict[str, Any]:
    """
    Extracts the Jezero Crater corridor DEM from the specified source (official USGS
    HTTPS archive via /vsicurl/ or a local file), verifies source bytes where possible,
    saves the local GeoTIFF, and writes an honest provenance sidecar.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds
    except ImportError as e:
        raise RuntimeError(
            "Rasterio is required for DEM ingestion. Install it via pip or ensure .deps is on PYTHONPATH."
        ) from e

    if output_path is None:
        base_dir = Path(__file__).resolve().parent / "rasters"
        base_dir.mkdir(parents=True, exist_ok=True)
        out_file = base_dir / DEFAULT_OUTPUT_FILENAME
    else:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

    sidecar_file = out_file.with_name(f"{out_file.name}.provenance.json")

    # If already ingested and local SHA-256 integrity is intact, return existing record unless forced
    if not force and out_file.exists() and sidecar_file.exists():
        integrity_ok, _, sidecar = verify_local_integrity(out_file)
        if integrity_ok and sidecar is not None:
            logger.info(
                "Existing Jezero DEM verified for local integrity at %s (SHA-256: %s..., status: %s)",
                out_file,
                sidecar["local_file_sha256"][:12],
                sidecar.get("validation_status"),
            )
            return sidecar

    source = source_url_or_path or USGS_MOLA_HRSC_GLOBAL_URL
    is_remote = source.startswith("http://") or source.startswith("https://")
    vsi_source = f"/vsicurl/{source}" if is_remote else source

    # Determine source authenticity BEFORE writing any provenance claims
    computed_source_md5: str | None = None
    computed_source_sha256: str | None = None
    published_upstream_md5: str | None = None
    source_checksum_verified: bool = False
    matched_catalog_item: dict[str, Any] | None = None

    if is_remote:
        if source in OFFICIAL_USGS_ENDPOINTS:
            ingestion_method = "official_endpoint_vsicurl_range_extract"
            validation_status = "official_endpoint_retrieved_checksum_unverified"
            published_upstream_md5 = USGS_MOLA_HRSC_MD5
            source_product_id: str | None = USGS_MOLA_HRSC_PRODUCT_ID
            source_product_name = USGS_MOLA_HRSC_PRODUCT_NAME
        else:
            ingestion_method = "unverified_remote_vsicurl_range_extract"
            validation_status = "valid_numeric_raster_unverified_source"
            source_product_id = None
            source_product_name = "Remote Numerical Elevation Extract (Unverified Endpoint)"
    else:
        src_path = Path(source)
        if not src_path.exists():
            raise FileNotFoundError(f"Local ingestion source file not found: {source}")

        # Independently hash the actual local source bytes
        computed_source_md5 = compute_file_md5(src_path).lower()
        computed_source_sha256 = compute_file_sha256(src_path).lower()

        for item in DATA_CATALOG_MANIFEST:
            cat_md5 = str(item.get("upstream_md5") or "").lower().strip()
            cat_sha = str(item.get("sha256") or "").lower().strip()
            if (cat_md5 and computed_source_md5 == cat_md5) or (
                cat_sha and computed_source_sha256 == cat_sha
            ):
                matched_catalog_item = item
                break

        if matched_catalog_item is not None:
            ingestion_method = "verified_local_full_source_extract"
            validation_status = "verified_source"
            source_checksum_verified = True
            published_upstream_md5 = matched_catalog_item.get("upstream_md5")
            source_product_id = matched_catalog_item["id"]
            source_product_name = matched_catalog_item["product_name"]
        else:
            # Crucial: Never mark unverified or synthetic local files as official USGS products!
            ingestion_method = "unverified_local_source_extract"
            validation_status = "valid_numeric_raster_unverified_source"
            source_checksum_verified = False
            published_upstream_md5 = None
            source_product_id = None
            source_product_name = "Local Numerical Elevation Extract (Unverified Source)"

    min_lon, min_lat, max_lon, max_lat = bounds
    logger.info("Opening source raster: %s (method=%s)", source, ingestion_method)

    with rasterio.open(vsi_source) as src:
        # Calculate integer-aligned pixel window for the given lon/lat bounds
        window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window)
        win_transform = rasterio.windows.transform(window, src.transform)
        win_bounds = rasterio.windows.bounds(window, src.transform)
        source_crs = src.crs
        nodata_val = src.nodata if src.nodata is not None else -32768.0
        src_tags = src.tags()

    height, width = data.shape
    valid_mask = data != nodata_val
    valid_data = data[valid_mask] if np.any(valid_mask) else data
    min_elev = float(np.min(valid_data))
    max_elev = float(np.max(valid_data))
    mean_elev = float(np.mean(valid_data))

    mars_crs_str = "+proj=longlat +a=3396190 +b=3396190 +no_defs"

    # Determine vertical datum honestly
    if source_product_id == USGS_MOLA_HRSC_PRODUCT_ID:
        vertical_datum = "Mars Areoid (MOLA 0m reference datum)"
    else:
        vertical_datum = src_tags.get(
            "VERTICAL_DATUM",
            src_tags.get("DATUM", "Unknown / Unspecified (unverified source)"),
        )

    # Write output GeoTIFF
    logger.info("Writing clipped Jezero DEM (%d x %d) to %s", height, width, out_file)
    with rasterio.open(
        out_file,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=data.dtype.name,
        crs=source_crs or mars_crs_str,
        transform=win_transform,
        nodata=nodata_val,
    ) as dst:
        out_tags: dict[str, str] = {
            "SOURCE_URL": str(source),
            "INGESTION_METHOD": ingestion_method,
            "VALIDATION_STATUS": validation_status,
            "COORDINATE_SYSTEM": "Mars 2000 Sphere / IAU2000:49900",
        }
        if source_product_id:
            out_tags["PRODUCT_ID"] = source_product_id
            out_tags["PRODUCT_NAME"] = source_product_name
        if vertical_datum and "Unknown" not in vertical_datum:
            out_tags["VERTICAL_DATUM"] = vertical_datum
        if computed_source_md5:
            out_tags["COMPUTED_SOURCE_MD5"] = computed_source_md5
        dst.update_tags(**out_tags)
        dst.write(data, 1)

    file_sha256 = compute_file_sha256(out_file)
    extracted_array_sha256 = compute_array_sha256(data)

    provenance_record: dict[str, Any] = {
        "source_product_id": source_product_id,
        "source_product_name": source_product_name,
        "source_url": str(source),
        "ingestion_method": ingestion_method,
        "source_md5": computed_source_md5,
        "computed_source_md5": computed_source_md5,
        "computed_source_sha256": computed_source_sha256,
        "published_upstream_md5": published_upstream_md5,
        "source_checksum_verified": source_checksum_verified,
        "local_integrity_verified": True,
        "source_pds3_label_url": (
            USGS_MOLA_HRSC_PDS3_LBL if source_product_id == USGS_MOLA_HRSC_PRODUCT_ID else None
        ),
        "source_isis3_label_url": (
            USGS_MOLA_HRSC_ISIS3_LBL if source_product_id == USGS_MOLA_HRSC_PRODUCT_ID else None
        ),
        "local_file_path": str(out_file),
        "local_file_sha256": file_sha256,
        "extracted_array_sha256": extracted_array_sha256,
        "requested_bounds": {
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
        },
        "window_bounds": {
            "min_lon": round(float(win_bounds[0]), 6),
            "min_lat": round(float(win_bounds[1]), 6),
            "max_lon": round(float(win_bounds[2]), 6),
            "max_lat": round(float(win_bounds[3]), 6),
        },
        "raster_shape": [int(height), int(width)],
        "resolution_meters": 200.0 if source_product_id == USGS_MOLA_HRSC_PRODUCT_ID else None,
        "min_elevation_meters": round(min_elev, 2),
        "max_elevation_meters": round(max_elev, 2),
        "mean_elevation_meters": round(mean_elev, 2),
        "vertical_datum": vertical_datum,
        "crs": "IAU2000:49900",
        "ingestion_timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        "validation_status": validation_status,
    }

    with open(sidecar_file, "w", encoding="utf-8") as f:
        json.dump(provenance_record, f, indent=2)

    logger.info(
        "Ingested Jezero DEM to %s (status=%s, source_checksum_verified=%s)",
        out_file,
        validation_status,
        source_checksum_verified,
    )
    return provenance_record


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest Jezero Crater DEM from USGS PDS archive.")
    parser.add_argument("--output", type=str, default=None, help="Output GeoTIFF path")
    parser.add_argument("--source", type=str, default=None, help="Source URL or local file path")
    parser.add_argument(
        "--force", action="store_true", help="Force re-ingestion even if local extract exists"
    )
    args = parser.parse_args()

    record = ingest_jezero_dem(
        output_path=args.output,
        source_url_or_path=args.source,
        force=args.force,
    )
    print(f"Ingested successfully: {record['local_file_path']}")
    print(f"Validation status: {record['validation_status']}")
    print(f"Source checksum verified: {record['source_checksum_verified']}")
    print(f"Local SHA-256: {record['local_file_sha256']}")
    print(f"Elevations: {record['min_elevation_meters']}m to {record['max_elevation_meters']}m")
