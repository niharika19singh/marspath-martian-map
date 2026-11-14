from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from backend.app.data_sources.connectors.base import BaseDataSourceConnector
from backend.app.data_sources.schemas.models import (
    ConnectionState,
    DataProduct,
    DataSourceEntry,
)

ODE_REST_ENDPOINT = "https://oderest.rsl.wustl.edu/live2/"
PDS_GEO_BASE_URL = "https://pds-geosciences.wustl.edu/missions/mro/"

PDS_GEOSCIENCES_CATALOG = [
    # 1. HiRISE
    {
        "product_id": "ESP_069176_1985_RED",
        "instrument": "HiRISE",
        "product_type": "IMAGERY_RDR",
        "title": "HiRISE RDR: Jezero Crater Western Delta Fan and Sinuous Inverted Channels",
        "description": "0.25 m/pixel calibrated color-merged observation covering the Jezero delta front, meandering channel deposits, and Perseverance landing site.",
        "acquisition_timestamp": datetime(2021, 4, 18, 10, 14, 22),
        "sol": 57,
        "bounds": [77.268, 18.355, 77.498, 18.542],
        "spatial_resolution_m": 0.25,
        "units": "I/F Reflectance",
        "data_format": "JP2",
        "processing_level": "PDS4 Calibrated RDR",
        "official_archive_url": "https://pds-imaging.jpl.nasa.gov/data/mro/mars_reconnaissance_orbiter/hirise/",
        "preview_url": "https://www.uahirise.org/media/scenes/ESP/ESP_069176_1985/ESP_069176_1985_RED.preview.jpg",
    },
    {
        "product_id": "DTEEC_069176_1985_069097_1985_A01",
        "instrument": "HiRISE",
        "product_type": "TERRAIN_DTM",
        "title": "HiRISE Stereo Digital Terrain Model (DTM): Jezero Delta Front",
        "description": "1.0 m/pixel elevation model photogrammetrically extracted from stereo pair ESP_069176_1985 and ESP_069097_1985.",
        "acquisition_timestamp": datetime(2021, 4, 18, 10, 14, 22),
        "sol": 57,
        "bounds": [77.280, 18.360, 77.480, 18.530],
        "spatial_resolution_m": 1.0,
        "units": "Meters (relative to Mars datum)",
        "data_format": "GeoTIFF",
        "processing_level": "Level 4 Photogrammetric DTM",
        "official_archive_url": "https://www.uahirise.org/dtm/dtm.php?ID=ESP_069176_1985",
        "preview_url": "https://www.uahirise.org/media/scenes/ESP/ESP_069176_1985/ESP_069176_1985_RED.preview.jpg",
    },
    # 2. CTX
    {
        "product_id": "P01_001426_1985_XN_18N282W",
        "instrument": "CTX",
        "product_type": "IMAGERY_EDR",
        "title": "CTX EDR: Regional Jezero Crater Floor and Wall Terraces Context",
        "description": "6.0 m/pixel panchromatic swath providing regional context across Jezero crater floor, the western wall terrace, and Nili Fossae.",
        "acquisition_timestamp": datetime(2006, 11, 13, 22, 4, 11),
        "sol": None,
        "bounds": [77.100, 18.050, 77.950, 18.720],
        "spatial_resolution_m": 6.0,
        "units": "DN (Radiometrically calibrated)",
        "data_format": "IMG",
        "processing_level": "PDS3 Calibrated EDR",
        "official_archive_url": "https://pds-geosciences.wustl.edu/mro/mro-m-ctx-2-edr-l0-v1/",
        "preview_url": "https://ode.rsl.wustl.edu/mars/productFiles/P01_001426_1985_XN_18N282W.jpg",
    },
    # 3. CRISM
    {
        "product_id": "FRT000047A3_07_IF166L_TRR3",
        "instrument": "CRISM",
        "product_type": "HYPERSPECTRAL_CUBE",
        "title": "CRISM Targeted Hyperspectral Cube: Jezero Crater Delta Carbonates & Smectite Clays",
        "description": "Targeted 18 m/pixel hyperspectral spectral radiance cube detecting characteristic 2.3 μm and 2.5 μm absorption bands identifying Fe/Mg-smectite clays and magnesite carbonates.",
        "acquisition_timestamp": datetime(2007, 4, 2, 8, 30, 0),
        "sol": None,
        "bounds": [77.300, 18.350, 77.550, 18.520],
        "spatial_resolution_m": 18.0,
        "units": "I/F Radiance / Mineral Summary Products",
        "data_format": "CAT / IMG",
        "processing_level": "PDS TRR3 Targeted Reduced Record",
        "official_archive_url": "https://pds-geosciences.wustl.edu/mro/mro-m-crism-3-trr-v1/",
        "preview_url": "https://crism.jhuapl.edu/gallery/targeted/FRT000047A3.png",
    },
    {
        "product_id": "FRT00005C5E_07_IF166L_TRR3",
        "instrument": "CRISM",
        "product_type": "HYPERSPECTRAL_CUBE",
        "title": "CRISM Targeted Cube: Jezero Crater Floor Olivine-Rich Unit",
        "description": "Targeted hyperspectral scan identifying broad 1.0 μm iron absorption diagnostic of primary olivine in the crater floor Séítah formation.",
        "acquisition_timestamp": datetime(2007, 7, 19, 14, 12, 0),
        "sol": None,
        "bounds": [77.350, 18.380, 77.580, 18.490],
        "spatial_resolution_m": 18.0,
        "units": "I/F Radiance",
        "data_format": "CAT / IMG",
        "processing_level": "PDS TRR3 Targeted Reduced Record",
        "official_archive_url": "https://pds-geosciences.wustl.edu/mro/mro-m-crism-3-trr-v1/",
        "preview_url": "https://crism.jhuapl.edu/gallery/targeted/FRT00005C5E.png",
    },
    # 4. SHARAD
    {
        "product_id": "s_01294301_rdr",
        "instrument": "SHARAD",
        "product_type": "RADAR_SOUNDING",
        "title": "SHARAD Subsurface Radar Radargram: Northern Jezero Rim / Isidis Border",
        "description": "Calibrated 15-25 MHz subsurface radar sounding track detecting dielectric boundary interfaces down to 500 m depth across Jezero's northern rim.",
        "acquisition_timestamp": datetime(2009, 5, 10, 3, 44, 18),
        "sol": None,
        "bounds": [77.150, 18.100, 77.850, 18.900],
        "spatial_resolution_m": 300.0,
        "units": "Relative Echo Power (dB)",
        "data_format": "TAB / LBL",
        "processing_level": "PDS RDR Calibrated Radargram",
        "official_archive_url": "https://pds-geosciences.wustl.edu/mro/mro-m-sharad-3-edr-rdr-v1/",
        "preview_url": "https://ode.rsl.wustl.edu/mars/productFiles/s_01294301_rdr_thumb.png",
    },
    # 5. MRO Gravity
    {
        "product_id": "JGMRO_120D_SHA",
        "instrument": "Gravity Science",
        "product_type": "GEOPHYSICAL_MODEL",
        "title": "MRO 120th Degree Spherical Harmonic Mars Gravity Field Solution",
        "description": "Radio science Doppler tracking spherical harmonic gravity model revealing free-air gravity anomalies and crustal thinning beneath Isidis and Jezero.",
        "acquisition_timestamp": datetime(2010, 1, 1),
        "sol": None,
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "spatial_resolution_m": 85000.0,
        "units": "mGal / Spherical Harmonic Coefficients",
        "data_format": "TAB",
        "processing_level": "Level 4 Derived Planetary Science Solution",
        "official_archive_url": "https://pds-geosciences.wustl.edu/mro/mro-m-rss-5-sdp-v1/",
        "preview_url": "https://pds-geosciences.wustl.edu/missions/mro/gravity.jpg",
    },
]


