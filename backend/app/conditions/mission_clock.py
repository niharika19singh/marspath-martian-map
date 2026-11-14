"""Route Mission Clock and Outbound/Return Daylight Accounting Engine.

Evaluates a planned traverse against NASA GISS Mars24 solar geometry and DEM terrain
shadows along every segment from departure UTC through outbound completion and optional
return leg, without silently modifying the underlying A*/Dijkstra terrain cost function.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from backend.app.conditions.mars24 import MARS_SOL_RATIO, compute_mars24, parse_utc_datetime
from backend.app.conditions.terrain_shadows import get_dem_shadow_analyzer


@dataclass(frozen=True)
class SegmentClockEntry:
    """Per-segment timing, solar geometry, and shadow state along a traverse."""

    segment_index: int
    leg: str  # "OUTBOUND" | "RETURN"
    start_lon: float
    start_lat: float
    end_lon: float
    end_lat: float
    segment_distance_m: float
    cumulative_distance_m: float
    slope_deg: float
    effective_speed_m_s: float
    walking_duration_s: float
    stop_duration_s: float
    cumulative_duration_s: float
    arrival_utc: str
    arrival_ltst_hours: float
    arrival_ltst_hms: str
    solar_elevation_deg: float
    solar_azimuth_deg: float
    shadow_state: str
    is_darkness: bool
    is_terrain_shadowed: bool


def _tobler_mars_speed_m_s(base_speed_m_s: float, slope_deg: float) -> float:
    """Slope-adjusted walking/traverse speed preserving positive physical bounds."""
    grade = math.tan(math.radians(min(45.0, abs(slope_deg))))
    factor = math.exp(-2.2 * abs(grade + 0.02))
    return max(0.08 * base_speed_m_s, min(1.15 * base_speed_m_s, base_speed_m_s * factor))


def evaluate_route_mission_clock(
    coordinates: list[list[float]],
    departure_utc: str | datetime | None = None,
    base_speed_m_s: float = 1.1111,  # 4.0 km/h EVA walking speed default
    stop_durations_minutes: list[float] | None = None,
    default_waypoint_stop_minutes: float = 15.0,
    waypoint_coords: list[tuple[float, float]] | None = None,
    include_return_leg: bool = True,
    return_time_multiplier: float = 1.0,
    max_eva_duration_hours: float = 8.0,
) -> dict[str, Any]:
    """Compute a complete mission clock timeline for a route geometry."""
    if not coordinates or len(coordinates) < 2:
        raise ValueError("Route mission clock requires at least 2 coordinate vertices.")

    dt_start = parse_utc_datetime(departure_utc)
    base_speed = max(0.05, float(base_speed_m_s))
    return_mult = max(0.25, float(return_time_multiplier))

    start_lon, start_lat = float(coordinates[0][0]), float(coordinates[0][1])
    m24_start = compute_mars24(start_lat, start_lon, dt_start)
    shadow_analyzer = get_dem_shadow_analyzer()

    # Calculate remaining daylight hours at departure if currently in daylight
    if m24_start.polar_day_state == "POLAR_CONTINUOUS_DAY":
        avail_daylight_earth_h = 24.0 * MARS_SOL_RATIO
    elif m24_start.polar_day_state == "POLAR_CONTINUOUS_NIGHT":
        avail_daylight_earth_h = 0.0
    elif m24_start.sunset_ltst_hours is not None and m24_start.sunrise_ltst_hours is not None:
        if m24_start.sunrise_ltst_hours <= m24_start.ltst_hours <= m24_start.sunset_ltst_hours:
            avail_mars_h = m24_start.sunset_ltst_hours - m24_start.ltst_hours
            avail_daylight_earth_h = max(0.0, avail_mars_h * MARS_SOL_RATIO)
        else:
            avail_daylight_earth_h = 0.0
    else:
        avail_daylight_earth_h = 0.0

    # Map waypoint stops to nearest vertex index
    wp_stops_s: dict[int, float] = {}
    if waypoint_coords:
        for wp_idx, (w_lon, w_lat) in enumerate(waypoint_coords):
            best_v = 1
            best_d = float("inf")
            for v_idx in range(1, len(coordinates)):
                vx, vy = float(coordinates[v_idx][0]), float(coordinates[v_idx][1])
                d2 = (vx - w_lon) ** 2 + (vy - w_lat) ** 2
                if d2 < best_d:
                    best_d = d2
                    best_v = v_idx
            stop_min = (
                stop_durations_minutes[wp_idx]
                if stop_durations_minutes and wp_idx < len(stop_durations_minutes)
                else default_waypoint_stop_minutes
            )
            wp_stops_s[best_v] = wp_stops_s.get(best_v, 0.0) + max(0.0, float(stop_min) * 60.0)
    elif stop_durations_minutes:
        # Distribute provided stop durations evenly across intermediate milestones
        n_stops = len(stop_durations_minutes)
        for s_idx, stop_min in enumerate(stop_durations_minutes):
            v_target = max(1, min(len(coordinates) - 1, int(((s_idx + 1) * (len(coordinates) - 1)) / max(1, n_stops))))
            wp_stops_s[v_target] = wp_stops_s.get(v_target, 0.0) + max(0.0, float(stop_min) * 60.0)

    mars_r = 3396190.0
    entries: list[SegmentClockEntry] = []
    cum_dist_m = 0.0
    cum_dur_s = 0.0
    outbound_walk_s = 0.0
    outbound_stop_s = 0.0
    outbound_dark_m = 0.0
    outbound_shadow_m = 0.0

    # Sample shadow & Mars24 every segment (subsampling ray-march on dense polylines for speed)
    stride = max(1, len(coordinates) // 60)
    last_shadow_state = "ILLUMINATED"

    for idx in range(len(coordinates) - 1):
        p0 = coordinates[idx]
        p1 = coordinates[idx + 1]
        lon0, lat0 = float(p0[0]), float(p0[1])
        lon1, lat1 = float(p1[0]), float(p1[1])
        z0 = float(p0[2]) if len(p0) > 2 and p0[2] is not None else None
        z1 = float(p1[2]) if len(p1) > 2 and p1[2] is not None else None

        dlat = math.radians(lat1 - lat0)
        dlon = math.radians(lon1 - lon0) * math.cos(math.radians(0.5 * (lat0 + lat1)))
        seg_dist_m = mars_r * math.hypot(dlat, dlon)
        if z0 is not None and z1 is not None and seg_dist_m > 0.1:
            slope_deg = math.degrees(math.atan2(abs(z1 - z0), seg_dist_m))
        else:
            slope_deg = 2.5

        eff_speed = _tobler_mars_speed_m_s(base_speed, slope_deg)
        walk_s = seg_dist_m / max(0.05, eff_speed)
        stop_s = wp_stops_s.get(idx + 1, 0.0)

        cum_dist_m += seg_dist_m
        outbound_walk_s += walk_s
        outbound_stop_s += stop_s
        cum_dur_s += walk_s + stop_s

        arr_dt = dt_start + timedelta(seconds=cum_dur_s)
        m24_seg = compute_mars24(lat1, lon1, arr_dt)

        if idx % stride == 0 or idx == len(coordinates) - 2:
            sh = shadow_analyzer.evaluate_shadow(
                lat1, lon1, m24_seg.solar_elevation_deg, m24_seg.solar_azimuth_deg
            )
            last_shadow_state = sh.shadow_state
        else:
            sh_state = "BELOW_HORIZON" if m24_seg.solar_elevation_deg <= 0.0 else last_shadow_state
            last_shadow_state = sh_state

        is_dark = m24_seg.solar_elevation_deg <= 0.0
        is_terr_sh = last_shadow_state == "TERRAIN_SHADOWED"
        if is_dark:
            outbound_dark_m += seg_dist_m
        if is_terr_sh:
            outbound_shadow_m += seg_dist_m

        entries.append(
            SegmentClockEntry(
                segment_index=idx,
                leg="OUTBOUND",
                start_lon=round(lon0, 6),
                start_lat=round(lat0, 6),
                end_lon=round(lon1, 6),
                end_lat=round(lat1, 6),
                segment_distance_m=round(seg_dist_m, 2),
                cumulative_distance_m=round(cum_dist_m, 2),
                slope_deg=round(slope_deg, 2),
                effective_speed_m_s=round(eff_speed, 3),
                walking_duration_s=round(walk_s, 1),
                stop_duration_s=round(stop_s, 1),
                cumulative_duration_s=round(cum_dur_s, 1),
                arrival_utc=arr_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                arrival_ltst_hours=m24_seg.ltst_hours,
                arrival_ltst_hms=m24_seg.ltst_hms,
                solar_elevation_deg=m24_seg.solar_elevation_deg,
                solar_azimuth_deg=m24_seg.solar_azimuth_deg,
                shadow_state=last_shadow_state,
                is_darkness=is_dark,
                is_terrain_shadowed=is_terr_sh,
            )
        )

    outbound_dist_m = cum_dist_m
    outbound_total_s = cum_dur_s
    outbound_arrival_dt = dt_start + timedelta(seconds=outbound_total_s)
    end_lon, end_lat = float(coordinates[-1][0]), float(coordinates[-1][1])
    m24_outbound_end = compute_mars24(end_lat, end_lon, outbound_arrival_dt)

    return_walk_s = 0.0
    return_dark_m = 0.0
    return_shadow_m = 0.0

    if include_return_leg:
        rev_coords = list(reversed(coordinates))
        base_idx = len(entries)
        for idx in range(len(rev_coords) - 1):
            p0 = rev_coords[idx]
            p1 = rev_coords[idx + 1]
            lon0, lat0 = float(p0[0]), float(p0[1])
            lon1, lat1 = float(p1[0]), float(p1[1])
            z0 = float(p0[2]) if len(p0) > 2 and p0[2] is not None else None
            z1 = float(p1[2]) if len(p1) > 2 and p1[2] is not None else None

            dlat = math.radians(lat1 - lat0)
            dlon = math.radians(lon1 - lon0) * math.cos(math.radians(0.5 * (lat0 + lat1)))
            seg_dist_m = mars_r * math.hypot(dlat, dlon)
            if z0 is not None and z1 is not None and seg_dist_m > 0.1:
                slope_deg = math.degrees(math.atan2(abs(z1 - z0), seg_dist_m))
            else:
                slope_deg = 2.5

            eff_speed = _tobler_mars_speed_m_s(base_speed, slope_deg) / return_mult
            walk_s = seg_dist_m / max(0.05, eff_speed)
            cum_dist_m += seg_dist_m
            return_walk_s += walk_s
            cum_dur_s += walk_s

            arr_dt = dt_start + timedelta(seconds=cum_dur_s)
            m24_seg = compute_mars24(lat1, lon1, arr_dt)

            if idx % stride == 0 or idx == len(rev_coords) - 2:
                sh = shadow_analyzer.evaluate_shadow(
                    lat1, lon1, m24_seg.solar_elevation_deg, m24_seg.solar_azimuth_deg
                )
                last_shadow_state = sh.shadow_state
            else:
                last_shadow_state = (
                    "BELOW_HORIZON" if m24_seg.solar_elevation_deg <= 0.0 else last_shadow_state
                )

            is_dark = m24_seg.solar_elevation_deg <= 0.0
            is_terr_sh = last_shadow_state == "TERRAIN_SHADOWED"
            if is_dark:
                return_dark_m += seg_dist_m
            if is_terr_sh:
                return_shadow_m += seg_dist_m

            entries.append(
                SegmentClockEntry(
                    segment_index=base_idx + idx,
                    leg="RETURN",
                    start_lon=round(lon0, 6),
                    start_lat=round(lat0, 6),
                    end_lon=round(lon1, 6),
                    end_lat=round(lat1, 6),
                    segment_distance_m=round(seg_dist_m, 2),
                    cumulative_distance_m=round(cum_dist_m, 2),
                    slope_deg=round(slope_deg, 2),
                    effective_speed_m_s=round(eff_speed, 3),
                    walking_duration_s=round(walk_s, 1),
                    stop_duration_s=0.0,
                    cumulative_duration_s=round(cum_dur_s, 1),
                    arrival_utc=arr_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    arrival_ltst_hours=m24_seg.ltst_hours,
                    arrival_ltst_hms=m24_seg.ltst_hms,
                    solar_elevation_deg=m24_seg.solar_elevation_deg,
                    solar_azimuth_deg=m24_seg.solar_azimuth_deg,
                    shadow_state=last_shadow_state,
                    is_darkness=is_dark,
                    is_terrain_shadowed=is_terr_sh,
                )
            )

    final_dt = dt_start + timedelta(seconds=cum_dur_s)
    m24_final = compute_mars24(
        start_lat if include_return_leg else end_lat,
        start_lon if include_return_leg else end_lon,
        final_dt,
    )

    total_dark_m = outbound_dark_m + return_dark_m
    total_shadow_m = outbound_shadow_m + return_shadow_m
    total_dist_m = max(1e-6, cum_dist_m)
    total_earth_hours = cum_dur_s / 3600.0
    rem_daylight_h = max(0.0, avail_daylight_earth_h - total_earth_hours)

    # Subsample returned segment entries if very long so JSON stays compact while preserving key milestones
    if len(entries) > 80:
        step = max(1, len(entries) // 60)
        sampled_entries = [
            asdict(e)
            for i, e in enumerate(entries)
            if i == 0 or i == len(entries) - 1 or e.stop_duration_s > 0 or i % step == 0
        ]
    else:
        sampled_entries = [asdict(e) for e in entries]

    return {
        "departure_utc": dt_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "departure_msd": m24_start.msd,
        "departure_lmst_hms": m24_start.lmst_hms,
        "departure_ltst_hms": m24_start.ltst_hms,
        "departure_ls_deg": m24_start.ls_deg,
        "departure_solar_elevation_deg": m24_start.solar_elevation_deg,
        "base_walking_speed_m_s": round(base_speed, 3),
        "include_return_leg": include_return_leg,
        "return_time_multiplier": round(return_mult, 2),
        "outbound_leg": {
            "distance_m": round(outbound_dist_m, 1),
            "walking_duration_hours": round(outbound_walk_s / 3600.0, 3),
            "stop_duration_hours": round(outbound_stop_s / 3600.0, 3),
            "total_duration_hours": round(outbound_total_s / 3600.0, 3),
            "arrival_utc": outbound_arrival_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "arrival_ltst_hms": m24_outbound_end.ltst_hms,
            "arrival_solar_elevation_deg": m24_outbound_end.solar_elevation_deg,
            "darkness_distance_m": round(outbound_dark_m, 1),
            "terrain_shadowed_distance_m": round(outbound_shadow_m, 1),
        },
        "return_leg": (
            {
                "distance_m": round(outbound_dist_m, 1),
                "walking_duration_hours": round(return_walk_s / 3600.0, 3),
                "arrival_utc": final_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "arrival_ltst_hms": m24_final.ltst_hms,
                "arrival_solar_elevation_deg": m24_final.solar_elevation_deg,
                "darkness_distance_m": round(return_dark_m, 1),
                "terrain_shadowed_distance_m": round(return_shadow_m, 1),
            }
            if include_return_leg
            else None
        ),
        "total_distance_m": round(cum_dist_m, 1),
        "total_duration_hours": round(total_earth_hours, 3),
        "max_eva_duration_hours": round(max_eva_duration_hours, 2),
        "within_eva_budget": total_earth_hours <= max_eva_duration_hours,
        "available_daylight_at_departure_hours": round(avail_daylight_earth_h, 3),
        "remaining_daylight_at_completion_hours": round(rem_daylight_h, 3),
        "completion_utc": final_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "completion_ltst_hms": m24_final.ltst_hms,
        "completion_solar_elevation_deg": m24_final.solar_elevation_deg,
        "darkness_encountered": total_dark_m > 0.0,
        "darkness_distance_m": round(total_dark_m, 1),
        "darkness_fraction": round(total_dark_m / total_dist_m, 4),
        "terrain_shadow_encountered": total_shadow_m > 0.0,
        "terrain_shadowed_distance_m": round(total_shadow_m, 1),
        "terrain_shadowed_fraction": round(total_shadow_m / total_dist_m, 4),
        "cost_function_modified": False,
        "segments": sampled_entries,
    }
