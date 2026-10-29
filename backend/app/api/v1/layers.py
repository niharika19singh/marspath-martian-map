from fastapi import APIRouter

from backend.app.schemas.layers import LayerListResponse
from backend.app.services.data_catalog import DataCatalogService

router = APIRouter(prefix="/api/v1", tags=["Geospatial Layers"])


@router.get(
    "/layers", response_model=LayerListResponse, summary="List configured Martian geospatial layers"
)
def list_layers():
    """
    Returns metadata for all available numerical and visual map layers,
    including units, spatial coverage, and source citations.
    """
    service = DataCatalogService()
    return service.get_layer_list()
