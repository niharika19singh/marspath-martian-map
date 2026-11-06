import hashlib
import json
import os
import tempfile

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.app.data.manifest import DATA_CATALOG_MANIFEST
from backend.app.data.providers.mola_hrsc import MOLAHRSCRasterProvider
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.geospatial.crs import METERS_PER_DEGREE_LATITUDE
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.routing.alternatives import reconstruct_route_summary
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, RouteConstraints
from backend.app.schemas.routes import EvidenceQualityTier, RoutePlanRequest
from backend.app.services.evidence_service import EvidenceService
from backend.app.services.route_service import RouteService


def _write_test_geotiff(
    path: str,
    data: np.ndarray,
    deg_per_px: float | None = None,
    vertical_datum: str | None = "Mars_2000_Areoid_MOLA_0m",
    nodata: float = -32768.0,
) -> tuple[str, str]:
    step = deg_per_px or (200.0 / METERS_PER_DEGREE_LATITUDE)
    transform = from_origin(77.20, 18.65, step, step)
    crs_str = "+proj=longlat +R=3396190 +no_defs"
    height, width = data.shape

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=crs_str,
        transform=transform,
        nodata=nodata,
    ) as dst:
        if vertical_datum:
            dst.update_tags(VERTICAL_DATUM=vertical_datum)
        dst.write(data.astype(np.float32), 1)

    with open(path, "rb") as f:
        file_sha = hashlib.sha256(f.read()).hexdigest()
    arr_sha = hashlib.sha256(np.ascontiguousarray(data, dtype=np.float32).tobytes()).hexdigest()
    return file_sha, arr_sha


def test_synthetic_terrain_passport_is_unverified_and_has_no_usgs_attribution():
    """
    Provenance Test 1 & 2:
    - Synthetic terrain is classified as `unverified`.
    - Synthetic terrain has no official source URL or product ID.
    - Segment count equals route coordinate count minus one.
    """
    service = RouteService(provider=SyntheticTerrainProvider())
    req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.44, lat=18.42),
        mode=OptimizationMode.BALANCED,
        num_alternatives=2,
    )
    resp = service.plan_route(req)
    assert len(resp.routes) >= 2

    for route in resp.routes:
        passport = route.evidence_passport
        assert passport is not None
        assert passport.quality_tier == EvidenceQualityTier.UNVERIFIED
        assert "procedurally synthesized" in passport.tier_explanation.lower()
        assert "not a probability" in passport.scientific_disclaimer.lower()

        src = passport.source
        assert src.is_synthetic is True
        assert src.dataset_name == "Synthetic Jezero Crater Terrain Model"
        assert src.product_id is None
        assert src.official_source_url is None
        assert src.source_checksum_verified is False

        assert "synthetic_terrain" in passport.quality_flags
        assert "coarse_resolution_for_obstacle_detection" in passport.quality_flags

        # Check segment count and coordinate alignment
        coords = route.geometry.coordinates
        assert len(passport.segments) == len(coords) - 1
        assert passport.segments[0].from_coord.lon == round(coords[0][0], 6)
        assert passport.segments[0].from_coord.lat == round(coords[0][1], 6)
        assert passport.segments[-1].to_coord.lon == round(coords[-1][0], 6)
        assert passport.segments[-1].to_coord.lat == round(coords[-1][1], 6)

        for idx, seg in enumerate(passport.segments):
            assert seg.segment_index == idx
            assert seg.is_valid_data is True
            assert seg.elevation_start_m is not None
            assert seg.elevation_end_m is not None
            assert seg.slope_deg is not None
            assert seg.roughness is not None
            assert "synthetic_terrain" in seg.quality_flags


