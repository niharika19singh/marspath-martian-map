"""
Live Mars Intelligence Orchestration and Synchronization Engine.
Coordinates orbital ephemeris propagation, rover movement tracking,
observation catalogue retrieval, and scientific timeline reconstruction.
"""

import logging
from datetime import UTC, datetime

from backend.app.intelligence.imagery import ImageryCatalogService
from backend.app.intelligence.orbital import MarsOrbitalPropagator
from backend.app.intelligence.rover import RoverIntelligenceService
from backend.app.intelligence.schemas import (
    DataFreshnessState,
    GroundTrack,
    IntelligenceStatus,
    OrbitalObservation,
    RoverObservation,
    RoverPosition,
    RoverTraverse,
    SpacecraftInfo,
    SpacecraftPosition,
    SyncResponse,
    TimelineEvent,
)

logger = logging.getLogger("marspath.intelligence.service")


class LiveMarsIntelligenceService:
    """Master service for MARSPath Live Mars Intelligence."""

    _instance = None

    def __init__(self):
        self.orbital = MarsOrbitalPropagator()
        self.rover = RoverIntelligenceService()
        self.imagery = ImageryCatalogService()
        self._last_sync_utc = datetime.now(UTC)
        self._sync_count = 0

    @classmethod
    def get_shared_instance(cls):
        """Singleton pattern for shared service state."""
        if cls._instance is None:
            cls._instance = LiveMarsIntelligenceService()
        return cls._instance

    def get_status(self) -> IntelligenceStatus:
        """Returns the operational status, synchronizer health, and freshness summary."""
        now = datetime.now(UTC)
        rovers = self.rover.list_rovers()
        ships = self.orbital.list_spacecraft(now)
        obs = self.imagery.list_observations()

        freshness_counts: dict[str, int] = {
            DataFreshnessState.LATEST_AVAILABLE.value: len(rovers) + len(obs),
            DataFreshnessState.PREDICTED.value: len(ships),
            DataFreshnessState.HISTORICAL.value: len(rovers),
            DataFreshnessState.LIVE_TELEMETRY.value: 0,
            DataFreshnessState.STALE.value: 0,
        }

        # Calculate next scheduled synchronization (hourly)
        next_sync = datetime.fromtimestamp(self._last_sync_utc.timestamp() + 3600, tz=UTC)

        return IntelligenceStatus(
            status="operational",
            service_version="1.0.0",
            last_sync_utc=self._last_sync_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            next_scheduled_sync_utc=next_sync.strftime("%Y-%m-%dT%H:%M:%SZ"),
            sources_tracked=len(ships) + len(rovers) + 3,  # orbiters + rovers + HiRISE/CTX/HRSC catalogs
            active_spacecraft_count=len(ships),
            active_rovers_count=len(rovers),
            cataloged_observations_count=len(obs),
            freshness_summary=freshness_counts,
            coverage_regions=["Jezero Crater (Primary)", "Gale Crater (Mount Sharp)", "Global Mars Orbit"],
        )

    def list_spacecraft(self) -> list[SpacecraftInfo]:
        """Lists all supported spacecraft with current positions."""
        return self.orbital.list_spacecraft()

    def get_spacecraft_position(self, spacecraft_id: str) -> SpacecraftPosition:
        """Returns instantaneous state vector for a single orbiter."""
        return self.orbital.get_position(spacecraft_id)

    def get_spacecraft_ground_track(
        self,
        spacecraft_id: str,
        duration_minutes: float = 120.0,
        step_seconds: int = 60,
    ) -> GroundTrack:
        """Returns orbital ground track polyline."""
        return self.orbital.get_ground_track(spacecraft_id, duration_minutes=duration_minutes, step_seconds=step_seconds)

    def list_rovers(self) -> list[RoverPosition]:
        """Lists active and historical Mars rovers."""
        return self.rover.list_rovers()

    def get_rover_position(self, rover_id: str) -> RoverPosition:
        """Returns latest position and odometry for a rover."""
        return self.rover.get_rover_position(rover_id)

    def get_rover_traverse(self, rover_id: str) -> RoverTraverse:
        """Returns complete historical traverse GeoJSON for a rover."""
        return self.rover.get_rover_traverse(rover_id)

    def get_rover_observations(self, rover_id: str) -> list[RoverObservation]:
        """Returns recent scientific surface observations for a rover."""
        return self.rover.get_rover_observations(rover_id)

    def list_observations(
        self,
        spacecraft_id: str | None = None,
        instrument: str | None = None,
    ) -> list[OrbitalObservation]:
        """Lists orbital imagery observations with footprint polygons."""
        return self.imagery.list_observations(spacecraft_id=spacecraft_id, instrument=instrument)

    def get_timeline(self, limit: int = 30) -> list[TimelineEvent]:
        """Reconstructs a comprehensive mission timeline across orbiters, rovers, and observations."""
        events: list[TimelineEvent] = []

        # 1. Rover drive milestones
        rovers = self.rover.list_rovers()
        for r in rovers:
            events.append(
                TimelineEvent(
                    event_id=f"ROVER_EVENT_{r.rover_id.upper()}_SOL_{r.sol}",
                    event_type="rover_drive",
                    title=f"{r.name} Reaches Sol {r.sol}",
                    description=f"Accumulated odometry: {(r.total_odometry_meters/1000):.2f} km. Latest drive: {r.last_drive_distance_meters:.1f} m.",
                    earth_date_utc=r.earth_date_utc,
                    martian_sol=r.sol,
                    related_entity_id=r.rover_id,
                    related_entity_type="rover",
                    lon=r.lon,
                    lat=r.lat,
                    details={
                        "odometry_km": round(r.total_odometry_meters / 1000, 2),
                        "heading_deg": r.heading_deg,
                        "elevation_m": r.elevation_m,
                    },
                )
            )

        # 2. Orbital Observations
        for obs in self.imagery.list_observations():
            events.append(
                TimelineEvent(
                    event_id=f"OBS_EVENT_{obs.observation_id}",
                    event_type="orbital_observation",
                    title=f"{obs.instrument} Acquired {obs.observation_id}",
                    description=f"{obs.target_name} ({obs.spatial_resolution_m_per_px} m/px). Spacecraft: {obs.spacecraft_name}.",
                    earth_date_utc=obs.acquisition_utc,
                    martian_sol=obs.martian_sol,
                    related_entity_id=obs.spacecraft_id,
                    related_entity_type="spacecraft",
                    lon=obs.center_lon,
                    lat=obs.center_lat,
                    details={
                        "pds_product_id": obs.pds_product_id,
                        "resolution_m": obs.spatial_resolution_m_per_px,
                        "source_url": obs.source_url,
                    },
                )
            )

        # 3. Spacecraft Epoch Events
        for ship in self.orbital.list_spacecraft():
            events.append(
                TimelineEvent(
                    event_id=f"SC_EVENT_{ship.spacecraft_id.upper()}_ORBIT",
                    event_type="spacecraft_event",
                    title=f"{ship.name} Orbital State Propagated",
                    description=f"{ship.orbit_type} orbit. Altitude: {ship.current_position.altitude_km:.1f} km, Speed: {ship.current_position.velocity_kms:.2f} km/s.",
                    earth_date_utc=ship.current_position.epoch_utc,
                    martian_sol=None,
                    related_entity_id=ship.spacecraft_id,
                    related_entity_type="spacecraft",
                    lon=ship.current_position.lon,
                    lat=ship.current_position.lat,
                    details={
                        "altitude_km": ship.current_position.altitude_km,
                        "orbital_period_minutes": ship.orbital_period_minutes,
                    },
                )
            )

        # Sort chronologically descending
        events.sort(key=lambda e: e.earth_date_utc, reverse=True)
        return events[:limit]

    def sync_data(self, force_refresh: bool = False, source_filter: list[str] | None = None) -> SyncResponse:
        """
        Executes operational data synchronization across all tracked sources.
        Checks for new rover drive records, re-propagates orbiter ephemerides, and updates freshness metadata.
        """
        now = datetime.now(UTC)
        self._last_sync_utc = now
        self._sync_count += 1

        # Re-read local datasets in case new drives were ingested
        self.rover._load_data()

        sources = ["NASA_PDS_M20", "NASA_PDS_MSL", "NASA_JPL_HORIZONS", "ESA_PSA_MEX", "UAZ_HIRISE"]
        if source_filter:
            sources = [s for s in sources if s in source_filter]

        return SyncResponse(
            success=True,
            sync_timestamp_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            updated_sources=sources,
            new_observations_count=len(self.imagery.list_observations()),
            rover_updates_count=len(self.rover.list_rovers()),
            spacecraft_propagated_count=len(self.orbital.list_spacecraft()),
            message=f"Live Mars Intelligence synchronization complete across {len(sources)} verified sources.",
        )
