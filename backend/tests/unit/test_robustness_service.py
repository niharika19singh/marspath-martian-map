"""
Unit and regression tests for MARSPath Phase 3: Route Robustness Stress Testing.

Covers all 20 mandatory requirements with dedicated test functions:
1. Identical seed and configuration produce identical scenario perturbations.
2. Different seeds produce different perturbations.
3. Original elevation arrays are never mutated.
4. Nodata masks remain unchanged.
5. Perturbation standard deviation matches the configured value within documented tolerance.
6. Spatial correlation is introduced rather than independent uncorrelated noise.
7. Actual X/Y pixel resolutions are used to derive filter scales.
8. Scenario slope and roughness are recalculated from perturbed elevation.
9. Scenario traversability is recalculated.
10. A baseline route that remains optimal has zero cost regret within numerical tolerance.
11. A baseline route that becomes infeasible is reported as infeasible.
12. Diagonal corner-cutting constraints remain enforced.
13. Route overlap is calculated correctly on known small test paths.
14. Cost regret is calculated correctly on a known test graph.
15. Retention fraction is computed from evaluated scenarios, not all requested scenarios when some fail.
16. Failed scenario results are represented honestly.
17. No uncertainty parameters are invented when robustness is disabled.
18. The existing API behavior is unchanged when `robustness_config` is absent.
19. Synthetic terrain assessments explicitly retain their unverified evidence status.
20. No probability-of-survival fields or claims are emitted.
Plus edge-case tests for untraversable endpoints, zero valid scenarios, and cell budget limits.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from pydantic import ValidationError

from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    InvalidConstraintError,
)
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.geospatial.terrain_metrics import (
    build_traversability_mask,
    compute_roughness_index,
    compute_slope_degrees,
)
from backend.app.routing.alternatives import generate_route_alternatives
from backend.app.routing.astar import astar_search
from backend.app.routing.graph_builder import TerrainGridGraph
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, RouteConstraints
from backend.app.schemas.routes import (
    EvidenceQualityTier,
    RobustnessConfig,
    RoutePlanRequest,
)
from backend.app.services.evidence_service import compute_nodata_and_boundary_masks
from backend.app.services.robustness_service import (
    MANDATORY_ROBUSTNESS_DISCLAIMER,
    RobustnessService,
    compute_cost_regret_fraction,
    compute_gaussian_filter_pixel_sigmas,
    compute_jaccard_route_overlap,
    derive_scenario_seeds,
    evaluate_path_on_scenario_graph,
    generate_perturbed_elevation,
)
from backend.app.services.route_service import RouteService


def _make_cropped_meta(rows: int = 24, cols: int = 24) -> RasterMetadata:
    deg_px = 0.00337412
    return RasterMetadata(
        width=cols,
        height=rows,
        coordinate_type="geographic",
        crs_str="IAU2000:49900",
        units="degrees",
        min_lon=77.35,
        min_lat=18.35,
        max_lon=77.35 + cols * deg_px,
        max_lat=18.35 + rows * deg_px,
        deg_per_px_lon=deg_px,
        deg_per_px_lat=deg_px,
        meters_per_px_x=190.0,
        meters_per_px_y=200.0,
        affine_transform=(deg_px, 0.0, 77.35, 0.0, -deg_px, 18.35 + rows * deg_px),
        nodata_value=-32768.0,
        vertical_datum="Synthetic Reference Datum (Mars Sphere R=3,396,190m)",
        is_synthetic=True,
    )


def test_01_identical_seed_and_config_produce_identical_perturbations():
    """Requirement 1: Identical seed and configuration produce identical scenario perturbations."""
    elev = np.full((30, 30), -2500.0, dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)

    seeds_1 = derive_scenario_seeds(master_seed=101, scenario_count=5)
    seeds_2 = derive_scenario_seeds(master_seed=101, scenario_count=5)
    assert seeds_1 == seeds_2

    p1, d1, std1 = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=2.5,
        correlation_length_m=400.0,
        dx_meters=190.0,
        dy_meters=200.0,
        scenario_seed=seeds_1[0],
    )
    p2, d2, std2 = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=2.5,
        correlation_length_m=400.0,
        dx_meters=190.0,
        dy_meters=200.0,
        scenario_seed=seeds_2[0],
    )
    assert np.array_equal(p1, p2)
    assert np.array_equal(d1, d2)
    assert std1 == std2


def test_02_different_seeds_produce_different_perturbations():
    """Requirement 2: Different seeds produce different perturbations."""
    elev = np.full((30, 30), -2500.0, dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)

    seeds_a = derive_scenario_seeds(master_seed=101, scenario_count=5)
    seeds_b = derive_scenario_seeds(master_seed=202, scenario_count=5)
    assert seeds_a != seeds_b

    pa, da, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=2.5,
        correlation_length_m=400.0,
        dx_meters=190.0,
        dy_meters=200.0,
        scenario_seed=seeds_a[0],
    )
    pb, db, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=2.5,
        correlation_length_m=400.0,
        dx_meters=190.0,
        dy_meters=200.0,
        scenario_seed=seeds_b[0],
    )
    assert not np.allclose(pa, pb)
    assert not np.allclose(da, db)


def test_03_original_elevation_arrays_are_never_mutated():
    """Requirement 3: Original elevation arrays are never mutated."""
    elev = np.linspace(-2550.0, -2450.0, 32 * 32, dtype=np.float32).reshape(32, 32)
    elev[5:9, 10:15] = -32768.0
    elev_snapshot = elev.copy()
    nodata, _ = compute_nodata_and_boundary_masks(elev, -32768.0)

    _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=4.0,
        correlation_length_m=600.0,
        dx_meters=189.8,
        dy_meters=200.0,
        scenario_seed=777,
    )
    assert np.array_equal(elev, elev_snapshot)


def test_04_nodata_masks_remain_unchanged():
    """Requirement 4: Nodata masks remain unchanged after perturbation."""
    elev = np.linspace(-2550.0, -2450.0, 32 * 32, dtype=np.float32).reshape(32, 32)
    elev[5:9, 10:15] = -32768.0
    elev[20, 22] = np.nan
    nodata_before, _ = compute_nodata_and_boundary_masks(elev, -32768.0)
    nodata_copy = nodata_before.copy()

    perturbed, delta, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata_before,
        vertical_sigma_m=5.0,
        correlation_length_m=400.0,
        dx_meters=190.0,
        dy_meters=200.0,
        scenario_seed=888,
    )
    nodata_after, _ = compute_nodata_and_boundary_masks(perturbed, -32768.0)
    assert np.array_equal(nodata_before, nodata_copy)
    assert np.array_equal(nodata_before, nodata_after)
    assert np.all(delta[nodata_before] == 0.0)
    assert np.all(perturbed[5:9, 10:15] == -32768.0)
    assert np.isnan(perturbed[20, 22])


def test_05_perturbation_standard_deviation_matches_configured_value():
    """Requirement 5: Perturbation standard deviation matches configured value within documented tolerance."""
    elev = np.full((40, 40), -2400.0, dtype=np.float32)
    elev[0:5, 0:5] = -32768.0
    nodata, _ = compute_nodata_and_boundary_masks(elev, -32768.0)
    valid = ~nodata

    for target_sigma in (0.75, 2.5, 8.0, 15.0):
        _, delta, realized_std = generate_perturbed_elevation(
            baseline_elevation=elev,
            nodata_mask=nodata,
            vertical_sigma_m=target_sigma,
            correlation_length_m=500.0,
            dx_meters=190.0,
            dy_meters=200.0,
            scenario_seed=42,
        )
        assert abs(float(np.mean(delta[valid]))) < 1e-10
        assert abs(float(np.std(delta[valid], ddof=0)) - target_sigma) < 1e-10
        assert abs(realized_std - target_sigma) < 1e-3


def test_06_spatial_correlation_is_introduced_vs_white_noise():
    """Requirement 6: Spatial correlation is introduced rather than independent uncorrelated noise."""
    elev = np.zeros((80, 80), dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)

    _, delta_corr, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=3.0,
        correlation_length_m=600.0,
        dx_meters=200.0,
        dy_meters=200.0,
        scenario_seed=12345,
    )
    corr_x = float(np.corrcoef(delta_corr[:, :-1].ravel(), delta_corr[:, 1:].ravel())[0, 1])
    corr_y = float(np.corrcoef(delta_corr[:-1, :].ravel(), delta_corr[1:, :].ravel())[0, 1])

    rng = np.random.default_rng(12345)
    white = rng.standard_normal((80, 80))
    corr_white = float(np.corrcoef(white[:, :-1].ravel(), white[:, 1:].ravel())[0, 1])

    assert corr_x > 0.75
    assert corr_y > 0.75
    assert abs(corr_white) < 0.10


def test_07_actual_xy_pixel_resolutions_derive_anisotropic_filter_scales():
    """Requirement 7: Actual X/Y pixel resolutions are used to derive filter scales."""
    sx, sy = compute_gaussian_filter_pixel_sigmas(
        correlation_length_m=600.0,
        dx_meters=150.0,
        dy_meters=300.0,
    )
    assert math.isclose(sx, 4.0, rel_tol=1e-9)
    assert math.isclose(sy, 2.0, rel_tol=1e-9)

    elev = np.zeros((80, 80), dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)
    _, delta_aniso, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=3.0,
        correlation_length_m=600.0,
        dx_meters=150.0,  # sigma_x = 4.0 px
        dy_meters=300.0,  # sigma_y = 2.0 px
        scenario_seed=12345,
    )
    corr_x = float(np.corrcoef(delta_aniso[:, :-1].ravel(), delta_aniso[:, 1:].ravel())[0, 1])
    corr_y = float(np.corrcoef(delta_aniso[:-1, :].ravel(), delta_aniso[1:, :].ravel())[0, 1])
    assert corr_x > corr_y


def test_08_scenario_slope_and_roughness_recalculated_from_perturbed_elevation():
    """Requirement 8: Scenario slope and roughness are recalculated from perturbed elevation."""
    elev = np.full((24, 24), -2500.0, dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)
    dx, dy = 190.0, 200.0

    base_slope = compute_slope_degrees(elev, dx, dy, nodata_mask=nodata)
    base_rough = compute_roughness_index(elev, kernel_size=3, nodata_mask=nodata)
    assert np.all(base_slope == 0.0)
    assert np.all(base_rough == 0.0)

    perturbed, _, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=45.0,
        correlation_length_m=200.0,
        dx_meters=dx,
        dy_meters=dy,
        scenario_seed=99,
    )
    scen_slope = compute_slope_degrees(perturbed, dx, dy, nodata_mask=nodata)
    scen_rough = compute_roughness_index(perturbed, kernel_size=3, nodata_mask=nodata)
    assert float(np.nanmax(scen_slope)) > 5.0
    assert float(np.nanmax(scen_rough)) > 0.05


def test_09_scenario_traversability_is_recalculated():
    """Requirement 9: Scenario traversability is recalculated under mission constraints."""
    elev = np.full((24, 24), -2500.0, dtype=np.float32)
    nodata = np.zeros_like(elev, dtype=bool)
    dx, dy = 190.0, 200.0

    perturbed, _, _ = generate_perturbed_elevation(
        baseline_elevation=elev,
        nodata_mask=nodata,
        vertical_sigma_m=45.0,
        correlation_length_m=200.0,
        dx_meters=dx,
        dy_meters=dy,
        scenario_seed=99,
    )
    scen_slope = compute_slope_degrees(perturbed, dx, dy, nodata_mask=nodata)
    scen_rough = compute_roughness_index(perturbed, kernel_size=3, nodata_mask=nodata)
    scen_trav = build_traversability_mask(
        scen_slope, scen_rough, max_slope_deg=5.0, max_roughness=0.5, nodata_mask=nodata
    )
    assert not np.all(scen_trav)


def test_10_baseline_route_remaining_optimal_has_zero_cost_regret():
    """Requirement 10: A baseline route that remains optimal has zero cost regret within numerical tolerance."""
    meta = _make_cropped_meta(16, 16)
    elev16 = np.full((16, 16), -2500.0, dtype=np.float32)
    slope16 = np.zeros_like(elev16)
    rough16 = np.zeros_like(elev16)
    trav16 = np.ones_like(elev16, dtype=bool)
    graph16 = TerrainGridGraph(
        elevation=elev16,
        slope_deg=slope16,
        roughness=rough16,
        traversable_mask=trav16,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    node_map: dict[str, list[tuple[int, int]]] = {}
    routes16, _ = generate_route_alternatives(
        graph=graph16,
        meta=meta,
        start_px=(2, 2),
        dest_px=(2, 12),
        requested_mode=OptimizationMode.BALANCED,
        num_alternatives=1,
        route_nodes_out=node_map,
    )
    cfg = RobustnessConfig(
        enabled=True,
        vertical_sigma_m=1e-4,
        correlation_length_m=600.0,
        scenario_count=3,
        seed=42,
        cost_regret_threshold_fraction=0.05,
    )
    assessment = RobustnessService.evaluate_route_robustness(
        config=cfg,
        cropped_elevation=elev16,
        cropped_meta=meta,
        dx_meters=200.0,
        dy_meters=200.0,
        start_px=(2, 2),
        dest_px=(2, 12),
        requested_mode=OptimizationMode.BALANCED,
        constraints=RouteConstraints(),
        baseline_routes=routes16,
        baseline_route_nodes=node_map,
        is_synthetic=True,
    )
    assert assessment is not None
    primary_rob = assessment.baseline_route_assessments[0]
    assert primary_rob.scenario_feasible_count == 3
    assert primary_rob.mean_route_overlap_fraction == 1.0
    assert primary_rob.mean_cost_regret_fraction is not None
    assert primary_rob.mean_cost_regret_fraction <= 1e-6
    assert primary_rob.baseline_route_retention_fraction == 1.0


def test_11_baseline_route_becoming_infeasible_is_reported_as_infeasible():
    """Requirement 11: A baseline route that becomes infeasible is reported as infeasible."""
    meta = _make_cropped_meta(20, 20)
    elev20 = np.full((20, 20), -2500.0, dtype=np.float32)
    slope20 = np.zeros_like(elev20)
    rough20 = np.zeros_like(elev20)
    trav20 = np.ones_like(elev20, dtype=bool)
    graph20 = TerrainGridGraph(
        elevation=elev20,
        slope_deg=slope20,
        roughness=rough20,
        traversable_mask=trav20,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    node_map: dict[str, list[tuple[int, int]]] = {}
    routes20, _ = generate_route_alternatives(
        graph=graph20,
        meta=meta,
        start_px=(10, 2),
        dest_px=(10, 17),
        requested_mode=OptimizationMode.BALANCED,
        num_alternatives=1,
        route_nodes_out=node_map,
    )
    # Central ramp at 19.9 deg so perturbations push straight baseline path over 20.0 deg limit
    elev_ramp = elev20.copy()
    for r in range(7, 14):
        for c in range(6, 14):
            elev_ramp[r, c] = -2500.0 + (c - 6) * (200.0 * math.tan(math.radians(19.9)))

    cfg = RobustnessConfig(
        enabled=True,
        vertical_sigma_m=8.0,
        correlation_length_m=300.0,
        scenario_count=4,
        seed=42,
        cost_regret_threshold_fraction=0.05,
    )
    assessment = RobustnessService.evaluate_route_robustness(
        config=cfg,
        cropped_elevation=elev_ramp,
        cropped_meta=meta,
        dx_meters=200.0,
        dy_meters=200.0,
        start_px=(10, 2),
        dest_px=(10, 17),
        requested_mode=OptimizationMode.BALANCED,
        constraints=RouteConstraints(max_slope_deg=20.0),
        baseline_routes=routes20,
        baseline_route_nodes=node_map,
        is_synthetic=True,
    )
    assert assessment is not None
    assert assessment.completed_scenario_count == 4
    primary_rob = assessment.baseline_route_assessments[0]
    assert primary_rob.scenario_infeasible_count == 4
    assert primary_rob.scenario_feasible_count == 0
    assert primary_rob.baseline_route_feasibility_fraction == 0.0
    assert primary_rob.baseline_route_retention_fraction == 0.0
    assert primary_rob.mean_cost_regret_fraction is None


def test_12_diagonal_corner_cutting_constraints_remain_enforced():
    """Requirement 12: Diagonal corner-cutting constraints remain enforced during scenario evaluation."""
    elev = np.full((10, 10), -2500.0, dtype=np.float32)
    slope = np.zeros_like(elev)
    rough = np.zeros_like(elev)
    trav = np.ones_like(elev, dtype=bool)
    trav[2, 3] = False  # Orthogonal neighbor of diagonal move (2, 2) -> (3, 3)

    scen_graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    diag_path = [(2, 2), (3, 3), (3, 4)]
    is_feas, cost, _, reason = evaluate_path_on_scenario_graph(diag_path, scen_graph)
    assert is_feas is False
    assert cost is None
    assert reason is not None and "diagonal corner-cutting" in reason.lower()


def test_13_route_overlap_calculated_correctly_on_known_small_paths():
    """Requirement 13: Route overlap (Jaccard) is calculated correctly on known small test paths."""
    path_a = [(0, 0), (0, 1), (0, 2), (0, 3)]
    path_b = [(0, 0), (0, 1), (1, 2), (0, 3)]
    b_cnt, s_cnt, sh_cnt, jaccard = compute_jaccard_route_overlap(path_a, path_b)
    assert b_cnt == 4
    assert s_cnt == 4
    assert sh_cnt == 3
    assert math.isclose(jaccard, 3.0 / 5.0, rel_tol=1e-9)

    assert compute_jaccard_route_overlap([], path_b) == (0, 4, 0, 0.0)
    assert compute_jaccard_route_overlap(path_a, []) == (4, 0, 0, 0.0)
    assert compute_jaccard_route_overlap([], []) == (0, 0, 0, 0.0)


def test_14_cost_regret_calculated_correctly_on_known_test_graph():
    """Requirement 14: Cost regret is calculated correctly on a known test graph."""
    assert math.isclose(compute_cost_regret_fraction(1150.0, 1000.0), 0.15, rel_tol=1e-12)
    assert compute_cost_regret_fraction(1000.0 - 1e-12, 1000.0) == 0.0
    assert compute_cost_regret_fraction(900.0, 1000.0) < -0.05  # Genuine negative not hidden

    elev = np.full((12, 12), -2500.0, dtype=np.float32)
    slope = np.zeros_like(elev)
    rough = np.zeros_like(elev)
    trav = np.ones_like(elev, dtype=bool)
    graph = TerrainGridGraph(
        elevation=elev,
        slope_deg=slope,
        roughness=rough,
        traversable_mask=trav,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    opt_nodes, opt_cost, _, _ = astar_search(graph, (2, 2), (2, 8))
    detour_nodes = [(2, 2), (3, 2), (4, 3), (4, 4), (4, 5), (4, 6), (4, 7), (3, 8), (2, 8)]
    feas_det, detour_cost, _, _ = evaluate_path_on_scenario_graph(detour_nodes, graph)
    assert feas_det is True
    assert detour_cost is not None and detour_cost > opt_cost
    expected_regret = (detour_cost - opt_cost) / opt_cost
    assert math.isclose(
        compute_cost_regret_fraction(detour_cost, opt_cost),
        expected_regret,
        rel_tol=1e-12,
    )


def test_15_retention_fraction_computed_from_evaluated_scenarios_when_some_fail(
    monkeypatch: pytest.MonkeyPatch,
):
    """Requirement 15: Retention fraction is computed from evaluated scenarios, not all requested scenarios when some fail."""
    meta = _make_cropped_meta(16, 16)
    elev16 = np.full((16, 16), -2500.0, dtype=np.float32)
    slope16 = np.zeros_like(elev16)
    rough16 = np.zeros_like(elev16)
    trav16 = np.ones_like(elev16, dtype=bool)
    graph16 = TerrainGridGraph(
        elevation=elev16,
        slope_deg=slope16,
        roughness=rough16,
        traversable_mask=trav16,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    node_map: dict[str, list[tuple[int, int]]] = {}
    routes16, _ = generate_route_alternatives(
        graph=graph16,
        meta=meta,
        start_px=(3, 2),
        dest_px=(3, 12),
        requested_mode=OptimizationMode.BALANCED,
        num_alternatives=1,
        route_nodes_out=node_map,
    )

    real_astar = astar_search
    call_counter = {"count": 0}

    def _flaky_astar(graph, start, goal, max_expansions=100000, penalized_edges=None):
        call_counter["count"] += 1
        if call_counter["count"] == 1:
            raise ComputationalBoundExceededError(
                "Simulated search bound failure on scenario 0",
                dimensions=(16, 16),
                max_allowed=10,
            )
        return real_astar(
            graph, start, goal, max_expansions=max_expansions, penalized_edges=penalized_edges
        )

    monkeypatch.setattr("backend.app.services.robustness_service.astar_search", _flaky_astar)

    cfg = RobustnessConfig(
        enabled=True,
        vertical_sigma_m=1e-4,
        correlation_length_m=600.0,
        scenario_count=4,
        seed=55,
        cost_regret_threshold_fraction=0.05,
    )
    assessment = RobustnessService.evaluate_route_robustness(
        config=cfg,
        cropped_elevation=elev16,
        cropped_meta=meta,
        dx_meters=200.0,
        dy_meters=200.0,
        start_px=(3, 2),
        dest_px=(3, 12),
        requested_mode=OptimizationMode.BALANCED,
        constraints=RouteConstraints(),
        baseline_routes=routes16,
        baseline_route_nodes=node_map,
        is_synthetic=True,
    )
    assert assessment is not None
    assert assessment.requested_scenario_count == 4
    assert assessment.completed_scenario_count == 3
    assert assessment.failed_scenario_count == 1

    primary_rob = assessment.baseline_route_assessments[0]
    assert primary_rob.evaluated_scenario_count == 3
    assert primary_rob.within_regret_threshold_count == 3
    assert primary_rob.baseline_route_retention_fraction == 1.0  # 3/3 evaluated, not 3/4 requested


def test_16_failed_scenario_results_represented_honestly(
    monkeypatch: pytest.MonkeyPatch,
):
    """Requirement 16: Failed scenario results are represented honestly and never treated as stability evidence."""
    meta = _make_cropped_meta(16, 16)
    elev16 = np.full((16, 16), -2500.0, dtype=np.float32)
    slope16 = np.zeros_like(elev16)
    rough16 = np.zeros_like(elev16)
    trav16 = np.ones_like(elev16, dtype=bool)
    graph16 = TerrainGridGraph(
        elevation=elev16,
        slope_deg=slope16,
        roughness=rough16,
        traversable_mask=trav16,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    node_map: dict[str, list[tuple[int, int]]] = {}
    routes16, _ = generate_route_alternatives(
        graph=graph16,
        meta=meta,
        start_px=(3, 2),
        dest_px=(3, 12),
        requested_mode=OptimizationMode.BALANCED,
        num_alternatives=1,
        route_nodes_out=node_map,
    )

    def _always_fail_astar(graph, start, goal, max_expansions=100000, penalized_edges=None):
        raise ComputationalBoundExceededError(
            "All scenarios exceeded search bound",
            dimensions=(16, 16),
            max_allowed=10,
        )

    monkeypatch.setattr("backend.app.services.robustness_service.astar_search", _always_fail_astar)

    cfg = RobustnessConfig(
        enabled=True,
        vertical_sigma_m=1.0,
        correlation_length_m=400.0,
        scenario_count=3,
        seed=42,
        cost_regret_threshold_fraction=0.05,
    )
    zero_valid = RobustnessService.evaluate_route_robustness(
        config=cfg,
        cropped_elevation=elev16,
        cropped_meta=meta,
        dx_meters=200.0,
        dy_meters=200.0,
        start_px=(3, 2),
        dest_px=(3, 12),
        requested_mode=OptimizationMode.BALANCED,
        constraints=RouteConstraints(),
        baseline_routes=routes16,
        baseline_route_nodes=node_map,
        is_synthetic=True,
    )
    assert zero_valid is not None
    assert zero_valid.completed_scenario_count == 0
    assert zero_valid.failed_scenario_count == 3
    for s_res in zero_valid.scenario_results:
        assert s_res.scenario_status == "failed_computational_bound"
        assert s_res.scenario_optimal_cost is None
        assert s_res.error_reason is not None

    z_rob = zero_valid.baseline_route_assessments[0]
    assert z_rob.evaluated_scenario_count == 0
    assert z_rob.baseline_route_retention_fraction == 0.0
    assert z_rob.baseline_route_feasibility_fraction == 0.0
    assert z_rob.mean_route_overlap_fraction is None
    assert z_rob.mean_cost_regret_fraction is None


def test_17_no_uncertainty_parameters_invented_when_disabled_or_omitted():
    """Requirement 17: No uncertainty parameters are invented when robustness is disabled or incomplete."""
    disabled_cfg = RobustnessConfig(enabled=False)
    assert disabled_cfg.vertical_sigma_m is None
    assert disabled_cfg.correlation_length_m is None
    assert RobustnessService.validate_config(disabled_cfg) is False
    assert RobustnessService.validate_config(None) is False

    with pytest.raises(ValidationError, match="vertical_sigma_m"):
        RobustnessConfig(enabled=True, correlation_length_m=400.0)

    with pytest.raises(ValidationError, match="correlation_length_m"):
        RobustnessConfig(enabled=True, vertical_sigma_m=2.0)

    bypassed = RobustnessConfig.model_construct(
        enabled=True,
        vertical_sigma_m=None,
        correlation_length_m=400.0,
        scenario_count=5,
        seed=42,
        cost_regret_threshold_fraction=0.05,
    )
    with pytest.raises(InvalidConstraintError, match="vertical_sigma_m"):
        RobustnessService.validate_config(bypassed)


def test_18_existing_api_behavior_unchanged_when_robustness_config_absent():
    """Requirement 18: Existing API behavior is unchanged when robustness_config is absent."""
    provider = SyntheticTerrainProvider()
    service = RouteService(provider=provider)

    req_default = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.44, lat=18.42),
        mode=OptimizationMode.BALANCED,
    )
    resp_default = service.plan_route(req_default)
    assert resp_default.robustness_assessment is None
    assert len(resp_default.routes) == 1
    assert resp_default.routes[0].summary.total_distance_meters > 0


def test_19_synthetic_terrain_assessments_retain_unverified_evidence_status():
    """Requirement 19: Synthetic terrain assessments explicitly retain their unverified evidence status."""
    provider = SyntheticTerrainProvider()
    service = RouteService(provider=provider)

    req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.44, lat=18.42),
        mode=OptimizationMode.BALANCED,
        num_alternatives=2,
        robustness_config=RobustnessConfig(
            enabled=True,
            vertical_sigma_m=2.0,
            correlation_length_m=400.0,
            scenario_count=3,
            seed=42,
            cost_regret_threshold_fraction=0.05,
        ),
    )
    resp = service.plan_route(req)
    assert resp.robustness_assessment is not None
    rob = resp.robustness_assessment
    assert resp.routes[0].evidence_passport is not None
    assert resp.routes[0].evidence_passport.quality_tier == EvidenceQualityTier.UNVERIFIED
    assert rob.baseline_quality_tier == EvidenceQualityTier.UNVERIFIED
    assert rob.baseline_is_synthetic is True
    assert rob.baseline_data_mode == "synthetic_test_fixture"
    assert any("unverified" in lim.lower() for lim in rob.known_limitations)


def test_20_no_probability_of_survival_fields_or_claims_emitted():
    """Requirement 20: No probability-of-survival fields or claims are emitted."""
    provider = SyntheticTerrainProvider()
    service = RouteService(provider=provider)

    req = RoutePlanRequest(
        start=MarsCoordinate(lon=77.40, lat=18.39),
        destination=MarsCoordinate(lon=77.44, lat=18.42),
        mode=OptimizationMode.BALANCED,
        robustness_config=RobustnessConfig(
            enabled=True,
            vertical_sigma_m=1.5,
            correlation_length_m=400.0,
            scenario_count=3,
            seed=42,
        ),
    )
    resp = service.plan_route(req)
    assert resp.robustness_assessment is not None
    rob = resp.robustness_assessment

    assert rob.scientific_disclaimer == MANDATORY_ROBUSTNESS_DISCLAIMER
    assert rob.uncertainty_assumptions.parameters_are_user_assumed_not_measured_dem_error is True
    assert rob.uncertainty_assumptions.source_uncertainty_metadata_available is False

    serialized = json.dumps(rob.model_dump(mode="json")).lower()
    for forbidden_term in (
        "survival_probability",
        "probability_of_survival",
        "mission_success_probability",
        "% rover survival",
        "% route safety",
        "calibrated_confidence",
    ):
        assert forbidden_term not in serialized


def test_21_untraversable_endpoint_and_cell_budget_enforcement():
    """Verifies start/destination becoming untraversable in scenarios and max_cells budget enforcement."""
    meta = _make_cropped_meta(16, 16)
    elev16 = np.full((16, 16), -2500.0, dtype=np.float32)
    slope16 = np.zeros_like(elev16)
    rough16 = np.zeros_like(elev16)
    trav16 = np.ones_like(elev16, dtype=bool)
    graph16 = TerrainGridGraph(
        elevation=elev16,
        slope_deg=slope16,
        roughness=rough16,
        traversable_mask=trav16,
        dx_meters=200.0,
        dy_meters=200.0,
        mode=OptimizationMode.BALANCED,
    )
    node_map: dict[str, list[tuple[int, int]]] = {}
    routes16, _ = generate_route_alternatives(
        graph=graph16,
        meta=meta,
        start_px=(2, 2),
        dest_px=(2, 12),
        requested_mode=OptimizationMode.BALANCED,
        num_alternatives=1,
        route_nodes_out=node_map,
    )
    cfg = RobustnessConfig(
        enabled=True,
        vertical_sigma_m=1.0,
        correlation_length_m=400.0,
        scenario_count=3,
        seed=42,
    )

    # 1. Cell budget exceeded
    with pytest.raises(ComputationalBoundExceededError):
        RobustnessService.evaluate_route_robustness(
            config=cfg,
            cropped_elevation=elev16,
            cropped_meta=meta,
            dx_meters=200.0,
            dy_meters=200.0,
            start_px=(2, 2),
            dest_px=(2, 12),
            requested_mode=OptimizationMode.BALANCED,
            constraints=RouteConstraints(),
            baseline_routes=routes16,
            baseline_route_nodes=node_map,
            max_cells=100,  # 16x16 = 256 > 100
        )

    # 2. Start cell on a steep local pinnacle so scenario traversability marks start untraversable
    elev_steep_start = elev16.copy()
    elev_steep_start[2, 2] = -2300.0  # +200m spike at start -> >20 deg slope in all scenarios
    assessment = RobustnessService.evaluate_route_robustness(
        config=cfg,
        cropped_elevation=elev_steep_start,
        cropped_meta=meta,
        dx_meters=200.0,
        dy_meters=200.0,
        start_px=(2, 2),
        dest_px=(2, 12),
        requested_mode=OptimizationMode.BALANCED,
        constraints=RouteConstraints(max_slope_deg=20.0),
        baseline_routes=routes16,
        baseline_route_nodes=node_map,
        is_synthetic=True,
    )
    assert assessment is not None
    assert assessment.completed_scenario_count == 0
    assert assessment.failed_scenario_count == 3
    for s_res in assessment.scenario_results:
        assert s_res.scenario_status == "failed_untraversable_endpoint"
        assert s_res.baseline_route_results[0].feasible is False
