from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ConnectionState(str, Enum):
    REGISTERED = "REGISTERED"
    CONNECTED = "CONNECTED"
    METADATA_AVAILABLE = "METADATA_AVAILABLE"
    DATA_INGESTED = "DATA_INGESTED"
    PROCESSING = "PROCESSING"
    STALE = "STALE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    ERROR = "ERROR"


class IntegrationType(str, Enum):
    OGC_WMTS = "OGC_WMTS"
    REST_SEARCH_API = "REST_SEARCH_API"
    PDS_ARCHIVE_BUNDLE = "PDS_ARCHIVE_BUNDLE"
    PDS_DATA_RELEASE_FEED = "PDS_DATA_RELEASE_FEED"
    SPICE_TOOLKIT = "SPICE_TOOLKIT"
    ODE_REST_SERVICE = "ODE_REST_SERVICE"
    DATA_PORTAL_CONNECTOR = "DATA_PORTAL_CONNECTOR"


class DataSourceEntry(BaseModel):
    source_id: str = Field(..., description="Unique source identifier")
    source_name: str = Field(..., description="Display name of the official source")
    organization: str = Field(..., description="Operating institution or NASA center")
    official_url: str = Field(..., description="Official landing URL")
    integration_type: IntegrationType = Field(..., description="Technical integration mechanism")
    description: str = Field(..., description="Authoritative summary of data provided")
    primary_use: str = Field(..., description="How MARSPath utilizes this data")
    supported_products: list[str] = Field(default_factory=list, description="List of supported scientific products")
    connection_status: ConnectionState = Field(ConnectionState.CONNECTED, description="Live connection status")
    metadata_access_status: str = Field(..., description="Summary of metadata query capability")
    ingestion_status: ConnectionState = Field(ConnectionState.DATA_INGESTED, description="State of data ingestion")
    last_checked_at: datetime | None = Field(None, description="Timestamp of last check")
    last_successful_sync: datetime | None = Field(None, description="Timestamp of last successful synchronization")
    indexed_products_count: int = Field(0, description="Number of products cataloged in MARSPath")
    is_data_ingested: bool = Field(False, description="Whether authentic scientific data is ingested")
    active_layers_count: int = Field(0, description="Number of active map layers backed by this source")
    last_error: str | None = Field(None, description="Last error message if connection degraded")
    citation_information: dict[str, Any] = Field(default_factory=dict, description="Formal attribution and DOI")


class GlobalSourcesStatus(BaseModel):
    total_sources: int = 7
    connected_count: int
    metadata_available_count: int
    data_ingested_count: int
    total_indexed_products: int
    active_map_layers_count: int
    last_sync_utc: datetime
    sources: list[DataSourceEntry]


class DataProduct(BaseModel):
    product_id: str = Field(..., description="Unique scientific product identifier")
    source_id: str = Field(..., description="Originating source ID")
    mission: str = Field(..., description="Planetary exploration mission")
    spacecraft: str = Field(..., description="Host spacecraft or lander")
    instrument: str = Field(..., description="Observing instrument")
    product_type: str = Field(..., description="Type of data product")
    title: str = Field(..., description="Human-readable title")
    description: str = Field(..., description="Scientific description")
    acquisition_timestamp: datetime | None = Field(None, description="Acquisition UTC timestamp")
    publication_timestamp: datetime | None = Field(None, description="PDS release publication timestamp")
    retrieval_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC), description="Ingestion timestamp")
    martian_sol: int | None = Field(None, description="Mission sol when acquired")
    min_lon: float | None = Field(None, description="Minimum longitude (IAU2000 Mars East)")
    max_lon: float | None = Field(None, description="Maximum longitude (IAU2000 Mars East)")
    min_lat: float | None = Field(None, description="Minimum latitude (IAU2000 Positive North)")
    max_lat: float | None = Field(None, description="Maximum latitude (IAU2000 Positive North)")
    spatial_resolution_m: float | None = Field(None, description="Spatial resolution in meters per pixel")
    units: str | None = Field(None, description="Physical units of data")
    data_format: str = Field(..., description="File format (e.g. GeoTIFF, CSV, IMG, JSON)")
    processing_level: str = Field(..., description="CODMAC or NASA processing level")
    quality_flags: list[str] = Field(default_factory=list, description="Calibration and validation flags")
    footprint_geojson: dict[str, Any] | None = Field(None, description="GeoJSON polygon of observation extent")
    preview_url: str | None = Field(None, description="Direct thumbnail or preview image URL")
    download_url: str | None = Field(None, description="Direct or archive download link")
    official_archive_url: str = Field(..., description="Upstream PDS or NASA portal URL")
    citation: str = Field(..., description="Formal data citation")
    map_layer_supported: bool = Field(False, description="Whether this product can be rendered as a map layer")
    map_layer_config: dict[str, Any] | None = Field(None, description="Tile URL or vector layer configuration")


