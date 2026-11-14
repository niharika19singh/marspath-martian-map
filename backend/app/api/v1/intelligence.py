"""
FastAPI Endpoints for MARSPath Live Mars Intelligence Subsystem.
Full multi-mission orbital tracking, rover position & traverse synchronization,
observation footprint retrieval, and operational data freshness auditing.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.intelligence.schemas import (
    GroundTrack,
    IntelligenceStatus,
    OrbitalObservation,
    RoverObservation,
    RoverPosition,
    RoverTraverse,
    SpacecraftInfo,
    SpacecraftPosition,
    SyncRequest,
    SyncResponse,
    TimelineEvent,
)
from backend.app.intelligence.service import LiveMarsIntelligenceService

router = APIRouter(prefix="/api/v1/intelligence", tags=["Live Mars Intelligence"])


def get_service() -> LiveMarsIntelligenceService:
    return LiveMarsIntelligenceService.get_shared_instance()


@router.get(
    "/status",
    response_model=IntelligenceStatus,
    summary="Live Mars Intelligence subsystem operational status",
)
def get_intelligence_status():
    """
    Returns operational readiness, tracked mission sources, active orbiter counts,
    active rover counts, and data freshness categorization.
    """
    return get_service().get_status()


@router.get(
    "/spacecraft",
    response_model=list[SpacecraftInfo],
    summary="List all tracked Mars orbiters and instantaneous ephemerides",
)
def list_spacecraft():
    """
    Returns complete profiles and state vectors for MRO, Mars Odyssey, MAVEN, Mars Express, and ExoMars TGO.
    """
    return get_service().list_spacecraft()


@router.get(
    "/spacecraft/{spacecraft_id}/position",
    response_model=SpacecraftPosition,
    summary="Instantaneous sub-satellite coordinates and orbital velocity",
)
def get_spacecraft_position(spacecraft_id: str):
    """
    Computes instantaneous planetocentric sub-satellite coordinates (lon, lat, altitude, speed)
    in the IAU2000 Mars-fixed reference frame.
    """
    try:
        return get_service().get_spacecraft_position(spacecraft_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/spacecraft/{spacecraft_id}/ground-track",
    response_model=GroundTrack,
    summary="Orbital ground track polyline covering past/predicted intervals",
)
def get_spacecraft_ground_track(
    spacecraft_id: str,
    duration_minutes: Annotated[float, Query(ge=10.0, le=720.0, description="Duration in minutes")] = 120.0,
    step_seconds: Annotated[int, Query(ge=10, le=600, description="Sampling interval in seconds")] = 60,
):
    """
    Propagates orbit forward/backward in time to calculate sub-satellite ground track coordinates.
    """
    try:
        return get_service().get_spacecraft_ground_track(
            spacecraft_id, duration_minutes=duration_minutes, step_seconds=step_seconds
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/rovers",
    response_model=list[RoverPosition],
    summary="List all active Mars rovers with latest telemetry",
)
def list_rovers():
    """
    Returns verified landing sites, current sol, cumulative odometry, and latest locations
    for Perseverance (M20) and Curiosity (MSL).
    """
    return get_service().list_rovers()


@router.get(
    "/rovers/{rover_id}/position",
    response_model=RoverPosition,
    summary="Latest verified position and odometry for a specific rover",
)
def get_rover_position(rover_id: str):
    """
    Returns latest published localization for Perseverance or Curiosity.
    """
    try:
        return get_service().get_rover_position(rover_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/rovers/{rover_id}/traverse",
    response_model=RoverTraverse,
    summary="Complete cumulative historical rover traverse GeoJSON",
)
def get_rover_traverse(rover_id: str):
    """
    Returns full path coordinates, drives, and odometry history without decimating historical milestones.
    """
    try:
        return get_service().get_rover_traverse(rover_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/rovers/{rover_id}/observations",
    response_model=list[RoverObservation],
    summary="Scientific surface images and spectral observations",
)
def get_rover_observations(rover_id: str):
    """
    Returns verified Mastcam, SuperCam, ChemCam, or PIXL observation products.
    """
    try:
        return get_service().get_rover_observations(rover_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/observations",
    response_model=list[OrbitalObservation],
    summary="Catalogue of high-resolution orbital observations and footprints",
)
def list_orbital_observations(
    spacecraft_id: Annotated[str | None, Query(description="Filter by spacecraft ID (e.g. mro, mex)")] = None,
    instrument: Annotated[str | None, Query(description="Filter by instrument (e.g. hirise, ctx, hrsc)")] = None,
):
    """
    Returns peer-reviewed PDS orbital imagery footprints georeferenced to Mars lon/lat coordinates.
    """
    return get_service().list_observations(spacecraft_id=spacecraft_id, instrument=instrument)


@router.get(
    "/timeline",
    response_model=list[TimelineEvent],
    summary="Chronological mission intelligence timeline",
)
def get_mission_timeline(
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of events")] = 30,
):
    """
    Returns unified chronological sequence of rover drives, spacecraft orbital states, and science observations.
    """
    return get_service().get_timeline(limit=limit)


@router.post(
    "/sync",
    response_model=SyncResponse,
    summary="Execute operational data synchronization",
)
def sync_intelligence_data(request: SyncRequest | None = None):
    """
    Triggers incremental synchronization across all tracked planetary archives,
    re-propagating orbits and checking rover drive manifests.
    """
    req = request or SyncRequest()
    return get_service().sync_data(force_refresh=req.force_refresh, source_filter=req.source_filter)
