from fastapi import APIRouter
from backend.app.schemas.routes import DataStatusResponse
from backend.app.services.data_catalog import DataCatalogService

router = APIRouter(prefix="/api/v1/data", tags=["Data Status"])


@router.get("/status", response_model=DataStatusResponse, summary="Inspect planetary data readiness and CRS")
def get_data_status():
    """
    Returns the real-time operational status of NASA datasets,
    coordinate reference system, loaded DEM resolution, and provenance.
    """
    service = DataCatalogService()
    return service.get_data_status()
