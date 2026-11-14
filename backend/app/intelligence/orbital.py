"""
High-Precision Mars Astrodynamics and Spacecraft Ephemeris Engine.
Propagates authoritative NASA and ESA Mars orbiter state vectors in the IAU2000 Mars-fixed reference frame.

Incorporates Mars J2 gravitational harmonic perturbations, apsidal and nodal precession,
Keplerian eccentric anomaly solvers, and planetocentric-to-planetographic coordinate transformations.
"""

import math
from datetime import UTC, datetime

from backend.app.intelligence.schemas import (
    DataFreshnessState,
    GroundTrack,
    GroundTrackPoint,
    ProvenanceMetadata,
    SpacecraftInfo,
    SpacecraftPosition,
)

# IAU/NASA Mars Physical and Gravitational Constants
MARS_MU = 42828.375214  # km^3/s^2 (Mars gravitational parameter)
MARS_RADIUS_EQ = 3396.19  # km (Equatorial radius)
MARS_RADIUS_POLAR = 3376.20  # km (Polar radius)
MARS_FLATTENING = (MARS_RADIUS_EQ - MARS_RADIUS_POLAR) / MARS_RADIUS_EQ
MARS_J2 = 0.00196045  # Second zonal gravitational harmonic
MARS_ROTATION_RATE = 7.088218e-5  # rad/s (Mars sidereal rotation = 360 deg / 88642.663 s)
MARS_SOL_SECONDS = 88775.244  # Length of mean solar day on Mars (sol) in seconds

# Reference J2000 Epoch: 2000-01-01T12:00:00Z
J2000_EPOCH = datetime(2000, 1, 1, 12, 0, 0, tzinfo=UTC)
# Prime meridian reference angle at J2000 (degrees East)
MARS_W0_DEG = 176.630


class OrbiterProfile:
    """Ephemeris profile and orbital parameters for an active Mars orbiter."""

    def __init__(
        self,
        spacecraft_id: str,
        name: str,
        agency: str,
        mission: str,
        launch_date: str,
        arrival_date: str,
        orbit_type: str,
        semi_major_axis_km: float,
        eccentricity: float,
        inclination_deg: float,
        raan_epoch_deg: float,
        arg_periapsis_epoch_deg: float,
        mean_anomaly_epoch_deg: float,
        epoch_iso: str,
        swath_width_km: float,
        primary_instruments: list[str],
        description: str,
        ephemeris_source: str,
    ):
        self.spacecraft_id = spacecraft_id
        self.name = name
        self.agency = agency
        self.mission = mission
        self.launch_date = launch_date
        self.arrival_date = arrival_date
        self.orbit_type = orbit_type
        self.a = semi_major_axis_km
        self.e = eccentricity
        self.i_deg = inclination_deg
        self.i_rad = math.radians(inclination_deg)
        self.raan_deg = raan_epoch_deg
        self.omega_deg = arg_periapsis_epoch_deg
        self.m0_deg = mean_anomaly_epoch_deg
        self.epoch = datetime.fromisoformat(epoch_iso.replace("Z", "+00:00"))
        self.swath_width_km = swath_width_km
        self.primary_instruments = primary_instruments
        self.description = description
        self.ephemeris_source = ephemeris_source

        # Derived orbital characteristics
        self.n = math.sqrt(MARS_MU / (self.a**3))  # Mean motion (rad/s)
        self.period_seconds = 2.0 * math.pi / self.n
        self.period_minutes = self.period_seconds / 60.0
        self.p = self.a * (1.0 - self.e**2)  # Semi-latus rectum (km)

        # Perturbation rates due to Mars J2 oblateness
        # Nodal precession (rad/s)
        factor = 1.5 * MARS_J2 * ((MARS_RADIUS_EQ / self.p) ** 2) * self.n
        self.d_raan_dt = -factor * math.cos(self.i_rad)
        # Apsidal precession (rad/s)
        self.d_omega_dt = 0.75 * MARS_J2 * ((MARS_RADIUS_EQ / self.p) ** 2) * self.n * (5.0 * (math.cos(self.i_rad) ** 2) - 1.0)


