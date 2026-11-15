from typing import Any

from fastapi import APIRouter, HTTPException, Response

from backend.app.core.exceptions import MarsPathError
from backend.app.data.surface_imagery import (
    NASA_SURFACE_POV_CATALOGUE,
    find_surface_imagery_for_coordinates,
)
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


@router.post("/plan", response_model=RoutePlanResponse, summary="Optimize traversable Martian route corridor")
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
        ai_mission_intel = payload.get("ai_mission_intel")

        pdf_bytes = generate_mission_pdf(
            plan_data=plan_data,
            selected_route_id=selected_route_id,
            request_data=request_data,
            ai_mission_intel=ai_mission_intel,
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


@router.get("/surface-imagery", summary="List authentic NASA Perseverance surface POV imagery")
def list_surface_imagery(lat: float | None = None, lon: float | None = None, max_distance_m: float = 3000.0):
    """Returns authentic NASA Perseverance Mastcam-Z and Navcam surface imagery across Jezero Crater."""
    if lat is not None and lon is not None:
        nearby = find_surface_imagery_for_coordinates(lat=lat, lon=lon, max_distance_m=max_distance_m)
        return {
            "status": "ok",
            "count": len(nearby),
            "imagery": [img.model_dump() for img in nearby],
            "query": {"lat": lat, "lon": lon, "max_distance_m": max_distance_m},
        }
    return {
        "status": "ok",
        "count": len(NASA_SURFACE_POV_CATALOGUE),
        "imagery": [img.model_dump() for img in NASA_SURFACE_POV_CATALOGUE],
    }


@router.get("/surface-imagery/{landmark_id}", summary="Get authentic NASA surface POV image by landmark ID")
def get_surface_imagery_by_id(landmark_id: str):
    """Returns authentic NASA surface imagery for a specific Jezero landmark."""
    match = next((img for img in NASA_SURFACE_POV_CATALOGUE if img.landmark_id == landmark_id), None)
    if not match:
        raise HTTPException(
            status_code=404,
            detail=f"No authentic NASA surface imagery found for landmark '{landmark_id}'",
        )
    return {"status": "ok", "image": match.model_dump()}