def test_unverified_local_raster_passport_is_unverified():
    """
    Provenance Test 3:
    An unverified local numeric raster is classified as `unverified` and never receives
    an official product ID or USGS URL.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        data = np.full((120, 160), -2500.0, dtype=np.float32)
        _write_test_geotiff(tmp_path, data)

        provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
        provider.use_real_dem = True
        provider.allow_fallback = False

        service = RouteService(provider=provider)
        resp = service.plan_route(
            RoutePlanRequest(
                start=MarsCoordinate(lon=77.35, lat=18.35),
                destination=MarsCoordinate(lon=77.42, lat=18.42),
            )
        )
        passport = resp.routes[0].evidence_passport
        assert passport is not None
        assert passport.quality_tier == EvidenceQualityTier.UNVERIFIED
        assert "unverified local source" in passport.tier_explanation.lower()
        assert passport.source.is_synthetic is False
        assert passport.source.product_id is None
        assert passport.source.official_source_url is None
        assert passport.source.validation_status == "valid_numeric_raster_unverified_source"
        assert "unverified_source" in passport.quality_flags
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_official_endpoint_extraction_receives_moderate_never_high():
    """
    Provenance Test 4 & 5:
    Official endpoint extraction (`official_endpoint_retrieved_checksum_unverified`)
    receives `moderate` when route/corridor coverage are complete, NEVER receives `high`,
    and discloses the unverified full-source checksum.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name
    sidecar_path = f"{tmp_path}.provenance.json"

    try:
        data = np.full((120, 160), -2480.0, dtype=np.float32)
        file_sha, arr_sha = _write_test_geotiff(tmp_path, data)

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_arr_sha = usgs_entry.get("jezero_window_array_sha256")
        usgs_entry["jezero_window_array_sha256"] = arr_sha

        try:
            sidecar_data = {
                "source_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
                "ingestion_method": "official_endpoint_vsicurl_range_extract",
                "published_upstream_md5": "e98092a06bea74d5ec9a704dcd1fe318",
                "source_checksum_verified": False,
                "local_file_sha256": file_sha,
                "extracted_array_sha256": arr_sha,
            }
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(sidecar_data, f)

            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            service = RouteService(provider=provider)
            resp = service.plan_route(
                RoutePlanRequest(
                    start=MarsCoordinate(lon=77.35, lat=18.35),
                    destination=MarsCoordinate(lon=77.42, lat=18.42),
                )
            )
            passport = resp.routes[0].evidence_passport
            assert passport is not None
            assert passport.quality_tier == EvidenceQualityTier.MODERATE
            assert passport.quality_tier != EvidenceQualityTier.HIGH
            assert "11.38 gb upstream archive md5 checksum remains unverified" in passport.tier_explanation.lower()

            assert passport.source.product_id == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
            assert passport.source.official_source_url is not None
            assert passport.source.local_integrity_verified is True
            assert passport.source.source_checksum_verified is False
            assert "source_checksum_unverified" in passport.quality_flags
            assert any("11.38 GB upstream file" in lim for lim in passport.known_limitations)
        finally:
            usgs_entry["jezero_window_array_sha256"] = orig_arr_sha
    finally:
        for p in (tmp_path, sidecar_path):
            if os.path.exists(p):
                os.remove(p)


