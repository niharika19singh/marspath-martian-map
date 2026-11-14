from fastapi import APIRouter, HTTPException

from backend.app.core.exceptions import MarsPathError
from backend.app.schemas.routes import RoutePlanRequest, RoutePlanResponse
from backend.app.services.planning_intelligence import (
    JEZERO_SCIENCE_TARGETS,
    MISSION_DEMONSTRATION_PRESETS,
)
from backend.app.services.route_service import RouteService

router = APIRouter(prefix="/api/v1/routes", tags=["Route Optimization"])


@router.get("/presets", summary="List curated Jezero Crater mission presets and flagship expedition")
def list_mission_presets():
    """Return the 5 curated demonstration mission presets plus the Flagship Jezero Expedition."""
    return {
        "status": "ok",
        "count": len(MISSION_DEMONSTRATION_PRESETS),
        "presets": list(MISSION_DEMONSTRATION_PRESETS),
    }


@router.get("/science-targets", summary="List geologically grounded Jezero Crater science targets")
def list_science_targets():
    """Return the geologically grounded Jezero Crater science target catalog."""
    return {
        "status": "ok",
        "count": len(JEZERO_SCIENCE_TARGETS),
        "targets": list(JEZERO_SCIENCE_TARGETS),
    }


@router.post(
    "/plan", response_model=RoutePlanResponse, summary="Optimize traversable Martian route corridor"
)
def plan_route(request: RoutePlanRequest):
    """
    Computes an optimal, explainable traversable route between start and destination coordinates
    on Mars terrain, evaluating local slope, roughness, and scientific opportunities.
    """
    service = RouteService()
    try:
        return service.plan_route(request)
    except MarsPathError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={"error": e.message, "details": e.details},
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": f"Internal routing engine error: {str(e)}"},
        ) from e
