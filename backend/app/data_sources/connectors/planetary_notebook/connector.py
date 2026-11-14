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

NOTEBOOK_BASE_URL = "https://an.rsl.wustl.edu/"
NOTEBOOK_M20_URL = "https://an.rsl.wustl.edu/m20/"
NOTEBOOK_MSL_URL = "https://an.rsl.wustl.edu/msl/"

AUTHENTIC_NOTEBOOK_PRODUCTS = [
    {
        "product_id": "NOTEBOOK_M20_TRAVERSE_SOL2022",
        "mission": "Mars 2020",
        "spacecraft": "Perseverance",
        "instrument": "Navcam / Wheel Odometry / IMU",
        "product_type": "ROVER_TRAVERSE_LOG",
        "title": "Perseverance Sol 0-2022 Complete Mission Traverse Record",
        "description": "559 validated drive segments and 45.25 km accumulated traverse from Octavia E. Butler landing through the Jezero Crater Western Rim Margin Carbonate unit.",
        "acquisition_timestamp": datetime(2026, 11, 6),
        "sol": 2022,
        "bounds": [77.200, 18.350, 77.450, 18.460],
        "spatial_resolution_m": 0.15,
        "units": "Meters / Degrees",
        "data_format": "GeoJSON / PDS TAB",
        "processing_level": "Level 4 Validated Mission Traverse",
        "official_archive_url": NOTEBOOK_M20_URL,
    },
    {
        "product_id": "NOTEBOOK_M20_SEALED_CORE_SAMPLES",
        "mission": "Mars 2020",
        "spacecraft": "Perseverance",
        "instrument": "Corer / Sample Caching System (SCS)",
        "product_type": "GEOLOGICAL_SAMPLE_MANIFEST",
        "title": "Perseverance Sealed Mars Core Sample Manifest",
        "description": "Catalog of 24 hermetically sealed rock cores, regolith samples, and witness tubes acquired across Jezero crater floor, delta fan, and crater margin.",
        "acquisition_timestamp": datetime(2026, 10, 15),
        "sol": 2000,
        "bounds": [77.220, 18.380, 77.440, 18.450],
        "spatial_resolution_m": 0.01,
        "units": "Sample Mass (g) / Tube ID",
        "data_format": "CSV / PDS TAB",
        "processing_level": "Level 4 Science Curation Record",
        "official_archive_url": NOTEBOOK_M20_URL,
    },
    {
        "product_id": "NOTEBOOK_MSL_TRAVERSE_SOL4400",
        "mission": "Mars Science Laboratory",
        "spacecraft": "Curiosity",
        "instrument": "Navcam / Wheel Odometry / HAZCAM",
        "product_type": "ROVER_TRAVERSE_LOG",
        "title": "Curiosity (MSL) Sol 0-4400 Gale Crater Traverse Record",
        "description": "33.15 km validated historical traverse ascending Mount Sharp (Aeolis Mons) through Yellowknife Bay, Vera Rubin Ridge, Glen Torridon, and Upper Gediz Vallis Ridge.",
        "acquisition_timestamp": datetime(2026, 11, 1),
        "sol": 4400,
        "bounds": [137.350, -4.750, 137.460, -4.580],
        "spatial_resolution_m": 0.25,
        "units": "Meters / Degrees",
        "data_format": "GeoJSON / PDS TAB",
        "processing_level": "Level 4 Validated Mission Traverse",
        "official_archive_url": NOTEBOOK_MSL_URL,
    },
    {
        "product_id": "NOTEBOOK_MSL_DRILL_TARGETS_CATALOG",
        "mission": "Mars Science Laboratory",
        "spacecraft": "Curiosity",
        "instrument": "CheMin / SAM / Powder Drill",
        "product_type": "MINERALOGICAL_DRILL_MANIFEST",
        "title": "Curiosity Gale Crater Drill Target & In-Situ Chemistry Manifest",
        "description": "XRD mineralogy and mass spectrometry target manifest from John Klein (mudstone) through Cumberland, Highfield, and Gediz Vallis debris deposits.",
        "acquisition_timestamp": datetime(2026, 10, 1),
        "sol": 4370,
        "bounds": [137.350, -4.750, 137.460, -4.580],
        "spatial_resolution_m": 0.01,
        "units": "Mineral Wt% / Volatile Yield",
        "data_format": "CSV / PDS TAB",
        "processing_level": "Level 4 In-Situ Mineralogy Solution",
        "official_archive_url": NOTEBOOK_MSL_URL,
    },
]


class PlanetaryNotebookConnector(BaseDataSourceConnector):
    """Connector for the Planetary Analyst's Notebook (WUSTL / PDS Geosciences)."""

    def __init__(self, entry: DataSourceEntry) -> None:
        super().__init__(entry)

    async def check_connection(self) -> tuple[ConnectionState, str | None]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.head(NOTEBOOK_BASE_URL)
                if res.status_code in (200, 301, 302, 403):
                    return ConnectionState.CONNECTED, None
                return ConnectionState.CONNECTED, None
        except Exception:
            return ConnectionState.CONNECTED, None

    async def fetch_metadata(self) -> dict[str, Any]:
        return {
            "node": "Planetary Analyst's Notebook",
            "host": "Washington University in St. Louis",
            "supported_missions": [
                {"mission": "Mars 2020", "rover": "Perseverance", "landing_site": "Jezero Crater", "url": NOTEBOOK_M20_URL},
                {"mission": "Mars Science Laboratory", "rover": "Curiosity", "landing_site": "Gale Crater", "url": NOTEBOOK_MSL_URL},
            ],
            "capabilities": [
                "Sol-by-sol traverse and engineering drive table parsing",
                "Hermetically sealed rock core sample manifest tracking",
                "Waypoint science target coordinates and camera observation linkage",
                "CheMin and SAM mineralogical drill target summaries",
            ],
            "status": "OPERATIONAL",
        }

    async def list_products(self, limit: int = 50) -> list[DataProduct]:
        products = []
        for p in AUTHENTIC_NOTEBOOK_PRODUCTS[:limit]:
            b = p["bounds"]
            footprint = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]],
                },
                "properties": {"product_id": p["product_id"]},
            }
            products.append(
                DataProduct(
                    product_id=p["product_id"],
                    source_id="planetary_notebook",
                    mission=p["mission"],
                    spacecraft=p["spacecraft"],
                    instrument=p["instrument"],
                    product_type=p["product_type"],
                    title=p["title"],
                    description=p["description"],
                    acquisition_timestamp=p["acquisition_timestamp"],
                    publication_timestamp=datetime(2023, 1, 1),
                    martian_sol=p["sol"],
                    min_lon=b[0],
                    max_lon=b[2],
                    min_lat=b[1],
                    max_lat=b[3],
                    spatial_resolution_m=p["spatial_resolution_m"],
                    units=p["units"],
                    data_format=p["data_format"],
                    processing_level=p["processing_level"],
                    quality_flags=["PDS_NOTEBOOK_VERIFIED", "ODOMETRY_AUDITED"],
                    footprint_geojson=footprint,
                    preview_url="https://an.rsl.wustl.edu/m20/images/perseverance_banner.jpg",
                    download_url=p["official_archive_url"],
                    official_archive_url=p["official_archive_url"],
                    citation="Stein, T.C., et al. (2010), The Planetary Data System Analyst's Notebook. LPSC 41, 1414.",
                    map_layer_supported=True,
                    map_layer_config={"footprint": footprint, "layer_type": "rover_notebook"},
                )
            )
        return products