def test_verified_full_source_receives_high_and_downgrades_on_conflicting_conditions():
    """
    Provenance Test 6 & Tier Conflict Tests:
    - Verified full-source provenance receives `high` ONLY when all checksum, metadata,
      route coverage, corridor coverage, and resolution requirements pass.
    - When a nodata hole is introduced in the corridor or vertical datum is unknown,
      tier is downgraded to `low` (or `moderate` for a minor far-away corridor gap).
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        data = np.full((120, 160), -2480.0, dtype=np.float32)
        file_sha, _ = _write_test_geotiff(
            tmp_path, data, vertical_datum="Mars_2000_Areoid_MOLA_0m"
        )

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_sha = usgs_entry.get("sha256")
        usgs_entry["sha256"] = file_sha

        try:
            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            service = RouteService(provider=provider)
            resp = service.plan_route(
                RoutePlanRequest(
                    start=MarsCoordinate(lon=77.35, lat=18.35),
                    destination=MarsCoordinate(lon=77.42, lat=18.42),
                )
            )
            passport = resp.routes[0].evidence_passport
            assert passport is not None
            assert passport.quality_tier == EvidenceQualityTier.HIGH
            assert passport.source.source_checksum_verified is True
            assert passport.source.local_integrity_verified is True
            assert passport.coverage.route_data_coverage_fraction == 1.0
            assert passport.coverage.corridor_data_coverage_fraction == 1.0
            assert passport.coverage.near_nodata_segment_count == 0
        finally:
            usgs_entry["sha256"] = orig_sha

        # Conflict Case A: Verified source but unknown vertical datum -> downgraded to LOW
        file_sha_no_datum, _ = _write_test_geotiff(tmp_path, data, vertical_datum=None)
        usgs_entry["sha256"] = file_sha_no_datum
        try:
            provider_no_datum = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider_no_datum.use_real_dem = True
            provider_no_datum.allow_fallback = False
            resp_no_datum = RouteService(provider=provider_no_datum).plan_route(
                RoutePlanRequest(
                    start=MarsCoordinate(lon=77.35, lat=18.35),
                    destination=MarsCoordinate(lon=77.42, lat=18.42),
                )
            )
            p_no_datum = resp_no_datum.routes[0].evidence_passport
            assert p_no_datum is not None
            assert p_no_datum.quality_tier == EvidenceQualityTier.LOW
            assert "unknown_vertical_datum" in p_no_datum.quality_flags
        finally:
            usgs_entry["sha256"] = orig_sha
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_corridor_nodata_hole_reduces_corridor_coverage_independently_of_route_coverage():
    """
    Coverage & Nodata Boundary Test:
    - A nodata hole in the corridor reduces `corridor_data_coverage_fraction` (< 1.0)
      while `route_data_coverage_fraction` remains 1.0 as the route navigates around the hole.
    - Segments skirting the nodata hole receive `near_nodata_boundary` and `incomplete_corridor_coverage` flags,
      downgrading quality_tier to `low`.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        data = np.full((120, 160), -2480.0, dtype=np.float32)
        # Place a nodata hole across the direct line between (77.35, 18.40) and (77.43, 18.40)
        # Row index for lat=18.40 when top=18.65 and step=0.003374 is ~74; col index for lon=77.39 is ~56
        data[72:77, 54:59] = -32768.0
        file_sha, _ = _write_test_geotiff(
            tmp_path, data, vertical_datum="Mars_2000_Areoid_MOLA_0m"
        )

        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_sha = usgs_entry.get("sha256")
        usgs_entry["sha256"] = file_sha

        try:
            provider = MOLAHRSCRasterProvider(dem_path=tmp_path)
            provider.use_real_dem = True
            provider.allow_fallback = False

            service = RouteService(provider=provider)
            resp = service.plan_route(
                RoutePlanRequest(
                    start=MarsCoordinate(lon=77.35, lat=18.40),
                    destination=MarsCoordinate(lon=77.43, lat=18.40),
                )
            )
            route = resp.routes[0]
            passport = route.evidence_passport
            assert passport is not None

            # Route avoids the nodata hole (100% valid route samples), while corridor coverage is < 1.0
            assert passport.coverage.route_data_coverage_fraction == 1.0
            assert passport.coverage.invalid_route_sample_count == 0
            assert passport.coverage.corridor_invalid_cells >= 25
            assert passport.coverage.corridor_data_coverage_fraction < 1.0
            assert passport.coverage.route_data_coverage_fraction != passport.coverage.corridor_data_coverage_fraction

            assert "incomplete_corridor_coverage" in passport.quality_flags
            assert passport.coverage.near_nodata_segment_count > 0
            assert "near_nodata_boundary" in passport.quality_flags
            assert passport.quality_tier == EvidenceQualityTier.LOW
        finally:
            usgs_entry["sha256"] = orig_sha
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_invalid_route_samples_reduce_measured_data_coverage_and_never_become_zero():
    """
    Verifies that:
    1. `RouteSummary.data_coverage_fraction` is no longer hardcoded to 1.0 and reflects
       actual valid route sample fraction when a path steps across an invalid/nodata cell.
    2. Invalid segment values are reported as `None` (`is_valid_data=False`), never
       silently converted to `0.0`.
    """
    rows, cols = 20, 20
    elevation = np.full((rows, cols), -2500.0, dtype=np.float32)
    nodata_mask = np.zeros((rows, cols), dtype=bool)
    nodata_mask[10, 10] = True
    elevation[10, 10] = -9999.0

    dx, dy = 200.0, 200.0
    slopes = compute_slope_degrees(elevation, dx, dy, nodata_mask=nodata_mask)
    roughness = compute_roughness_index(elevation, kernel_size=3, nodata_mask=nodata_mask)
    traversable = build_traversability_mask(
        slope_deg=slopes,
        roughness=roughness,
        nodata_mask=nodata_mask,
        avoid_unobserved_terrain=False,
    )

    graph = TerrainGridGraph(
        elevation=elevation,
        slope_deg=slopes,
        roughness=roughness,
        traversable_mask=traversable,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )
    deg_step = 200.0 / METERS_PER_DEGREE_LATITUDE
    meta = RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.30,
        min_lat=18.30,
        max_lon=77.30 + cols * deg_step,
        max_lat=18.30 + rows * deg_step,
        deg_per_px_lon=deg_step,
        deg_per_px_lat=deg_step,
        meters_per_px_x=dx,
        meters_per_px_y=dy,
        affine_transform=(deg_step, 0.0, 77.30, 0.0, -deg_step, 18.30 + rows * deg_step),
        nodata_value=-9999.0,
        vertical_datum="Mars_2000_Areoid_MOLA_0m",
        is_synthetic=False,
    )

    # Path of 5 nodes passing directly through nodata cell (10, 10)
    path_nodes = [(10, 8), (10, 9), (10, 10), (10, 11), (10, 12)]
    summary, geom, _, _, _ = reconstruct_route_summary(
        path_nodes=path_nodes,
        graph=graph,
        meta=meta,
        mode=OptimizationMode.BALANCED,
    )

    # Nodes (10, 9), (10, 10), (10, 11) have NaN slope/roughness due to nodata dilation;
    # only (10, 8) and (10, 12) are fully valid (2 / 5 = 0.4), while 4/5 elevations are valid (0.8)
    assert summary.data_coverage_fraction == 0.4
    assert summary.elevation_sample_coverage_fraction == 0.8
    assert summary.is_complete_measurement is False
    assert summary.data_coverage_fraction < 1.0
    # Valid elevations are -2500.0; nodata -9999.0 or 0.0 must NOT corrupt min/max elevation
    assert summary.min_elevation_meters == -2500.0
    assert summary.max_elevation_meters == -2500.0

    # Because 1 elevation sample is invalid, geometry must be a 2D RFC 7946 LineString
    # and NEVER contain a fabricated 0.0 Z coordinate
    assert geom.type == "LineString"
    assert len(geom.coordinates) == 5
    for coord in geom.coordinates:
        assert len(coord) == 2

    passport = EvidenceService.build_route_evidence_passport(
        path_nodes=path_nodes,
        graph=graph,
        master_meta=meta,
        cropped_meta=meta,
        provenance={
            "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
            "official_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
            "official_source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
            "data_mode": "real",
            "real_data_validation_status": "verified_source",
            "provenance_verification_method": "authoritative_manifest_sha256_match",
            "local_integrity_verified": True,
            "source_checksum_verified": True,
            "is_synthetic": False,
        },
        mode=OptimizationMode.BALANCED,
    )

    assert passport.coverage.route_sample_count == 5
    assert passport.coverage.valid_route_sample_count == 2
    assert passport.coverage.invalid_route_sample_count == 3
    assert passport.coverage.route_data_coverage_fraction == 0.4
    assert passport.quality_tier == EvidenceQualityTier.LOW

    # Segment 1 ((10, 9) -> (10, 10)) steps into nodata cell (10, 10):
    # elevation_end_m, delta_elevation_m, slope_deg, roughness must be None (not 0.0!)
    seg_into_nodata = passport.segments[1]
    assert seg_into_nodata.is_valid_data is False
    assert seg_into_nodata.elevation_end_m is None
    assert seg_into_nodata.delta_elevation_m is None
    assert seg_into_nodata.slope_deg is None
    assert seg_into_nodata.roughness is None
    assert "invalid_or_nodata_segment" in seg_into_nodata.quality_flags


