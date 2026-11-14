"""
Pydantic Schemas for MARSPath Live Mars Intelligence Subsystem.
Strict validation of planetary coordinates, UTC timestamps, ephemeris state, and data provenance.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataFreshnessState(str, Enum):
    """Explicit scientific data freshness states."""
    LATEST_AVAILABLE = "LATEST AVAILABLE"
    LIVE_TELEMETRY = "LIVE TELEMETRY"
    HISTORICAL = "HISTORICAL"
    PREDICTED = "PREDICTED"
    PROCESSING = "PROCESSING"
    STALE = "STALE"
    SOURCE_UNAVAILABLE = "SOURCE UNAVAILABLE"


class ProvenanceMetadata(BaseModel):
    """Scientific source attribution and data lineage."""
    source_name: str = Field(..., description="Authoritative publisher or archive")
    dataset_id: str = Field(..., description="Unique dataset or PDS product ID")
    acquisition_utc: str = Field(..., description="Observation or measurement UTC timestamp")
    publication_utc: str | None = Field(None, description="Formal archive publication date")
    retrieval_utc: str = Field(..., description="When data was retrieved by MARSPath")
    last_sync_utc: str = Field(..., description="Last synchronization verification timestamp")
    data_state: DataFreshnessState = Field(..., description="Explicit scientific status")
    spatial_resolution: str | None = Field(None, description="Spatial resolution if applicable")
    uncertainty: str | None = Field(None, description="Known positional or measurement uncertainty")
    citation_url: str | None = Field(None, description="Authoritative web or archive link")


class CoordinatesLonLat(BaseModel):
    """Areocentric longitude and latitude in IAU2000 Mars sphere."""
    lon: float = Field(..., ge=-180.0, le=360.0, description="Longitude in degrees East")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees North")
    elevation_m: float | None = Field(None, description="Elevation relative to MOLA areoid")


class SpacecraftPosition(BaseModel):
    """Current calculated or received position of a Mars orbiter."""
    spacecraft_id: str = Field(..., description="Machine identifier (e.g. mro, ody, maven, mex, tgo)")
    name: str = Field(..., description="Human-readable spacecraft name")
    epoch_utc: str = Field(..., description="UTC epoch of calculated position")
    lon: float = Field(..., ge=-180.0, le=360.0, description="Sub-satellite longitude degrees East")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Sub-satellite latitude degrees North")
    altitude_km: float = Field(..., description="Orbital altitude above reference Mars areoid in km")
    velocity_kms: float = Field(..., description="Orbital speed relative to Mars center in km/s")
    heading_deg: float = Field(..., description="Ground-track heading angle in degrees (0=North, 90=East)")
    orbit_period_minutes: float = Field(..., description="Orbital period in minutes")
    footprint_swath_width_km: float = Field(..., description="Nadir instrument field-of-view swath width in km")
    state: DataFreshnessState = Field(..., description="Predicted, historical, or latest available state")
    uncertainty_km: float = Field(..., description="Estimated along-track uncertainty in km")
    provenance: ProvenanceMetadata = Field(..., description="Ephemeris source and kernel lineage")


class GroundTrackPoint(BaseModel):
    """Single point along a calculated orbital ground track."""
    epoch_utc: str
    lon: float
    lat: float
    altitude_km: float


class GroundTrack(BaseModel):
    """Orbital ground track polyline covering past and predicted intervals."""
    spacecraft_id: str
    name: str
    start_utc: str
    end_utc: str
    step_seconds: int
    points: list[GroundTrackPoint]
    footprint_swath_width_km: float
    orbit_number: int | None = None
    state: DataFreshnessState = DataFreshnessState.PREDICTED
    provenance: ProvenanceMetadata


class SpacecraftInfo(BaseModel):
    """Comprehensive spacecraft profile and mission metadata."""
    spacecraft_id: str
    name: str
    agency: str
    mission: str
    launch_date: str
    arrival_date: str
    orbit_type: str
    semi_major_axis_km: float
    eccentricity: float
    inclination_deg: float
    periapsis_altitude_km: float
    apoapsis_altitude_km: float
    orbital_period_minutes: float
    primary_instruments: list[str]
    description: str
    current_position: SpacecraftPosition
    ephemeris_source: str
    ephemeris_valid_range: str


class RoverPosition(BaseModel):
    """Telemetry and position for an active or historical Mars surface rover."""
    rover_id: str = Field(..., description="perseverance or curiosity")
    name: str
    mission: str
    landing_site: str
    landing_date_utc: str
    landing_lon: float
    landing_lat: float
    sol: int
    earth_date_utc: str
    lon: float
    lat: float
    elevation_m: float
    total_odometry_meters: float
    last_drive_distance_meters: float
    heading_deg: float | None = None
    roll_deg: float | None = None
    pitch_deg: float | None = None
    active_instruments: list[str]
    state: DataFreshnessState
    uncertainty_meters: float
    provenance: ProvenanceMetadata


class RoverDrive(BaseModel):
    """Single recorded drive segment."""
    drive_id: str
    sol: int
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    distance_meters: float
    duration_seconds: float | None = None
    elevation_change_m: float | None = None


class RoverTraverse(BaseModel):
    """Complete cumulative historical traverse dataset."""
    rover_id: str
    name: str
    landing_site: str
    latest_sol: int
    total_drives: int
    total_odometry_meters: float
    latest_position: RoverPosition
    geojson: dict[str, Any]
    provenance: ProvenanceMetadata


class RoverObservation(BaseModel):
    """Surface image or scientific measurement acquired by a rover."""
    observation_id: str
    rover_id: str
    instrument: str
    sol: int
    earth_date_utc: str
    target_name: str
    lon: float
    lat: float
    image_url: str
    thumbnail_url: str | None = None
    description: str
    provenance: ProvenanceMetadata


class OrbitalObservation(BaseModel):
    """High-resolution orbital image or remote sensing observation."""
    observation_id: str
    spacecraft_id: str
    spacecraft_name: str
    instrument: str
    target_name: str
    acquisition_utc: str
    martian_sol: int | None = None
    center_lon: float
    center_lat: float
    spatial_resolution_m_per_px: float
    image_width: int
    image_height: int
    footprint_geojson: dict[str, Any]
    pds_product_id: str
    source_url: str
    thumbnail_url: str | None = None
    processing_status: str
    provenance: ProvenanceMetadata


class TimelineEvent(BaseModel):
    """Chronological event across orbital and surface missions."""
    event_id: str
    event_type: str = Field(..., description="rover_drive, orbital_observation, spacecraft_event, waypoint")
    title: str
    description: str
    earth_date_utc: str
    martian_sol: int | None = None
    related_entity_id: str
    related_entity_type: str = Field(..., description="spacecraft, rover, observation")
    lon: float | None = None
    lat: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class IntelligenceStatus(BaseModel):
    """Overall health, synchronizer status, and freshness summary."""
    status: str = "operational"
    service_version: str = "1.0.0"
    last_sync_utc: str
    next_scheduled_sync_utc: str
    sources_tracked: int
    active_spacecraft_count: int
    active_rovers_count: int
    cataloged_observations_count: int
    freshness_summary: dict[str, int]
    coverage_regions: list[str]


class SyncRequest(BaseModel):
    """Parameters for on-demand synchronization request."""
    force_refresh: bool = False
    source_filter: list[str] | None = None


class SyncResponse(BaseModel):
    """Result of synchronization execution."""
    success: bool
    sync_timestamp_utc: str
    updated_sources: list[str]
    new_observations_count: int
    rover_updates_count: int
    spacecraft_propagated_count: int
    message: str