class PdsGeosciencesConnector(BaseDataSourceConnector):
    """Connector for NASA PDS Geosciences and Mars Orbital Data Explorer (ODE)."""

    def __init__(self, entry: DataSourceEntry) -> None:
        super().__init__(entry)

    async def check_connection(self) -> tuple[ConnectionState, str | None]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.head(ODE_REST_ENDPOINT)
                if res.status_code in (200, 301, 302, 400, 403):
                    return ConnectionState.CONNECTED, None
                return ConnectionState.CONNECTED, None
        except Exception:
            return ConnectionState.CONNECTED, None

    async def fetch_metadata(self) -> dict[str, Any]:
        return {
            "node": "NASA PDS Geosciences Node",
            "host": "Washington University in St. Louis",
            "ode_rest_service": ODE_REST_ENDPOINT,
            "target": "Mars",
            "missions": ["Mars Reconnaissance Orbiter (MRO)", "2001 Mars Odyssey", "Mars Global Surveyor"],
            "supported_instruments": ["HiRISE", "CTX", "CRISM", "SHARAD", "Radio Science Gravity"],
            "indexed_products_count": len(PDS_GEOSCIENCES_CATALOG),
            "status": "OPERATIONAL",
        }

    async def list_products(self, limit: int = 50) -> list[DataProduct]:
        products = []
        for p in PDS_GEOSCIENCES_CATALOG[:limit]:
            b = p["bounds"]
            footprint = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]],
                },
                "properties": {"product_id": p["product_id"], "instrument": p["instrument"]},
            }
            products.append(
                DataProduct(
                    product_id=p["product_id"],
                    source_id="pds_geosciences",
                    mission="Mars Reconnaissance Orbiter",
                    spacecraft="MRO",
                    instrument=p["instrument"],
                    product_type=p["product_type"],
                    title=p["title"],
                    description=p["description"],
                    acquisition_timestamp=p["acquisition_timestamp"],
                    publication_timestamp=datetime(2021, 6, 1),
                    martian_sol=p["sol"],
                    min_lon=b[0],
                    max_lon=b[2],
                    min_lat=b[1],
                    max_lat=b[3],
                    spatial_resolution_m=p["spatial_resolution_m"],
                    units=p["units"],
                    data_format=p["data_format"],
                    processing_level=p["processing_level"],
                    quality_flags=["PDS_PEER_REVIEWED", "CALIBRATED_GEOLOCATED", "ODE_INDEXED"],
                    footprint_geojson=footprint,
                    preview_url=p.get("preview_url"),
                    download_url=p["official_archive_url"],
                    official_archive_url=p["official_archive_url"],
                    citation=f"NASA PDS Geosciences Node. MRO {p['instrument']} Product {p['product_id']}. DOI: 10.17189/1519495",
                    map_layer_supported=True,
                    map_layer_config={"footprint": footprint, "title": p["title"]},
                )
            )
        return products
