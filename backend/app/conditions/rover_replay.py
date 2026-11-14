"""Historical Perseverance Rover Replay Synchronizer for the Mars Time Machine.

Synchronizes the official Mars 2020 Perseverance traverse archive (`perseverance-waypoints.geojson`
and `perseverance-traverse.geojson`) with arbitrary UTC timestamps or Mission Sol numbers.

Strict Archive Boundary Semantics:
- PRE_LANDING: Requested timestamp is prior to Perseverance landing (2021-02-18T20:55:00Z, Sol 0).
  No rover surface position is fabricated.
- EXACT_SOL_RECORD: Exact published waypoint record exists for the requested Sol.
- STATIONARY_OR_ARCHIVE_GAP: Requested Sol lies within [0, max_published_sol] between two
  published drive sols. Returns the last confirmed waypoint and explicitly identifies the
  surrounding published sols without interpolating fake intermediate positions.
- POST_ARCHIVE_CUTOFF: Requested Sol exceeds the last published archive Sol (`max_published_sol`).
  Returns the final published waypoint and explicitly reports the archive cutoff boundary.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.conditions.mars24 import MARS_SOL_SECONDS, compute_mars24, parse_utc_datetime

PERSEVERANCE_LANDING_UTC = datetime(2021, 2, 18, 20, 55, 0, tzinfo=UTC)
PERSEVERANCE_LANDING_LON = 77.45089
PERSEVERANCE_LANDING_LAT = 18.44463


class RoverReplayService:
    """Loads official Perseverance waypoints and synchronizes replay state with Mars24."""

    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is not None:
            self._data_dir = data_dir
        else:
            repo_root = Path(__file__).resolve().parents[3]
            candidate_dist = repo_root / "dist" / "mission-data"
            candidate_ui = repo_root / "mission-ui" / "public" / "mission-data"
            self._data_dir = candidate_dist if candidate_dist.exists() else candidate_ui
        self._waypoints: list[dict[str, Any]] = []
        self._by_sol: dict[int, dict[str, Any]] = {}
        self._sorted_sols: list[int] = []
        self._load()

    def _load(self) -> None:
        wp_path = self._data_dir / "perseverance-waypoints.geojson"
        if not wp_path.exists():
            return
        with open(wp_path, encoding="utf-8") as f:
            geo = json.load(f)
        features = geo.get("features", [])
        parsed: list[dict[str, Any]] = []
        for idx, feat in enumerate(features):
            props = feat.get("properties", {})
            coords = feat.get("geometry", {}).get("coordinates", [])
            if len(coords) < 2:
                continue
            sol = int(props.get("sol", idx))
            lon = float(coords[0])
            lat = float(coords[1])
            elev = float(coords[2]) if len(coords) > 2 and coords[2] is not None else -2570.0
            dist_m = float(props.get("dist_m", props.get("drive_m", 0.0)) or 0.0)
            total_m = float(
                props.get("dist_total_m", props.get("odometry_m", props.get("total_m", 0.0))) or 0.0
            )
            approx_dt = PERSEVERANCE_LANDING_UTC + timedelta(seconds=sol * MARS_SOL_SECONDS)
            item = {
                "waypoint_index": idx,
                "sol": sol,
                "historical_utc_estimate": props.get("utc") or approx_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lon": round(lon, 6),
                "lat": round(lat, 6),
                "elev_m": round(elev, 2),
                "elevation_m": round(elev, 2),
                "drive_distance_m": round(dist_m, 2),
                "cumulative_odometry_m": round(total_m, 2),
                "site": props.get("site"),
                "drive": props.get("drive"),
                "rmc": props.get("rmc") or props.get("RMC"),
                "note": props.get("Note") or props.get("note"),
            }
            parsed.append(item)
            self._by_sol[sol] = item

        # Ensure Sol 0 touchdown record at Octavia E. Butler Landing is anchored if archive starts at Sol 13
        if parsed and 0 not in self._by_sol:
            first_wp = parsed[0]
            sol0_item = {
                "waypoint_index": 0,
                "sol": 0,
                "historical_utc_estimate": PERSEVERANCE_LANDING_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lon": first_wp["lon"],
                "lat": first_wp["lat"],
                "elev_m": first_wp["elevation_m"],
                "elevation_m": first_wp["elevation_m"],
                "drive_distance_m": 0.0,
                "cumulative_odometry_m": 0.0,
                "site": first_wp.get("site", 3),
                "drive": 0,
                "rmc": "3_0_TOUCHDOWN",
                "note": "Octavia E. Butler Landing touchdown (Sol 0)",
            }
            parsed.insert(0, sol0_item)
            self._by_sol[0] = sol0_item

        parsed.sort(key=lambda w: (w["sol"], w["waypoint_index"]))
        self._waypoints = parsed
        self._sorted_sols = sorted(self._by_sol.keys())

    @property
    def min_sol(self) -> int:
        return self._sorted_sols[0] if self._sorted_sols else 0

    @property
    def max_sol(self) -> int:
        return self._sorted_sols[-1] if self._sorted_sols else 0

    def get_replay_state(
        self,
        utc_time: str | datetime | None = None,
        sol: int | None = None,
    ) -> dict[str, Any]:
        """Resolve Perseverance traverse state at a requested UTC or mission Sol."""
        if sol is not None:
            requested_sol = int(sol)
            dt_utc = PERSEVERANCE_LANDING_UTC + timedelta(seconds=max(0, requested_sol) * MARS_SOL_SECONDS)
            if requested_sol < 0:
                dt_utc = PERSEVERANCE_LANDING_UTC + timedelta(seconds=requested_sol * MARS_SOL_SECONDS)
        else:
            dt_utc = parse_utc_datetime(utc_time)
            if dt_utc < PERSEVERANCE_LANDING_UTC:
                delta_s = (dt_utc - PERSEVERANCE_LANDING_UTC).total_seconds()
                requested_sol = int(math.floor(delta_s / MARS_SOL_SECONDS))
            else:
                m24 = compute_mars24(PERSEVERANCE_LANDING_LAT, PERSEVERANCE_LANDING_LON, dt_utc)
                requested_sol = m24.perseverance_mission_sol if m24.perseverance_mission_sol is not None else 0

        min_pub_sol = self.min_sol
        max_pub_sol = self.max_sol
        total_waypoints = len(self._waypoints)

        if requested_sol < 0 or dt_utc < PERSEVERANCE_LANDING_UTC:
            m24_site = compute_mars24(PERSEVERANCE_LANDING_LAT, PERSEVERANCE_LANDING_LON, dt_utc)
            return {
                "rover_id": "perseverance",
                "archive_status": "PRE_LANDING",
                "position_available": False,
                "position_interpolated": False,
                "requested_sol": requested_sol,
                "requested_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "landing_utc": PERSEVERANCE_LANDING_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "archive_sol_range": [min_pub_sol, max_pub_sol],
                "total_published_waypoints": total_waypoints,
                "completed_waypoints_count": 0,
                "active_waypoint": None,
                "previous_confirmed_waypoint": None,
                "next_confirmed_waypoint": self._waypoints[0] if self._waypoints else None,
                "mars24_at_site": {
                    "msd": m24_site.msd,
                    "lmst_hms": m24_site.lmst_hms,
                    "ltst_hms": m24_site.ltst_hms,
                    "ls_deg": m24_site.ls_deg,
                    "solar_elevation_deg": m24_site.solar_elevation_deg,
                },
                "explanation": (
                    f"Requested timestamp ({dt_utc.strftime('%Y-%m-%dT%H:%M:%SZ')}, Sol {requested_sol}) "
                    "precedes Mars 2020 Perseverance touchdown at Octavia E. Butler Landing "
                    "(2021-02-18T20:55:00Z, Sol 0). No surface rover position is fabricated."
                ),
            }

        if not self._waypoints:
            return {
                "rover_id": "perseverance",
                "archive_status": "ARCHIVE_UNAVAILABLE",
                "position_available": False,
                "position_interpolated": False,
                "requested_sol": requested_sol,
                "requested_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "explanation": "Perseverance waypoint archive file could not be loaded.",
            }

        completed_wps = [w for w in self._waypoints if w["sol"] <= requested_sol]
        active_wp = completed_wps[-1] if completed_wps else self._waypoints[0]
        m24_rover = compute_mars24(active_wp["lat"], active_wp["lon"], dt_utc)

        if requested_sol > max_pub_sol:
            sols_past = requested_sol - max_pub_sol
            return {
                "rover_id": "perseverance",
                "archive_status": "POST_ARCHIVE_CUTOFF",
                "position_available": True,
                "position_interpolated": False,
                "requested_sol": requested_sol,
                "requested_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "archive_sol_range": [min_pub_sol, max_pub_sol],
                "sols_beyond_archive_cutoff": sols_past,
                "total_published_waypoints": total_waypoints,
                "completed_waypoints_count": len(completed_wps),
                "active_waypoint": active_wp,
                "previous_confirmed_waypoint": active_wp,
                "next_confirmed_waypoint": None,
                "mars24_at_rover": {
                    "msd": m24_rover.msd,
                    "lmst_hms": m24_rover.lmst_hms,
                    "ltst_hms": m24_rover.ltst_hms,
                    "ls_deg": m24_rover.ls_deg,
                    "solar_elevation_deg": m24_rover.solar_elevation_deg,
                },
                "explanation": (
                    f"Requested Sol {requested_sol} is {sols_past} sol(s) beyond the latest published "
                    f"Mars 2020 localization archive cutoff (Sol {max_pub_sol}). Holding at last "
                    f"verified waypoint (Sol {active_wp['sol']}, odometry {active_wp['cumulative_odometry_m']:.1f} m) "
                    "without extrapolating unverified coordinates."
                ),
            }

        if requested_sol in self._by_sol:
            exact_wp = self._by_sol[requested_sol]
            next_wps = [w for w in self._waypoints if w["sol"] > requested_sol]
            return {
                "rover_id": "perseverance",
                "archive_status": "EXACT_SOL_RECORD",
                "position_available": True,
                "position_interpolated": False,
                "requested_sol": requested_sol,
                "requested_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "archive_sol_range": [min_pub_sol, max_pub_sol],
                "total_published_waypoints": total_waypoints,
                "completed_waypoints_count": len(completed_wps),
                "active_waypoint": exact_wp,
                "previous_confirmed_waypoint": exact_wp,
                "next_confirmed_waypoint": next_wps[0] if next_wps else None,
                "mars24_at_rover": {
                    "msd": m24_rover.msd,
                    "lmst_hms": m24_rover.lmst_hms,
                    "ltst_hms": m24_rover.ltst_hms,
                    "ls_deg": m24_rover.ls_deg,
                    "solar_elevation_deg": m24_rover.solar_elevation_deg,
                },
                "explanation": (
                    f"Exact published localization waypoint confirmed on Sol {requested_sol} "
                    f"({exact_wp['lon']:.5f}°E, {exact_wp['lat']:.5f}°N, odometry {exact_wp['cumulative_odometry_m']:.1f} m)."
                ),
            }

        next_wps = [w for w in self._waypoints if w["sol"] > requested_sol]
        next_wp = next_wps[0] if next_wps else None
        return {
            "rover_id": "perseverance",
            "archive_status": "STATIONARY_OR_ARCHIVE_GAP",
            "position_available": True,
            "position_interpolated": False,
            "requested_sol": requested_sol,
            "requested_utc": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "archive_sol_range": [min_pub_sol, max_pub_sol],
            "total_published_waypoints": total_waypoints,
            "completed_waypoints_count": len(completed_wps),
            "active_waypoint": active_wp,
            "previous_confirmed_waypoint": active_wp,
            "next_confirmed_waypoint": next_wp,
            "mars24_at_rover": {
                "msd": m24_rover.msd,
                "lmst_hms": m24_rover.lmst_hms,
                "ltst_hms": m24_rover.ltst_hms,
                "ls_deg": m24_rover.ls_deg,
                "solar_elevation_deg": m24_rover.solar_elevation_deg,
            },
            "explanation": (
                f"No new drive localization published on Sol {requested_sol}; rover remained stationary "
                f"at Sol {active_wp['sol']} position ({active_wp['lon']:.5f}°E, {active_wp['lat']:.5f}°N) "
                + (f"until next recorded drive on Sol {next_wp['sol']}." if next_wp else ".")
            ),
        }


_default_replay_service: RoverReplayService | None = None


def get_rover_replay_service() -> RoverReplayService:
    global _default_replay_service
    if _default_replay_service is None:
        _default_replay_service = RoverReplayService()
    return _default_replay_service
