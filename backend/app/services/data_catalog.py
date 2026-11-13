from typing import Any

from backend.app.core.config import get_settings
from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.data.providers.hirise import (
    HiRISERasterProvider,
    get_shared_hirise_provider,
)
from backend.app.data.providers.mola_hrsc import (
    get_shared_mola_provider,
)
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.schemas.coordinates import BoundingBox
from backend.app.schemas.layers import LayerCategory, LayerInfo, LayerListResponse
from backend.app.schemas.routes import DataStatusResponse

DEFAULT_USGS_200M_URL = (
    "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m"
)

ACCEPTABLE_REAL_VALIDATION_STATUSES: frozenset[str] = frozenset(
    {
        "verified_source",
        "official_endpoint_retrieved_checksum_unverified",
    }
)


def evaluate_terrain_readiness(
    *,
    is_synthetic: bool,
    provenance: dict[str, Any],
    default_use_real_dem: bool,
    dem_path: str | None = None,
) -> dict[str, Any]:
    """
    Shared production readiness gate evaluated identically by `/health` and `/api/v1/data/status`.

    1. When `real_dem_requested` is False (`MARSPATH_USE_REAL_DEM=false`):
       - Local synthetic development mode (`data_mode="synthetic_test_fixture"`).
       - Returns `status="healthy"`, `http_status_code=200`.
    2. When `real_dem_requested` is True (`MARSPATH_USE_REAL_DEM=true`):
       - Production readiness (`status="healthy"`, `http_status_code=200`) requires ALL of:
         * `real_dem_requested is True`
         * `real_dem_loaded is True`
         * `dem_loaded is True`
         * `is_synthetic is False`
         * `local_integrity_verified is True`
         * `real_data_validation_status in {"verified_source", "official_endpoint_retrieved_checksum_unverified"}`
       - For `"official_endpoint_retrieved_checksum_unverified"`, `source_checksum_verified == False`
         is explicitly permitted when `local_integrity_verified is True`.
       - For `"verified_source"`, `source_checksum_verified` must be `True`.
       - Any unacceptable real-data state (synthetic fallback, `local_integrity_verified is False`,
         `local_integrity_verified is None`, `valid_numeric_raster_unverified_source`, or any
         non-synthetic raster without acceptable provenance) returns `status="degraded"`,
         `http_status_code=503`, and populates `blocking_errors` with the diagnostic reason(s).
    """
    effective_path = str(dem_path or provenance.get("file_path") or "unknown")
    real_dem_requested = bool(provenance.get("real_dem_requested", default_use_real_dem))
    raw_real_dem_loaded = bool(provenance.get("real_dem_loaded", not is_synthetic))
    raw_data_mode = str(
        provenance.get("data_mode") or ("synthetic_test_fixture" if is_synthetic else "real")
    )
    raw_val_status = str(
        provenance.get("real_data_validation_status")
        or ("synthetic_test_fixture" if is_synthetic else "valid_numeric_raster_unverified_source")
    )
    local_integrity_verified = provenance.get("local_integrity_verified")
    source_checksum_verified = bool(provenance.get("source_checksum_verified", False))
    verification_method = str(
        provenance.get("provenance_verification_method") or "unverified"
    )
    raw_fallback_reason = provenance.get("fallback_reason")

    # Case 1: Local synthetic development mode (MARSPATH_USE_REAL_DEM=false)
    if not real_dem_requested:
        return {
            "status": "healthy",
            "http_status_code": 200,
            "dem_loaded": False,
            "real_dem_requested": False,
            "real_dem_loaded": False,
            "is_synthetic": True,
            "data_mode": "synthetic_test_fixture",
            "real_data_validation_status": "synthetic_test_fixture",
            "local_integrity_verified": None,
            "source_checksum_verified": False,
            "provenance_verification_method": provenance.get(
                "provenance_verification_method", "none_synthetic"
            ),
            "fallback_reason": None,
            "blocking_errors": [],
        }

    # Case 2: Real DEM requested, but synthetic fallback is active
    if is_synthetic or not raw_real_dem_loaded or raw_data_mode == "synthetic_fallback":
        val_status = (
            "incomplete_missing_genuine_dem"
            if raw_val_status == "synthetic_test_fixture"
            else raw_val_status
        )
        fallback_reason = str(
            raw_fallback_reason
            or (
                f"Real DEM requested (MARSPATH_USE_REAL_DEM=true) but file not found "
                f"or invalid at: {effective_path}"
            )
        )
        return {
            "status": "degraded",
            "http_status_code": 503,
            "dem_loaded": False,
            "real_dem_requested": True,
            "real_dem_loaded": False,
            "is_synthetic": True,
            "data_mode": "synthetic_fallback",
            "real_data_validation_status": val_status,
            "local_integrity_verified": None,
            "source_checksum_verified": False,
            "provenance_verification_method": provenance.get(
                "provenance_verification_method", "none_file_missing_or_invalid"
            ),
            "fallback_reason": fallback_reason,
            "blocking_errors": [fallback_reason],
        }

    # Case 3: Real DEM requested and non-synthetic raster is loaded -> enforce strict provenance & integrity gate
    dem_loaded = True
    real_dem_loaded = True
    blocking_errors: list[str] = []

    if local_integrity_verified is False:
        blocking_errors.append(
            f"Local DEM integrity verification failed (local_integrity_verified=false; "
            f"method={verification_method}) for '{effective_path}'."
        )
    elif local_integrity_verified is not True:
        blocking_errors.append(
            f"Local DEM integrity is unverified (local_integrity_verified=null; missing or "
            f"unauthenticated provenance sidecar; method={verification_method}) for '{effective_path}'."
        )

    if raw_val_status not in ACCEPTABLE_REAL_VALIDATION_STATUSES:
        blocking_errors.append(
            f"Real DEM provenance validation status '{raw_val_status}' is not acceptable for "
            f"production readiness (requires 'verified_source' or "
            f"'official_endpoint_retrieved_checksum_unverified'; method={verification_method}) "
            f"for '{effective_path}'."
        )
    elif raw_val_status == "verified_source" and not source_checksum_verified:
        blocking_errors.append(
            f"Real DEM claims validation_status='verified_source' but source_checksum_verified=false "
            f"for '{effective_path}'."
        )

    if raw_data_mode not in ("real", "real_official_endpoint_unverified_checksum"):
        msg = (
            f"Real DEM data_mode '{raw_data_mode}' is not acceptable for production readiness "
            f"(validation_status='{raw_val_status}') for '{effective_path}'."
        )
        if not blocking_errors:
            blocking_errors.append(msg)

    if blocking_errors:
        return {
            "status": "degraded",
            "http_status_code": 503,
            "dem_loaded": dem_loaded,
            "real_dem_requested": True,
            "real_dem_loaded": real_dem_loaded,
            "is_synthetic": False,
            "data_mode": raw_data_mode,
            "real_data_validation_status": raw_val_status,
            "local_integrity_verified": (
                local_integrity_verified if isinstance(local_integrity_verified, bool) else None
            ),
            "source_checksum_verified": source_checksum_verified,
            "provenance_verification_method": verification_method,
            "fallback_reason": raw_fallback_reason,
            "blocking_errors": blocking_errors,
        }

    return {
        "status": "healthy",
        "http_status_code": 200,
        "dem_loaded": True,
        "real_dem_requested": True,
        "real_dem_loaded": True,
        "is_synthetic": False,
        "data_mode": raw_data_mode,
        "real_data_validation_status": raw_val_status,
        "local_integrity_verified": True,
        "source_checksum_verified": source_checksum_verified,
        "provenance_verification_method": verification_method,
        "fallback_reason": None,
        "blocking_errors": [],
    }


