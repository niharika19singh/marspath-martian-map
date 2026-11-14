"""Mars Conditions, Terrain Shadows, Climate, MEDA, and Rover Replay API router."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.app.conditions.climate import (
    evaluate_modelled_climatology,
    find_comparable_meda_observation,
)
from backend.app.conditions.mars24 import compute_mars24
from backend.app.conditions.mission_clock import evaluate_route_mission_clock
from backend.app.conditions.rover_replay import get_rover_replay_service
from backend.app.conditions.terrain_shadows import get_dem_shadow_analyzer

router = APIRouter(tags=["Mars Conditions & Time Machine"])


def _metric(
    value: Any,
    unit: str,
    kind: str,
    source: str,
    status: str = "VALID",
) -> dict[str, Any]:
    return {
        "value": value,
        "unit": unit,
        "kind": kind,
        "source": source,
        "status": status,
    }


class MissionClockRequest(BaseModel):
    """Request schema for evaluating the Mars24 Route Mission Clock on a polyline."""

    coordinates: list[list[float]] = Field(..., min_length=2)
    departure_utc: str | None = Field(default="2026-06-15T08:00:00Z")
    base_speed_m_s: float = Field(default=1.1111, gt=0.01, le=20.0)
    stop_durations_minutes: list[float] | None = Field(default=None)
    default_waypoint_stop_minutes: float = Field(default=15.0, ge=0.0, le=480.0)
    waypoint_coords: list[tuple[float, float]] | None = Field(default=None)
    include_return_leg: bool = Field(default=True)
    return_time_multiplier: float = Field(default=1.0, gt=0.1, le=10.0)
    max_eva_duration_hours: float = Field(default=8.0, gt=0.5, le=72.0)


@router.get("/conditions")
def get_mars_conditions(
    lat: float = Query(default=18.4447, description="Planetocentric latitude in degrees [-90, 90]"),
    lon: float = Query(default=77.4508, description="Positive-east longitude in degrees [-180, 360]"),
    utc: str | None = Query(default=None, description="ISO-8601 UTC timestamp (defaults to now)"),
    sol: int | None = Query(default=None, description="Optional Mars 2020 Sol override for rover replay"),
) -> dict[str, Any]:
    """Compute canonical Mars24 solar geometry, DEM terrain shadows, climatology, MEDA, and rover replay."""
    if not (-90.0 <= lat <= 90.0):
        raise HTTPException(
            status_code=422,
            detail=f"Latitude must be between -90 and +90 degrees (got {lat}).",
        )
    if not (-180.0 <= lon <= 360.0):
        raise HTTPException(
            status_code=422,
            detail=f"Longitude must be between -180 and +360 degrees (got {lon}).",
        )

    try:
        m24 = compute_mars24(latitude_deg=lat, longitude_east_deg=lon, utc_time=utc)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid UTC timestamp '{utc}': {exc}",
        ) from exc

    shadow_analyzer = get_dem_shadow_analyzer()
    shadow = shadow_analyzer.evaluate_shadow(
        latitude_deg=lat,
        longitude_east_deg=lon,
        solar_elevation_deg=m24.solar_elevation_deg,
        solar_azimuth_deg=m24.solar_azimuth_deg,
    )

    climatology = evaluate_modelled_climatology(
        latitude_deg=lat,
        longitude_east_deg=lon,
        ls_deg=m24.ls_deg,
        ltst_hours=m24.ltst_hours,
        elevation_m=shadow.observer_elevation_m,
    )

    meda = find_comparable_meda_observation(
        latitude_deg=lat,
        longitude_east_deg=lon,
        ls_deg=m24.ls_deg,
        ltst_hours=m24.ltst_hours,
        requested_sol=sol if sol is not None else m24.perseverance_mission_sol,
    )

    replay = get_rover_replay_service().get_replay_state(
        utc_time=m24.utc_iso if sol is None else None,
        sol=sol,
    )

    m24_src = "NASA GISS Mars24 (Allison & McEwen 2000; IERS Leap-Second TT Table)"
    dem_src = f"USGS MOLA-HRSC 200m DEM ({shadow.dem_source_id})"
    clim_src = climatology["source"]
    meda_src = meda["source"]
    dem_status = "VALID" if shadow.has_dem_coverage else "INSUFFICIENT_COVERAGE"

    metrics = {
        "mars_sol_date": _metric(m24.msd, "sol", "astronomical_exact", m24_src),
        "coordinated_mars_time": _metric(m24.mtc_hms, "HH:MM:SS", "astronomical_exact", m24_src),
        "local_mean_solar_time": _metric(m24.lmst_hms, "HH:MM:SS", "astronomical_exact", m24_src),
        "local_true_solar_time": _metric(m24.ltst_hms, "HH:MM:SS", "astronomical_exact", m24_src),
        "local_true_solar_time_hours": _metric(m24.ltst_hours, "hours", "astronomical_exact", m24_src),
        "solar_longitude_ls": _metric(m24.ls_deg, "deg", "astronomical_exact", m24_src),
        "equation_of_time": _metric(m24.eot_hours, "hours", "astronomical_exact", m24_src),
        "solar_declination": _metric(m24.solar_declination_deg, "deg", "astronomical_exact", m24_src),
        "heliocentric_distance": _metric(m24.heliocentric_distance_au, "AU", "astronomical_exact", m24_src),
        "solar_elevation": _metric(m24.solar_elevation_deg, "deg", "astronomical_exact", m24_src),
        "solar_azimuth": _metric(m24.solar_azimuth_deg, "deg", "astronomical_exact", m24_src),
        "sunrise_ltst": _metric(
            m24.sunrise_ltst_hours,
            "hours",
            "astronomical_exact",
            m24_src,
            "VALID" if m24.sunrise_ltst_hours is not None else m24.polar_day_state,
        ),
        "sunset_ltst": _metric(
            m24.sunset_ltst_hours,
            "hours",
            "astronomical_exact",
            m24_src,
            "VALID" if m24.sunset_ltst_hours is not None else m24.polar_day_state,
        ),
        "daylight_duration_mars_hours": _metric(
            m24.daylight_mars_hours, "mars_hours", "astronomical_exact", m24_src
        ),
        "daylight_duration_earth_hours": _metric(
            m24.daylight_earth_hours, "earth_hours", "astronomical_exact", m24_src
        ),
        "tt_minus_utc": _metric(m24.tt_minus_utc_s, "s", "astronomical_exact", m24_src),
        "terrain_shadow_state": _metric(
            shadow.shadow_state, "state", "dem_derived", dem_src, dem_status
        ),
        "max_horizon_obstruction": _metric(
            shadow.max_horizon_angle_deg, "deg", "dem_derived", dem_src, dem_status
        ),
        "effective_solar_clearance": _metric(
            shadow.effective_solar_clearance_deg, "deg", "dem_derived", dem_src, dem_status
        ),
        "observer_elevation": _metric(
            shadow.observer_elevation_m, "m", "dem_derived", dem_src, dem_status
        ),
        "surface_incidence_angle": _metric(
            shadow.surface_incidence_deg, "deg", "dem_derived", dem_src, dem_status
        ),
        "modelled_air_temperature": _metric(
            climatology["air_temperature_c"], "°C", "modelled_climatology", clim_src, "MODELLED"
        ),
        "modelled_ground_temperature": _metric(
            climatology["ground_temperature_c"], "°C", "modelled_climatology", clim_src, "MODELLED"
        ),
        "modelled_pressure": _metric(
            climatology["pressure_pa"], "Pa", "modelled_climatology", clim_src, "MODELLED"
        ),
        "modelled_wind_speed": _metric(
            climatology["wind_speed_m_s"], "m/s", "modelled_climatology", clim_src, "MODELLED"
        ),
        "modelled_dust_tau": _metric(
            climatology["dust_optical_depth_880nm"], "tau_880nm", "modelled_climatology", clim_src, "MODELLED"
        ),
        "measured_meda_air_temperature": _metric(
            meda["nearest_record"]["air_temp_c"],
            "°C",
            "measured_observation",
            meda_src,
            "MEASURED_ARCHIVE" if meda["is_directly_comparable"] else "NOT_COMPARABLE",
        ),
        "measured_meda_pressure": _metric(
            meda["nearest_record"]["pressure_pa"],
            "Pa",
            "measured_observation",
            meda_src,
            "MEASURED_ARCHIVE" if meda["is_directly_comparable"] else "NOT_COMPARABLE",
        ),
    }

    return {
        "status": "ok",
        "query": {
            "lat": lat,
            "lon": lon,
            "utc": m24.utc_iso,
            "requested_sol": sol,
        },
        "metrics": metrics,
        "mars24": asdict(m24),
        "terrain_shadow": asdict(shadow),
        "modelled_climatology": climatology,
        "measured_meda": meda,
        "rover_replay": replay,
    }


@router.get("/conditions/rover-replay")
def get_rover_replay(
    utc: str | None = Query(default=None, description="ISO-8601 UTC timestamp"),
    sol: int | None = Query(default=None, description="Mars 2020 mission Sol"),
) -> dict[str, Any]:
    """Retrieve historical Perseverance traverse replay state for the Mars Time Machine."""
    return get_rover_replay_service().get_replay_state(utc_time=utc, sol=sol)


@router.post("/conditions/mission-clock")
def compute_mission_clock_endpoint(req: MissionClockRequest) -> dict[str, Any]:
    """Compute segment-by-segment Mars24 Mission Clock and daylight/shadow exposure for a route."""
    try:
        return evaluate_route_mission_clock(
            coordinates=req.coordinates,
            departure_utc=req.departure_utc,
            base_speed_m_s=req.base_speed_m_s,
            stop_durations_minutes=req.stop_durations_minutes,
            default_waypoint_stop_minutes=req.default_waypoint_stop_minutes,
            waypoint_coords=req.waypoint_coords,
            include_return_leg=req.include_return_leg,
            return_time_multiplier=req.return_time_multiplier,
            max_eva_duration_hours=req.max_eva_duration_hours,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
