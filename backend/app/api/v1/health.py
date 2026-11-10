from fastapi import APIRouter, Response

from backend.app.core.config import get_settings
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health check")
def get_health(response: Response):
    """
    Returns service health, version, active environment,
    and scientific planetary data readiness status.
    Separates API service availability from scientific data readiness:
    - Case A: Real DEM requested and loaded (including official endpoint extract with
      local_integrity_verified=True and source_checksum_verified=False) -> HTTP 200, status="healthy".
    - Case B: Real DEM requested but synthetic fallback is active -> HTTP 503, status="degraded".
    - Case C: Real DEM requested, unavailable, and fallback disabled -> raises TerrainDataUnavailableError (HTTP 503).
    - Case D: Local synthetic development mode (USE_REAL_DEM=false) -> HTTP 200, status="healthy".
    """
    settings = get_settings()
    provider = MOLAHRSCRasterProvider()
    raster = provider.get_dem_raster()
    is_syn = provider.is_synthetic()
    prov = provider.get_provenance()

    real_dem_requested = bool(prov.get("real_dem_requested", settings.USE_REAL_DEM))
    real_dem_loaded = bool(prov.get("real_dem_loaded", not is_syn))
    dem_loaded = not is_syn
    data_mode = prov.get("data_mode", "synthetic_test_fixture" if is_syn else "real")
    fallback_reason = prov.get("fallback_reason")

    is_degraded_fallback = bool(
        real_dem_requested and (not real_dem_loaded or is_syn or data_mode == "synthetic_fallback")
    )
    if is_degraded_fallback:
        response.status_code = 503
        overall_status = "degraded"
        data_mode = "synthetic_fallback"
        real_dem_loaded = False
        dem_loaded = False
        is_syn = True
        if not fallback_reason:
            fallback_reason = (
                f"Real DEM requested (MARSPATH_USE_REAL_DEM=true) but synthetic fallback is active "
                f"at '{provider.dem_path}'."
            )
    else:
        overall_status = "healthy"

    blocking_errors = [fallback_reason] if fallback_reason else []
    validation_status = prov.get(
        "real_data_validation_status",
        "incomplete_missing_genuine_dem" if is_degraded_fallback else "synthetic_test_fixture",
    )

    readiness_payload = {
        "status": overall_status,
        "dem_loaded": dem_loaded,
        "real_dem_requested": real_dem_requested,
        "real_dem_loaded": real_dem_loaded,
        "is_synthetic": is_syn,
        "data_mode": data_mode,
        "real_data_validation_status": validation_status,
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
        "blocking_errors": blocking_errors,
    }

    return {
        "status": overall_status,
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENV,
        "planetary_target": "Mars",
        "pilot_region": "Jezero Crater",
        "dem_loaded": dem_loaded,
        "real_dem_requested": real_dem_requested,
        "real_dem_loaded": real_dem_loaded,
        "is_synthetic": is_syn,
        "data_mode": data_mode,
        "real_data_validation_status": validation_status,
        "local_integrity_verified": prov.get("local_integrity_verified"),
        "source_checksum_verified": bool(prov.get("source_checksum_verified", False)),
        "fallback_reason": fallback_reason,
        "blocking_errors": blocking_errors,
        "data_readiness": readiness_payload,
    }
