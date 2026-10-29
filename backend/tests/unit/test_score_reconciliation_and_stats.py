import pytest
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode
from backend.app.schemas.routes import RoutePlanRequest
from backend.app.services.route_service import RouteService


@pytest.fixture
def route_service():
    provider = SyntheticTerrainProvider()
    return RouteService(provider=provider)


def test_score_reconciliation(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)

    for mode in [OptimizationMode.SAFETY_FIRST, OptimizationMode.BALANCED, OptimizationMode.SCIENCE_FIRST]:
        req = RoutePlanRequest(
            start=start,
            destination=dest,
            mode=mode,
            num_alternatives=1,
        )
        res = route_service.plan_route(req)
        primary = res.routes[0]

        breakdown = primary.cost_breakdown
        sum_components = (
            breakdown["base_distance_cost"]
            + breakdown["slope_penalty"]
            + breakdown["roughness_penalty"]
            + breakdown["hazard_penalty"]
            + breakdown["extra_penalty"]
        )

        # Sum of breakdown must match total_cost within float precision
        assert abs(sum_components - primary.total_cost) < 0.1, (
            f"Mode {mode}: sum={sum_components} != total_cost={primary.total_cost}"
        )


def test_actual_search_expansion_stats(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)

    req = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.BALANCED,
    )
    res = route_service.plan_route(req)
    stats = res.stats

    # Real nodes expanded must be a positive integer measured from search
    assert stats.nodes_expanded > 0
    # Must NOT simply equal len(coords) * 4
    num_coords = len(res.routes[0].geometry.coordinates)
    assert stats.nodes_expanded != num_coords * 4

    assert stats.search_duration_seconds > 0.0
    assert stats.grid_rows > 0
    assert stats.grid_cols > 0


def test_motion_profile_and_duration(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)

    req = RoutePlanRequest(start=start, destination=dest)
    res = route_service.plan_route(req)
    summary = res.routes[0].summary

    assert summary.motion_profile == "rover_slope_derated_0.15mps"
    assert summary.estimated_duration_hours > 0.0
    # Duration = distance / (speed * 3600). Speed is around 0.10 - 0.15 m/s.
    expected_nominal_hrs = (summary.total_distance_meters / 0.15) / 3600.0
    # Slope derating makes duration >= expected_nominal_hrs
    assert summary.estimated_duration_hours >= expected_nominal_hrs * 0.95
