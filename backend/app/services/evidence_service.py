"""
Terrain Evidence & Route Confidence Passport Service.

Constructs a deterministic, explainable `RouteEvidencePassport` for every candidate
route alternative, capturing:
- Source dataset identity and cryptographic provenance verification state.
- Independent route observation coverage and cropped corridor observation coverage.
- Physical pixel resolution assessment (actual X/Y vs. nominal) and scale suitability.
- Segment-by-segment terrain measurements and data-quality flags.
- Conservative 4-tier evidence classification (`high`, `moderate`, `low`, `unverified`).

Scientific Integrity Invariant:
Terrain evidence quality measures the provenance, resolution, and completeness of the
underlying topographic observations. It is NEVER a probability of rover survival,
mission success, or calibrated probability of mechanical failure.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage

from backend.app.geospatial.crs import pixel_to_geo
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.cost_model import calculate_edge_cost
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.coordinates import BoundingBox, MarsCoordinate
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import (
    CoverageEvidence,
    EvidenceQualityTier,
    ResolutionAssessment,
    RouteEvidencePassport,
    RouteSegment,
    SourceEvidence,
)


def compute_nodata_and_boundary_masks(
    elevation: np.ndarray,
    nodata_value: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Computes:
    1. `nodata_mask`: True where elevation is NaN, matches `nodata_value`, or falls outside
       physical Martian bounds (<-9000m or >1e30).
    2. `near_nodata_mask`: True for valid cells within a 2-cell (5x5 window) neighborhood
       of any nodata cell, capturing routes that skirt the dilated nodata barrier.
    """
    nodata_mask = np.isnan(elevation) | (elevation < -9000.0) | (elevation > 1e30)
    if nodata_value is not None:
        nodata_mask = nodata_mask | np.isclose(elevation, nodata_value, atol=1e-3)

    if np.any(nodata_mask):
        near_nodata_mask = ndimage.binary_dilation(
            nodata_mask, structure=np.ones((5, 5), dtype=bool)
        ) & (~nodata_mask)
    else:
        near_nodata_mask = np.zeros_like(nodata_mask, dtype=bool)

    return nodata_mask, near_nodata_mask


