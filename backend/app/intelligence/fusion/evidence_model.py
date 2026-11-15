"""
Normalized Observation & Unified Evidence Schema for MARSPath Mission Intelligence & Risk Fusion.
Strict scientific data modeling preserving IAU2000 Mars coordinates, Solar Longitude (Ls),
provenance classifications, and explicit missing-value semantics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProvenanceKind(str, Enum):
    """Explicit scientific data provenance classification."""

    MEASURED = "measured"
    HISTORICAL = "historical"
    COMPUTED = "computed"
    MODELED = "modeled"
    DERIVED = "derived"


class QualityTier(str, Enum):
    """Scientific validation tier."""

    GOLD = "GOLD"
    SILVER = "SILVER"
    BRONZE = "BRONZE"
    UNVERIFIED = "UNVERIFIED"


class SourceFreshness(str, Enum):
    """Authoritative source connection and freshness state."""

    CONNECTED_CURRENT = "Connected and current"
    CONNECTED_STALE = "Connected but stale"
    PARTIALLY_AVAILABLE = "Partially available"
    UNAVAILABLE = "Unavailable"
    UNVERIFIED = "Unverified"


class NormalizedObservation(BaseModel):
    """
    Unified evidence entity representing a planetary observation or measurement
    from NASA PDS, HiRISE, CTX, MOLA-HRSC, MEDA, THEMIS, NAIF/SPICE, or rover telemetry.
    """

    observation_id: str = Field(..., description="Globally unique observation identifier")
    source_id: str = Field(
        ..., description="Authoritative source identifier (e.g. pds_geosciences, themis, naif_spice)"
    )
    dataset_id: str = Field(..., description="Specific dataset or catalog identifier")
    instrument: str = Field(..., description="Observing instrument or sensor (e.g. HiRISE, CTX, MEDA-ATS, THEMIS-IR)")
    measurement_type: str = Field(..., description="Scientific property or data product type")
    measurement_value: Any = Field(None, description="Scalar, vector, or structured value (None if missing)")
    units: str | None = Field(None, description="Physical units (SI or standard planetary units)")
    geometry: dict[str, Any] = Field(..., description="GeoJSON geometry (Point, Polygon, LineString)")
    bbox: list[float] | None = Field(None, description="[min_lon, min_lat, max_lon, max_lat] in degrees")
    crs: str = Field("IAU2000:49900", description="Planetary coordinate reference system")
    timestamp_utc: datetime | None = Field(None, description="Observation epoch in Earth UTC")
    martian_sol: int | None = Field(None, description="Mission sol when observation was taken")
    solar_longitude_ls: float | None = Field(
        None, description="Martian season / solar longitude Ls in degrees [0, 360)"
    )
    validity_start_utc: datetime | None = Field(None, description="Start of temporal validity window")
    validity_end_utc: datetime | None = Field(None, description="End of temporal validity window")
    spatial_resolution_m: float | None = Field(
        None, description="Spatial resolution in meters per pixel or spatial footprint"
    )
    vertical_datum: str | None = Field(None, description="Vertical reference datum (e.g. Mars Areoid (MOLA))")
    provenance_kind: ProvenanceKind = Field(
        ..., description="Kind of data: measured, historical, computed, modeled, derived"
    )
    quality_tier: QualityTier = Field(QualityTier.SILVER, description="Evidence quality tier")
    quality_flags: list[str] = Field(default_factory=list, description="Data flags or caveats")
    uncertainty_info: dict[str, Any] = Field(
        default_factory=dict, description="Quantified uncertainty bounds or error estimates"
    )
    doi: str | None = Field(None, description="Persistent identifier / DOI (e.g. 10.5066/P9REJ9JN)")
    official_url: str | None = Field(None, description="Authoritative web or archive landing link")
    source_timestamp: datetime | None = Field(None, description="Timestamp asserted by originating archive")
    ingestion_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When ingested into MARSPath"
    )
    checksum: str | None = Field(None, description="SHA-256 or official checksum of underlying product")
    title: str | None = Field(None, description="Human-readable title")
    description: str | None = Field(None, description="Scientific context and methodology notes")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extended source-specific attributes")
    # Backwards-compatible fields for legacy orbital observation consumers
    spacecraft_id: str | None = Field(None, description="Spacecraft identifier (e.g. mro, ody, tgo)")
    spacecraft_name: str | None = Field(None, description="Spacecraft full name")
    target_name: str | None = Field(None, description="Target landmark or feature name")
    acquisition_utc: str | None = Field(None, description="ISO UTC acquisition timestamp string")
    center_lon: float | None = Field(None, description="Center longitude")
    center_lat: float | None = Field(None, description="Center latitude")
    spatial_resolution_m_per_px: float | None = Field(None, description="Pixel resolution in meters")
    footprint_geojson: dict[str, Any] | None = Field(None, description="Footprint GeoJSON feature or geometry")
    pds_product_id: str | None = Field(None, description="NASA PDS product identifier")
    source_url: str | None = Field(None, description="Direct archive or landing URL")
    processing_status: str | None = Field("VALIDATED", description="Processing and validation status")


class SourceHealthStatus(BaseModel):
    """Current health, connection state, and freshness metrics for a registered source."""

    source_id: str
    source_name: str
    freshness: SourceFreshness
    is_connected: bool
    is_stale: bool
    last_sync_utc: datetime | None = None
    item_count: int = 0
    latency_ms: float | None = None
    freshness_explanation: str = ""


class CoverageGap(BaseModel):
    """Identified spatial region lacking high-resolution observation coverage."""

    gap_id: str
    region_name: str
    bbox: list[float]
    missing_evidence_types: list[str]
    available_fallback_resolution_m: float | None = None
    risk_assessment: str = ""
    recommended_reconnaissance: str = ""


class DataFreshnessReport(BaseModel):
    """Subsystem-wide freshness and health audit across all integrated data sources."""

    status: str = "operational"
    evaluated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sources_count: int
    connected_count: int
    stale_count: int
    sources: list[SourceHealthStatus]
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
