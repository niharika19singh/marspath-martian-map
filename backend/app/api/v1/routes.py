from fastapi import APIRouter, HTTPException

from backend.app.core.exceptions import MarsPathError
from backend.app.schemas.routes import RoutePlanRequest, RoutePlanResponse
from backend.app.services.route_service import RouteService

router = APIRouter(prefix="/api/v1/routes", tags=["Route Optimization"])


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
