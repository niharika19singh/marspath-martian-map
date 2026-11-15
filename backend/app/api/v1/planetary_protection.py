"""API Router for Planetary Protection Special-Region Geofencing and Scout Reconnaissance."""

from __future__ import annotations

import datetime
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.data.planetary_protection import (
    get_all_special_regions,
    get_special_region_by_id,
)
from backend.app.routing.geofence import evaluate_route_geofence
from backend.app.schemas.planetary_protection import (
    PlanetaryProtectionRouteAssessment,
    ScoutRoverReconRequest,
)

router = APIRouter(prefix="/api/v1/planetary-protection", tags=["Planetary Protection"])


class RouteEvaluationRequest(BaseModel):
    """Coordinates to evaluate against active planetary protection geofences."""

    coordinates: list[list[float]] = Field(
        ...,
        description="Array of [lon, lat] coordinates representing the traverse LineString",
    )


class ScoutDispatchRequest(BaseModel):
    """Parameters for dispatching a simulated robotic scout reconnaissance sortie."""

    target_region_id: str = Field(..., description="ID of the special region to reconnoiter")
    scout_platform: str | None = Field(
        default=None,
        description="Optional override for scout robotic platform model",
    )
    instrument_payload: list[str] | None = Field(
        default=None,
        description="Optional override for scout scientific instruments",
    )


@router.get("/zones", summary="List all active Planetary Protection Special Regions in Jezero Crater")
def list_special_regions():
    """Returns all verified, candidate, and demonstration special-region geofences."""
    zones = get_all_special_regions()
    return {
        "status": "ok",
        "count": len(zones),
        "zones": [z.model_dump() for z in zones],
    }


@router.get("/zones/{zone_id}", summary="Get specific Planetary Protection Special Region by ID")
def get_special_region(zone_id: str):
    """Returns full scientific provenance and polygon coordinates for a designated zone."""
    zone = get_special_region_by_id(zone_id)
    if not zone:
        raise HTTPException(
            status_code=404,
            detail=f"Planetary Protection Zone with ID '{zone_id}' not found.",
        )
    return {"status": "ok", "zone": zone.model_dump()}


@router.post(
    "/evaluate-route",
    response_model=PlanetaryProtectionRouteAssessment,
    summary="Evaluate traverse LineString against planetary protection geofences",
)
def evaluate_traverse(payload: RouteEvaluationRequest):
    """
    Checks line-segment intersections and point-in-polygon containment against all active zones.
    If an official restricted zone is breached, human_route_approved is set to False.
    """
    return evaluate_route_geofence(payload.coordinates)


@router.post(
    "/scout-rover-request",
    response_model=ScoutRoverReconRequest,
    summary="Dispatch a simulated scout rover reconnaissance request",
)
def dispatch_scout_rover(payload: ScoutDispatchRequest):
    """
    Generates a simulated robotic scout reconnaissance sortie for a sensitive or restricted region.
    Strictly documents that this is a simulated mission planning drill.
    """
    zone = get_special_region_by_id(payload.target_region_id)
    if not zone:
        raise HTTPException(
            status_code=404,
            detail=f"Cannot dispatch scout rover: Zone '{payload.target_region_id}' not found.",
        )

    mission_uuid = str(uuid.uuid4())[:8].upper()
    recon_id = f"SCOUT-SORTIE-{zone.id.replace('ppz_', '').upper()}-{mission_uuid}"
    platform = payload.scout_platform or "Ingenuity-Class Aerial Scout / Sample Fetch Micro-Rover"
    payload_suite = payload.instrument_payload or ["APXS", "Microscopic Imager", "Raman Bio-Signature Spectrometer"]
    now_utc = datetime.datetime.now(datetime.UTC).isoformat()

    return ScoutRoverReconRequest(
        target_region_id=zone.id,
        target_region_name=zone.name,
        recon_mission_id=recon_id,
        scout_platform=platform,
        instrument_payload=payload_suite,
        bio_cleanliness_level="Planetary Protection Cat IVb Post-Bakeout (< 300 spores/m²)",
        target_coordinates=zone.center,
        estimated_survey_sol=2024,
        reconnaissance_eta_hours=4.5,
        status="SIMULATED SCOUT ROVER RECONNAISSANCE REQUEST",
        simulation_disclaimer=(
            "MOCK MISSION SIMULATION ONLY. This conceptual reconnaissance request generates simulated "
            "robotic scout telemetry and does not interface with active NASA spacecraft operations."
        ),
        timestamp_utc=now_utc,
    )
