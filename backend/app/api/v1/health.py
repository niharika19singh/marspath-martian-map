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
    prov = provider.get_provenance()

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENV,
        "planetary_target": "Mars",
        "pilot_region": "Jezero Crater",
        "data_readiness": {
            "dem_loaded": not is_syn,
            "real_dem_requested": bool(prov.get("real_dem_requested", settings.USE_REAL_DEM)),
            "real_dem_loaded": bool(prov.get("real_dem_loaded", not is_syn)),
            "data_mode": prov.get("data_mode", "synthetic_test_fixture" if is_syn else "real"),
            "real_data_validation_status": prov.get(
                "real_data_validation_status", "synthetic_test_fixture"
            ),
            "is_synthetic": is_syn,
            "crs": "IAU2000:49900",
            "dataset_name": prov.get("dataset_name"),
        },
    }
