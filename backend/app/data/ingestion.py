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
import os
from pathlib import Path
from typing import Any

import numpy as np

# Configure CA bundle for GDAL /vsicurl/ and curl HTTPS requests if certifi is available
try:
    import certifi

    _ca_file = certifi.where()
    if "CURL_CA_BUNDLE" not in os.environ:
        os.environ["CURL_CA_BUNDLE"] = _ca_file
    if "GDAL_CA_BUNDLE" not in os.environ:
        os.environ["GDAL_CA_BUNDLE"] = _ca_file
    if "SSL_CERT_FILE" not in os.environ:
        os.environ["SSL_CERT_FILE"] = _ca_file
except ImportError:
    pass

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
    manifest: list[dict[str, Any]] | None = None,
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

        effective_manifest = manifest if manifest is not None else DATA_CATALOG_MANIFEST
        for item in effective_manifest:
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

    candidate_sources = [source]
    if source_url_or_path is None and source == USGS_MOLA_HRSC_GLOBAL_URL:
        candidate_sources.append(USGS_MOLA_HRSC_BACKUP_URL)

    last_open_err: Exception | None = None
    data = None
    for cand_src in candidate_sources:
        cand_vsi = (
            f"/vsicurl/{cand_src}"
            if (cand_src.startswith("http://") or cand_src.startswith("https://"))
            else cand_src
        )
        try:
            with rasterio.open(cand_vsi) as src:
                # Calculate integer-aligned pixel window for the given lon/lat bounds
                window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
                window = window.round_offsets().round_lengths()
                data = src.read(1, window=window)
                win_transform = rasterio.windows.transform(window, src.transform)
                win_bounds = rasterio.windows.bounds(window, src.transform)
                source_crs = src.crs
                nodata_val = src.nodata if src.nodata is not None else -32768.0
                src_tags = src.tags()
            source = cand_src
            break
        except Exception as exc:
            last_open_err = exc
            logger.warning("Failed reading window from source '%s': %s", cand_src, exc)

    if data is None:
        assert last_open_err is not None
        raise last_open_err

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


