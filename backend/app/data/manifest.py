"""
NASA, USGS, and ESA Planetary Data Product Manifest for Jezero Crater, Mars.
Documents verified scientific datasets, official landing pages, spatial resolutions,
coordinate reference systems, formats, and physical terrain suitability.

Provenance Verification Architecture:
- Separates local file SHA-256 integrity from authoritative upstream source authenticity.
- Reserves `verified_source` strictly for rasters whose full source bytes have been
  independently hashed and matched against an authoritative catalog checksum.
- Partial HTTP range extractions (/vsicurl/) from official USGS endpoints are reported
  as `official_endpoint_retrieved_checksum_unverified` because the published MD5 applies
  to the full 11.38 GB global archive rather than a streamed sub-window.
- Arbitrary local files, unauthenticated TIFF tags, and manually forged sidecars without
  independently verifiable upstream source bytes are classified as
  `valid_numeric_raster_unverified_source`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

# Deterministic SHA-256 of the float32 elevation array for the Jezero Crater window
# (col_off=76212, row_off=21131, width=252, height=178; 77.1485°E-77.9988°E, 18.1009°N-18.7015°N)
# streamed from USGS Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif
USGS_JEZERO_WINDOW_ARRAY_SHA256 = "e9a823c7ee00f68e6b5985425b90e574e30638f6223d07010bc75f98214f3074"

DATA_CATALOG_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
        "product_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
        "mission_instruments": "ESA Mars Express HRSC & NASA Mars Global Surveyor MOLA",
        "publisher": "USGS Astrogeology Science Center / PDS Geosciences Node / DLR / ESA",
        "landing_page": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
        "landing_page_alt": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200mp",
        "upstream_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "upstream_backup_url": "https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "upstream_md5_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif.md5",
        "upstream_md5": "e98092a06bea74d5ec9a704dcd1fe318",
        "pds3_label_url": "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/99f5a18a-b4fb-4e87-8417-7408d8440651/download/mars_hrsc_mola_blenddem_global_200mp_v2_pds3.lbl",
        "isis3_label_url": "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/mars_hrsc_mola_blenddem_global_200mp_v2.lbl",
        "pds_doi": "https://doi.org/10.5066/P9P7W018",
        "spatial_coverage": "Global Mars (90°N to -90°S, -180°E to +180°E / 0°E to 360°E); Jezero Crater window (18.1009°N - 18.7015°N, 77.1485°E - 77.9988°E)",
        "resolution_meters": 200.0,
        "resolution_units": "meters/pixel (296.3735 px/deg; 0.00337412 deg/px)",
        "coordinate_system": "Mars 2000 Sphere / IAU2000:49900 / ESRI:104971 (R=3,396,190m)",
        "projection": "Simple Cylindrical / Equirectangular",
        "vertical_datum": "Mars Areoid (MOLA 0m reference datum)",
        "nodata_value": -32768.0,
        "is_numerical_elevation": True,
        "contains_imagery_only": False,
        "format": "GeoTIFF (BigTIFF, Striped, Signed 16-bit Int meters)",
        "sha256": None,
        "jezero_window_array_sha256": USGS_JEZERO_WINDOW_ARRAY_SHA256,
        "authoritative_product_ids": [
            "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
            "HRSC_MOLA_JEZERO_200M",
            "10.5066/P9P7W018",
        ],
        "acquisition_date": "2004 - 2018 compiled (Fergason et al., 2018)",
        "license_and_reuse": "Public Domain (NASA / USGS / ESA open planetary science data policy)",
        "download_method": "Direct HTTP range request from USGS AWS S3 archive / PDS Geosciences archive",
        "file_size_mb": 11380.0,
        "suitability": "Regional corridor terrain assessment for slope and roughness routing across Jezero Crater.",
        "limitations": (
            "Nominal 200m/px resolution supports regional terrain assessment only, not metre-scale obstacle detection "
            "or flight-grade rover navigation. USGS warns of HRSC/MOLA blending seam inconsistencies and notes this "
            "dataset was originally generated for thermal-modelling (THEMIS thermal inertia) rather than precision local navigation."
        ),
    },
    {
        "id": "dem_hirise_jezero_delta_1m",
        "product_name": "HiRISE Jezero Crater Western Delta Digital Terrain Model (DTM)",
        "mission_instruments": "NASA Mars Reconnaissance Orbiter (MRO) HiRISE",
        "publisher": "University of Arizona / NASA PDS Geosciences Node",
        "landing_page": "https://www.uahirise.org/dtm/dtm.php?ID=ESP_037803_1985",
        "pds_doi": "https://doi.org/10.17189/1519501",
        "spatial_coverage": "Jezero Western Delta Scarp (18.35°N - 18.46°N, 77.38°E - 77.47°E)",
        "resolution_meters": 1.0,
        "resolution_units": "meters/pixel",
        "coordinate_system": "Mars 2000 Equirectangular (clon=77.0°E, clat=0.0°)",
        "projection": "Equirectangular",
        "is_numerical_elevation": True,
        "contains_imagery_only": False,
        "format": "IMG (PDS3) / GeoTIFF",
        "sha256": None,
        "authoritative_product_ids": [
            "ESP_037803_1985",
            "dem_hirise_jezero_delta_1m",
            "10.17189/1519501",
        ],
        "acquisition_date": "2014 - 2020",
        "license_and_reuse": "Public Domain (NASA PDS open data)",
        "download_method": "HiRISE website DTM product archive",
        "file_size_mb": 480.0,
        "suitability": "Ultra-high resolution local corridor validation for delta front ascent routes.",
        "limitations": "Very narrow spatial footprint (~6 km x 18 km); does not cover outer crater rim or floor.",
    },
    {
        "id": "img_ctx_jezero_mosaic_6m",
        "product_name": "CTX Jezero Crater Controlled Orthorectified Image Mosaic",
        "mission_instruments": "NASA Mars Reconnaissance Orbiter Context Camera (CTX)",
        "publisher": "Murray Lab, Caltech / NASA PDS Cartography Node",
        "landing_page": "https://murray-lab.caltech.edu/CTX/tiles/beta/Jezero.html",
        "pds_doi": "https://doi.org/10.17189/1519500",
        "spatial_coverage": "Full Jezero Crater Basin and Rim (18.0°N - 19.0°N, 77.0°E - 78.5°E)",
        "resolution_meters": 6.0,
        "resolution_units": "meters/pixel",
        "coordinate_system": "Mars 2000 IAU2000:49900",
        "projection": "Equirectangular",
        "is_numerical_elevation": False,
        "contains_imagery_only": True,
        "format": "GeoTIFF / Cloud-Optimized GeoTIFF (COG)",
        "acquisition_date": "2006 - 2021",
        "license_and_reuse": "Public Domain (NASA Caltech CTX Global Mosaic)",
        "download_method": "Caltech Murray Lab open AWS S3 / HTTP archive",
        "file_size_mb": 310.0,
        "suitability": "Visual basemap context for frontend display; NOT valid for slope calculation.",
        "limitations": "Pure visible radiance/reflectance imagery. Lacks elevation values; slopes cannot be computed from pixel grayscale.",
    },
    {
        "id": "spec_crism_mineralogy_jezero",
        "product_name": "CRISM Targeted Hyperspectral Mineralogy Products (MTR3)",
        "mission_instruments": "NASA MRO Compact Reconnaissance Imaging Spectrometer for Mars (CRISM)",
        "publisher": "PDS Geosciences Node / JHU Applied Physics Laboratory",
        "landing_page": "https://pds-geosciences.wustl.edu/missions/mro/crism.htm",
        "pds_doi": "https://doi.org/10.17189/1519498",
        "spatial_coverage": "Targeted footprints across Jezero delta and northern rim",
        "resolution_meters": 18.0,
        "resolution_units": "meters/pixel",
        "coordinate_system": "Mars 2000 Sphere",
        "projection": "Equirectangular",
        "is_numerical_elevation": False,
        "contains_imagery_only": False,
        "format": "PDS3 IMG / Spectral Summary Parameter GeoTIFFs (BD1900, D2300, HCPINDEX)",
        "acquisition_date": "2007 - 2018",
        "license_and_reuse": "Public Domain (NASA PDS open data)",
        "download_method": "PDS Geosciences Spectral Library / CRISM Data Archive",
        "file_size_mb": 85.0,
        "suitability": "Scientific POI weighting (Fe/Mg phyllosilicates, smectite clays, carbonates for biosignature preservation).",
        "limitations": "Discontinuous spatial swaths; requires mineral parameter interpretation.",
    },
    {
        "id": "thermal_themis_night_ir",
        "product_name": "THEMIS Nighttime Infrared Global Mosaic (Thermal Inertia / Block Abundance)",
        "mission_instruments": "NASA 2001 Mars Odyssey Thermal Emission Imaging System (THEMIS)",
        "publisher": "Arizona State University Mars Space Flight Facility / NASA PDS",
        "landing_page": "https://themis.asu.edu/maps",
        "pds_doi": "https://doi.org/10.17189/1519495",
        "spatial_coverage": "Global Mars, including Jezero Crater pilot quadrant",
        "resolution_meters": 100.0,
        "resolution_units": "meters/pixel",
        "coordinate_system": "Mars 2000 IAU2000:49900",
        "projection": "Simple Cylindrical / Equirectangular",
        "is_numerical_elevation": False,
        "contains_imagery_only": False,
        "format": "GeoTIFF",
        "acquisition_date": "2002 - present",
        "license_and_reuse": "Public Domain (NASA / ASU)",
        "download_method": "THEMIS Web Map Service / USGS Astrogeology Trek Service",
        "file_size_mb": 120.0,
        "suitability": "Surface thermal inertia proxy: differentiates high-inertia bedrock/boulder hazards from low-inertia fine dust mantle.",
        "limitations": "100m pixel resolution averages micro-scale boulder clusters.",
    },
    {
        "id": "map_mars_trek_wmts",
        "product_name": "NASA Solar System Treks — Mars Trek WMTS / Tile Service",
        "mission_instruments": "NASA JPL / Solar System Treks Project multi-mission composite",
        "publisher": "NASA Jet Propulsion Laboratory (JPL)",
        "landing_page": "https://trek.nasa.gov/mars/",
        "pds_doi": "NASA JPL Planetary Portal",
        "spatial_coverage": "Global Mars interactive tile service",
        "resolution_meters": 6.0,
        "resolution_units": "meters/pixel (variable by zoom level)",
        "coordinate_system": "Mars 2000 IAU2000:49900",
        "projection": "Equirectangular Tile Matrix Set",
        "is_numerical_elevation": False,
        "contains_imagery_only": True,
        "format": "XYZ / WMTS PNG/JPEG raster map tiles",
        "acquisition_date": "Continuously updated",
        "license_and_reuse": "Public Domain (NASA JPL Solar System Treks)",
        "download_method": "Standard WMTS / XYZ REST tile requests (https://trek.nasa.gov/tiles/Mars/EQ/...)",
        "file_size_mb": 0.0,
        "suitability": "Ideal interactive basemap visual layer for Kunal's React OpenLayers / Leaflet frontend.",
        "limitations": "Rendered RGB image tiles; zero elevation data. Strictly visualization-only.",
    },
]


def _compute_file_digest(filepath: str | Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def _compute_raster_array_sha256(filepath: str | Path) -> str | None:
    try:
        import rasterio

        with rasterio.open(filepath) as src:
            arr = np.ascontiguousarray(src.read(1), dtype=np.float32)
            return hashlib.sha256(arr.tobytes()).hexdigest().lower()
    except Exception:
        return None


def _verify_window_against_source_file(
    extracted_path: str | Path,
    source_path: str | Path,
    window_bounds: dict[str, float],
) -> bool:
    """
    Independently verifies that `extracted_path` contains the exact pixel window
    clipped from `source_path` for `window_bounds`.
    """
    try:
        import rasterio
        from rasterio.windows import from_bounds

        min_lon = float(window_bounds["min_lon"])
        min_lat = float(window_bounds["min_lat"])
        max_lon = float(window_bounds["max_lon"])
        max_lat = float(window_bounds["max_lat"])

        with rasterio.open(source_path) as src:
            window = from_bounds(min_lon, min_lat, max_lon, max_lat, src.transform)
            window = window.round_offsets().round_lengths()
            src_win_data = np.ascontiguousarray(src.read(1, window=window), dtype=np.float32)

        with rasterio.open(extracted_path) as ext_src:
            ext_data = np.ascontiguousarray(ext_src.read(1), dtype=np.float32)

        return src_win_data.shape == ext_data.shape and np.allclose(
            src_win_data, ext_data, equal_nan=True
        )
    except Exception:
        return False


def verify_manifest_provenance(
    file_sha256: str,
    metadata_tags: dict[str, str],
    file_path: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Evaluates whether a loaded raster matches an official NASA/ESA/USGS planetary product.

    Strict Separation of Concerns:
    1. Authoritative Source Verification (`verified_source`, returns True):
       - Direct SHA-256 or MD5 match of the loaded file's bytes against `DATA_CATALOG_MANIFEST`, OR
       - Sidecar with verified local SHA-256 where the upstream `source_url` exists as a local
         file on disk, its actual full-file bytes hash to the catalog's `upstream_md5` or `sha256`,
         AND the extracted window pixels match the upstream source file.
    2. Official Endpoint Partial Range Retrieval (`official_endpoint_retrieved_checksum_unverified`, returns False):
       - Sidecar with verified local SHA-256 produced by `/vsicurl/` range extraction from the
         official USGS HTTPS endpoint, where the extracted elevation array SHA-256 matches the
         deterministic USGS Jezero window array digest, but the full 11.38 GB upstream file
         checksum could not be computed over all upstream source bytes.
    3. Local Integrity Failure (`failed_local_sha256_integrity_mismatch`, returns False):
       - A sidecar exists alongside `file_path`, but `local_file_sha256` does not match the
         actual SHA-256 of `file_path` (indicating local file tampering or corruption).
    4. Unverified Sidecar / Unauthenticated Tags / No Credentials (returns False):
       - Manually forged sidecar, unverified source MD5 string, self-asserted TIFF tags, or
         arbitrary local numeric rasters.
    """
    clean_sha = file_sha256.lower().strip() if file_sha256 else ""

    # 1. Direct manifest SHA-256 match over loaded file bytes
    if clean_sha:
        for item in DATA_CATALOG_MANIFEST:
            manifest_sha = item.get("sha256")
            if manifest_sha and manifest_sha.lower().strip() == clean_sha:
                return True, "authoritative_manifest_sha256_match", item

    # 1b. Direct manifest MD5 match over loaded file bytes
    if file_path and Path(file_path).exists():
        try:
            file_md5 = _compute_file_digest(file_path, "md5")
            for item in DATA_CATALOG_MANIFEST:
                up_md5 = item.get("upstream_md5")
                if up_md5 and up_md5.lower().strip() == file_md5:
                    return True, "authoritative_manifest_md5_match", item
        except Exception:
            pass

    # 2. Sidecar inspection (local integrity + independent source verification)
    if file_path:
        fp = Path(file_path)
        sidecar_candidates = [
            fp.with_name(f"{fp.name}.provenance.json"),
            fp.with_suffix(".provenance.json"),
        ]
        for sc_path in sidecar_candidates:
            if sc_path.exists():
                try:
                    with open(sc_path, encoding="utf-8") as f:
                        sc_data = json.load(f)
                except Exception:
                    return False, "failed_local_sidecar_corrupted_json", None

                sc_local_sha = str(sc_data.get("local_file_sha256", "")).lower().strip()
                if not sc_local_sha or sc_local_sha != clean_sha:
                    # Tampered local file or mismatched sidecar digest
                    return False, "failed_local_sha256_integrity_mismatch", None

                # Local SHA-256 matches sidecar. Now evaluate upstream source authenticity!
                # Never trust a sidecar's source_md5 string unless verified against actual source bytes.
                source_ref = str(sc_data.get("source_url", "")).strip()
                window_bounds = sc_data.get("window_bounds")

                # Path 2a: Full upstream source file exists on disk -> verify its bytes & window
                if (
                    source_ref
                    and not source_ref.startswith(("http://", "https://", "/vsicurl/"))
                    and Path(source_ref).exists()
                    and isinstance(window_bounds, dict)
                ):
                    actual_src_md5 = _compute_file_digest(source_ref, "md5")
                    actual_src_sha256 = _compute_file_digest(source_ref, "sha256")
                    for item in DATA_CATALOG_MANIFEST:
                        cat_md5 = str(item.get("upstream_md5") or "").lower().strip()
                        cat_sha = str(item.get("sha256") or "").lower().strip()
                        md5_ok = bool(cat_md5 and actual_src_md5 == cat_md5)
                        sha_ok = bool(cat_sha and actual_src_sha256 == cat_sha)
                        if (md5_ok or sha_ok) and _verify_window_against_source_file(
                            fp, source_ref, window_bounds
                        ):
                            return True, "authoritative_full_source_bytes_verified", item

                # Path 2b: Official endpoint partial HTTP range extraction (/vsicurl/)
                # Full upstream 11.38 GB file checksum is unverified, so this NEVER returns True (verified_source),
                # but returns the honest intermediate status if the extracted array matches the USGS window.
                ingestion_method = str(sc_data.get("ingestion_method", "")).strip()
                if ingestion_method == "official_endpoint_vsicurl_range_extract":
                    actual_arr_sha = _compute_raster_array_sha256(fp)
                    sc_arr_sha = str(sc_data.get("extracted_array_sha256", "")).lower().strip()
                    for item in DATA_CATALOG_MANIFEST:
                        expected_win_sha = str(item.get("jezero_window_array_sha256") or "").lower().strip()
                        if (
                            actual_arr_sha
                            and expected_win_sha
                            and actual_arr_sha == expected_win_sha
                            and sc_arr_sha == expected_win_sha
                        ):
                            return False, "official_endpoint_retrieved_checksum_unverified", item

                # Any other sidecar (forged sidecar, unverified source_md5 string, or unverified local source)
                return False, "unverified_sidecar_source_not_authenticated", None

    # 3. Check metadata tags for metadata consistency (NEVER authenticating alone)
    norm_tags = {str(k).upper(): str(v).strip() for k, v in metadata_tags.items()}
    tag_candidates = [
        norm_tags.get("PRODUCT_ID", ""),
        norm_tags.get("DATASET_ID", ""),
        norm_tags.get("PDS_DOI", ""),
        norm_tags.get("OFFICIAL_PRODUCT_ID", ""),
        norm_tags.get("SOURCE_PRODUCT_ID", ""),
    ]

    for item in DATA_CATALOG_MANIFEST:
        auth_ids = [str(x).upper() for x in item.get("authoritative_product_ids", [])]
        item_id = item.get("id", "").upper()
        item_doi = item.get("pds_doi", "").upper()
        targets = set(auth_ids + [item_id, item_doi])

        for cand in tag_candidates:
            if not cand:
                continue
            cand_upper = cand.upper()
            if cand_upper in targets or any(t and t in cand_upper for t in targets):
                return False, "unverified_source_unauthenticated_tags", item

    return False, "unverified_source_no_authoritative_credentials", None
