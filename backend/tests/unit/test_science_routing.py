import pytest
from backend.app.core.exceptions import CoordinatesOutOfBoundsError, UnreachableDestinationError
from backend.app.data.providers.synthetic import SyntheticTerrainProvider
from backend.app.schemas.coordinates import MarsCoordinate
from backend.app.schemas.mission import OptimizationMode, RouteConstraints
from backend.app.schemas.routes import RoutePlanRequest
from backend.app.services.route_service import RouteService


@pytest.fixture
def route_service():
    provider = SyntheticTerrainProvider()
    return RouteService(provider=provider)


def test_user_science_waypoint_influences_route(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.46, lat=18.42)
    # Intermediate waypoint placed off the direct line: Delta Front (77.44°E, 18.42°N)
    science_wp = MarsCoordinate(lon=77.44, lat=18.42)

    # 1. Direct plan without waypoints
    req_direct = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.BALANCED,
    )
    res_direct = route_service.plan_route(req_direct)

    # 2. Plan with explicit science waypoint
    req_wp = RoutePlanRequest(
        start=start,
        destination=dest,
        science_waypoints=[science_wp],
        mode=OptimizationMode.BALANCED,
    )
    res_wp = route_service.plan_route(req_wp)

    route_direct = res_direct.routes[0]
    route_wp = res_wp.routes[0]

    # Waypoint route must have waypoints_visited containing science_wp
    assert len(route_wp.waypoints_visited) == 1
    assert abs(route_wp.waypoints_visited[0].lon - science_wp.lon) < 1e-4

    # The geometries must differ because route_wp is guided through the waypoint
    assert route_wp.geometry.coordinates != route_direct.geometry.coordinates


def test_out_of_bounds_science_waypoint_raises(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.44, lat=18.42)
    bad_wp = MarsCoordinate(lon=120.0, lat=45.0)  # Outside Jezero pilot bounds

    req = RoutePlanRequest(
        start=start,
        destination=dest,
        science_waypoints=[bad_wp],
    )
    with pytest.raises(CoordinatesOutOfBoundsError):
        route_service.plan_route(req)


def test_science_first_mode_candidate_detour(route_service):
    start = MarsCoordinate(lon=77.40, lat=18.39)
    dest = MarsCoordinate(lon=77.45, lat=18.42)

    req_sci = RoutePlanRequest(
        start=start,
        destination=dest,
        mode=OptimizationMode.SCIENCE_FIRST,
        num_alternatives=2,
    )
    res_sci = route_service.plan_route(req_sci)

    assert len(res_sci.routes) >= 1
    primary = res_sci.routes[0]
    # Check that science score is awarded
    assert primary.summary.science_score > 0.0
    # Must enforce slope ceiling (max slope <= 22 deg)
    assert primary.summary.max_slope_deg <= 22.0