class MedaObservation(BaseModel):
    sol: int = Field(..., description="Martian sol")
    timestamp_utc: datetime = Field(..., description="UTC timestamp of observation")
    air_temp_c: float | None = Field(None, description="Ambient air temperature in Celsius from ATS")
    ground_temp_c: float | None = Field(None, description="Ground surface temperature in Celsius from TIRS")
    pressure_pa: float | None = Field(None, description="Atmospheric pressure in Pascals from PS")
    wind_speed_m_s: float | None = Field(None, description="Horizontal wind speed in m/s from WIND")
    wind_dir_deg: float | None = Field(None, description="Wind azimuth direction in degrees")
    relative_humidity_pct: float | None = Field(None, description="Relative humidity percentage from RHS")
    dust_optical_depth_tau: float | None = Field(None, description="Column optical depth tau from RDS")
    uv_flux_w_m2: float | None = Field(None, description="Ultraviolet downward flux in W/m^2")
    sensor_status: str = Field("NOMINAL", description="Operating health of sensor suite")
    quality_flags: list[str] = Field(default_factory=list, description="Scientific quality flags")
    source_product: str = Field(..., description="Underlying NASA PDS product identifier")


class ThemisObservation(BaseModel):
    product_id: str = Field(..., description="THEMIS Product ID")
    observation_type: str = Field(..., description="DAY_IR, NIGHT_IR, or THERMAL_INERTIA")
    center_lon: float = Field(..., description="Center East Longitude")
    center_lat: float = Field(..., description="Center Latitude")
    thermal_inertia_tiu: float | None = Field(None, description="Thermal inertia (J m^-2 K^-1 s^-1/2)")
    brightness_temp_k: float | None = Field(None, description="Calibrated brightness temperature in Kelvin")
    spatial_resolution_m: float = Field(100.0, description="Spatial resolution in meters")
    acquisition_utc: str = Field(..., description="UTC acquisition timestamp")
    pds_id: str = Field(..., description="PDS volume and product identifier")
    archive_url: str = Field(..., description="ASU / PDS archive URL")
    footprint_geojson: dict[str, Any] | None = Field(None, description="Spatial bounding polygon")


class SpiceGeometryResult(BaseModel):
    spacecraft_id: str = Field(..., description="Spacecraft identifier")
    target: str = Field("MARS", description="Observed target body")
    epoch_utc: str = Field(..., description="Target epoch in UTC")
    sub_spacecraft_lon: float = Field(..., description="Sub-spacecraft aerocentric longitude")
    sub_spacecraft_lat: float = Field(..., description="Sub-spacecraft aerocentric latitude")
    spacecraft_altitude_km: float = Field(..., description="Altitude above reference areoid")
    sub_solar_lon: float = Field(..., description="Sub-solar planetocentric longitude")
    sub_solar_lat: float = Field(..., description="Sub-solar planetocentric latitude")
    solar_incidence_angle_deg: float = Field(..., description="Solar incidence angle at sub-spacecraft point")
    phase_angle_deg: float = Field(..., description="Sun-target-observer phase angle")
    emission_angle_deg: float = Field(..., description="Surface normal to spacecraft emission angle")
    local_solar_time: str = Field(..., description="True local solar time HH:MM:SS")
    ephemeris_source: str = Field(..., description="Kernel provenance or SPICE configuration")


class DataRelease(BaseModel):
    release_id: str = Field(..., description="PDS release identifier")
    release_name: str = Field(..., description="Display title of the release")
    mission: str = Field(..., description="Target planetary mission")
    spacecraft: str = Field(..., description="Host spacecraft")
    publication_date: str = Field(..., description="Release date in UTC (YYYY-MM-DD)")
    coverage_start: str = Field(..., description="Earliest sol or date in release")
    coverage_end: str = Field(..., description="Latest sol or date in release")
    instruments_included: list[str] = Field(default_factory=list, description="Instruments contributing data")
    products_added_count: int = Field(0, description="Estimated number of new products")
    processing_status: str = Field("INDEXED", description="Status within MARSPath")
    official_release_url: str = Field(..., description="URL to official PDS release notes")
    is_processed_in_marspath: bool = Field(True, description="Whether MARSPath has indexed this release")


class ProductSearchQuery(BaseModel):
    query: str | None = None
    instrument: str | None = None
    spacecraft: str | None = None
    source_id: str | None = None
    product_type: str | None = None
    min_sol: int | None = None
    max_sol: int | None = None
    min_lon: float | None = None
    max_lon: float | None = None
    min_lat: float | None = None
    max_lat: float | None = None
    limit: int = Field(25, ge=1, le=200)
    offset: int = Field(0, ge=0)


class ProductSearchResponse(BaseModel):
    total_matched: int
    limit: int
    offset: int
    products: list[DataProduct]


class SyncResponse(BaseModel):
    success: bool
    sync_timestamp_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sources_updated: list[str]
    new_products_indexed: int
    errors: list[str] = Field(default_factory=list)
    message: str
