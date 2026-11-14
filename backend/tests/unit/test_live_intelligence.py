"""
Unit and Integration Tests for MARSPath Live Mars Intelligence Subsystem.
Verifies orbital ephemeris propagation, rover synchronization, observation catalogue,
Pydantic schema validation, and FastAPI endpoint contracts.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.intelligence.imagery import ImageryCatalogService
from backend.app.intelligence.orbital import MarsOrbitalPropagator
from backend.app.intelligence.rover import RoverIntelligenceService
from backend.app.intelligence.schemas import DataFreshnessState
from backend.app.main import app

client = TestClient(app)


class TestMarsOrbitalPropagator:
    """Verifies orbital mechanics and astrodynamics calculations."""

    def test_all_five_orbiters_present(self):
        prop = MarsOrbitalPropagator()
        ships = prop.list_spacecraft()
        ids = {s.spacecraft_id for s in ships}
        assert ids == {"mro", "ody", "maven", "mex", "tgo"}

    def test_mro_orbital_parameters_and_state(self):
        prop = MarsOrbitalPropagator()
        pos = prop.get_position("mro")
        assert pos.spacecraft_id == "mro"
        assert pos.name == "Mars Reconnaissance Orbiter"
        assert -90.0 <= pos.lat <= 90.0
        assert -180.0 <= pos.lon <= 180.0
        assert 200.0 <= pos.altitude_km <= 350.0  # MRO frozen orbit
        assert 3.2 <= pos.velocity_kms <= 3.8
        assert 110.0 <= pos.orbit_period_minutes <= 114.0
        assert pos.state == DataFreshnessState.PREDICTED
        assert pos.provenance.source_name == "NASA / JPL"

    def test_ground_track_generation(self):
        prop = MarsOrbitalPropagator()
        gt = prop.get_ground_track("mro", duration_minutes=60.0, step_seconds=120)
        assert gt.spacecraft_id == "mro"
        assert len(gt.points) == 31  # 60 min / 2 min + 1
        for pt in gt.points:
            assert -90.0 <= pt.lat <= 90.0
            assert -180.0 <= pt.lon <= 180.0
            assert pt.altitude_km > 0

    def test_unknown_spacecraft_raises_keyerror(self):
        prop = MarsOrbitalPropagator()
        with pytest.raises(KeyError):
            prop.get_position("voyager1")


class TestRoverIntelligenceService:
    """Verifies rover telemetry, odometry, and traverse history."""

    def test_perseverance_localization_and_odometry(self):
        srv = RoverIntelligenceService()
        p = srv.get_rover_position("perseverance")
        assert p.rover_id == "perseverance"
        assert p.sol >= 2022
        assert 77.0 <= p.lon <= 78.0  # Jezero Crater
        assert 18.0 <= p.lat <= 19.0
        assert p.total_odometry_meters >= 40000.0  # > 40 km cumulative
        assert p.state == DataFreshnessState.LATEST_AVAILABLE
        assert "Mastcam-Z" in p.active_instruments

    def test_curiosity_localization_and_odometry(self):
        srv = RoverIntelligenceService()
        c = srv.get_rover_position("curiosity")
        assert c.rover_id == "curiosity"
        assert c.sol >= 4400
        assert 137.0 <= c.lon <= 138.0  # Gale Crater
        assert -5.0 <= c.lat <= -4.0
        assert c.total_odometry_meters >= 30000.0  # > 30 km cumulative
        assert c.state == DataFreshnessState.LATEST_AVAILABLE
        assert "ChemCam" in c.active_instruments

    def test_perseverance_historical_traverse_preservation(self):
        srv = RoverIntelligenceService()
        trav = srv.get_rover_traverse("perseverance")
        features = trav.geojson.get("features", [])
        assert len(features) >= 550  # All 559 drives preserved
        assert trav.total_odometry_meters >= 40000.0
        assert trav.latest_sol >= 2022

    def test_rover_observations(self):
        srv = RoverIntelligenceService()
        obs = srv.get_rover_observations("perseverance")
        assert len(obs) >= 2
        for o in obs:
            assert o.rover_id == "perseverance"
            assert o.image_url.startswith("https://")


class TestImageryCatalogService:
    """Verifies peer-reviewed orbital observation footprints."""

    def test_orbital_observations_catalog(self):
        srv = ImageryCatalogService()
        obs = srv.list_observations()
        assert len(obs) >= 7
        ids = {o.observation_id for o in obs}
        assert "ESP_069176_1985" in ids
        assert "P01_001426_1985_XN_18N282W" in ids
        assert "H5270_0000" in ids

    def test_observation_footprint_geometry(self):
        srv = ImageryCatalogService()
        hirise = srv.get_observation("ESP_069176_1985")
        assert hirise is not None
        assert hirise.spatial_resolution_m_per_px == 0.25
        geo = hirise.footprint_geojson
        assert geo["type"] == "Feature"
        coords = geo["geometry"]["coordinates"][0]
        assert len(coords) == 5  # Closed polygon
        # Check Jezero bounds
        for lon, lat in coords:
            assert 77.2 <= lon <= 77.5
            assert 18.3 <= lat <= 18.6


class TestLiveIntelligenceAPIEndpoints:
    """End-to-end integration tests for FastAPI router."""

    def test_api_status_endpoint(self):
        r = client.get("/api/v1/intelligence/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "operational"
        assert data["active_spacecraft_count"] == 5
        assert data["active_rovers_count"] == 2
        assert data["cataloged_observations_count"] >= 7

    def test_api_spacecraft_endpoints(self):
        r = client.get("/api/v1/intelligence/spacecraft")
        assert r.status_code == 200
        ships = r.json()
        assert len(ships) == 5

        r_pos = client.get("/api/v1/intelligence/spacecraft/mro/position")
        assert r_pos.status_code == 200
        assert r_pos.json()["spacecraft_id"] == "mro"

        r_track = client.get("/api/v1/intelligence/spacecraft/mro/ground-track?duration_minutes=30&step_seconds=60")
        assert r_track.status_code == 200
        assert len(r_track.json()["points"]) == 31

        r_404 = client.get("/api/v1/intelligence/spacecraft/nonexistent/position")
        assert r_404.status_code == 404

    def test_api_rover_endpoints(self):
        r = client.get("/api/v1/intelligence/rovers")
        assert r.status_code == 200
        assert len(r.json()) == 2

        r_pos = client.get("/api/v1/intelligence/rovers/perseverance/position")
        assert r_pos.status_code == 200
        assert r_pos.json()["rover_id"] == "perseverance"

        r_trav = client.get("/api/v1/intelligence/rovers/perseverance/traverse")
        assert r_trav.status_code == 200
        assert len(r_trav.json()["geojson"]["features"]) >= 550

        r_obs = client.get("/api/v1/intelligence/rovers/perseverance/observations")
        assert r_obs.status_code == 200
        assert len(r_obs.json()) >= 2

        r_404 = client.get("/api/v1/intelligence/rovers/unknown_rover/position")
        assert r_404.status_code == 404

    def test_api_observations_endpoint(self):
        r = client.get("/api/v1/intelligence/observations?instrument=hirise")
        assert r.status_code == 200
        for obs in r.json():
            assert "HiRISE" in obs["instrument"]

    def test_api_timeline_endpoint(self):
        r = client.get("/api/v1/intelligence/timeline?limit=10")
        assert r.status_code == 200
        events = r.json()
        assert 1 <= len(events) <= 10
        # Verify chronological order
        dates = [e["earth_date_utc"] for e in events]
        assert dates == sorted(dates, reverse=True)

    def test_api_sync_endpoint(self):
        r = client.post("/api/v1/intelligence/sync", json={"force_refresh": True})
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert len(data["updated_sources"]) >= 3
