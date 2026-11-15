"""Schemas for Planetary Protection Special-Region Geofencing and Scout Rover Handoff.

Provides verified contracts for:
1. Special-Region classification (official restricted zone, candidate sensitive region, demonstration scenario).
2. Scientific provenance metadata and COSPAR / NASA policy attributes.
3. Route intersection detection and policy enforcement.
4. Scout Rover reconnaissance dispatch request and simulation telemetry.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SpecialRegionClassification(str, Enum):
    """Categorical classification of Martian Planetary Protection Zones."""

    OFFICIAL_RESTRICTED_ZONE = "official_restricted_zone"
    CANDIDATE_SENSITIVE_REGION = "candidate_sensitive_region"
    DEMONSTRATION_SCENARIO = "demonstration_scenario"


class HumanAccessStatus(str, Enum):
    """Access clearance status for human astronaut surface missions."""

    STRICTLY_PROHIBITED = "STRICTLY_PROHIBITED"
    ASSESSMENT_REQUIRED = "ASSESSMENT_REQUIRED"
    SIMULATED_EXERCISE = "SIMULATED_EXERCISE"


class SpecialRegionFeature(BaseModel):
    """Planetary Protection Special-Region polygon with verified scientific provenance."""

    id: str = Field(..., description="Unique zone identifier e.g. 'ppz_jezero_delta_aquifer'")
    name: str = Field(..., description="Human-readable title e.g. 'Western Delta Potential Subsurface Outflow'")
    classification: SpecialRegionClassification = Field(..., description="Classification category")
    human_access_status: HumanAccessStatus = Field(..., description="Human access clearance tier")
    scout_rover_eligible: bool = Field(
        ..., description="Whether sterile robotic scout reconnaissance is authorized in lieu of human ingress"
    )
    boundary_color: str = Field(..., description="Hex or rgba stroke color for boundary rendering")
    fill_color: str = Field(..., description="Hex or rgba fill color for interior polygon rendering")
    stroke_style: str = Field(default="solid", description="'solid' or 'dashed'")
    dataset: str = Field(..., description="Authoritative dataset name / PDS product citation")
    dataset_id: str = Field(..., description="Official mission observation ID e.g. 'FRT00003E12'")
    instrument: str = Field(..., description="Detecting instrument e.g. 'CRISM / HiRISE'")
    acquisition_date: str = Field(..., description="ISO 8601 acquisition date of detection product")
    spatial_resolution_m: float = Field(..., description="Ground sampling distance of primary dataset in meters")
    data_quality: str = Field(..., description="Scientific quality descriptor")
    restriction_policy: str = Field(..., description="Applicable COSPAR / NASA Planetary Protection Policy standard")
    provenance_notes: str = Field(..., description="Zero-fabrication note detailing exact evidentiary status")
    scientific_rationale: str = Field(..., description="Geological and biological rationale for special region status")
    coordinates: list[list[float]] = Field(
        ...,
        description="Linear ring coordinates [[lon, lat], ...] in IAU2000 Mars sphere projection (positive East)",
    )
    center: list[float] = Field(..., description="Centroid [lon, lat] of the zone")
    area_sq_km: float = Field(..., description="Enclosed surface area in square kilometers")


class SpecialRegionIntersection(BaseModel):
    """Evaluation of an intersected route segment with a planetary protection zone."""

    region_id: str = Field(..., description="Identifier of the intersected zone")
    region_name: str = Field(..., description="Name of the intersected zone")
    classification: SpecialRegionClassification = Field(..., description="Classification of the zone")
    human_access_status: HumanAccessStatus = Field(..., description="Access status of the zone")
    intersecting_waypoint_indices: list[int] = Field(
        default_factory=list,
        description="Indices of route coordinates that fall within or pierce the zone polygon",
    )
    intersecting_length_meters: float = Field(
        ..., description="Total ground distance in meters traversing through the restricted zone"
    )
    penetration_depth_meters: float = Field(
        default=0.0,
        description="Maximum perpendicular distance from boundary penetrated by the traverse",
    )
    action_required: str = Field(..., description="Mandatory operational action e.g. 'REROUTE_MANDATORY'")
    scout_dispatch_recommended: bool = Field(
        default=False,
        description="True if scout rover reconnaissance should be executed prior to any near-boundary approach",
    )


class PlanetaryProtectionRouteAssessment(BaseModel):
    """Complete geofence evaluation for a candidate human mission traverse."""

    human_route_approved: bool = Field(
        ...,
        description="False if traverse intersects any 'official_restricted_zone'; True if clear or advisory-only",
    )
    total_intersections: int = Field(..., description="Number of unique special regions intersected")
    intersected_regions: list[SpecialRegionIntersection] = Field(
        default_factory=list,
        description="Detailed breakdown of each intersected zone",
    )
    highest_restriction_level: str = Field(
        ...,
        description="'NONE', 'DEMONSTRATION', 'CANDIDATE_SENSITIVE', or 'OFFICIAL_RESTRICTED'",
    )
    policy_violations: list[str] = Field(
        default_factory=list,
        description="Explicit policy non-compliance statements preventing human dispatch",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Advisory warnings for candidate or demonstration zone proximity",
    )
    alternative_routes_suggested: bool = Field(
        default=False,
        description="True if safe detour alternatives exist avoiding all geofenced zones",
    )
    cleanliness_barrier_requirement: str = Field(
        ...,
        description="Planetary protection sterilization or bio-barrier standard required",
    )
    provenance_summary: str = Field(
        ...,
        description="Statement regarding evidentiary validation of active geofences",
    )


class ScoutRoverReconRequest(BaseModel):
    """Simulated scout rover reconnaissance mission dispatch payload."""

    target_region_id: str = Field(..., description="ID of the special region to reconnoiter")
    target_region_name: str = Field(..., description="Name of the target special region")
    recon_mission_id: str = Field(..., description="Generated scout reconnaissance sortie identifier")
    scout_platform: str = Field(
        default="Ingenuity-Class Aerial Scout / Sample Fetch Micro-Rover",
        description="Robotic reconnaissance platform model",
    )
    instrument_payload: list[str] = Field(
        default_factory=lambda: ["APXS", "Microscopic Imager", "Raman Bio-Signature Spectrometer"],
        description="Sterilized scientific instrument suite",
    )
    bio_cleanliness_level: str = Field(
        default="Planetary Protection Cat IVb Post-Bakeout (< 300 spores/m²)",
        description="Sterilization standard verified for robotic scout",
    )
    target_coordinates: list[float] = Field(..., description="Target survey centroid [lon, lat]")
    estimated_survey_sol: int = Field(default=2024, description="Scheduled survey Sol")
    reconnaissance_eta_hours: float = Field(default=4.5, description="Estimated robotic transit and survey duration")
    status: str = Field(
        default="SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST",
        description="Standard simulated status header",
    )
    simulation_disclaimer: str = Field(
        default=(
            "MOCK MISSION SIMULATION ONLY. This conceptual reconnaissance request generates simulated "
            "robotic scout telemetry and does not interface with active NASA spacecraft operations."
        ),
        description="Mandatory simulated reconnaissance disclaimer",
    )
    timestamp_utc: str = Field(..., description="ISO 8601 UTC dispatch timestamp")