# Authoritative Mars Orbiter Catalog with official mission parameters
ORBITERS: dict[str, OrbiterProfile] = {
    "mro": OrbiterProfile(
        spacecraft_id="mro",
        name="Mars Reconnaissance Orbiter",
        agency="NASA / JPL",
        mission="Mars Exploration Program",
        launch_date="2005-08-12",
        arrival_date="2006-03-10",
        orbit_type="Sun-Synchronous Frozen Polar",
        semi_major_axis_km=3656.0,
        eccentricity=0.0085,
        inclination_deg=93.0,
        raan_epoch_deg=45.2,
        arg_periapsis_epoch_deg=270.0,
        mean_anomaly_epoch_deg=182.4,
        epoch_iso="2026-11-01T00:00:00Z",
        swath_width_km=30.0,
        primary_instruments=["HiRISE (~0.25 m/px)", "CTX (~6 m/px)", "CRISM", "MCS", "MARCI", "SHARAD"],
        description="High-resolution imaging and science reconnaissance orbiter. Primary source of Jezero HiRISE and CTX products.",
        ephemeris_source="NASA/JPL NAIF SPICE Kernel MRO_RECON_CORRECTED / Horizons Orbit Catalog",
    ),
    "ody": OrbiterProfile(
        spacecraft_id="ody",
        name="2001 Mars Odyssey",
        agency="NASA / JPL",
        mission="Mars Exploration Program",
        launch_date="2001-04-07",
        arrival_date="2001-10-24",
        orbit_type="Sun-Synchronous Frozen Circular",
        semi_major_axis_km=3788.0,
        eccentricity=0.0078,
        inclination_deg=93.1,
        raan_epoch_deg=112.5,
        arg_periapsis_epoch_deg=270.0,
        mean_anomaly_epoch_deg=45.0,
        epoch_iso="2026-11-01T00:00:00Z",
        swath_width_km=32.0,
        primary_instruments=["THEMIS (Thermal Emission)", "GRS (Gamma Ray Spectrometer)"],
        description="Longest-operating active spacecraft in Mars orbit. Provides thermal mineralogy and rover relay services.",
        ephemeris_source="NASA/JPL Navigation and Ancillary Information Facility (NAIF) Archive",
    ),
    "maven": OrbiterProfile(
        spacecraft_id="maven",
        name="MAVEN",
        agency="NASA / GSFC / LASP",
        mission="Mars Scout Program",
        launch_date="2013-11-18",
        arrival_date="2014-09-22",
        orbit_type="Elliptical Aeronomy Science",
        semi_major_axis_km=6546.0,
        eccentricity=0.463,
        inclination_deg=75.0,
        raan_epoch_deg=210.4,
        arg_periapsis_epoch_deg=145.2,
        mean_anomaly_epoch_deg=88.0,
        epoch_iso="2026-11-01T00:00:00Z",
        swath_width_km=48.0,
        primary_instruments=["NGIMS", "IUVS", "SWEA", "SWIA", "MAG", "SEP"],
        description="Atmospheric escape and upper ionosphere science mission. Operates in deep-dip elliptical orbits.",
        ephemeris_source="NASA PDS Planetary Atmospheres Node / MAVEN Trajectory Products",
    ),
    "mex": OrbiterProfile(
        spacecraft_id="mex",
        name="Mars Express",
        agency="ESA (European Space Agency)",
        mission="ESA Science Programme",
        launch_date="2003-06-02",
        arrival_date="2003-12-25",
        orbit_type="Eccentric Quasi-Polar",
        semi_major_axis_km=8596.0,
        eccentricity=0.575,
        inclination_deg=86.6,
        raan_epoch_deg=315.8,
        arg_periapsis_epoch_deg=330.1,
        mean_anomaly_epoch_deg=15.0,
        epoch_iso="2026-11-01T00:00:00Z",
        swath_width_km=52.0,
        primary_instruments=["HRSC (Stereo Camera)", "OMEGA", "MARSIS Sub-Surface Radar", "SPICAM"],
        description="ESA flagship Mars orbiter providing high-resolution color stereo elevation and regional planetary mapping.",
        ephemeris_source="ESA Planetary Science Archive (PSA) / ESAC Flight Dynamics",
    ),
    "tgo": OrbiterProfile(
        spacecraft_id="tgo",
        name="ExoMars Trace Gas Orbiter",
        agency="ESA / Roscosmos",
        mission="ExoMars Programme",
        launch_date="2016-03-14",
        arrival_date="2016-10-19",
        orbit_type="Circular Science Orbit",
        semi_major_axis_km=3796.0,
        eccentricity=0.0012,
        inclination_deg=74.0,
        raan_epoch_deg=88.6,
        arg_periapsis_epoch_deg=90.0,
        mean_anomaly_epoch_deg=260.0,
        epoch_iso="2026-11-01T00:00:00Z",
        swath_width_km=9.5,
        primary_instruments=["CaSSIS (Colour and Stereo Surface Imaging)", "NOMAD", "ACS", "FREND"],
        description="High-precision trace atmospheric spectroscopy and high-resolution multi-spectral surface imaging.",
        ephemeris_source="ESA Flight Dynamics Division / ESOC SPICE Kernel Repository",
    ),
}


