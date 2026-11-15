from typing import Any

from fastapi import APIRouter, HTTPException, Response

from backend.app.core.exceptions import MarsPathError
from backend.app.schemas.routes import RoutePlanRequest, RoutePlanResponse
from backend.app.services.pdf_export_service import generate_mission_pdf
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


@router.post("/export/pdf", summary="Export mission plan as a formal PDF brief")
def export_mission_plan_pdf(payload: dict[str, Any]):
    """Generates a publication-grade PDF mission dossier for the provided route plan."""
    try:
        plan_data = payload.get("plan") or payload
        selected_route_id = payload.get("selected_route_id")
        request_data = payload.get("request")

        pdf_bytes = generate_mission_pdf(
            plan_data=plan_data,
            selected_route_id=selected_route_id,
            request_data=request_data,
        )
        mission_id = plan_data.get("mission_id", "jezero_mission")
        filename = f"marspath_mission_{mission_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": f"Failed to generate mission PDF: {str(exc)}"},
        ) from exc
