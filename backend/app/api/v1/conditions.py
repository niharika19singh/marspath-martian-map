"""Mars Conditions, Terrain Shadows, Climate, MEDA, and Rover Replay API router."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import numpy as np
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
from backend.app.data.providers.hirise import get_shared_hirise_provider
from backend.app.data.providers.mola_hrsc import get_shared_mola_provider
from backend.app.geospatial.crs import geo_to_pixel
from backend.app.geospatial.terrain_metrics import compute_slope_degrees

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
    daylight_buffer_minutes: float = Field(default=0.0, ge=0.0, le=120.0)


@router.get("/conditions")
def get_mars_conditions(
    lat: float = Query(default=18.4447, description="Planetocentric latitude in degrees [-90, 90]"),
    lon: float = Query(default=77.4508, description="Positive-east longitude in degrees [-180, 360]"),
    utc: str | None = Query(default=None, description="Timezone-aware ISO-8601 UTC timestamp (defaults to now)"),
    sol: int | None = Query(default=None, description="Optional Mars 2020 Sol override for rover replay"),
) -> dict[str, Any]:
    """Compute canonical Mars24 solar geometry, DEM terrain metrics, and rover replay."""
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise HTTPException(
            status_code=422,
            detail="Latitude and longitude coordinates must be finite numerical values.",
        )
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

    # Normalize longitude according to Mars IAU2000 positive-east convention [0, 360)
    lon_normalized = lon % 360.0
    if lon_normalized < 0.0:
        lon_normalized += 360.0

    try:
        m24 = compute_mars24(latitude_deg=lat, longitude_east_deg=lon_normalized, utc_time=utc)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid UTC timestamp '{utc}': {exc}",
        ) from exc

    shadow_analyzer = get_dem_shadow_analyzer()
    shadow = shadow_analyzer.evaluate_shadow(
        latitude_deg=lat,
        longitude_east_deg=lon_normalized,
        solar_elevation_deg=m24.solar_elevation_deg,
        solar_azimuth_deg=m24.solar_azimuth_deg,
    )

    climatology = evaluate_modelled_climatology(
        latitude_deg=lat,
        longitude_east_deg=lon_normalized,
        ls_deg=m24.ls_deg,
        ltst_hours=m24.ltst_hours,
        elevation_m=shadow.observer_elevation_m,
    )

    meda = find_comparable_meda_observation(
        latitude_deg=lat,
        longitude_east_deg=lon_normalized,
        ls_deg=m24.ls_deg,
        ltst_hours=m24.ltst_hours,
        requested_sol=sol if sol is not None else m24.perseverance_mission_sol,
    )

    replay = get_rover_replay_service().get_replay_state(
        utc_time=m24.utc_iso if sol is None else None,
        sol=sol,
    )

    # Deterministic terrain point sampling from active DEM providers
    active_dataset = None
    active_doi = None
    active_res = None
    elevation_val: float | None = None
    slope_val: float | None = None
    terrain_status = "OUT_OF_COVERAGE"
    terrain_reason: str | None = None
    provenance_info: dict[str, Any] | None = None

    try:
        selected_raster = None
        selected_meta = None

        # 1. Check localized 1 m HiRISE DTM first
        hirise_p = get_shared_hirise_provider()
        if hirise_p is not None and getattr(hirise_p, "enabled", False):
            v_res = hirise_p.validate_hirise_raster()
            if v_res.is_valid and v_res.raster is not None:
                h_meta = v_res.raster.metadata
                if (h_meta.min_lon <= lon_normalized <= h_meta.max_lon) and (h_meta.min_lat <= lat <= h_meta.max_lat):
                    selected_raster = v_res.raster
                    selected_meta = h_meta
                    active_dataset = "USGS Mars 2020 HiRISE DTM"
                    active_doi = "10.5066/P9REJ9JN"
                    active_res = 1.0

        # 2. Fall back to regional MOLA-HRSC 200 m blended DEM
        if selected_raster is None:
            mola_p = get_shared_mola_provider()
            m_raster = mola_p.get_dem_raster()
            m_meta = m_raster.metadata
            if (m_meta.min_lon <= lon_normalized <= m_meta.max_lon) and (m_meta.min_lat <= lat <= m_meta.max_lat):
                selected_raster = m_raster
                selected_meta = m_meta
                active_dataset = "USGS MOLA-HRSC 200m Blended DEM"
                active_doi = "10.5066/P907276M"
                active_res = 200.0

        if selected_raster is not None and selected_meta is not None:
            col, row = geo_to_pixel(
                lon_normalized,
                lat,
                selected_meta.min_lon,
                selected_meta.max_lat,
                selected_meta.deg_per_px_lon,
                selected_meta.deg_per_px_lat,
                pixel_center=True,
            )
            H, W = selected_raster.data.shape
            if 0 <= row < H and 0 <= col < W:
                raw_elev = selected_raster.get_elevation_at_pixel(col, row)
                if not math.isnan(raw_elev) and math.isfinite(raw_elev):
                    elevation_val = round(raw_elev, 2)
                    terrain_status = "VALID"
                    # Compute slope using 3x3 patch with physical cell dimensions
                    r0 = max(0, row - 1)
                    r1 = min(H, row + 2)
                    c0 = max(0, col - 1)
                    c1 = min(W, col + 2)
                    patch = selected_raster.data[r0:r1, c0:c1].astype(np.float64)
                    dx = selected_meta.meters_per_px_x
                    dy = selected_meta.meters_per_px_y
                    slope_patch = compute_slope_degrees(patch, dx, dy)
                    loc_slope = float(slope_patch[row - r0, col - c0])
                    if not math.isnan(loc_slope) and math.isfinite(loc_slope):
                        slope_val = round(loc_slope, 2)
                    provenance_info = {
                        "dataset_name": active_dataset,
                        "doi": active_doi,
                        "resolution_meters": active_res,
                        "crs": "IAU2000:49900",
                        "pixel_x": col,
                        "pixel_y": row,
                        "grid_dimensions": [W, H],
                    }
                else:
                    terrain_status = "NODATA_MASKED"
                    terrain_reason = "Target coordinate falls on a masked NoData cell in the active DEM."
            else:
                terrain_status = "OUT_OF_COVERAGE"
                terrain_reason = "Pixel indices mapped outside the active DEM raster bounds."
        else:
            terrain_status = "OUT_OF_COVERAGE"
            terrain_reason = "Target coordinates lie outside the spatial coverage of the loaded DEM providers."
    except Exception as dem_exc:
        terrain_status = "UNAVAILABLE"
        terrain_reason = f"DEM point sampling error: {dem_exc}"

    m24_src = "NASA GISS Mars24 (Allison & McEwen 2000; IERS Leap-Second TT Table)"
    dem_src = active_dataset or f"USGS MOLA-HRSC 200m DEM ({shadow.dem_source_id})"
    clim_src = climatology["source"]
    meda_src = meda["source"]
    dem_status = "VALID" if shadow.has_dem_coverage else "INSUFFICIENT_COVERAGE"

    # Sunlight day / twilight / night classification
    daylight_state = (
        "DAYLIGHT"
        if m24.solar_elevation_deg > 0
        else ("TWILIGHT" if m24.solar_elevation_deg > -6.0 else "NIGHT")
    )

    sun_block = {
        "local_true_solar_time": _metric(m24.ltst_hms, "HH:MM:SS", "computed", m24_src, "VALID"),
        "local_true_solar_time_hours": _metric(m24.ltst_hours, "hours", "computed", m24_src, "VALID"),
        "solar_longitude_ls": _metric(m24.ls_deg, "deg", "computed", m24_src, "VALID"),
        "solar_elevation": _metric(m24.solar_elevation_deg, "deg", "computed", m24_src, "VALID"),
        "solar_azimuth": _metric(m24.solar_azimuth_deg, "deg", "computed", m24_src, "VALID"),
        "solar_elevation_type": "geometric",
        "solar_declination": _metric(m24.solar_declination_deg, "deg", "computed", m24_src, "VALID"),
        "daylight_state": _metric(daylight_state, "state", "computed", m24_src, "VALID"),
        "mars_sol_date": _metric(m24.msd, "sol", "computed", m24_src, "VALID"),
        "coordinated_mars_time": _metric(m24.mtc_hms, "HH:MM:SS", "computed", m24_src, "VALID"),
    }

    terrain_block = {
        "elevation": _metric(elevation_val, "m", "derived", active_dataset or "None", terrain_status),
        "slope": _metric(slope_val, "deg", "derived", active_dataset or "None", terrain_status),
        "elevation_m": elevation_val,
        "slope_deg": slope_val,
        "dataset": active_dataset,
        "doi": active_doi,
        "resolution_m": active_res,
        "provenance": provenance_info,
        "status": terrain_status,
        "reason": terrain_reason,
    }

    rover_block = {
        "rover_id": "perseverance",
        "status": replay.get("archive_status", "VALID"),
        "latest_published_waypoint": replay.get("active_waypoint"),
        "sol": replay.get("requested_sol"),
        "distance_traversed_m": (
            replay.get("active_waypoint", {}).get("cumulative_odometry_m", 0.0)
            if replay.get("active_waypoint")
            else 0.0
        ),
        "position_available": replay.get("position_available", False),
        "position_interpolated": False,
        "is_post_archive": replay.get("archive_status") == "POST_ARCHIVE_CUTOFF",
        "explanation": replay.get("explanation"),
        "archive_sol_range": replay.get("archive_sol_range"),
    }

    atmosphere_block = {
        "temperature": {
            "value": None,
            "unit": "°C",
            "kind": "measured",
            "source": None,
            "status": "UNAVAILABLE",
            "reason": "No in-situ atmospheric sensor or calibrated real-time atmospheric model connected at target coordinate.",
        },
        "pressure": {
            "value": None,
            "unit": "Pa",
            "kind": "measured",
            "source": None,
            "status": "UNAVAILABLE",
            "reason": "No in-situ atmospheric sensor or calibrated real-time atmospheric model connected at target coordinate.",
        },
        "status": "UNAVAILABLE",
        "reason": "In-situ atmospheric telemetry is currently marked unavailable pending direct atmospheric sensor stream connection.",
    }

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
            "lon": lon_normalized,
            "lon_raw": lon,
            "utc": m24.utc_iso,
            "requested_sol": sol,
        },
        "sun": sun_block,
        "terrain": terrain_block,
        "rover": rover_block,
        "atmosphere": atmosphere_block,
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
            daylight_buffer_minutes=req.daylight_buffer_minutes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