def test_geometry_and_summary_never_fabricate_zero_elevations_across_valid_partial_and_all_invalid_routes():
    """
    Phase 2.1 Section 1 Regression Suite:
    1. A route with one invalid elevation sample emits 2D LineString coordinates and partial summary aggregates.
    2. A route with all elevation samples invalid emits 2D LineString coordinates and None for min/max/gain/loss/slope/roughness.
    3. A route with fully valid elevations preserves 3D [lon, lat, elev] coordinates and complete summary metrics.
    4. Neither geometry nor summary ever fabricates 0.0 for missing terrain observations.
    """
    rows, cols = 12, 12
    deg_step = 200.0 / METERS_PER_DEGREE_LATITUDE
    dx, dy = 200.0, 200.0
    meta = RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.30,
        min_lat=18.30,
        max_lon=77.30 + cols * deg_step,
        max_lat=18.30 + rows * deg_step,
        deg_per_px_lon=deg_step,
        deg_per_px_lat=deg_step,
        meters_per_px_x=dx,
        meters_per_px_y=dy,
        affine_transform=(deg_step, 0.0, 77.30, 0.0, -deg_step, 18.30 + rows * deg_step),
        nodata_value=-9999.0,
        vertical_datum="Mars_2000_Areoid_MOLA_0m",
        is_synthetic=False,
    )
    path_nodes = [(5, 2), (5, 3), (5, 4), (5, 5), (5, 6)]

    # Case 1: Fully valid elevations (-2540m to -2500m) -> 3D coordinates preserved
    elev_valid = np.linspace(-2540.0, -2500.0, rows * cols, dtype=np.float32).reshape(rows, cols)
    nodata_valid = np.zeros((rows, cols), dtype=bool)
    slopes_valid = compute_slope_degrees(elev_valid, dx, dy, nodata_mask=nodata_valid)
    rough_valid = compute_roughness_index(elev_valid, kernel_size=3, nodata_mask=nodata_valid)
    trav_valid = build_traversability_mask(
        slope_deg=slopes_valid,
        roughness=rough_valid,
        nodata_mask=nodata_valid,
        avoid_unobserved_terrain=False,
    )
    graph_valid = TerrainGridGraph(
        elevation=elev_valid,
        slope_deg=slopes_valid,
        roughness=rough_valid,
        traversable_mask=trav_valid,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )
    sum_valid, geom_valid, _, _, _ = reconstruct_route_summary(
        path_nodes=path_nodes,
        graph=graph_valid,
        meta=meta,
        mode=OptimizationMode.BALANCED,
    )
    assert sum_valid.is_complete_measurement is True
    assert sum_valid.data_coverage_fraction == 1.0
    assert sum_valid.elevation_sample_coverage_fraction == 1.0
    assert sum_valid.min_elevation_meters is not None and sum_valid.min_elevation_meters < -2500.0
    assert sum_valid.max_elevation_meters is not None and sum_valid.max_elevation_meters < -2500.0
    assert all(len(c) == 3 and c[2] < -2500.0 for c in geom_valid.coordinates)

    # Case 2: One invalid elevation sample at (5, 4) -> 2D LineString, no 0.0 Z value
    elev_one_bad = elev_valid.copy()
    elev_one_bad[5, 4] = -9999.0
    nodata_one_bad = np.zeros((rows, cols), dtype=bool)
    nodata_one_bad[5, 4] = True
    slopes_one_bad = compute_slope_degrees(elev_one_bad, dx, dy, nodata_mask=nodata_one_bad)
    rough_one_bad = compute_roughness_index(elev_one_bad, kernel_size=3, nodata_mask=nodata_one_bad)
    trav_one_bad = build_traversability_mask(
        slope_deg=slopes_one_bad,
        roughness=rough_one_bad,
        nodata_mask=nodata_one_bad,
        avoid_unobserved_terrain=False,
    )
    graph_one_bad = TerrainGridGraph(
        elevation=elev_one_bad,
        slope_deg=slopes_one_bad,
        roughness=rough_one_bad,
        traversable_mask=trav_one_bad,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )
    sum_one_bad, geom_one_bad, _, _, _ = reconstruct_route_summary(
        path_nodes=path_nodes,
        graph=graph_one_bad,
        meta=meta,
        mode=OptimizationMode.BALANCED,
    )
    assert sum_one_bad.is_complete_measurement is False
    assert sum_one_bad.elevation_sample_coverage_fraction == 0.8
    assert sum_one_bad.data_coverage_fraction == 0.4
    assert sum_one_bad.min_elevation_meters is not None and sum_one_bad.min_elevation_meters < -2500.0
    assert sum_one_bad.max_elevation_meters is not None and sum_one_bad.max_elevation_meters < -2500.0
    assert all(len(c) == 2 for c in geom_one_bad.coordinates)

    # Case 3: All elevation samples invalid -> 2D LineString and None for terrain aggregates (never 0.0)
    elev_all_bad = np.full((rows, cols), -9999.0, dtype=np.float32)
    nodata_all_bad = np.ones((rows, cols), dtype=bool)
    slopes_all_bad = compute_slope_degrees(elev_all_bad, dx, dy, nodata_mask=nodata_all_bad)
    rough_all_bad = compute_roughness_index(elev_all_bad, kernel_size=3, nodata_mask=nodata_all_bad)
    trav_all_bad = np.ones((rows, cols), dtype=bool)
    graph_all_bad = TerrainGridGraph(
        elevation=elev_all_bad,
        slope_deg=slopes_all_bad,
        roughness=rough_all_bad,
        traversable_mask=trav_all_bad,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )
    sum_all_bad, geom_all_bad, _, _, _ = reconstruct_route_summary(
        path_nodes=path_nodes,
        graph=graph_all_bad,
        meta=meta,
        mode=OptimizationMode.BALANCED,
    )
    assert sum_all_bad.is_complete_measurement is False
    assert sum_all_bad.data_coverage_fraction == 0.0
    assert sum_all_bad.elevation_sample_coverage_fraction == 0.0
    assert sum_all_bad.min_elevation_meters is None
    assert sum_all_bad.max_elevation_meters is None
    assert sum_all_bad.elevation_gain_meters is None
    assert sum_all_bad.elevation_loss_meters is None
    assert sum_all_bad.max_slope_deg is None
    assert sum_all_bad.average_slope_deg is None
    assert sum_all_bad.average_roughness is None
    assert sum_all_bad.risk_category == "high"
    assert all(len(c) == 2 for c in geom_all_bad.coordinates)