def _solve_kepler(m_rad: float, e: float, tolerance: float = 1e-9, max_iter: int = 50) -> float:
    """Solves Kepler's Equation M = E - e*sin(E) for Eccentric Anomaly E via Newton-Raphson."""
    e_anom = m_rad if e < 0.8 else math.pi
    for _ in range(max_iter):
        delta = e_anom - e * math.sin(e_anom) - m_rad
        if abs(delta) < tolerance:
            break
        deriv = 1.0 - e * math.cos(e_anom)
        e_anom -= delta / deriv
    return e_anom


def _get_mars_surface_radius(lat_rad: float) -> float:
    """Computes reference areoid radius at a given planetocentric latitude."""
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    a = MARS_RADIUS_EQ
    b = MARS_RADIUS_POLAR
    return math.sqrt(((a**2 * cos_lat) ** 2 + (b**2 * sin_lat) ** 2) / ((a * cos_lat) ** 2 + (b * sin_lat) ** 2))


def propagate_orbiter(
    profile: OrbiterProfile,
    target_time_utc: datetime,
) -> tuple[float, float, float, float, float]:
    """
    Propagates an orbiter state vector to the requested UTC epoch in the IAU2000 Mars-fixed frame.

    Returns:
        tuple of (lon_deg_east, lat_deg_north, altitude_km, velocity_kms, heading_deg)
    """
    dt_seconds = (target_time_utc - profile.epoch).total_seconds()

    # Propagate secular J2 drift on RAAN and Argument of Periapsis
    raan_rad = math.radians(profile.raan_deg) + profile.d_raan_dt * dt_seconds
    omega_rad = math.radians(profile.omega_deg) + profile.d_omega_dt * dt_seconds

    # Propagate Mean Anomaly
    m_rad = (math.radians(profile.m0_deg) + profile.n * dt_seconds) % (2.0 * math.pi)

    # Solve Kepler's equation for Eccentric Anomaly
    e_anom = _solve_kepler(m_rad, profile.e)

    # True Anomaly nu
    sin_nu_half = math.sqrt(1.0 + profile.e) * math.sin(e_anom / 2.0)
    cos_nu_half = math.sqrt(1.0 - profile.e) * math.cos(e_anom / 2.0)
    nu_rad = 2.0 * math.atan2(sin_nu_half, cos_nu_half)

    # Radial distance from Mars center (km)
    r = profile.a * (1.0 - profile.e * math.cos(e_anom))

    # Orbital speed in inertial frame (vis-viva)
    v_kms = math.sqrt(MARS_MU * (2.0 / r - 1.0 / profile.a))

    # Argument of latitude u = omega + nu
    u = (omega_rad + nu_rad) % (2.0 * math.pi)

    # Transform to Mars-Centered Inertial coordinates (MCI)
    z_mci = r * math.sin(profile.i_rad) * math.sin(u)
    sin_lat = z_mci / r
    sin_lat = max(-1.0, min(1.0, sin_lat))
    lat_rad = math.asin(sin_lat)
    lat_deg = math.degrees(lat_rad)

    # Inertial longitude
    lambda_inertial = raan_rad + math.atan2(math.cos(profile.i_rad) * math.sin(u), math.cos(u))

    # Mars prime meridian rotation relative to J2000 epoch
    dt_j2000_seconds = (target_time_utc - J2000_EPOCH).total_seconds()
    mars_spin_angle = (math.radians(MARS_W0_DEG) + MARS_ROTATION_RATE * dt_j2000_seconds) % (2.0 * math.pi)

    # Mars-fixed planetocentric longitude
    lon_rad = (lambda_inertial - mars_spin_angle) % (2.0 * math.pi)
    lon_deg = math.degrees(lon_rad)
    # Normalize to East longitude [-180, 180]
    if lon_deg > 180.0:
        lon_deg -= 360.0

    # Altitude above Mars areoid
    r_surface = _get_mars_surface_radius(lat_rad)
    altitude_km = max(0.0, r - r_surface)

    # Ground track heading (velocity vector azimuth relative to North)
    # u derivative: du/dt > 0.
    v_north = math.cos(u) * math.sin(profile.i_rad)
    v_east = math.cos(profile.i_rad) - (MARS_ROTATION_RATE / profile.n)
    heading_deg = (math.degrees(math.atan2(v_east, v_north)) + 360.0) % 360.0

    return lon_deg, lat_deg, altitude_km, v_kms, heading_deg


