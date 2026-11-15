"""Schemas for Dual-Radius Walk-Back Safety Envelopes and RF line-of-sight analysis.

Provides verified contracts for:
1. Envelope A: Rover-Assisted Reachable Range (vehicle mobility model).
2. Envelope B: On-Foot Walk-Back Range (conservative pedestrian mobility model).
3. On-Foot Return Feasibility metrics and high-difficulty segment breakdowns.
4. RF Line-of-Sight and Relay Blackout warnings for Martian ground traverses.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.app.schemas.coordinates import MarsCoordinate


class WalkBackStatus(str, Enum):
    """Categorical status for astronaut on-foot return feasibility."""

    SAFE_WITHIN_LIMIT = "SAFE WITHIN CONFIGURED LIMIT"
    LIMITED_MARGIN = "LIMITED MARGIN"
    LIMIT_EXCEEDED = "WALK-BACK LIMIT EXCEEDED"
    DATA_UNAVAILABLE = "DATA UNAVAILABLE"


class HighDifficultySegment(BaseModel):
    """A traverse segment imposing severe slope, roughness, or metabolic cost."""

    segment_index: int = Field(..., description="0-based waypoint segment index along route")
    start_coord: MarsCoordinate
    end_coord: MarsCoordinate
    length_meters: float
    slope_deg: float
    roughness_tri: float
    difficulty_score: float = Field(..., description="0-100 normalized difficulty rating")
    reason: str = Field(..., description="Primary limiting factor (e.g. 'Steep uphill scarp > 15°')")


class OnFootReturnFeasibility(BaseModel):
    """Feasibility of astronaut on-foot walk-back to habitat if rover fails."""

    walk_back_distance_km: float = Field(..., description="Direct terrain-conforming walking distance to habitat in km")
    walk_back_duration_hours: float = Field(..., description="Estimated walking time under pedestrian mobility model")
    walk_back_duration_formatted: str = Field(..., description="Human-readable duration e.g. '2h 15m'")
    remaining_eva_hours: float = Field(
        ..., description="Remaining usable EVA margin before suit life-support expiration"
    )
    emergency_resource_margin_pct: float = Field(
        ..., description="Estimated emergency O2/battery reserve percentage remaining after walk-back"
    )
    max_permitted_walking_hours: float = Field(
        ..., description="Configured ceiling for emergency pedestrian return (default 3.5h)"
    )
    terrain_difficulty: str = Field(..., description="Categorical terrain challenge: MILD, MODERATE, HIGH, SEVERE")
    status: WalkBackStatus = Field(..., description="Feasibility status enum")
    destination_exceeds_limit: bool = Field(
        ..., description="True if destination point is outside the on-foot walk-back envelope"
    )
    warning_message: str | None = Field(
        default=None,
        description="Explicit warning message when walk-back limit is exceeded or marginal",
    )
    high_difficulty_segments: list[HighDifficultySegment] = Field(
        default_factory=list,
        description="List of traverse segments responsible for reduced walk-back feasibility",
    )


class EnvelopeMetadata(BaseModel):
    """Metadata and serialized raster grid for a mobility reachability envelope."""

    envelope_type: str = Field(..., description="'rover_assisted' or 'on_foot_walkback'")
    label: str = Field(..., description="Human-readable label for the envelope")
    color: str = Field(..., description="Hex color for map visualization (#00d2ff cyan or #00e676 green)")
    mobility_model: str = Field(..., description="Description of the mathematical mobility profile")
    assumed_speed_m_s: float = Field(..., description="Base traversing velocity in m/s")
    assumed_speed_km_h: float = Field(..., description="Base traversing velocity in km/h")
    max_slope_deg: float = Field(..., description="Traversability slope cutoff threshold")
    budget_hours: float = Field(..., description="Time budget in hours")
    budget_minutes: float = Field(..., description="Time budget in minutes")
    reachable_fraction: float = Field(..., description="Fraction of corridor cells reachable within budget")
    time_grid: dict[str, Any] | None = Field(
        default=None,
        description="Downsampled time grid matrix for map rendering overlay",
    )


class DualRadiusEnvelopes(BaseModel):
    """Container for both Rover-Assisted and On-Foot Walk-Back safety envelopes."""

    rover_assisted: EnvelopeMetadata
    on_foot_walkback: EnvelopeMetadata
    habitat_coordinate: MarsCoordinate
    astronaut_coordinate: MarsCoordinate
    combined_mode_supported: bool = Field(
        default=True,
        description="Whether frontend map can display both envelopes simultaneously",
    )
    model_assumptions: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed physical and metabolic assumptions of each model",
    )


class RFRelayOrbiterStatus(BaseModel):
    """Status of verified Mars relay orbiters with UHF payload."""

    spacecraft: str = Field(..., description="Orbiter name e.g. 'Mars Reconnaissance Orbiter (MRO)'")
    payload: str = Field(..., description="Payload name e.g. 'Electra UHF Proximity Link'")
    frequency_band: str = Field(default="UHF 390-450 MHz")
    is_in_view: bool = Field(..., description="True if orbiter elevation angle > 10° above local horizon")
    elevation_angle_deg: float = Field(..., description="Orbiter elevation angle above terrain horizon")
    pass_window_remaining_min: float | None = Field(default=None)


class RFCommunicationStatus(BaseModel):
    """RF line-of-sight and relay availability along the route."""

    direct_habitat_los: str = Field(
        ...,
        description="'CONNECTED', 'POTENTIAL_OBSTRUCTION', 'CONFIRMED_BLACKOUT', or 'UNKNOWN'",
    )
    active_orbiters: list[RFRelayOrbiterStatus] = Field(default_factory=list)
    best_orbiter_contact: str | None = Field(default=None)
    terrain_shadow_risk: str = Field(
        ...,
        description="'LOW', 'ELEVATED', or 'CRITICAL' terrain shadow exposure",
    )
    line_of_sight_fraction: float = Field(
        default=1.0,
        description="Fraction of route waypoints with uninterrupted direct or relay line of sight",
    )
    notes: str = Field(
        ...,
        description="Scientific and topological explanation of RF conditions",
    )


class WalkBackAssessment(BaseModel):
    """Comprehensive walk-back safety assessment combining envelopes, feasibility, and RF."""

    on_foot_feasibility: OnFootReturnFeasibility
    rover_assisted_return_hours: float = Field(..., description="Vehicle-assisted return time from destination")
    rover_vs_foot_ratio: float = Field(
        ..., description="Ratio of on-foot duration to vehicle duration (pedestrian / rover)"
    )
    dual_envelopes: DualRadiusEnvelopes | None = Field(default=None)
    rf_communication: RFCommunicationStatus | None = Field(default=None)