def test_explicit_high_tier_verification_gates_and_regional_200m_semantics():
    """
    Phase 2.1 Section 2 & 3 Regression Suite:
    1. Verified source with missing local integrity status (`None` or omitted) cannot receive `high`.
    2. Verified source with missing CRS cannot receive `high` and does not silently default to `IAU2000:49900`.
    3. Verified source with unknown vertical datum cannot receive `high`.
    4. A 200 m/px source with independently verified checksum and complete regional evidence receives `high`,
       with `obstacle_detection_capable` remaining `False`.
    """
    rows, cols = 12, 12
    deg_step = 200.0 / METERS_PER_DEGREE_LATITUDE
    dx, dy = 189.79, 200.0
    elev = np.full((rows, cols), -2480.0, dtype=np.float32)
    nodata_mask = np.zeros((rows, cols), dtype=bool)
    slopes = compute_slope_degrees(elev, dx, dy, nodata_mask=nodata_mask)
    rough = compute_roughness_index(elev, kernel_size=3, nodata_mask=nodata_mask)
    trav = np.ones((rows, cols), dtype=bool)
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slopes,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=dx,
        dy_meters=dy,
        mode=OptimizationMode.BALANCED,
    )
    base_meta = RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.30,
        min_lat=18.30,
        max_lon=77.30 + cols * deg_step,
        max_lat=18.30 + rows * deg_step,
        deg_per_px_lon=deg_step,
        deg_per_px_lat=deg_step,
        meters_per_px_x=dx,
        meters_per_px_y=dy,
        affine_transform=(deg_step, 0.0, 77.30, 0.0, -deg_step, 18.30 + rows * deg_step),
        nodata_value=-32768.0,
        vertical_datum="Mars_2000_Areoid_MOLA_0m",
        is_synthetic=False,
    )
    base_prov = {
        "dataset_name": "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2",
        "official_product_id": "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
        "official_source_url": "https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m",
        "data_mode": "real",
        "real_data_validation_status": "verified_source",
        "provenance_verification_method": "authoritative_manifest_sha256_match",
        "local_integrity_verified": True,
        "source_checksum_verified": True,
        "is_synthetic": False,
    }
    path_nodes = [(4, 3), (4, 4), (4, 5), (4, 6)]

    # Gate 4: 200 m/px source with verified checksum + local integrity + Mars CRS + vertical datum + 100% coverage -> HIGH,
    # while obstacle_detection_capable remains False
    passport_high = EvidenceService.build_route_evidence_passport(
        path_nodes=path_nodes,
        graph=graph,
        master_meta=base_meta,
        cropped_meta=base_meta,
        provenance=base_prov,
        mode=OptimizationMode.BALANCED,
    )
    assert passport_high.quality_tier == EvidenceQualityTier.HIGH
    assert passport_high.resolution_assessment.effective_resolution_meters == 200.0
    assert passport_high.resolution_assessment.obstacle_detection_capable is False
    assert (
        passport_high.resolution_assessment.suitability_classification
        == "regional_corridor_assessment_only"
    )

    # Gate 1: Verified source with missing local_integrity_verified (omitted or None) cannot receive HIGH
    prov_missing_local_int = dict(base_prov)
    prov_missing_local_int.pop("local_integrity_verified")
    passport_no_local_int = EvidenceService.build_route_evidence_passport(
        path_nodes=path_nodes,
        graph=graph,
        master_meta=base_meta,
        cropped_meta=base_meta,
        provenance=prov_missing_local_int,
        mode=OptimizationMode.BALANCED,
    )
    assert passport_no_local_int.source.local_integrity_verified is None
    assert passport_no_local_int.quality_tier == EvidenceQualityTier.MODERATE
    assert passport_no_local_int.quality_tier != EvidenceQualityTier.HIGH
    assert "local_integrity_unverified" in passport_no_local_int.quality_flags

    # Gate 2: Verified source with missing CRS cannot receive HIGH and does not silently default to IAU2000:49900
    meta_missing_crs = RasterMetadata(
        **{**base_meta.__dict__, "crs_str": ""}
    )
    passport_no_crs = EvidenceService.build_route_evidence_passport(
        path_nodes=path_nodes,
        graph=graph,
        master_meta=meta_missing_crs,
        cropped_meta=meta_missing_crs,
        provenance=base_prov,
        mode=OptimizationMode.BALANCED,
    )
    assert passport_no_crs.source.crs_identifier == "Unknown / Unspecified"
    assert passport_no_crs.quality_tier == EvidenceQualityTier.LOW
    assert passport_no_crs.quality_tier != EvidenceQualityTier.HIGH
    assert "unknown_crs" in passport_no_crs.quality_flags

    # Also verify end-to-end GeoTIFF with crs=None loaded through MOLAHRSCRasterProvider
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp_nocrs:
        nocrs_path = tmp_nocrs.name
    try:
        step = 200.0 / METERS_PER_DEGREE_LATITUDE
        transform = from_origin(77.20, 18.65, step, step)
        geotiff_data = np.full((120, 160), -2480.0, dtype=np.float32)
        with rasterio.open(
            nocrs_path,
            "w",
            driver="GTiff",
            height=120,
            width=160,
            count=1,
            dtype="float32",
            crs=None,
            transform=transform,
            nodata=-32768.0,
        ) as dst:
            dst.update_tags(VERTICAL_DATUM="Mars_2000_Areoid_MOLA_0m")
            dst.write(geotiff_data, 1)
        with open(nocrs_path, "rb") as f:
            nocrs_sha = hashlib.sha256(f.read()).hexdigest()
        usgs_entry = next(
            p for p in DATA_CATALOG_MANIFEST if p["id"] == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2"
        )
        orig_sha = usgs_entry.get("sha256")
        usgs_entry["sha256"] = nocrs_sha
        try:
            prov_nocrs = MOLAHRSCRasterProvider(dem_path=nocrs_path)
            prov_nocrs.use_real_dem = True
            prov_nocrs.allow_fallback = False
            resp_nocrs = RouteService(provider=prov_nocrs).plan_route(
                RoutePlanRequest(
                    start=MarsCoordinate(lon=77.35, lat=18.35),
                    destination=MarsCoordinate(lon=77.42, lat=18.42),
                )
            )
            p_nocrs = resp_nocrs.routes[0].evidence_passport
            assert p_nocrs is not None
            assert p_nocrs.source.crs_identifier == "Unknown / Unspecified"
            assert p_nocrs.quality_tier == EvidenceQualityTier.LOW
            assert "unknown_crs" in p_nocrs.quality_flags
        finally:
            usgs_entry["sha256"] = orig_sha
    finally:
        if os.path.exists(nocrs_path):
            os.remove(nocrs_path)

    # Gate 3: Verified source with unknown vertical datum cannot receive HIGH
    meta_missing_datum = RasterMetadata(
        **{**base_meta.__dict__, "vertical_datum": "Unknown / Unspecified"}
    )
    passport_no_datum = EvidenceService.build_route_evidence_passport(
        path_nodes=path_nodes,
        graph=graph,
        master_meta=meta_missing_datum,
        cropped_meta=meta_missing_datum,
        provenance=base_prov,
        mode=OptimizationMode.BALANCED,
    )
    assert passport_no_datum.quality_tier == EvidenceQualityTier.LOW
    assert passport_no_datum.quality_tier != EvidenceQualityTier.HIGH
    assert "unknown_vertical_datum" in passport_no_datum.quality_flags


