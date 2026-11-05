"""
NASA, USGS, and ESA Planetary Data Product Manifest for Jezero Crater, Mars.
Documents verified scientific datasets, official landing pages, spatial resolutions,
coordinate reference systems, formats, and physical terrain suitability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_CATALOG_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
        "product_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
        "mission_instruments": "ESA Mars Express HRSC & NASA Mars Global Surveyor MOLA",
        "publisher": "USGS Astrogeology Science Center / PDS Geosciences Node / DLR / ESA",
        "landing_page": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200mp",
        "upstream_url": "https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif",
        "upstream_md5": "e98092a06bea74d5ec9a704dcd1fe318",
        "pds3_label_url": "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/99f5a18a-b4fb-4e87-8417-7408d8440651/download/mars_hrsc_mola_blenddem_global_200mp_v2_pds3.lbl",
        "isis3_label_url": "https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/mars_hrsc_mola_blenddem_global_200mp_v2.lbl",
        "pds_doi": "https://doi.org/10.5066/P9P7W018",
        "spatial_coverage": "Global Mars (90°N to -90°S, 0°E to 360°E); Jezero Crater sub-window (18.10°N - 18.70°N, 77.15°E - 78.00°E)",
        "resolution_meters": 200.0,
        "resolution_units": "meters/pixel (296.3735 px/deg)",
        "coordinate_system": "Mars 2000 Sphere / IAU2000:49900 (R=3,396,190m)",
        "projection": "Simple Cylindrical / Equirectangular",
        "vertical_datum": "Mars Areoid (MOLA 0m reference datum)",
        "nodata_value": -32768.0,
        "is_numerical_elevation": True,
        "contains_imagery_only": False,
        "format": "GeoTIFF (BigTIFF, Striped, Signed 16-bit Int meters)",
        "sha256": None,
        "authoritative_product_ids": [
            "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
            "JEZERO_HRSC_MOLA_blended_DEM",
            "dem_hrsc_mola_blended_50m",
            "HRSC_MOLA_JEZERO_200M",
            "10.5066/P9P7W018",
        ],
        "acquisition_date": "2004 - 2020 compiled",
        "license_and_reuse": "Public Domain (NASA / USGS / ESA open planetary science data policy)",
        "download_method": "Direct HTTP range request from USGS AWS S3 archive / PDS Geosciences archive",
        "file_size_mb": 11380.0,
        "suitability": "Primary regional numerical elevation source for rover/EVA slope and roughness routing across Jezero Crater.",
        "limitations": "200m/px resolution cannot resolve sub-50m boulders, wheel-scale traps, or micro-scarps.",
    },
    {
        "id": "dem_hrsc_mola_blended_50m",
        "product_name": "HRSC and MOLA Blended Digital Elevation Model (200m & 50m Jezero Mosaic)",
        "mission_instruments": "ESA Mars Express HRSC & NASA Mars Global Surveyor MOLA",
        "publisher": "USGS Astrogeology Science Center / PDS Geosciences Node",
        "landing_page": "https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM",
        "pds_doi": "https://doi.org/10.5066/P9P7W018",
        "spatial_coverage": "Jezero Crater & Nili Fossae (MC-11E, 17.5°N - 19.5°N, 76.5°E - 78.5°E)",
        "resolution_meters": 50.0,
        "resolution_units": "meters/pixel",
        "coordinate_system": "Mars 2000 Sphere / IAU2000:49900 (R=3,396,190m)",
        "projection": "Equirectangular / Sinusoidal",
        "is_numerical_elevation": True,
        "contains_imagery_only": False,
        "format": "GeoTIFF / ISIS3 .cub",
        "sha256": None,
        "authoritative_product_ids": [
            "JEZERO_HRSC_MOLA_blended_DEM",
            "dem_hrsc_mola_blended_50m",
            "HRSC_MOLA_JEZERO_50M",
            "10.5066/P9P7W018",
        ],
        "acquisition_date": "2004 - 2020 compiled",
        "license_and_reuse": "Public Domain (NASA / USGS / ESA open planetary science data policy)",
        "download_method": "USGS Astrogeology Astropedia direct HTTP download / PDS Geosciences archive",
        "file_size_mb": 145.0,
        "suitability": "Primary regional numerical elevation source for rover/EVA slope and roughness routing.",
        "limitations": "50m/px cannot resolve metre-scale boulder obstacles, rover wheel traps, or sub-5m scarps.",
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


def verify_manifest_provenance(
    file_sha256: str,
    metadata_tags: dict[str, str],
    file_path: str = "",
) -> tuple[bool, str, dict[str, Any] | None]:
    """
    Evaluates whether a loaded raster matches an official NASA/ESA/USGS planetary product
    through authoritative cryptographic evidence:

    1. Direct SHA-256 match recorded in official DATA_CATALOG_MANIFEST.
    2. Authoritative cryptographic ingestion sidecar (.provenance.json) linking the local
       extract to an authoritative upstream product MD5 checksum and matching the local file SHA-256.

    Crucial: Unauthenticated header metadata tags (e.g. self-asserted PRODUCT_ID) DO NOT
    grant verified_source status. They only establish metadata consistency and are categorized
    as valid_numeric_raster_unverified_source.
    """
    # 1. Direct manifest SHA-256 match
    if file_sha256:
        clean_sha = file_sha256.lower().strip()
        for item in DATA_CATALOG_MANIFEST:
            manifest_sha = item.get("sha256")
            if manifest_sha and manifest_sha.lower().strip() == clean_sha:
                return True, "authoritative_manifest_sha256_match", item

    # 2. Cryptographic ingestion sidecar verification
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
                    sc_local_sha = str(sc_data.get("local_file_sha256", "")).lower().strip()
                    sc_source_md5 = str(sc_data.get("source_md5", "")).lower().strip()

                    # Cryptographic link check: local file matches sidecar digest
                    if sc_local_sha and sc_local_sha == file_sha256.lower().strip():
                        # Upstream catalog check: upstream MD5 matches official catalog
                        for item in DATA_CATALOG_MANIFEST:
                            up_md5 = str(item.get("upstream_md5", "")).lower().strip()
                            if up_md5 and up_md5 == sc_source_md5:
                                return True, "authoritative_ingestion_sidecar_checksum_chain", item
                except Exception:
                    pass

    # 3. Check metadata tags for metadata consistency (NOT authenticating alone)
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
                # Returns False for is_verified, because metadata tags can be self-asserted
                return False, "unverified_source_unauthenticated_tags", item

    return False, "unverified_source_no_authoritative_credentials", None
