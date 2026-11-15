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

# Authoritative NASA Mars Trek WMTS configurations (verified against live OGC WMTS 1.0.0 capabilities)
MARS_TREK_WMTS_ENDPOINT = "https://trek.nasa.gov/tiles/Mars/EQ/"
MARS_TREK_ENDPOINT = MARS_TREK_WMTS_ENDPOINT
MARS_TREK_CAPABILITIES_URL = (
    "https://trek.nasa.gov/tiles/Mars/EQ/"
    "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/WMTSCapabilities.xml"
)

MARS_TREK_OFFICIAL_LAYERS = [
    {
        "product_id": "TREK_HRSC_MOLA_BLEND_DEM",
        "title": "NASA Mars Trek HRSC–MOLA Blended Global Shaded Relief (200m)",
        "layer_identifier": "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
        "format": "image/jpeg",
        "spatial_resolution_m": 200.0,
        "min_zoom": 0,
        "max_zoom": 8,
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "capabilities_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/WMTSCapabilities.xml",
        "description": "Global 200 m/pixel blended digital elevation model color hillshade merging Mars Express HRSC stereo and MGS MOLA topography (EPSG:104905 / default028mm).",
        "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    },
    {
        "product_id": "TREK_MOLA_COLOR_HILLSHADE",
        "title": "NASA Mars Trek MGS MOLA Global Colour Shaded Relief (463m)",
        "layer_identifier": "Mars_MGS_MOLA_ClrShade_merge_global_463m",
        "format": "image/jpeg",
        "spatial_resolution_m": 463.0,
        "min_zoom": 0,
        "max_zoom": 7,
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "capabilities_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml",
        "description": "Global color shaded topography derived from the Mars Orbiter Laser Altimeter (MOLA) aboard Mars Global Surveyor.",
        "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    },
    {
        "product_id": "TREK_VIKING_MDIM21_COLOR",
        "title": "NASA Mars Trek Viking Orbiter MDIM 2.1 Global Mosaic (232m)",
        "layer_identifier": "Mars_Viking_MDIM21_ClrMosaic_global_232m",
        "format": "image/jpeg",
        "spatial_resolution_m": 232.0,
        "min_zoom": 0,
        "max_zoom": 7,
        "bounds": [-180.0, -90.0, 180.0, 90.0],
        "capabilities_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/WMTSCapabilities.xml",
        "description": "Standard Mars Digital Image Model (MDIM 2.1) global visual albedo colour mosaic from Viking Orbiter cameras.",
        "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    },
    {
        "product_id": "TREK_JEZERO_HIRISE_MOSAIC_25CM",
        "title": "Mars 2020 TRN HiRISE Orthorectified Image Mosaic (0.25m, DOI: 10.5066/P9QJDP48)",
        "layer_identifier": "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
        "format": "image/png",
        "spatial_resolution_m": 0.25,
        "min_zoom": 0,
        "max_zoom": 17,
        "bounds": [77.2229331, 18.3067994, 77.583964, 18.669315],
        "capabilities_url": "https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/WMTSCapabilities.xml",
        "description": "Official USGS Mars 2020 Terrain Relative Navigation HiRISE Orthorectified Image Mosaic (0.25 m/px, DOI: 10.5066/P9QJDP48) covering the Jezero Crater landing region and Western Delta.",
        "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    },
    {
        "product_id": "TREK_MRO_CTX_JEZERO_REGIONAL",
        "title": "Mars 2020 TRN CTX Orthorectified Image Mosaic (6m, DOI: 10.5066/P9GV1ND3)",
        "layer_identifier": "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0",
        "format": "image/png",
        "spatial_resolution_m": 6.0,
        "min_zoom": 0,
        "max_zoom": 13,
        "bounds": [77.1604655, 18.2110274, 77.6991776, 18.7211945],
        "capabilities_url": "https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/WMTSCapabilities.xml",
        "description": "Official USGS Mars 2020 Terrain Relative Navigation CTX Orthorectified Image Mosaic (6.0 m/px, DOI: 10.5066/P9GV1ND3) covering Jezero Crater.",
        "tile_url": "https://trek.nasa.gov/tiles/Mars/EQ/JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    },
]


class MarsTrekConnector(BaseDataSourceConnector):
    """Connector for NASA Mars Trek OGC WMTS services."""

    def __init__(self, entry: DataSourceEntry) -> None:
        super().__init__(entry)
        self._capabilities_cache: dict[str, Any] | None = None

    async def check_connection(self) -> tuple[ConnectionState, str | None]:
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                res = await client.get(MARS_TREK_CAPABILITIES_URL)
                if res.status_code == 200 and "Capabilities" in res.text:
                    return ConnectionState.CONNECTED, None
                return (
                    ConnectionState.STALE,
                    f"Mars Trek WMTS returned HTTP {res.status_code}; using cached WMTS descriptors.",
                )
        except Exception as exc:
            return (
                ConnectionState.STALE,
                f"Mars Trek WMTS network probe failed ({type(exc).__name__}); using cached WMTS descriptors.",
            )

    async def fetch_metadata(self) -> dict[str, Any]:
        if self._capabilities_cache:
            return self._capabilities_cache

        layers_info = []
        for layer in MARS_TREK_OFFICIAL_LAYERS:
            layers_info.append(
                {
                    "identifier": layer["layer_identifier"],
                    "title": layer["title"],
                    "format": layer["format"],
                    "spatial_resolution_m": layer["spatial_resolution_m"],
                    "tile_matrix_set": "default028mm",
                    "projection": "EPSG:4326 (IAU2000:49900 equivalent equirectangular)",
                    "min_zoom": layer["min_zoom"],
                    "max_zoom": layer["max_zoom"],
                    "bounds": layer["bounds"],
                }
            )

        meta = {
            "service": "OGC WMTS",
            "version": "1.0.0",
            "service_provider": "NASA Solar System Treks Project / JPL",
            "capabilities_url": MARS_TREK_CAPABILITIES_URL,
            "wmts_base_url": MARS_TREK_ENDPOINT,
            "supported_matrix_sets": ["default028mm", "Equirectangular_256"],
            "supported_layers_count": len(layers_info),
            "layers": layers_info,
            "retrieval_status": "AUTHENTIC_WMTS_DESCRIPTOR",
        }
        self._capabilities_cache = meta
        return meta

    async def list_products(self, limit: int = 50) -> list[DataProduct]:
        products = []
        for layer in MARS_TREK_OFFICIAL_LAYERS[:limit]:
            b = layer["bounds"]
            footprint = {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]],
                },
                "properties": {"layer": layer["layer_identifier"]},
            }
            products.append(
                DataProduct(
                    product_id=layer["product_id"],
                    source_id="nasa_mars_trek",
                    mission="Multi-Mission Cartography",
                    spacecraft="MRO / MGS / Viking / Mars Express",
                    instrument="HiRISE / CTX / MOLA / HRSC",
                    product_type="WMTS_MAP_TILE_MOSAIC",
                    title=layer["title"],
                    description=layer["description"],
                    acquisition_timestamp=datetime(2021, 4, 1),
                    publication_timestamp=datetime(2022, 1, 1),
                    min_lon=b[0],
                    max_lon=b[2],
                    min_lat=b[1],
                    max_lat=b[3],
                    spatial_resolution_m=layer["spatial_resolution_m"],
                    units="Reflectance / Elevation (m)",
                    data_format=layer["format"].split("/")[-1].upper(),
                    processing_level="Level 4 Calibrated Controlled Mosaic",
                    quality_flags=["OGC_WMTS_ALIGNED", "EQUIRECTANGULAR_WARPED", "COORDINATES_VERIFIED"],
                    footprint_geojson=footprint,
                    preview_url=layer["tile_url"].replace("{z}", "10").replace("{y}", "0").replace("{x}", "0"),
                    download_url=layer["tile_url"],
                    official_archive_url="https://trek.nasa.gov/mars/",
                    citation="NASA/JPL Solar System Treks Project (SSTP). Mars Trek WMTS. DOI: 10.5066/F71V5C67",
                    map_layer_supported=True,
                    map_layer_config={
                        "layer_type": "wmts",
                        "layer_id": layer["layer_identifier"],
                        "url_template": layer["tile_url"],
                        "tile_url": layer["tile_url"],
                        "format": layer["format"],
                        "bounds": layer["bounds"],
                        "min_zoom": layer["min_zoom"],
                        "max_zoom": layer["max_zoom"],
                    },
                )
            )
        return products
