"""
FastAPI Endpoints for MARSPath Live Mars Intelligence Subsystem.
Full multi-mission orbital tracking, rover position & traverse synchronization,
observation footprint retrieval, and operational data freshness auditing.
"""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status

from backend.app.intelligence.fusion.evidence_model import (
    DataFreshnessReport,
    NormalizedObservation,
)
from backend.app.intelligence.fusion_hub import MissionIntelligenceHub
from backend.app.intelligence.graph.entities import (
    EvidenceTrace,
    GraphNode,
    ImpactTrace,
    SubgraphResponse,
)
from backend.app.intelligence.risk_propagation.propagation_engine import (
    RouteRiskPropagationResult,
)
from backend.app.intelligence.risk_propagation.scenarios import (
    MissionScenario,
    ScenarioAnalysisResult,
    ScenarioComparisonReport,
    ScenarioCreateRequest,
)
from backend.app.intelligence.schemas import (
    GroundTrack,
    IntelligenceStatus,
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


def get_hub() -> MissionIntelligenceHub:
    return MissionIntelligenceHub.get_instance()


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
    "/data-freshness",
    response_model=DataFreshnessReport,
    summary="Multi-source data freshness, synchronization latency, and coverage gaps",
)
def get_data_freshness():
    """
    Evaluates synchronization recency, connection health, and spatial coverage gaps
    across all integrated NASA planetary archives.
    """
    return get_hub().get_data_freshness()


@router.get(
    "/observations",
    response_model=list[NormalizedObservation],
    summary="Catalogue of high-resolution orbital observations, in-situ measurements, and footprints",
)
def list_observations(
    bbox: Annotated[str | None, Query(description="Bounding box 'min_lon,min_lat,max_lon,max_lat'")] = None,
    min_sol: Annotated[int | None, Query(description="Minimum Martian sol")] = None,
    max_sol: Annotated[int | None, Query(description="Maximum Martian sol")] = None,
    min_ls: Annotated[float | None, Query(description="Minimum solar longitude Ls (0-360)")] = None,
    max_ls: Annotated[float | None, Query(description="Maximum solar longitude Ls (0-360)")] = None,
    spacecraft_id: Annotated[str | None, Query(description="Filter by spacecraft ID (e.g. mro, mex)")] = None,
    instrument: Annotated[str | None, Query(description="Filter by instrument (e.g. hirise, ctx, themis)")] = None,
    provenance_kind: Annotated[
        str | None, Query(description="Filter by kind: measured, historical, computed, modeled, derived")
    ] = None,
    quality_tier: Annotated[str | None, Query(description="Filter by tier: GOLD, SILVER, BRONZE, UNVERIFIED")] = None,
    measurement_type: Annotated[str | None, Query(description="Filter by measurement type")] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum number of observations")] = 50,
):
    """
    Returns normalized observations with spatial footprints, uncertainty bounds, and direct archive lineage.
    """
    parsed_bbox: list[float] | None = None
    if bbox:
        try:
            parts = [float(p.strip()) for p in bbox.split(",")]
            if len(parts) == 4:
                parsed_bbox = parts
        except ValueError:
            pass

    return get_hub().query_observations(
        bbox=parsed_bbox,
        min_sol=min_sol,
        max_sol=max_sol,
        min_ls=min_ls,
        max_ls=max_ls,
        instrument=instrument,
        provenance_kind=provenance_kind,
        quality_tier=quality_tier,
        measurement_type=measurement_type,
        limit=limit,
    )


@router.get(
    "/graph",
    response_model=SubgraphResponse,
    summary="Query geospatial mission knowledge graph",
)
def get_mission_knowledge_graph(
    node_type: Annotated[
        str | None, Query(description="Filter by node type (e.g. observation, hazard, route_segment)")
    ] = None,
    max_nodes: Annotated[int, Query(ge=1, le=500, description="Maximum nodes in subgraph")] = 100,
):
    """
    Returns interconnected subgraph with datasets, observations, terrain regions, hazards, and route segments.
    """
    return get_hub().get_graph_subgraph(node_type=node_type, max_nodes=max_nodes)


@router.get(
    "/graph/{node_id:path}/evidence",
    response_model=EvidenceTrace,
    summary="Trace multi-hop upstream evidence from node back to source observations and datasets",
)
def trace_node_evidence(
    node_id: str,
    max_depth: Annotated[int, Query(ge=1, le=10, description="Maximum traversal depth")] = 5,
):
    trace = get_hub().trace_node_evidence(node_id=node_id, max_depth=max_depth)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found in knowledge graph",
        )
    return trace


@router.get(
    "/graph/{node_id:path}/impacts",
    response_model=ImpactTrace,
    summary="Trace multi-hop downstream impacts from node to affected route segments and mission constraints",
)
def trace_node_impacts(
    node_id: str,
    max_depth: Annotated[int, Query(ge=1, le=10, description="Maximum traversal depth")] = 5,
):
    trace = get_hub().trace_node_impacts(node_id=node_id, max_depth=max_depth)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found in knowledge graph",
        )
    return trace


@router.get(
    "/graph/{node_id:path}",
    response_model=GraphNode,
    summary="Retrieve single knowledge graph entity by ID",
)
def get_graph_node(node_id: str):
    node = get_hub().get_graph_node(node_id=node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found in knowledge graph",
        )
    return node


@router.get(
    "/scenarios",
    response_model=list[MissionScenario],
    summary="List available mission what-if contingency scenarios",
)
def list_scenarios():
    return get_hub().list_scenarios()


@router.post(
    "/scenarios",
    response_model=MissionScenario,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new mission what-if scenario with parameter modifiers",
)
def create_scenario(request: ScenarioCreateRequest):
    return get_hub().create_scenario(request)


@router.get(
    "/scenarios/{scenario_id}",
    response_model=MissionScenario,
    summary="Retrieve mission scenario configuration",
)
def get_scenario(scenario_id: str):
    sc = get_hub().get_scenario(scenario_id=scenario_id)
    if not sc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario '{scenario_id}' not found",
        )
    return sc


@router.post(
    "/scenarios/{scenario_id}/analyze",
    response_model=ScenarioAnalysisResult,
    summary="Execute risk propagation and sensitivity analysis under scenario conditions",
)
def analyze_scenario(scenario_id: str, payload: dict[str, Any] | None = None):
    route_data = payload.get("route_data") if payload else None
    try:
        return get_hub().analyze_scenario(scenario_id=scenario_id, route_data=route_data)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get(
    "/scenarios/{scenario_id}/compare",
    response_model=ScenarioComparisonReport,
    summary="Compare scenario risk and effort against nominal baseline route",
)
def compare_scenario(
    scenario_id: str,
    baseline_route_id: Annotated[str, Query(description="Baseline route identifier")] = "primary",
):
    try:
        return get_hub().compare_scenario(scenario_id=scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/risk-propagation",
    response_model=RouteRiskPropagationResult,
    summary="Execute multi-source evidence-backed risk propagation on a route",
)
def evaluate_route_risk(payload: dict[str, Any]):
    route_data = payload.get("route_data", payload)
    max_slope = float(payload.get("max_slope_ceiling_deg", 14.0))
    max_rough = float(payload.get("max_roughness_limit", 0.85))
    return get_hub().evaluate_route_risk(
        route_data=route_data,
        max_slope_ceiling_deg=max_slope,
        max_roughness_limit=max_rough,
    )


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