class EvidenceService:
    """Builds structured `RouteEvidencePassport` objects from active raster and route data."""

    @staticmethod
    def _is_established_mars_crs(crs_identifier: str | None) -> bool:
        """Returns True only if `crs_identifier` is an established Mars planetary CRS."""
        if not crs_identifier or not crs_identifier.strip():
            return False
        norm = crs_identifier.strip().upper()
        if norm in ("UNKNOWN", "UNSPECIFIED", "UNKNOWN / UNSPECIFIED", "NONE"):
            return False
        return any(
            token in norm
            for token in (
                "IAU2000:49900",
                "IAU_2000:49900",
                "IAU_2015:49900",
                "ESRI:104971",
                "MARS",
                "49900",
                "104971",
                "3396190",
            )
        )

    @staticmethod
    def _is_known_vertical_datum(vertical_datum: str | None) -> bool:
        """Returns True only if `vertical_datum` is explicitly declared and not unknown/unspecified."""
        if not vertical_datum or not vertical_datum.strip():
            return False
        norm = vertical_datum.strip().lower()
        return "unknown" not in norm and "unspecified" not in norm and norm != "none"

    @staticmethod
    def build_source_evidence(
        master_meta: RasterMetadata,
        provenance: dict[str, Any],
        dx_meters: float,
        dy_meters: float,
    ) -> SourceEvidence:
        is_syn = bool(master_meta.is_synthetic or provenance.get("is_synthetic", False))
        data_mode = str(
            provenance.get("data_mode", "synthetic_test_fixture" if is_syn else "real")
        )
        val_status = str(
            provenance.get(
                "real_data_validation_status",
                "synthetic_test_fixture" if is_syn else "valid_numeric_raster_unverified_source",
            )
        )
        ver_method = str(
            provenance.get(
                "provenance_verification_method",
                "deterministic_synthetic_procedural_generator"
                if is_syn
                else "unverified_source_no_authoritative_credentials",
            )
        )

        # Enforce strict source attribution: synthetic and unverified local rasters never receive
        # official product IDs or USGS/NASA URLs
        if is_syn:
            dataset_name = "Synthetic Jezero Crater Terrain Model"
            product_id = None
            publisher = "MARSPath Internal Synthetic Generator"
            official_source_url = None
            local_integrity_verified = None
            source_checksum_verified = False
            nominal_res = float(provenance.get("nominal_resolution_meters", round(dy_meters, 1)))
        elif val_status in ("verified_source", "official_endpoint_retrieved_checksum_unverified"):
            dataset_name = str(
                provenance.get("dataset_name")
                or "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2"
            )
            product_id = provenance.get("official_product_id")
            publisher = provenance.get("data_publisher") or "USGS Astrogeology Science Center"
            official_source_url = provenance.get("official_source_url")
            raw_local_integrity = provenance.get("local_integrity_verified")
            local_integrity_verified = (
                raw_local_integrity if isinstance(raw_local_integrity, bool) else None
            )
            source_checksum_verified = provenance.get("source_checksum_verified") is True
            if product_id == "Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2":
                nominal_res = 200.0
            elif product_id == "dem_hirise_jezero_delta_1m":
                nominal_res = 1.0
            else:
                nominal_res = round(dy_meters, 1)
        else:
            dataset_name = str(
                provenance.get("dataset_name")
                or "Local Numerical Elevation Model (Unverified Source)"
            )
            product_id = None
            publisher = provenance.get("data_publisher") or "Unknown / Local Origin"
            official_source_url = None
            raw_local_integrity = provenance.get("local_integrity_verified")
            local_integrity_verified = (
                raw_local_integrity if isinstance(raw_local_integrity, bool) else None
            )
            source_checksum_verified = False
            nominal_res = None

        source_lims = list(provenance.get("provenance_limitations", []))
        if is_syn and not source_lims:
            source_lims = [
                "Operating on deterministic synthetic/procedural terrain model for Jezero Crater. Real NASA/USGS DEM is not loaded.",
                "Elevation and terrain gradients are mathematically synthesized; unsuitable for operational navigation.",
            ]

        raw_crs = str(master_meta.crs_str or "").strip()
        crs_identifier = raw_crs if raw_crs else "Unknown / Unspecified"
        raw_datum = str(master_meta.vertical_datum or "").strip()
        vertical_datum = raw_datum if raw_datum else "Unknown / Unspecified"

        return SourceEvidence(
            dataset_name=dataset_name,
            product_id=product_id,
            publisher=publisher,
            official_source_url=official_source_url,
            data_mode=data_mode,
            validation_status=val_status,
            verification_method=ver_method,
            is_synthetic=is_syn,
            local_integrity_verified=local_integrity_verified,
            source_checksum_verified=source_checksum_verified,
            file_sha256=provenance.get("file_sha256"),
            pixel_resolution_x_meters=round(dx_meters, 2),
            pixel_resolution_y_meters=round(dy_meters, 2),
            nominal_resolution_meters=nominal_res,
            raster_width=int(master_meta.width),
            raster_height=int(master_meta.height),
            crs_identifier=crs_identifier,
            vertical_datum=vertical_datum,
            spatial_coverage=BoundingBox(
                min_lon=round(float(master_meta.min_lon), 6),
                min_lat=round(float(master_meta.min_lat), 6),
                max_lon=round(float(master_meta.max_lon), 6),
                max_lat=round(float(master_meta.max_lat), 6),
            ),
            source_limitations=source_lims,
        )

    @staticmethod
    def build_resolution_assessment(
        is_synthetic: bool,
        dx_meters: float,
        dy_meters: float,
        nominal_res: float | None,
    ) -> ResolutionAssessment:
        actual_x = round(dx_meters, 2)
        actual_y = round(dy_meters, 2)
        effective_res = round(max(dx_meters, dy_meters), 2)

        if is_synthetic:
            suitability = "synthetic_simulation_only"
            obstacle_capable = False
            statement = (
                f"Active grid is a procedurally synthesized model at {actual_x} m (X) × {actual_y} m (Y) "
                f"per pixel (effective resolution {effective_res} m/px). Suitable only for algorithm "
                "testing and UI simulation; does not represent physical Martian surface obstacles."
            )
        elif effective_res <= 1.5:
            suitability = "local_corridor_and_hazard_assessment"
            obstacle_capable = effective_res <= 1.0
            statement = (
                f"Actual metric cell resolution is {actual_x} m (X) × {actual_y} m (Y) per pixel "
                f"(effective {effective_res} m/px"
                + (f", nominal {nominal_res} m/px" if nominal_res else "")
                + "). Supports local landform and metre-scale hazard evaluation, though sub-pixel "
                "cobbles and wheel-scale regolith traps (<1 m) remain unresolved."
            )
        elif effective_res <= 250.0:
            suitability = "regional_corridor_assessment_only"
            obstacle_capable = False
            nominal_note = (
                f" (nominal equatorial resolution {nominal_res} m/px; zonal width compressed by cos(lat) at Jezero Crater)"
                if nominal_res is not None
                else ""
            )
            statement = (
                f"Actual metric cell resolution at corridor latitude is {actual_x} m (X) × {actual_y} m (Y) "
                f"per pixel (effective {effective_res} m/px){nominal_note}. Supports regional corridor "
                "topographic screening only; does NOT resolve metre-scale boulders, local scarps, "
                "sand ripples, or flight-grade rover obstacles."
            )
        else:
            suitability = "coarse_planetary_overview_only"
            obstacle_capable = False
            statement = (
                f"Coarse grid resolution of {actual_x} m (X) × {actual_y} m (Y) per pixel "
                f"(effective {effective_res} m/px) is suitable only for macro-scale synoptic overview "
                "and is too coarse for regional or local route hazard assessment."
            )

        return ResolutionAssessment(
            actual_x_meters_per_pixel=actual_x,
            actual_y_meters_per_pixel=actual_y,
            effective_resolution_meters=effective_res,
            nominal_dataset_resolution_meters=nominal_res,
            suitability_classification=suitability,
            obstacle_detection_capable=obstacle_capable,
            limitation_statement=statement,
        )

    @classmethod
    def build_segments_and_coverage(
        cls,
        path_nodes: list[tuple[int, int]],
        graph: TerrainGridGraph,
        cropped_meta: RasterMetadata,
        mode: OptimizationMode,
        source: SourceEvidence,
        resolution: ResolutionAssessment,
        penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] | None = None,
    ) -> tuple[list[RouteSegment], CoverageEvidence, list[str]]:
        """
        Computes:
        1. Segment-level evidence (`list[RouteSegment]`) for all N-1 steps along `path_nodes`.
        2. Independent route sample coverage and cropped corridor cell coverage (`CoverageEvidence`).
        3. Aggregated route-level `quality_flags`.
        """
        nodata_mask, near_nodata_mask = compute_nodata_and_boundary_masks(
            graph.elevation, cropped_meta.nodata_value
        )

        # 1. Corridor-level coverage
        corridor_total_cells = int(graph.elevation.size)
        corridor_invalid_cells = int(nodata_mask.sum())
        corridor_valid_cells = corridor_total_cells - corridor_invalid_cells
        corridor_cov_fraction = round(
            corridor_valid_cells / max(corridor_total_cells, 1), 4
        )

        # 2. Route node sample coverage
        route_sample_count = len(path_nodes)
        valid_route_sample_count = 0
        for r, c in path_nodes:
            cell_is_valid = (
                not bool(nodata_mask[r, c])
                and not math.isnan(float(graph.slope_deg[r, c]))
                and not math.isnan(float(graph.roughness[r, c]))
            )
            if cell_is_valid:
                valid_route_sample_count += 1
        invalid_route_sample_count = route_sample_count - valid_route_sample_count
        route_cov_fraction = round(
            valid_route_sample_count / max(route_sample_count, 1), 4
        )

        # Baseline flags applicable to all segments on this dataset
        base_segment_flags: list[str] = []
        if source.is_synthetic:
            base_segment_flags.append("synthetic_terrain")
        elif source.validation_status == "valid_numeric_raster_unverified_source":
            base_segment_flags.append("unverified_source")
        elif not source.source_checksum_verified:
            base_segment_flags.append("source_checksum_unverified")

        if (
            not source.is_synthetic
            and source.validation_status != "valid_numeric_raster_unverified_source"
            and source.local_integrity_verified is not True
        ):
            base_segment_flags.append("local_integrity_unverified")

        if not cls._is_established_mars_crs(source.crs_identifier):
            base_segment_flags.append("unknown_crs")

        if not cls._is_known_vertical_datum(source.vertical_datum):
            base_segment_flags.append("unknown_vertical_datum")

        if not resolution.obstacle_detection_capable:
            base_segment_flags.append("coarse_resolution_for_obstacle_detection")

        if corridor_cov_fraction < 1.0:
            base_segment_flags.append("incomplete_corridor_coverage")

        segments: list[RouteSegment] = []
        near_nodata_segment_count = 0
        has_invalid_segment = False

        for idx in range(len(path_nodes) - 1):
            r_u, c_u = path_nodes[idx]
            r_v, c_v = path_nodes[idx + 1]

            lon_u, lat_u = pixel_to_geo(
                c_u,
                r_u,
                cropped_meta.min_lon,
                cropped_meta.max_lat,
                cropped_meta.deg_per_px_lon,
                cropped_meta.deg_per_px_lat,
                pixel_center=True,
            )
            lon_v, lat_v = pixel_to_geo(
                c_v,
                r_v,
                cropped_meta.min_lon,
                cropped_meta.max_lat,
                cropped_meta.deg_per_px_lon,
                cropped_meta.deg_per_px_lat,
                pixel_center=True,
            )

            u_valid_elev = not bool(nodata_mask[r_u, c_u])
            v_valid_elev = not bool(nodata_mask[r_v, c_v])

            z_u_raw = float(graph.elevation[r_u, c_u])
            z_v_raw = float(graph.elevation[r_v, c_v])
            slope_v_raw = float(graph.slope_deg[r_v, c_v])
            rough_v_raw = float(graph.roughness[r_v, c_v])

            slope_valid = not math.isnan(slope_v_raw)
            rough_valid = not math.isnan(rough_v_raw)
            seg_is_valid = bool(u_valid_elev and v_valid_elev and slope_valid and rough_valid)

            dr = r_v - r_u
            dc = c_v - c_u
            d2d = (
                graph.dist_diag
                if (dr != 0 and dc != 0)
                else (graph.dist_orth_y if dr != 0 else graph.dist_orth_x)
            )

            # Never silently convert missing/nodata values to 0.0
            elev_start_m = round(z_u_raw, 2) if u_valid_elev else None
            elev_end_m = round(z_v_raw, 2) if v_valid_elev else None
            if u_valid_elev and v_valid_elev:
                dz_raw = z_v_raw - z_u_raw
                delta_elev_m: float | None = round(dz_raw, 2)
                d3d = math.sqrt(d2d**2 + dz_raw**2)
            else:
                dz_raw = 0.0
                delta_elev_m = None
                d3d = d2d

            slope_val: float | None = round(slope_v_raw, 2) if slope_valid else None
            rough_val: float | None = round(rough_v_raw, 3) if rough_valid else None

            extra_pen = 0.0
            if penalized_edges and ((r_u, c_u), (r_v, c_v)) in penalized_edges:
                extra_pen = penalized_edges[((r_u, c_u), (r_v, c_v))]

            step_cost, _ = calculate_edge_cost(
                distance_3d=d3d,
                slope_deg=slope_v_raw if slope_valid else 0.0,
                roughness=rough_v_raw if rough_valid else 0.0,
                delta_z=dz_raw,
                mode=mode,
                is_nodata=not seg_is_valid,
                extra_penalty=extra_pen,
            )

            seg_flags = list(base_segment_flags)
            if not seg_is_valid:
                has_invalid_segment = True
                if "invalid_or_nodata_segment" not in seg_flags:
                    seg_flags.append("invalid_or_nodata_segment")

            is_near_nodata = bool(
                near_nodata_mask[r_u, c_u] or near_nodata_mask[r_v, c_v]
            )
            if is_near_nodata:
                near_nodata_segment_count += 1
                if "near_nodata_boundary" not in seg_flags:
                    seg_flags.append("near_nodata_boundary")

            segments.append(
                RouteSegment(
                    segment_index=idx,
                    from_coord=MarsCoordinate(lon=round(lon_u, 6), lat=round(lat_u, 6)),
                    to_coord=MarsCoordinate(lon=round(lon_v, 6), lat=round(lat_v, 6)),
                    step_distance_meters=round(d3d, 2),
                    elevation_start_m=elev_start_m,
                    elevation_end_m=elev_end_m,
                    delta_elevation_m=delta_elev_m,
                    slope_deg=slope_val,
                    roughness=rough_val,
                    is_valid_data=seg_is_valid,
                    segment_cost=round(step_cost, 2) if not math.isinf(step_cost) else 1e9,
                    quality_flags=seg_flags,
                )
            )

        route_flags = list(base_segment_flags)
        if near_nodata_segment_count > 0 and "near_nodata_boundary" not in route_flags:
            route_flags.append("near_nodata_boundary")
        if (has_invalid_segment or route_cov_fraction < 1.0) and "invalid_or_nodata_segment" not in route_flags:
            route_flags.append("invalid_or_nodata_segment")

        coverage = CoverageEvidence(
            route_sample_count=route_sample_count,
            valid_route_sample_count=valid_route_sample_count,
            invalid_route_sample_count=invalid_route_sample_count,
            route_data_coverage_fraction=route_cov_fraction,
            corridor_total_cells=corridor_total_cells,
            corridor_valid_cells=corridor_valid_cells,
            corridor_invalid_cells=corridor_invalid_cells,
            corridor_data_coverage_fraction=corridor_cov_fraction,
            near_nodata_segment_count=near_nodata_segment_count,
        )

        return segments, coverage, route_flags

    @staticmethod
    def classify_quality_tier(
        source: SourceEvidence,
        coverage: CoverageEvidence,
        resolution: ResolutionAssessment,
    ) -> tuple[EvidenceQualityTier, str]:
        """
        Deterministically classifies terrain evidence quality into one of:
        `high`, `moderate`, `low`, or `unverified` using conservative rules.
        Never uses arbitrary numeric weights or probabilities.
        """
        # 1. UNVERIFIED rules (most conservative)
        if source.is_synthetic or source.data_mode in (
            "synthetic_test_fixture",
            "synthetic_fallback",
        ):
            return (
                EvidenceQualityTier.UNVERIFIED,
                "Assigned 'unverified' tier because the route was computed on procedurally "
                "synthesized terrain ('Synthetic Jezero Crater Terrain Model') rather than "
                "verified spacecraft observation data.",
            )

        if source.local_integrity_verified is False:
            return (
                EvidenceQualityTier.UNVERIFIED,
                "Assigned 'unverified' tier because local GeoTIFF SHA-256 integrity verification "
                "failed against its provenance sidecar.",
            )

        if (
            source.validation_status == "valid_numeric_raster_unverified_source"
            or not source.product_id
            or not source.official_source_url
        ):
            return (
                EvidenceQualityTier.UNVERIFIED,
                "Assigned 'unverified' tier because the loaded numeric raster comes from an "
                "unverified local source without an authenticated NASA/ESA/USGS product identity "
                "or cryptographic provenance chain.",
            )

        # 2. LOW rules (established planetary source, but material coverage/nodata/metadata issues)
        low_reasons: list[str] = []
        if (
            coverage.route_data_coverage_fraction < 1.0
            or coverage.invalid_route_sample_count > 0
        ):
            low_reasons.append(
                f"incomplete route observation coverage ({coverage.valid_route_sample_count}/"
                f"{coverage.route_sample_count} valid route samples, "
                f"coverage={coverage.route_data_coverage_fraction:.4f})"
            )

        if coverage.corridor_data_coverage_fraction < 0.95:
            low_reasons.append(
                f"material nodata gaps in the mission corridor "
                f"(corridor coverage={coverage.corridor_data_coverage_fraction:.4f} < 0.95 threshold)"
            )

        if coverage.near_nodata_segment_count > 0:
            low_reasons.append(
                f"{coverage.near_nodata_segment_count} route segment(s) pass directly along a "
                "nodata boundary in the cropped corridor"
            )

        if (
            not EvidenceService._is_established_mars_crs(source.crs_identifier)
            or not EvidenceService._is_known_vertical_datum(source.vertical_datum)
        ):
            low_reasons.append(
                f"missing or unconfirmed geodetic metadata (CRS='{source.crs_identifier}', "
                f"vertical_datum='{source.vertical_datum}')"
            )

        if resolution.effective_resolution_meters > 500.0:
            low_reasons.append(
                f"effective grid resolution ({resolution.effective_resolution_meters} m/px) is "
                "coarser than the 500 m/px maximum for regional route screening"
            )

        if low_reasons:
            return (
                EvidenceQualityTier.LOW,
                f"Assigned 'low' tier despite established planetary source '{source.product_id}' "
                f"due to material terrain evidence limitations: {'; '.join(low_reasons)}.",
            )

        # 3. MODERATE rules (official source & complete route coverage, but upstream checksum/local integrity unverified or minor corridor gap)
        moderate_reasons: list[str] = []
        if (
            source.validation_status != "verified_source"
            or source.source_checksum_verified is not True
        ):
            moderate_reasons.append(
                "the Jezero Crater sub-window was extracted from the official USGS HTTPS endpoint "
                "with verified local SHA-256 integrity, but the full 11.38 GB upstream archive MD5 "
                "checksum remains unverified over all source bytes"
            )

        if source.local_integrity_verified is not True:
            moderate_reasons.append(
                "local file SHA-256 integrity verification status is missing or unconfirmed "
                "(local_integrity_verified is None)"
            )

        if coverage.corridor_data_coverage_fraction < 1.0 or coverage.corridor_invalid_cells > 0:
            moderate_reasons.append(
                f"the surrounding corridor contains minor nodata cells "
                f"(corridor coverage={coverage.corridor_data_coverage_fraction:.4f}), though "
                "100% of route samples are valid and away from nodata boundaries"
            )

        if resolution.effective_resolution_meters > 250.0:
            moderate_reasons.append(
                f"effective resolution ({resolution.effective_resolution_meters} m/px) exceeds "
                "250 m/px nominal regional benchmark"
            )

        if moderate_reasons:
            return (
                EvidenceQualityTier.MODERATE,
                f"Assigned 'moderate' tier for official dataset '{source.dataset_name}' "
                f"({source.product_id}) with 100% valid route observation coverage because "
                f"{'; and '.join(moderate_reasons)}.",
            )

        # 4. Explicit HIGH verification gate: all provenance, checksum, local integrity,
        # geodetic metadata, coverage, and regional resolution criteria must be satisfied.
        is_high_eligible = (
            source.validation_status == "verified_source"
            and source.source_checksum_verified is True
            and source.local_integrity_verified is True
            and EvidenceService._is_established_mars_crs(source.crs_identifier)
            and EvidenceService._is_known_vertical_datum(source.vertical_datum)
            and coverage.route_data_coverage_fraction == 1.0
            and coverage.invalid_route_sample_count == 0
            and coverage.corridor_data_coverage_fraction == 1.0
            and coverage.corridor_invalid_cells == 0
            and coverage.near_nodata_segment_count == 0
            and resolution.effective_resolution_meters <= 250.0
        )
        if not is_high_eligible:
            return (
                EvidenceQualityTier.MODERATE,
                "Assigned 'moderate' tier because one or more mandatory high-tier verification "
                "requirements were not satisfied.",
            )

        return (
            EvidenceQualityTier.HIGH,
            f"Assigned 'high' regional terrain evidence tier: full upstream source checksum and "
            f"local SHA-256 integrity are independently verified for official product "
            f"'{source.product_id}', planetary CRS ('{source.crs_identifier}') and vertical datum "
            f"('{source.vertical_datum}') are established, 100% of route samples "
            f"({coverage.valid_route_sample_count}/{coverage.route_sample_count}) and 100% of "
            f"corridor cells ({coverage.corridor_valid_cells}/{coverage.corridor_total_cells}) "
            f"contain valid observations, and effective resolution "
            f"({resolution.effective_resolution_meters} m/px) meets regional assessment requirements "
            f"(<= 250 m/px; obstacle_detection_capable={resolution.obstacle_detection_capable}).",
        )

    @classmethod
    def build_known_limitations(
        cls,
        source: SourceEvidence,
        coverage: CoverageEvidence,
        resolution: ResolutionAssessment,
    ) -> list[str]:
        limitations: list[str] = [
            resolution.limitation_statement,
            "Route cost weights, hazard penalties, and categorical risk levels are deterministic multi-criteria decision heuristics, not empirically calibrated probabilities of rover failure or mission survival.",
        ]

        if source.is_synthetic:
            limitations.append(
                "Synthetic terrain is procedurally generated and unsuitable for real planetary navigation or operational mission risk assessment."
            )
        elif source.validation_status in (
            "verified_source",
            "official_endpoint_retrieved_checksum_unverified",
        ):
            limitations.append(
                "USGS warns of HRSC/MOLA blending seam inconsistencies and notes the global blended DEM (200 m/px nominal) was originally constructed for global thermal-modelling (THEMIS thermal inertia) rather than precision local surface navigation."
            )
            if not source.source_checksum_verified:
                limitations.append(
                    "Retrieved via HTTP range extraction from the official USGS endpoint; local GeoTIFF SHA-256 integrity is verified, but the full 11.38 GB upstream file MD5 checksum was not computed over all upstream source bytes."
                )
        elif source.validation_status == "valid_numeric_raster_unverified_source":
            limitations.append(
                "Loaded from an unverified local numerical terrain raster; authoritative NASA/ESA/USGS source provenance and product identity are not established."
            )

        if coverage.corridor_data_coverage_fraction < 1.0:
            limitations.append(
                f"Cropped mission corridor contains {coverage.corridor_invalid_cells} nodata cell(s) "
                f"(corridor coverage {coverage.corridor_data_coverage_fraction * 100.0:.2f}%)."
            )

        if coverage.near_nodata_segment_count > 0:
            limitations.append(
                f"{coverage.near_nodata_segment_count} route segment(s) pass near a nodata boundary where adjacent terrain observations are missing."
            )

        for src_lim in source.source_limitations:
            if src_lim not in limitations:
                limitations.append(src_lim)

        return limitations

    @classmethod
    def build_route_evidence_passport(
        cls,
        path_nodes: list[tuple[int, int]],
        graph: TerrainGridGraph,
        master_meta: RasterMetadata,
        cropped_meta: RasterMetadata,
        provenance: dict[str, Any],
        mode: OptimizationMode,
        penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] | None = None,
    ) -> RouteEvidencePassport:
        """
        Builds the complete `RouteEvidencePassport` for a candidate route path.
        """
        source = cls.build_source_evidence(
            master_meta=master_meta,
            provenance=provenance,
            dx_meters=graph.dx,
            dy_meters=graph.dy,
        )
        resolution = cls.build_resolution_assessment(
            is_synthetic=source.is_synthetic,
            dx_meters=graph.dx,
            dy_meters=graph.dy,
            nominal_res=source.nominal_resolution_meters,
        )
        segments, coverage, route_flags = cls.build_segments_and_coverage(
            path_nodes=path_nodes,
            graph=graph,
            cropped_meta=cropped_meta,
            mode=mode,
            source=source,
            resolution=resolution,
            penalized_edges=penalized_edges,
        )
        quality_tier, tier_explanation = cls.classify_quality_tier(
            source=source,
            coverage=coverage,
            resolution=resolution,
        )
        known_limitations = cls.build_known_limitations(
            source=source,
            coverage=coverage,
            resolution=resolution,
        )

        return RouteEvidencePassport(
            quality_tier=quality_tier,
            tier_explanation=tier_explanation,
            quality_flags=route_flags,
            source=source,
            coverage=coverage,
            resolution_assessment=resolution,
            known_limitations=known_limitations,
            segments=segments,
        )