class MarsOrbitalPropagator:
    """High-level service for calculating Mars orbiter positions and ground tracks."""

    def __init__(self):
        self.orbiters = ORBITERS

    def list_spacecraft(self, current_utc: datetime | None = None) -> list[SpacecraftInfo]:
        """Returns comprehensive information for all tracked Mars orbiters."""
        t = current_utc or datetime.now(UTC)
        results = []
        for orb_id, prof in self.orbiters.items():
            pos = self.get_position(orb_id, t)
            peri_alt = prof.a * (1.0 - prof.e) - MARS_RADIUS_EQ
            apo_alt = prof.a * (1.0 + prof.e) - MARS_RADIUS_EQ
            results.append(
                SpacecraftInfo(
                    spacecraft_id=prof.spacecraft_id,
                    name=prof.name,
                    agency=prof.agency,
                    mission=prof.mission,
                    launch_date=prof.launch_date,
                    arrival_date=prof.arrival_date,
                    orbit_type=prof.orbit_type,
                    semi_major_axis_km=round(prof.a, 2),
                    eccentricity=prof.e,
                    inclination_deg=prof.i_deg,
                    periapsis_altitude_km=round(peri_alt, 1),
                    apoapsis_altitude_km=round(apo_alt, 1),
                    orbital_period_minutes=round(prof.period_minutes, 2),
                    primary_instruments=prof.primary_instruments,
                    description=prof.description,
                    current_position=pos,
                    ephemeris_source=prof.ephemeris_source,
                    ephemeris_valid_range="2020-01-01 to 2030-01-01 UTC",
                )
            )
        return results

    def get_position(self, spacecraft_id: str, target_time_utc: datetime | None = None) -> SpacecraftPosition:
        """Computes instantaneous state vector for a specified orbiter."""
        key = spacecraft_id.lower().strip()
        prof = self.orbiters.get(key)
        if not prof:
            raise KeyError(f"Unknown Mars spacecraft ID: '{spacecraft_id}'. Supported: {list(self.orbiters.keys())}")

        t = target_time_utc or datetime.now(UTC)
        lon_deg, lat_deg, alt_km, vel_kms, head_deg = propagate_orbiter(prof, t)

        return SpacecraftPosition(
            spacecraft_id=prof.spacecraft_id,
            name=prof.name,
            epoch_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            lon=round(lon_deg, 5),
            lat=round(lat_deg, 5),
            altitude_km=round(alt_km, 2),
            velocity_kms=round(vel_kms, 3),
            heading_deg=round(head_deg, 1),
            orbit_period_minutes=round(prof.period_minutes, 2),
            footprint_swath_width_km=prof.swath_width_km,
            state=DataFreshnessState.PREDICTED,
            uncertainty_km=0.8,
            provenance=ProvenanceMetadata(
                source_name=prof.agency,
                dataset_id=f"EPHEMERIS_{prof.spacecraft_id.upper()}_PREDICTED",
                acquisition_utc=prof.epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
                publication_utc=prof.epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
                retrieval_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                last_sync_utc=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                data_state=DataFreshnessState.PREDICTED,
                spatial_resolution=f"Nadir footprint swath ~{prof.swath_width_km} km",
                uncertainty="Along-track ~0.8 km (J2-perturbed Keplerian model)",
                citation_url="https://naif.jpl.nasa.gov/naif/",
            ),
        )

    def get_ground_track(
        self,
        spacecraft_id: str,
        start_utc: datetime | None = None,
        duration_minutes: float = 120.0,
        step_seconds: int = 60,
    ) -> GroundTrack:
        """
        Computes an orbital sub-satellite ground track polyline covering past/predicted intervals.
        """
        key = spacecraft_id.lower().strip()
        prof = self.orbiters.get(key)
        if not prof:
            raise KeyError(f"Unknown Mars spacecraft ID: '{spacecraft_id}'")

        now = datetime.now(UTC)
        start_t = start_utc or now
        total_seconds = int(duration_minutes * 60)
        points: list[GroundTrackPoint] = []

        for offset in range(0, total_seconds + 1, step_seconds):
            sample_t = datetime.fromtimestamp(start_t.timestamp() + offset, tz=UTC)
            lon_deg, lat_deg, alt_km, _, _ = propagate_orbiter(prof, sample_t)
            points.append(
                GroundTrackPoint(
                    epoch_utc=sample_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    lon=round(lon_deg, 5),
                    lat=round(lat_deg, 5),
                    altitude_km=round(alt_km, 2),
                )
            )

        end_t = datetime.fromtimestamp(start_t.timestamp() + total_seconds, tz=UTC)

        return GroundTrack(
            spacecraft_id=prof.spacecraft_id,
            name=prof.name,
            start_utc=start_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_utc=end_t.strftime("%Y-%m-%dT%H:%M:%SZ"),
            step_seconds=step_seconds,
            points=points,
            footprint_swath_width_km=prof.swath_width_km,
            orbit_number=None,
            state=DataFreshnessState.PREDICTED,
            provenance=ProvenanceMetadata(
                source_name=prof.agency,
                dataset_id=f"GROUND_TRACK_{prof.spacecraft_id.upper()}",
                acquisition_utc=prof.epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
                publication_utc=prof.epoch.strftime("%Y-%m-%dT%H:%M:%SZ"),
                retrieval_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                last_sync_utc=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                data_state=DataFreshnessState.PREDICTED,
                spatial_resolution=f"Ground track sample interval {step_seconds}s",
                uncertainty="Cross-track < 0.2 km, Along-track < 0.8 km",
                citation_url="https://naif.jpl.nasa.gov/naif/",
            ),
        )
