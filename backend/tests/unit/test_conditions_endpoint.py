"""Comprehensive unit and API contract tests for GET /api/v1/conditions and Mars24 solar geometry."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from backend.app.conditions.mars24 import (
    compute_mars24,
    parse_utc_datetime,
    utc_to_tt_offset_seconds,
)
from backend.app.main import app

client = TestClient(app)


class TestMars24Algorithm:
    """Validate NASA GISS Mars24 algorithm against published worked examples and standards."""

    def test_utc_to_tt_leap_seconds(self) -> None:
        """Verify historical IERS TAI-UTC table and TT - UTC offset."""
        # For 2026, 37 leap seconds + 32.184 = 69.184 seconds
        dt_2026 = datetime(2026, 11, 14, 10, 0, 0, tzinfo=UTC)
        offset = utc_to_tt_offset_seconds(dt_2026)
        assert abs(offset - 69.184) < 1e-3

        # For 2000-01-01 (32 leap seconds + 32.184 = 64.184)
        dt_2000 = datetime(2000, 1, 1, 0, 0, 0, tzinfo=UTC)
        offset_2000 = utc_to_tt_offset_seconds(dt_2000)
        assert abs(offset_2000 - 64.184) < 1e-3

    def test_canonical_pathfinder_worked_example(self) -> None:
        """Verify Mars Pathfinder landing (1997-07-04T17:00:00Z) solar coordinates."""
        # Pathfinder: 19.33° N, 33.55° W (326.45° E)
        res = compute_mars24(
            latitude_deg=19.33,
            longitude_east_deg=326.45,
            utc_time="1997-07-04T17:00:00Z",
        )
        # Allison & McEwen (2000) worked example:
        # Ls ~ 142° - 143° (Northern Summer)
        assert 142.0 <= res.ls_deg <= 144.0
        # MSD around 43905.7
        assert 43905.0 <= res.msd <= 43906.5
        # Nighttime / early morning LTST before dawn
        assert res.ltst_hours < 5.0 or res.ltst_hours > 20.0
        assert res.solar_elevation_deg < 0.0
        assert res.is_daylight is False

    def test_perseverance_touchdown_geometry(self) -> None:
        """Verify Mars 2020 Perseverance landing (2021-02-18T20:55:00Z) at Jezero Crater."""
        res = compute_mars24(
            latitude_deg=18.4447,
            longitude_east_deg=77.4508,
            utc_time="2021-02-18T20:55:00Z",
        )
        assert res.perseverance_mission_sol == 0
        assert 52303.0 <= res.msd <= 52305.0
        assert 5.0 <= res.ls_deg <= 7.0  # Northern early Spring
        # Landing was in Martian mid-afternoon (LTST ~ 15:50)
        assert 15.0 <= res.ltst_hours <= 16.5
        assert res.solar_elevation_deg > 15.0
        assert res.is_daylight is True

    def test_timezone_naive_timestamp_rejected(self) -> None:
        """Timezone-naive string must raise ValueError."""
        with pytest.raises(ValueError, match="Timezone-naive"):
            parse_utc_datetime("2026-11-14T10:00:00")

    def test_longitude_wrapping_invariance(self) -> None:
        """Coordinates at 77.40°E and 437.40°E (77.40 + 360) must give identical solar time and elevation."""
        res1 = compute_mars24(18.39, 77.40, "2026-11-14T10:00:00Z")
        res2 = compute_mars24(18.39, 437.40, "2026-11-14T10:00:00Z")
        assert abs(res1.ltst_hours - res2.ltst_hours) < 1e-5
        assert abs(res1.solar_elevation_deg - res2.solar_elevation_deg) < 1e-5
        assert abs(res1.solar_azimuth_deg - res2.solar_azimuth_deg) < 1e-5


class TestConditionsEndpointAPI:
    """Validate GET /api/v1/conditions HTTP contract and failure modes."""

    def test_get_conditions_success(self) -> None:
        """Verify successful conditions query with sun, terrain, rover, atmosphere blocks."""
        response = client.get("/api/v1/conditions?lat=18.39&lon=77.40&utc=2026-11-14T10%3A00%3A00Z")
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["status"] == "ok"
        assert "query" in data
        assert data["query"]["lat"] == 18.39
        assert abs(data["query"]["lon"] - 77.40) < 1e-4

        # 1. Sun block
        assert "sun" in data
        sun = data["sun"]
        assert "local_true_solar_time" in sun
        assert "solar_longitude_ls" in sun
        assert "solar_elevation" in sun
        assert "solar_azimuth" in sun
        assert sun["solar_elevation_type"] == "geometric"
        assert sun["local_true_solar_time"]["kind"] == "computed"
        assert sun["solar_elevation"]["unit"] == "deg"

        # 2. Terrain block
        assert "terrain" in data
        terrain = data["terrain"]
        assert "elevation_m" in terrain
        assert "slope_deg" in terrain
        assert "dataset" in terrain
        assert "resolution_m" in terrain
        assert "provenance" in terrain
        assert terrain["status"] in ("VALID", "OUT_OF_COVERAGE", "UNAVAILABLE")

        # 3. Rover block
        assert "rover" in data
        rover = data["rover"]
        assert rover["rover_id"] == "perseverance"
        assert "latest_published_waypoint" in rover
        assert "sol" in rover
        assert "position_available" in rover
        assert rover["position_interpolated"] is False

        # 4. Atmosphere block (marked unavailable as required)
        assert "atmosphere" in data
        atmo = data["atmosphere"]
        assert atmo["status"] == "UNAVAILABLE"
        assert atmo["temperature"]["value"] is None
        assert atmo["temperature"]["status"] == "UNAVAILABLE"
        assert atmo["pressure"]["value"] is None
        assert atmo["pressure"]["status"] == "UNAVAILABLE"

    def test_timezone_naive_utc_returns_422(self) -> None:
        """Timezone-naive ISO 8601 string must return HTTP 422."""
        response = client.get("/api/v1/conditions?lat=18.39&lon=77.40&utc=2026-11-14T10%3A00%3A00")
        assert response.status_code == 422
        assert "timezone" in response.text.lower() or "utc" in response.text.lower()

    def test_malformed_utc_returns_422(self) -> None:
        """Malformed timestamp string must return HTTP 422."""
        response = client.get("/api/v1/conditions?lat=18.39&lon=77.40&utc=invalid-timestamp")
        assert response.status_code == 422

    def test_non_finite_coordinates_return_422(self) -> None:
        """NaN or infinite coordinates must return HTTP 422."""
        response = client.get("/api/v1/conditions?lat=NaN&lon=77.40&utc=2026-11-14T10%3A00%3A00Z")
        assert response.status_code == 422

    def test_out_of_bounds_latitude_returns_422(self) -> None:
        """Latitude outside [-90, 90] must return HTTP 422."""
        response = client.get("/api/v1/conditions?lat=95.0&lon=77.40&utc=2026-11-14T10%3A00%3A00Z")
        assert response.status_code == 422

    def test_out_of_coverage_terrain_preserves_solar_calculations(self) -> None:
        """Coordinates outside active DEM coverage must return null terrain without failing solar calculations."""
        # Olympus Mons: ~18.65°N, 226.2°E (outside Jezero regional bounds)
        response = client.get("/api/v1/conditions?lat=-5.0&lon=137.4&utc=2026-11-14T10%3A00%3A00Z")
        assert response.status_code == 200
        data = response.json()

        # Solar block MUST still compute accurately
        assert data["sun"]["solar_elevation"]["value"] is not None
        assert data["sun"]["local_true_solar_time"]["value"] is not None

        # Terrain block reports OUT_OF_COVERAGE or UNAVAILABLE with null elevation and slope
        assert data["terrain"]["status"] in ("OUT_OF_COVERAGE", "UNAVAILABLE")
        assert data["terrain"]["elevation_m"] is None
        assert data["terrain"]["slope_deg"] is None

    def test_rover_post_archive_cutoff_label(self) -> None:
        """Scrubbing to future Sol past the archive end shows last recorded position without interpolation."""
        response = client.get("/api/v1/conditions?lat=18.39&lon=77.40&sol=3000")
        assert response.status_code == 200
        data = response.json()
        rover = data["rover"]
        assert rover["is_post_archive"] is True
        assert rover["status"] == "POST_ARCHIVE_CUTOFF"
        assert rover["latest_published_waypoint"] is not None
        assert rover["position_interpolated"] is False
