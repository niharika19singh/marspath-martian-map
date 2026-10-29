from fastapi import APIRouter
from backend.app.core.config import get_settings
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health check")
def get_health():
    """
    Returns service health, version, active environment,
    and scientific planetary data readiness status.
    """
    settings = get_settings()
    provider = MOLAHRSCRasterProvider()
    is_syn = provider.is_synthetic()

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENV,
        "planetary_target": "Mars",
        "pilot_region": "Jezero Crater",
        "data_readiness": {
            "dem_loaded": True,
            "data_mode": "synthetic_test_fixture" if is_syn else "real",
            "is_synthetic": is_syn,
            "crs": "IAU2000:49900",
        },
    }