class DataCatalogService:
    def __init__(
        self,
        provider: BaseRasterProvider | None = None,
        hirise_provider: HiRISERasterProvider | None = None,
    ):
        self.settings = get_settings()
        self.provider = provider or get_shared_mola_provider()
        self.hirise_provider = hirise_provider or get_shared_hirise_provider()

    @staticmethod
    def _resolve_dem_attribution(is_syn: bool, provenance: dict[str, Any]) -> dict[str, Any]:
        """
        Determines accurate, non-misleading source attribution for DEM-based layers
        across all four provenance states:
        - Case A: Genuine USGS endpoint retrieval (`official_endpoint_retrieved_checksum_unverified`)
        - Case B: Verified full source (`verified_source`)
        - Case C: Synthetic terrain (`is_synthetic == True`)
        - Case D: Unverified local numerical raster (`valid_numeric_raster_unverified_source`)
        """
        val_status = str(provenance.get("real_data_validation_status", "synthetic_test_fixture"))

        if is_syn:
            # Case C: Synthetic terrain — NEVER advertise USGS URL or official product ID
            return {
                "source_name": "Synthetic Jezero Crater Terrain Model",
                "source_url": None,
                "product_id": None,
                "validation_status": val_status,
                "source_checksum_verified": False,
                "provenance_note": (
                    "Internal deterministic procedural terrain model for Jezero Crater; "
                    "not derived from NASA or USGS observation data."
                ),
            }

        if val_status == "verified_source":
            # Case B: Independently verified full-source checksum
            dataset_name = str(
                provenance.get("dataset_name")
                or "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
            )
            source_url = provenance.get("official_source_url") or DEFAULT_USGS_200M_URL
            product_id = provenance.get("official_product_id")
            return {
                "source_name": dataset_name,
                "source_url": source_url,
                "product_id": product_id,
                "validation_status": "verified_source",
                "source_checksum_verified": True,
                "provenance_note": (
                    "Authoritative full-source cryptographic checksum independently verified "
                    "against official planetary catalog."
                ),
            }

        if val_status == "official_endpoint_retrieved_checksum_unverified":
            # Case A: Retrieved from official USGS endpoint via HTTP Range extract
            dataset_name = str(
                provenance.get("dataset_name")
                or "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
            )
            source_url = provenance.get("official_source_url") or DEFAULT_USGS_200M_URL
            product_id = provenance.get("official_product_id")
            return {
                "source_name": dataset_name,
                "source_url": source_url,
                "product_id": product_id,
                "validation_status": "official_endpoint_retrieved_checksum_unverified",
                "source_checksum_verified": False,
                "provenance_note": (
                    "Retrieved from official USGS Astrogeology HTTPS endpoint via GDAL /vsicurl/ "
                    "range extraction; local GeoTIFF SHA-256 integrity verified, but full 11.38 GB "
                    "upstream file MD5 checksum remains unverified."
                ),
            }

        # Case D: Unverified local numerical raster — NEVER assign USGS product ID or NASA/USGS URL
        return {
            "source_name": "Local Numerical Elevation Model (Unverified Source)",
            "source_url": None,
            "product_id": None,
            "validation_status": "valid_numeric_raster_unverified_source",
            "source_checksum_verified": False,
            "provenance_note": (
                "Loaded from an unverified local numerical raster. Authoritative NASA/ESA/USGS "
                "provenance, product identity, and upstream checksum are not established."
            ),
        }

    def get_layer_list(self) -> LayerListResponse:
        raster = self.provider.get_dem_raster()
        crs_info = get_mars_crs_info()
        bounds = self.provider.get_bounds()
        is_syn = self.provider.is_synthetic()
        provenance = self.provider.get_provenance()

        # Derive actual physical pixel resolution from loaded raster metadata
        res_meters = round(raster.metadata.meters_per_px_y, 1)
        attr = self._resolve_dem_attribution(is_syn=is_syn, provenance=provenance)

        layers: list[LayerInfo] = [
            LayerInfo(
                id="mars_elevation_jezero",
                name="Martian Digital Elevation Model (Topography)",
                category=LayerCategory.ELEVATION,
                layer_type="analysis_derived",
                description="Numerical surface elevation relative to the Mars reference datum. Internal analysis layer queried via /api/v1/routes/plan.",
                units="meters",
                resolution_meters=res_meters,
                bounds=bounds,
                crs=crs_info,
                source_name=attr["source_name"],
                source_url=attr["source_url"],
                product_id=attr["product_id"],
                validation_status=attr["validation_status"],
                source_checksum_verified=attr["source_checksum_verified"],
                provenance_note=attr["provenance_note"],
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_slope_degrees",
                name="Terrain Slope Gradient",
                category=LayerCategory.SLOPE,
                layer_type="analysis_derived",
                description="Physical ground inclination derived from numerical elevation gradients. Internal analysis layer queried via /api/v1/routes/plan.",
                units="degrees",
                resolution_meters=res_meters,
                bounds=bounds,
                crs=crs_info,
                source_name=attr["source_name"],
                source_url=attr["source_url"],
                product_id=attr["product_id"],
                validation_status=attr["validation_status"],
                source_checksum_verified=attr["source_checksum_verified"],
                provenance_note=attr["provenance_note"],
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_roughness_tri",
                name="Terrain Ruggedness Index (TRI)",
                category=LayerCategory.ROUGHNESS,
                layer_type="analysis_derived",
                description="Localized standard deviation of detrended elevation differences. Internal analysis layer queried via /api/v1/routes/plan.",
                units="dimensionless [0.0 - 1.0]",
                resolution_meters=res_meters,
                bounds=bounds,
                crs=crs_info,
                source_name=attr["source_name"],
                source_url=attr["source_url"],
                product_id=attr["product_id"],
                validation_status=attr["validation_status"],
                source_checksum_verified=attr["source_checksum_verified"],
                provenance_note=attr["provenance_note"],
                is_numerical=True,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_traversability_mask",
                name="Traversability & Hazard Ceiling Mask",
                category=LayerCategory.HAZARD,
                layer_type="analysis_derived",
                description="Binary traversability envelope enforcing slope limits and nodata masking. Internal analysis layer queried via /api/v1/routes/plan.",
                units="boolean",
                resolution_meters=res_meters,
                bounds=bounds,
                crs=crs_info,
                source_name=attr["source_name"],
                source_url=attr["source_url"],
                product_id=attr["product_id"],
                validation_status=attr["validation_status"],
                source_checksum_verified=attr["source_checksum_verified"],
                provenance_note=attr["provenance_note"],
                is_numerical=False,
                is_available=True,
                is_renderable=False,
                render_url=None,
                is_synthetic=is_syn,
            ),
            LayerInfo(
                id="mars_trek_imagery_basemap",
                name="NASA Mars Trek Visible Basemap",
                category=LayerCategory.IMAGERY,
                layer_type="tile_service",
                description="Global orthorectified multi-mission visible mosaic for direct frontend display via XYZ/WMTS tile services.",
                units="reflectance RGB",
                resolution_meters=6.0,
                bounds=BoundingBox(min_lon=0.0, min_lat=-90.0, max_lon=360.0, max_lat=90.0),
                crs=crs_info,
                source_name="NASA Solar System Treks (JPL)",
                source_url="https://trek.nasa.gov/mars/",
                product_id=None,
                validation_status="external_tile_service",
                source_checksum_verified=False,
                provenance_note="External NASA Mars Trek WMTS/XYZ visual imagery tile service for frontend map display only; never used for numerical terrain or routing calculations.",
                is_numerical=False,
                is_available=True,
                is_renderable=True,
                render_url="https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
                is_synthetic=False,
            ),
        ]

        hi_val = self.hirise_provider.validate_hirise_raster()
        if hi_val.is_valid and hi_val.raster is not None:
            hi_prov = self.hirise_provider.get_provenance()
            hi_attr = self._resolve_dem_attribution(is_syn=False, provenance=hi_prov)
            hi_meta = hi_val.raster.metadata
            layers.append(
                LayerInfo(
                    id="mars_hirise_jezero_delta_dtm",
                    name="HiRISE Jezero Western Delta High-Resolution DTM",
                    category=LayerCategory.ELEVATION,
                    layer_type="localized_high_res_dem",
                    description=(
                        "Localized high-resolution (~1 m/px) stereo Digital Terrain Model covering the "
                        "Jezero Western Delta. Selected automatically only when the entire padded route "
                        "corridor lies within valid HiRISE coverage."
                    ),
                    units="meters",
                    resolution_meters=round(hi_meta.meters_per_px_y, 2),
                    bounds=BoundingBox(
                        min_lon=round(hi_meta.min_lon, 6),
                        min_lat=round(hi_meta.min_lat, 6),
                        max_lon=round(hi_meta.max_lon, 6),
                        max_lat=round(hi_meta.max_lat, 6),
                    ),
                    crs=crs_info,
                    source_name=hi_attr["source_name"],
                    source_url=hi_attr["source_url"],
                    product_id=hi_attr["product_id"],
                    validation_status=hi_attr["validation_status"],
                    source_checksum_verified=hi_attr["source_checksum_verified"],
                    provenance_note=hi_attr["provenance_note"],
                    is_numerical=True,
                    is_available=True,
                    is_renderable=False,
                    render_url=None,
                    is_synthetic=False,
                )
            )

        return LayerListResponse(
            count=len(layers),
            pilot_region="Jezero Crater, Mars",
            layers=layers,
        )

    def get_data_status(self) -> DataStatusResponse:
        raster = self.provider.get_dem_raster()
        is_syn = self.provider.is_synthetic()
        bounds = self.provider.get_bounds()
        crs_info = self.provider.get_crs_info()

        # Compute valid data fraction
        total_pixels = raster.data.size
        nodata_count = int(raster.nodata_mask.sum())
        valid_frac = float((total_pixels - nodata_count) / max(total_pixels, 1))

        res_meters = round(raster.metadata.meters_per_px_y, 1)

        provenance = self.provider.get_provenance()
        readiness = evaluate_terrain_readiness(
            is_synthetic=is_syn,
            provenance=provenance,
            default_use_real_dem=bool(
                getattr(self.provider, "use_real_dem", self.settings.USE_REAL_DEM)
            ),
            dem_path=getattr(self.provider, "dem_path", None),
        )
        overall_status = readiness["status"]
        real_dem_requested = readiness["real_dem_requested"]
        real_dem_loaded = readiness["real_dem_loaded"]
        dem_loaded = readiness["dem_loaded"]
        effective_is_syn = readiness["is_synthetic"]
        active_mode = readiness["data_mode"]
        val_status = readiness["real_data_validation_status"]
        fallback_reason = readiness["fallback_reason"]
        blocking_errors: list[str] = list(readiness["blocking_errors"])

        hi_val = self.hirise_provider.validate_hirise_raster()
        hi_prov = (
            self.hirise_provider.get_provenance()
            if (self.hirise_provider.enabled or hi_val.is_valid)
            else None
        )

        limitations: list[str] = [
            f"Active DEM grid resolution ({res_meters} m/px) supports regional corridor terrain assessment rather than metre-scale obstacle detection or flight-grade rover navigation.",
            "Route cost weights, hazard exposure metrics, and risk categories are deterministic multi-criteria decision heuristics, not empirically calibrated probabilities of failure.",
            "Visual imagery layers must not be used for physical slope or energy calculations.",
        ]

        if effective_is_syn or (real_dem_requested and not real_dem_loaded):
            if active_mode == "synthetic_fallback" or real_dem_requested:
                limitations.append(
                    f"Fallback to Synthetic Jezero Crater Terrain Model occurred: {fallback_reason}."
                )
            else:
                limitations.append(
                    "Operating in development mode with Synthetic Jezero Crater Terrain Model. Real NASA/USGS DEM is not loaded."
                )
        else:
            if val_status in ACCEPTABLE_REAL_VALIDATION_STATUSES:
                limitations.append(
                    "The USGS global blended DEM (Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2) has a nominal resolution of 200 m/px; USGS warns of HRSC/MOLA blending seam inconsistencies and notes this dataset was originally constructed for global thermal-modelling (THEMIS thermal inertia) rather than precision local surface navigation."
                )
            for lim in provenance.get("provenance_limitations", []):
                if lim not in limitations:
                    limitations.append(lim)

        enriched_products: list[dict[str, Any]] = []
        for entry in DATA_CATALOG_MANIFEST:
            prod = dict(entry)
            if prod.get("id") == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2":
                prod["is_loaded"] = dem_loaded
                prod["runtime_status"] = val_status
            elif prod.get("id") == "dem_hirise_jezero_delta_1m":
                prod["is_loaded"] = bool(hi_val.is_valid)
                prod["runtime_status"] = hi_val.status_code
            else:
                prod["is_loaded"] = True
                prod["runtime_status"] = "external_tile_service"
            enriched_products.append(prod)

        return DataStatusResponse(
            status=overall_status,
            data_mode=active_mode,
            real_data_validation_status=val_status,
            dem_loaded=dem_loaded,
            real_dem_requested=real_dem_requested,
            real_dem_loaded=real_dem_loaded,
            local_integrity_verified=readiness["local_integrity_verified"],
            source_checksum_verified=readiness["source_checksum_verified"],
            is_synthetic=effective_is_syn,
            active_pilot_region="Jezero Crater, Mars",
            pilot_bounds=bounds,
            crs=crs_info,
            loaded_dem=(
                self.provider.dem_path
                if not effective_is_syn
                else "Synthetic Jezero Crater Terrain Model"
            ),
            active_dem_dataset_name=provenance.get("dataset_name"),
            active_dem_product_id=provenance.get("official_product_id"),
            active_dem_source_url=provenance.get("official_source_url"),
            fallback_reason=fallback_reason,
            dem_resolution_meters=res_meters,
            grid_shape=[raster.metadata.height, raster.metadata.width],
            valid_data_fraction=round(valid_frac, 4),
            active_dem_provenance=provenance,
            hirise_enabled=bool(self.hirise_provider.enabled),
            hirise_loaded=bool(hi_val.is_valid),
            hirise_status=hi_val.status_code,
            hirise_validation_reason=hi_val.reason,
            hirise_dem_provenance=hi_prov,
            configured_products=enriched_products,
            limitations=limitations,
            blocking_errors=blocking_errors,
        )
