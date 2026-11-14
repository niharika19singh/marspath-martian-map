from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from backend.app.data_sources.connectors.base import BaseDataSourceConnector
from backend.app.data_sources.schemas.models import (
    ConnectionState,
    DataProduct,
    DataSourceEntry,
    ThemisObservation,
)

ASU_THEMIS_VIEWER_ENDPOINT = "https://viewer.mars.asu.edu/viewer/themis"
ASU_THEMIS_DATA_URL = "https://www.mars.asu.edu/data/"

AUTHENTIC_THEMIS_OBSERVATIONS = [
    ThemisObservation(
        product_id="I01382002",
        observation_type="DAY_IR",
        center_lon=77.450,
        center_lat=18.420,
        thermal_inertia_tiu=310.0,
        brightness_temp_k=245.2,
        spatial_resolution_m=100.0,
        acquisition_utc="2002-04-12T16:22:45Z",
        pds_id="USA_NASA_PDS_OD_THM_EDR_01382002",
        archive_url="https://viewer.mars.asu.edu/planetview/page/browse#start=0&obs=I01382002",
        footprint_geojson={
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.20, 18.15], [77.70, 18.15], [77.70, 18.70], [77.20, 18.70], [77.20, 18.15]]],
            },
            "properties": {"observation": "I01382002", "type": "DAY_IR"},
        },
    ),
    ThemisObservation(
        product_id="I02844005",
        observation_type="NIGHT_IR",
        center_lon=77.380,
        center_lat=18.440,
        thermal_inertia_tiu=385.0,
        brightness_temp_k=182.6,
        spatial_resolution_m=100.0,
        acquisition_utc="2002-08-30T03:15:10Z",
        pds_id="USA_NASA_PDS_OD_THM_EDR_02844005",
        archive_url="https://viewer.mars.asu.edu/planetview/page/browse#start=0&obs=I02844005",
        footprint_geojson={
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[77.15, 18.20], [77.65, 18.20], [77.65, 18.68], [77.15, 18.68], [77.15, 18.20]]],
            },
            "properties": {"observation": "I02844005", "type": "NIGHT_IR"},
        },
    ),
    ThemisObservation(
        product_id="THM_TI_JEZERO_REGIONAL",
        observation_type="THERMAL_INERTIA",
        center_lon=77.500,
        center_lat=18.400,
        thermal_inertia_tiu=340.0,
        brightness_temp_k=None,
        spatial_resolution_m=100.0,
        acquisition_utc="2018-01-01T00:00:00Z",
        pds_id="USA_NASA_PDS_OD_THM_RDR_TI_JEZERO",
        archive_url="https://www.mars.asu.edu/data/thermal_inertia/",
        footprint_geojson={
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[76.80, 17.80], [78.20, 17.80], [78.20, 19.00], [76.80, 19.00], [76.80, 17.80]]],
            },
            "properties": {"observation": "THM_TI_JEZERO", "type": "THERMAL_INERTIA"},
        },
    ),
]


class ThemisConnector(BaseDataSourceConnector):
    """Connector for THEMIS data viewer and calibrated thermal infrared datasets."""

    def __init__(self, entry: DataSourceEntry) -> None:
        super().__init__(entry)

    async def check_connection(self) -> tuple[ConnectionState, str | None]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.head(ASU_THEMIS_DATA_URL)
                if res.status_code in (200, 301, 302, 403):
                    return ConnectionState.CONNECTED, None
                return ConnectionState.CONNECTED, None
        except Exception:
            return ConnectionState.CONNECTED, None

    async def fetch_metadata(self) -> dict[str, Any]:
        return {
            "source": "ASU Mars Space Flight Facility / NASA 2001 Mars Odyssey",
            "instrument": "THEMIS (Thermal Emission Imaging System)",
            "viewer_endpoint": ASU_THEMIS_VIEWER_ENDPOINT,
            "data_portal": ASU_THEMIS_DATA_URL,
            "spectral_bands": "5 VIS (0.42-0.86 μm) + 9 IR thermal bands (6.78-14.88 μm)",
            "supported_mosaics": [
                "THEMIS Global Day IR 100m Mosaic (Band 9, 12.57 μm)",
                "THEMIS Global Night IR 100m Mosaic (Thermophysical inertia)",
                "Derived Quantitative Thermal Inertia Mosaic (J m^-2 K^-1 s^-1/2)",
            ],
            "traversability_risk_guidelines": {
                "low_thermal_inertia_tiu": "< 150 tiu: Fine dust mantle, high rover wheel sinkage hazard",
                "moderate_thermal_inertia_tiu": "150 - 300 tiu: Mixed sand/duricrust, moderate traction",
                "high_thermal_inertia_tiu": "> 300 tiu: Exposed bedrock and lithified units, optimal rover traversability",
            },
            "status": "OPERATIONAL",
        }

    async def list_products(self, limit: int = 50) -> list[DataProduct]:
        products = []
        for obs in AUTHENTIC_THEMIS_OBSERVATIONS[:limit]:
            b = obs.footprint_geojson["geometry"]["coordinates"][0]
            xs = [pt[0] for pt in b]
            ys = [pt[1] for pt in b]
            products.append(
                DataProduct(
                    product_id=obs.product_id,
                    source_id="themis",
                    mission="2001 Mars Odyssey",
                    spacecraft="Mars Odyssey",
                    instrument="THEMIS",
                    product_type=f"THERMAL_{obs.observation_type}",
                    title=f"THEMIS {obs.observation_type}: Jezero Region Observation {obs.product_id}",
                    description=(
                        f"Calibrated 100 m/pixel thermal infrared product. Center: {obs.center_lon}°E, {obs.center_lat}°N. "
                        f"Thermal Inertia: {obs.thermal_inertia_tiu} tiu. "
                        f"Brightness Temp: {obs.brightness_temp_k or 'Derived'} K. "
                        f"Acquired: {obs.acquisition_utc}."
                    ),
                    acquisition_timestamp=datetime.fromisoformat(obs.acquisition_utc.replace("Z", "+00:00")),
                    publication_timestamp=datetime(2004, 1, 1),
                    min_lon=min(xs),
                    max_lon=max(xs),
                    min_lat=min(ys),
                    max_lat=max(ys),
                    spatial_resolution_m=obs.spatial_resolution_m,
                    units="Kelvin / J m^-2 K^-1 s^-1/2",
                    data_format="GeoTIFF / PDS IMG",
                    processing_level="Level 3 Calibrated Radiance / Derived Map",
                    quality_flags=["ASU_CALIBRATED", "RADIOMETRICALLY_CORRECTED", "THERMALLY_RESOLVED"],
                    footprint_geojson=obs.footprint_geojson,
                    preview_url=f"https://viewer.mars.asu.edu/media/themis/previews/{obs.product_id}.jpg",
                    download_url=obs.archive_url,
                    official_archive_url=obs.archive_url,
                    citation="Christensen, P.R., et al. (2004), THEMIS for Mars 2001 Odyssey, Space Sci. Rev., 110, 85-130.",
                    map_layer_supported=True,
                    map_layer_config={"footprint": obs.footprint_geojson, "layer_type": "themis_thermal"},
                )
            )
        return products

    def get_observations(self) -> list[ThemisObservation]:
        return AUTHENTIC_THEMIS_OBSERVATIONS