def test_waypoint_guided_and_science_first_routes_include_complete_passports():
    """
    Verifies that waypoint-guided routes and science-first routes (both detour and
    direct baseline alternative) include complete `RouteEvidencePassport` and segment lists.
    """
    service = RouteService(provider=SyntheticTerrainProvider())

    # 1. Waypoint-guided route with 2 alternatives
    wp_resp = service.plan_route(
        RoutePlanRequest(
            start=MarsCoordinate(lon=77.40, lat=18.39),
            destination=MarsCoordinate(lon=77.45, lat=18.42),
            science_waypoints=[MarsCoordinate(lon=77.42, lat=18.405)],
            mode=OptimizationMode.BALANCED,
            num_alternatives=2,
        )
    )
    assert len(wp_resp.routes) >= 2
    for r in wp_resp.routes:
        assert r.evidence_passport is not None
        assert len(r.evidence_passport.segments) == len(r.geometry.coordinates) - 1
        assert len(r.evidence_passport.segments) > 0

    # 2. Science-first route with 2 alternatives (detour + direct baseline)
    sci_resp = service.plan_route(
        RoutePlanRequest(
            start=MarsCoordinate(lon=77.40, lat=18.39),
            destination=MarsCoordinate(lon=77.45, lat=18.42),
            mode=OptimizationMode.SCIENCE_FIRST,
            num_alternatives=2,
            constraints=RouteConstraints(max_slope_deg=20.0),
        )
    )
    assert len(sci_resp.routes) >= 2
    for r in sci_resp.routes:
        assert r.evidence_passport is not None
        assert len(r.evidence_passport.segments) == len(r.geometry.coordinates) - 1
        assert len(r.evidence_passport.segments) > 0