def _validate_existing_local_dem(dem_path: Path) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Validates that `dem_path` and its provenance sidecar exist, pass SHA-256 local
    integrity verification, and load cleanly as a valid numeric Mars DEM over Jezero Crater.
    """
    from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
    from backend.app.geospatial.raster_loader import load_raster_file

    integrity_ok, reason, sidecar = verify_local_integrity(dem_path)
    if not integrity_ok or sidecar is None:
        return False, reason, None

    try:
        loaded = load_raster_file(str(dem_path))
        validator = MOLAHRSCRasterProvider(dem_path=str(dem_path))
        validator._validate_dem_integrity(loaded)
    except Exception as exc:
        return False, f"raster_validation_failed: {exc}", sidecar

    return True, "valid_local_dem_and_sidecar", sidecar


def provision_runtime_dem(
    dem_path: str | Path | None = None,
    use_real_dem: bool | None = None,
    allow_fallback: bool | None = None,
    source_url_or_path: str | None = None,
    force: bool = False,
    manifest: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Idempotent runtime DEM provisioning helper for cloud/Render startup:
    1. When `use_real_dem` is False, skips remote ingestion and returns immediately.
    2. When `use_real_dem` is True:
       - Checks whether the target raster and provenance sidecar already exist,
         validates local SHA-256 integrity, and verifies the raster metadata.
         If valid and `force=False`, reuses the existing local data without re-ingesting.
       - If missing or invalid, removes any stale/corrupted files and runs `ingest_jezero_dem`
         against the official USGS endpoint (extracting only the 178x252 Jezero window via HTTP Range).
       - Verifies the newly ingested raster and sidecar before returning.
       - If ingestion fails: cleans up any partial files, records the failure reason for
         health/readiness reporting, and either returns `fallback_to_synthetic` when
         `allow_fallback=True` or raises `RuntimeError` when `allow_fallback=False`.
    """
    from backend.app.core.config import get_settings

    settings = get_settings()
    target_path = Path(dem_path or settings.DEM_PATH)
    effective_use_real = settings.USE_REAL_DEM if use_real_dem is None else use_real_dem
    effective_fallback = (
        settings.ALLOW_SYNTHETIC_FALLBACK if allow_fallback is None else allow_fallback
    )
    sidecar_path = get_provenance_sidecar_path(target_path)
    error_marker_path = Path(f"{target_path}.provision_error.json")

    if not effective_use_real:
        logger.info(
            "MARSPATH_USE_REAL_DEM=false; skipping real DEM provisioning. Operating in synthetic_test_fixture mode."
        )
        return {
            "status": "skipped_real_dem_disabled",
            "real_dem_requested": False,
            "real_dem_provisioned": False,
            "action": "none",
            "dem_path": str(target_path),
        }

    if not force and target_path.exists() and sidecar_path.exists():
        is_valid, reason, sidecar = _validate_existing_local_dem(target_path)
        if is_valid and sidecar is not None:
            if error_marker_path.exists():
                error_marker_path.unlink(missing_ok=True)
            logger.info(
                "Valid local Jezero DEM and provenance sidecar already present at %s (SHA-256=%s..., status=%s). Skipping re-ingestion.",
                target_path,
                str(sidecar.get("local_file_sha256", ""))[:12],
                sidecar.get("validation_status"),
            )
            return {
                "status": "already_provisioned_valid",
                "real_dem_requested": True,
                "real_dem_provisioned": True,
                "action": "reused_existing_valid_dem",
                "dem_path": str(target_path),
                "local_file_sha256": sidecar.get("local_file_sha256"),
                "validation_status": sidecar.get("validation_status"),
            }
        logger.warning(
            "Existing DEM at %s failed local integrity/validation (%s); removing before re-ingestion.",
            target_path,
            reason,
        )

    # Remove any stale/corrupted partial files before attempting fresh ingestion
    for stale in (target_path, sidecar_path):
        if stale.exists():
            stale.unlink(missing_ok=True)

    try:
        record = ingest_jezero_dem(
            output_path=target_path,
            source_url_or_path=source_url_or_path,
            force=True,
            manifest=manifest,
        )
        is_valid, reason, _ = _validate_existing_local_dem(target_path)
        if not is_valid:
            raise RuntimeError(f"Post-ingestion raster verification failed: {reason}")

        if error_marker_path.exists():
            error_marker_path.unlink(missing_ok=True)

        logger.info(
            "Successfully provisioned and verified Jezero DEM at %s (status=%s, SHA-256=%s...)",
            target_path,
            record.get("validation_status"),
            str(record.get("local_file_sha256", ""))[:12],
        )
        return {
            "status": "provisioned_from_source",
            "real_dem_requested": True,
            "real_dem_provisioned": True,
            "action": "ingested_and_verified",
            "dem_path": str(target_path),
            "local_file_sha256": record.get("local_file_sha256"),
            "validation_status": record.get("validation_status"),
        }
    except Exception as exc:
        # Clean up any partial files so failed ingestion can NEVER masquerade as ready real data
        for partial in (target_path, sidecar_path):
            if partial.exists():
                partial.unlink(missing_ok=True)

        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(error_marker_path, "w", encoding="utf-8") as ef:
                json.dump(
                    {
                        "error": str(exc),
                        "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                    },
                    ef,
                )
        except Exception:
            pass

        if effective_fallback:
            logger.warning(
                "Failed to provision real DEM at %s (%s). MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true; "
                "continuing startup in synthetic_fallback mode (real_dem_loaded=false, dem_loaded=false).",
                target_path,
                exc,
            )
            return {
                "status": "fallback_to_synthetic",
                "real_dem_requested": True,
                "real_dem_provisioned": False,
                "action": "ingestion_failed_using_synthetic_fallback",
                "dem_path": str(target_path),
                "error": str(exc),
            }

        logger.error(
            "CRITICAL: Failed to provision real DEM at %s (%s) and MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false. Aborting startup.",
            target_path,
            exc,
        )
        raise RuntimeError(
            f"Mandatory real DEM provisioning failed (MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false): {exc}"
        ) from exc


def verify_runtime_dem(
    dem_path: str | Path | None = None,
    use_real_dem: bool | None = None,
    allow_fallback: bool | None = None,
) -> dict[str, Any]:
    """
    Strict read-only runtime DEM verification for container startup (Phase 7.2.1):
    1. When `use_real_dem` is False, logs and returns immediately with 'skipped_real_dem_disabled'.
    2. When `use_real_dem` is True:
       - Strictly verifies that the pre-built target raster exists and is non-empty.
       - Strictly verifies that the provenance sidecar exists and is valid JSON.
       - Strictly verifies local file SHA-256 integrity against the sidecar.
       - Loads the raster via MOLAHRSCRasterProvider and validates DEM data integrity.
       - Evaluates the unified evaluate_terrain_readiness() gate.
       - Enforces acceptable real DEM validation status ('verified_source' or
         'official_endpoint_retrieved_checksum_unverified').
       - NEVER makes network requests, NEVER downloads or re-ingests data,
         NEVER mutates, deletes, or regenerates artifacts.
       - If any check fails:
         * When `allow_fallback=True`: logs a warning and returns 'fallback_to_synthetic'.
         * When `allow_fallback=False`: raises RuntimeError to abort startup immediately.
    """
    from backend.app.core.config import get_settings
    from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
    from backend.app.services.data_catalog import (
        ACCEPTABLE_REAL_VALIDATION_STATUSES,
        evaluate_terrain_readiness,
    )

    settings = get_settings()
    target_path = Path(dem_path or settings.DEM_PATH)
    effective_use_real = settings.USE_REAL_DEM if use_real_dem is None else use_real_dem
    effective_fallback = (
        settings.ALLOW_SYNTHETIC_FALLBACK if allow_fallback is None else allow_fallback
    )
    sidecar_path = get_provenance_sidecar_path(target_path)

    if not effective_use_real:
        logger.info(
            "MARSPATH_USE_REAL_DEM=false; skipping real DEM runtime verification. Operating in synthetic_test_fixture mode."
        )
        return {
            "status": "skipped_real_dem_disabled",
            "real_dem_requested": False,
            "real_dem_loaded": False,
            "is_synthetic": True,
            "dem_path": str(target_path),
            "readiness_status": "healthy",
        }

    try:
        if not target_path.is_file():
            raise RuntimeError(
                f"Runtime DEM raster missing at '{target_path}'. Build-time provisioning did not create artifact."
            )
        if target_path.stat().st_size == 0:
            raise RuntimeError(f"Runtime DEM raster is empty (0 bytes) at '{target_path}'.")
        if not sidecar_path.is_file():
            raise RuntimeError(
                f"Runtime DEM provenance sidecar missing at '{sidecar_path}'."
            )

        try:
            with open(sidecar_path, encoding="utf-8") as f:
                sidecar = json.load(f)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse runtime DEM provenance sidecar JSON at '{sidecar_path}': {exc}"
            ) from exc

        integrity_ok, reason, _ = verify_local_integrity(target_path)
        if not integrity_ok:
            raise RuntimeError(
                f"Runtime DEM local SHA-256 integrity verification failed: {reason}"
            )

        try:
            provider = MOLAHRSCRasterProvider(
                dem_path=str(target_path),
                use_real_dem=effective_use_real,
                allow_fallback=effective_fallback,
            )
            raster = provider.get_dem_raster()
            provenance = provider.get_provenance()
        except Exception as exc:
            raise RuntimeError(
                f"Runtime DEM provider failed to load raster at '{target_path}': {exc}"
            ) from exc

        readiness = evaluate_terrain_readiness(
            is_synthetic=raster.metadata.is_synthetic,
            provenance=provenance,
            default_use_real_dem=True,
            dem_path=str(target_path),
        )

        if readiness.get("status") != "healthy":
            raise RuntimeError(
                f"Runtime DEM readiness gate failed (status='{readiness.get('status')}'): {readiness.get('blocking_errors')}"
            )
        if readiness.get("is_synthetic") is not False:
            raise RuntimeError("Runtime DEM is marked as synthetic when real DEM was requested.")
        if readiness.get("local_integrity_verified") is not True:
            raise RuntimeError(
                f"Runtime DEM local_integrity_verified is not True: {readiness.get('local_integrity_verified')}"
            )
        val_status = readiness.get("real_data_validation_status")
        if val_status not in ACCEPTABLE_REAL_VALIDATION_STATUSES:
            raise RuntimeError(
                f"Runtime DEM validation_status '{val_status}' not in acceptable statuses: {sorted(ACCEPTABLE_REAL_VALIDATION_STATUSES)}"
            )
        if readiness.get("blocking_errors"):
            raise RuntimeError(
                f"Runtime DEM blocking errors present: {readiness.get('blocking_errors')}"
            )

        logger.info(
            "Runtime DEM verification passed for %s (status=%s, SHA-256=%s...)",
            target_path,
            val_status,
            str(sidecar.get("local_file_sha256", ""))[:12],
        )
        return {
            "status": "verified_valid",
            "real_dem_requested": True,
            "real_dem_loaded": True,
            "is_synthetic": False,
            "dem_path": str(target_path),
            "local_file_sha256": sidecar.get("local_file_sha256"),
            "validation_status": val_status,
            "readiness_status": readiness.get("status"),
        }
    except Exception as exc:
        if effective_fallback:
            logger.warning(
                "Runtime DEM verification failed (%s), but MARSPATH_ALLOW_SYNTHETIC_FALLBACK=true; "
                "continuing startup in degraded synthetic fallback mode.",
                exc,
            )
            return {
                "status": "fallback_to_synthetic",
                "real_dem_requested": True,
                "real_dem_loaded": False,
                "is_synthetic": True,
                "dem_path": str(target_path),
                "error": str(exc),
                "readiness_status": "degraded",
            }

        logger.error(
            "CRITICAL: Runtime DEM verification failed (%s) and MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false. Aborting startup.",
            exc,
        )
        raise RuntimeError(
            f"Strict runtime DEM verification failed (MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false): {exc}"
        ) from exc


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest Jezero Crater DEM from USGS PDS archive.")
    parser.add_argument("--output", type=str, default=None, help="Output GeoTIFF path")
    parser.add_argument("--source", type=str, default=None, help="Source URL or local file path")
    parser.add_argument(
        "--force", action="store_true", help="Force re-ingestion even if local extract exists"
    )
    parser.add_argument(
        "--provision-runtime",
        action="store_true",
        help="Run idempotent runtime DEM provisioning honoring MARSPATH_USE_REAL_DEM and MARSPATH_ALLOW_SYNTHETIC_FALLBACK",
    )
    parser.add_argument(
        "--verify-runtime",
        action="store_true",
        help="Run strict read-only runtime DEM verification (never downloads, extracts, or deletes)",
    )
    args = parser.parse_args()

    if args.verify_runtime:
        try:
            res = verify_runtime_dem(dem_path=args.output)
            print(f"Runtime verification status: {res['status']}")
            print(f"Real DEM requested: {res['real_dem_requested']}")
            print(f"Real DEM loaded: {res['real_dem_loaded']}")
            if res.get("validation_status"):
                print(f"Validation status: {res['validation_status']}")
            if res.get("local_file_sha256"):
                print(f"Local SHA-256: {res['local_file_sha256']}")
            sys.exit(0)
        except Exception as err:
            print(f"Runtime verification failed: {err}", file=sys.stderr)
            sys.exit(1)

    if args.provision_runtime:
        try:
            res = provision_runtime_dem(
                dem_path=args.output,
                source_url_or_path=args.source,
                force=args.force,
            )
            print(f"Runtime provisioning status: {res['status']}")
            print(f"Real DEM requested: {res['real_dem_requested']}")
            print(f"Real DEM provisioned: {res['real_dem_provisioned']}")
            sys.exit(0)
        except Exception as err:
            print(f"Runtime provisioning failed: {err}", file=sys.stderr)
            sys.exit(1)

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
