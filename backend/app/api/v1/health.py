from fastapi import APIRouter, Response

from backend.app.core.config import get_settings
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.services.data_catalog import evaluate_terrain_readiness

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Service health check")
def get_health(response: Response):
    """
    Returns service health, version, active environment,
    and scientific planetary data readiness status.
    Separates API service availability from scientific data readiness using
    the unified evaluate_terrain_readiness() gate:
    - Case A: Real DEM requested and loaded with acceptable provenance
      (verified_source or official_endpoint_retrieved_checksum_unverified with
      local_integrity_verified=True) -> HTTP 200, status="healthy".
    - Case B: Real DEM requested but unacceptable real-data readiness
      (synthetic fallback, local_integrity_verified=False/None, or
      valid_numeric_raster_unverified_source) -> HTTP 503, status="degraded".
    - Case C: Real DEM requested, unavailable, and fallback disabled -> raises TerrainDataUnavailableError (HTTP 503).
    - Case D: Local synthetic development mode (USE_REAL_DEM=false) -> HTTP 200, status="healthy".
    """
    settings = get_settings()
    provider = MOLAHRSCRasterProvider()
    raster = provider.get_dem_raster()
    is_syn = provider.is_synthetic()
    prov = provider.get_provenance()

    readiness = evaluate_terrain_readiness(
        is_synthetic=is_syn,
        provenance=prov,
        default_use_real_dem=bool(getattr(provider, "use_real_dem", settings.USE_REAL_DEM)),
        dem_path=getattr(provider, "dem_path", None),
    )

    response.status_code = readiness["http_status_code"]
    overall_status = readiness["status"]
    dem_loaded = readiness["dem_loaded"]
    real_dem_requested = readiness["real_dem_requested"]
    real_dem_loaded = readiness["real_dem_loaded"]
    is_syn = readiness["is_synthetic"]
    data_mode = readiness["data_mode"]
    validation_status = readiness["real_data_validation_status"]
    local_integrity_verified = readiness["local_integrity_verified"]
    source_checksum_verified = readiness["source_checksum_verified"]
    fallback_reason = readiness["fallback_reason"]
    blocking_errors = readiness["blocking_errors"]

    readiness_payload = {
        "status": overall_status,
        "dem_loaded": dem_loaded,
        "real_dem_requested": real_dem_requested,
        "real_dem_loaded": real_dem_loaded,
        "is_synthetic": is_syn,
        "data_mode": data_mode,
        "real_data_validation_status": validation_status,
        "local_integrity_verified": local_integrity_verified,
        "source_checksum_verified": source_checksum_verified,
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
        "local_integrity_verified": local_integrity_verified,
        "source_checksum_verified": source_checksum_verified,
        "fallback_reason": fallback_reason,
        "blocking_errors": blocking_errors,
        "data_readiness": readiness_payload,
    }
