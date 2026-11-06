from fastapi import APIRouter

from backend.app.core.config import get_settings
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health check")
def get_health():
    """
    Returns service health, version, active environment,
    and scientific planetary data readiness status.
    Separates API service availability from scientific data readiness.
    """
    settings = get_settings()
    provider = MOLAHRSCRasterProvider()
    raster = provider.get_dem_raster()
    is_syn = provider.is_synthetic()
    prov = provider.get_provenance()
    fallback_reason = prov.get("fallback_reason")

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
            "is_synthetic": is_syn,
            "data_mode": prov.get("data_mode", "synthetic_test_fixture" if is_syn else "real"),
            "real_data_validation_status": prov.get(
                "real_data_validation_status", "synthetic_test_fixture"
            ),
            "local_integrity_verified": prov.get("local_integrity_verified"),
            "source_checksum_verified": bool(prov.get("source_checksum_verified", False)),
            "dem_resolution_meters": round(raster.metadata.meters_per_px_y, 1),
            "grid_shape": [raster.metadata.height, raster.metadata.width],
            "spatial_coverage": prov.get(
                "spatial_coverage",
                {
                    "min_lon": round(raster.metadata.min_lon, 4),
                    "max_lon": round(raster.metadata.max_lon, 4),
                    "min_lat": round(raster.metadata.min_lat, 4),
                    "max_lat": round(raster.metadata.max_lat, 4),
                },
            ),
            "crs": "IAU2000:49900",
            "dataset_name": prov.get("dataset_name"),
            "official_product_id": prov.get("official_product_id"),
            "official_source_url": prov.get("official_source_url"),
            "fallback_reason": fallback_reason,
            "blocking_errors": [fallback_reason] if fallback_reason else [],
        },
    }
