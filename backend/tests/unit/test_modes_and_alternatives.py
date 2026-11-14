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


def test_safety_first_vs_balanced_modes(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)

    req_balanced = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.BALANCED,
        num_alternatives=1,
    )
    req_safety = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.SAFETY_FIRST,
        num_alternatives=1,
    )

    res_balanced = route_service.plan_route(req_balanced)
    res_safety = route_service.plan_route(req_safety)

    r_bal = res_balanced.routes[0]
    r_saf = res_safety.routes[0]

    # Safety first must enforce lower or equal average slope and roughness
    assert r_saf.summary.average_slope_deg <= r_bal.summary.average_slope_deg + 0.5
    assert r_saf.summary.max_slope_deg <= 14.0  # Safety mode slope cap


def test_multi_alternative_generation(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)

    req = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.BALANCED,
        num_alternatives=2,
    )
    res = route_service.plan_route(req)

    assert len(res.routes) >= 2
    primary = res.routes[0]
    secondary = res.routes[1]

    assert primary.route_id != secondary.route_id
    assert primary.score_rank == 1
    assert secondary.score_rank == 2
    # Verify both have valid GeoJSON LineString coordinates
    assert len(primary.geometry.coordinates) > 5
    assert len(secondary.geometry.coordinates) > 5
