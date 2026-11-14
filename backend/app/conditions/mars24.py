"""Canonical NASA GISS Mars24 sunclock and solar geometry algorithm.

Reference:
- Allison, M., and M. McEwen, 2000: A post-Pathfinder evaluation of areocentric
  solar coordinates with improved timing recipes for Mars seasonal/diurnal
  climate studies. Planet. Space Sci., 48, 215-235, doi:10.1016/S0032-0633(99)00092-6.
- NASA GISS Mars24 Algorithm Page:
  https://www.giss.nasa.gov/tools/mars24/help/algorithm.html
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

# IERS historical TAI - UTC leap-second step table (effective UTC date -> TAI-UTC seconds).
# TT - UTC = (TAI - UTC) + 32.184 seconds.
_LEAP_SECOND_TABLE: tuple[tuple[datetime, float], ...] = (
    (datetime(1972, 1, 1, 0, 0, 0, tzinfo=UTC), 10.0),
    (datetime(1972, 7, 1, 0, 0, 0, tzinfo=UTC), 11.0),
    (datetime(1973, 1, 1, 0, 0, 0, tzinfo=UTC), 12.0),
    (datetime(1974, 1, 1, 0, 0, 0, tzinfo=UTC), 13.0),
    (datetime(1975, 1, 1, 0, 0, 0, tzinfo=UTC), 14.0),
    (datetime(1976, 1, 1, 0, 0, 0, tzinfo=UTC), 15.0),
    (datetime(1977, 1, 1, 0, 0, 0, tzinfo=UTC), 16.0),
    (datetime(1978, 1, 1, 0, 0, 0, tzinfo=UTC), 17.0),
    (datetime(1979, 1, 1, 0, 0, 0, tzinfo=UTC), 18.0),
    (datetime(1980, 1, 1, 0, 0, 0, tzinfo=UTC), 19.0),
    (datetime(1981, 7, 1, 0, 0, 0, tzinfo=UTC), 20.0),
    (datetime(1982, 7, 1, 0, 0, 0, tzinfo=UTC), 21.0),
    (datetime(1983, 7, 1, 0, 0, 0, tzinfo=UTC), 22.0),
    (datetime(1985, 7, 1, 0, 0, 0, tzinfo=UTC), 23.0),
    (datetime(1988, 1, 1, 0, 0, 0, tzinfo=UTC), 24.0),
    (datetime(1990, 1, 1, 0, 0, 0, tzinfo=UTC), 25.0),
    (datetime(1991, 1, 1, 0, 0, 0, tzinfo=UTC), 26.0),
    (datetime(1992, 7, 1, 0, 0, 0, tzinfo=UTC), 27.0),
    (datetime(1993, 7, 1, 0, 0, 0, tzinfo=UTC), 28.0),
    (datetime(1994, 7, 1, 0, 0, 0, tzinfo=UTC), 29.0),
    (datetime(1996, 1, 1, 0, 0, 0, tzinfo=UTC), 30.0),
    (datetime(1997, 7, 1, 0, 0, 0, tzinfo=UTC), 31.0),
    (datetime(1999, 1, 1, 0, 0, 0, tzinfo=UTC), 32.0),
    (datetime(2006, 1, 1, 0, 0, 0, tzinfo=UTC), 33.0),
    (datetime(2009, 1, 1, 0, 0, 0, tzinfo=UTC), 34.0),
    (datetime(2012, 7, 1, 0, 0, 0, tzinfo=UTC), 35.0),
    (datetime(2015, 7, 1, 0, 0, 0, tzinfo=UTC), 36.0),
    (datetime(2017, 1, 1, 0, 0, 0, tzinfo=UTC), 37.0),
)

# Planetary perturbation terms (Table 1 of Allison & McEwen 2000 / GISS B-3)
_PERTURBERS: tuple[tuple[float, float, float], ...] = (
    (0.0071, 2.2353, 49.409),
    (0.0057, 2.7543, 168.173),
    (0.0039, 1.1177, 191.837),
    (0.0037, 15.7866, 21.736),
    (0.0021, 2.1354, 15.704),
    (0.0020, 2.4694, 95.528),
    (0.0018, 32.8493, 49.095),
)

MARS_SOL_RATIO = 1.0274912517
MARS_SOL_SECONDS = 88775.244147


@dataclass(frozen=True)
class Mars24Result:
    """Complete output of the NASA GISS Mars24 solar geometry calculation."""

    utc_iso: str
    latitude_deg: float
    longitude_east_deg: float
    longitude_west_deg: float
    tt_minus_utc_s: float
    jd_ut: float
    jd_tt: float
    delta_t_j2000: float
    mean_anomaly_deg: float
    alpha_fms_deg: float
    perturbers_deg: float
    equation_of_center_deg: float
    ls_deg: float
    eot_deg: float
    eot_hours: float
    msd: float
    mtc_hours: float
    mtc_hms: str
    lmst_hours: float
    lmst_hms: str
    ltst_hours: float
    ltst_hms: str
    solar_declination_deg: float
    heliocentric_distance_au: float
    subsolar_lon_east_deg: float
    subsolar_lon_west_deg: float
    hour_angle_deg: float
    solar_zenith_deg: float
    solar_elevation_deg: float
    solar_azimuth_deg: float
    sunrise_ltst_hours: float | None
    sunset_ltst_hours: float | None
    daylight_mars_hours: float
    daylight_earth_hours: float
    polar_day_state: str  # "NORMAL_DIURNAL" | "POLAR_CONTINUOUS_DAY" | "POLAR_CONTINUOUS_NIGHT"
    is_daylight: bool
    mars_season_northern: str
    perseverance_mission_sol: int | None


def parse_utc_datetime(utc_input: str | datetime | None) -> datetime:
    """Parse an ISO-8601 UTC string or datetime into a timezone-aware UTC datetime.

    Rejects timezone-naive strings or datetimes with a ValueError.
    """
    if utc_input is None:
        return datetime.now(UTC)
    if isinstance(utc_input, datetime):
        if utc_input.tzinfo is None:
            raise ValueError(
                "Timezone-naive datetime is not permitted. Supply a timezone-aware ISO 8601 timestamp (e.g. ending in 'Z' or '+00:00')."
            )
        return utc_input.astimezone(UTC)

    raw = str(utc_input).strip()
    # Check for timezone indicator
    has_z = raw.endswith("Z") or raw.endswith("z")
    has_offset = False
    if len(raw) >= 6 and (raw[-6] in ("+", "-") or raw[-5] in ("+", "-")):
        has_offset = True

    if not (has_z or has_offset):
        raise ValueError(
            f"Timezone-naive ISO 8601 timestamp '{raw}' rejected: timestamp must explicitly specify a timezone (e.g. 'Z' or '+00:00')."
        )

    if has_z:
        raw = raw[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(raw)
    except Exception as exc:
        raise ValueError(f"Malformed ISO 8601 timestamp '{utc_input}': {exc}") from exc

    if dt.tzinfo is None:
        raise ValueError(
            f"Timezone-naive ISO 8601 timestamp '{utc_input}' rejected: timestamp must explicitly specify a timezone."
        )
    return dt.astimezone(UTC)


def utc_to_tt_offset_seconds(dt_utc: datetime) -> float:
    """Return TT - UTC in seconds for a given UTC datetime using the IERS leap-second table."""
    dt = parse_utc_datetime(dt_utc)
    tai_minus_utc = 10.0
    for effective_dt, offset_s in _LEAP_SECOND_TABLE:
        if dt >= effective_dt:
            tai_minus_utc = offset_s
        else:
            break
    if dt < _LEAP_SECOND_TABLE[0][0]:
        # Pre-1972 polynomial approximation from GISS Mars24 A-2
        year_frac = dt.year + (dt.timetuple().tm_yday - 1) / 365.25
        c = (year_frac - 1820.0) / 100.0
        return -20.0 + 32.0 * (c * c)
    return tai_minus_utc + 32.184


def format_mars_hms(hours_val: float) -> str:
    """Format fractional Mars hours [0, 24) as HH:MM:SS."""
    h_norm = hours_val % 24.0
    total_seconds = int(round(h_norm * 3600.0)) % 86400
    hh = total_seconds // 3600
    mm = (total_seconds % 3600) // 60
    ss = total_seconds % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _northern_season_from_ls(ls_deg: float) -> str:
    ls = ls_deg % 360.0
    if ls < 90.0:
        return "Northern Spring / Southern Autumn"
    if ls < 180.0:
        return "Northern Summer / Southern Winter"
    if ls < 270.0:
        return "Northern Autumn / Southern Spring"
    return "Northern Winter / Southern Summer"


def compute_mars24(
    latitude_deg: float,
    longitude_east_deg: float,
    utc_time: str | datetime | None = None,
) -> Mars24Result:
    """Execute the NASA GISS Mars24 solar geometry and timekeeping algorithm.

    Parameters
    ----------
    latitude_deg:
        Planetocentric latitude in degrees [-90, 90].
    longitude_east_deg:
        Positive-east longitude in degrees [-180, 360].
    utc_time:
        UTC timestamp (ISO-8601 string or datetime). Defaults to current UTC.
    """
    if not math.isfinite(latitude_deg) or not math.isfinite(longitude_east_deg):
        raise ValueError("Latitude and longitude must be finite numerical values.")
    if not (-90.0 <= latitude_deg <= 90.0):
        raise ValueError(f"Latitude must be within [-90, 90], got {latitude_deg}")

    # Normalize longitude into [0, 360)
    longitude_east_deg = longitude_east_deg % 360.0
    if longitude_east_deg < 0.0:
        longitude_east_deg += 360.0

    dt_utc = parse_utc_datetime(utc_time)
    epoch_ms = dt_utc.timestamp() * 1000.0

    # Normalize East and West longitudes into [0, 360)
    lon_e_norm = longitude_east_deg % 360.0
    lon_w_norm = (360.0 - lon_e_norm) % 360.0

    # Step A-1: Julian Date (UT)
    jd_ut = 2440587.5 + (epoch_ms / 8.64e7)

    # Step A-2 & A-3: UTC to TT conversion and JD_TT
    tt_minus_utc = utc_to_tt_offset_seconds(dt_utc)
    jd_tt = jd_ut + (tt_minus_utc / 86400.0)

    # Step A-4: Days since J2000.0 epoch (TT)
    delta_t_j2000 = jd_tt - 2451545.0

    # Step B-1: Mars Mean Anomaly (M)
    m_deg = (19.3871 + 0.52402073 * delta_t_j2000) % 360.0
    m_rad = math.radians(m_deg)

    # Step B-2: Angle of Fiction Mean Sun (alpha_FMS)
    alpha_fms_deg = (270.3871 + 0.524038496 * delta_t_j2000) % 360.0

    # Step B-3: Perturbers (PBS)
    pbs_deg = 0.0
    for amp, tau, phi in _PERTURBERS:
        arg_deg = (0.985626 * delta_t_j2000 / tau) + phi
        pbs_deg += amp * math.cos(math.radians(arg_deg))

    # Step B-4: Equation of Center (v - M)
    v_minus_m_deg = (
        (10.691 + 3.0e-7 * delta_t_j2000) * math.sin(m_rad)
        + 0.623 * math.sin(2.0 * m_rad)
        + 0.050 * math.sin(3.0 * m_rad)
        + 0.005 * math.sin(4.0 * m_rad)
        + 0.0005 * math.sin(5.0 * m_rad)
        + pbs_deg
    )

    # Step B-5: Areocentric solar longitude (Ls)
    ls_deg = (alpha_fms_deg + v_minus_m_deg) % 360.0
    ls_rad = math.radians(ls_deg)

    # Step C-1: Equation of Time (EOT)
    eot_deg = (
        2.861 * math.sin(2.0 * ls_rad)
        - 0.071 * math.sin(4.0 * ls_rad)
        + 0.002 * math.sin(6.0 * ls_rad)
        - v_minus_m_deg
    )
    eot_hours = eot_deg / 15.0

    # Step C-2: Mars Sol Date (MSD) & Coordinated Mars Time (MTC)
    msd = ((delta_t_j2000 - 4.5) / MARS_SOL_RATIO) + 44796.0 - 0.0009626
    mtc_hours = (24.0 * msd) % 24.0

    # Step C-3: Local Mean Solar Time (LMST) & Local True Solar Time (LTST)
    lmst_hours = (mtc_hours - (lon_w_norm / 15.0)) % 24.0
    ltst_hours = (lmst_hours + eot_hours) % 24.0

    # Step D-1: Solar Declination (delta_s)
    sin_ls = math.sin(ls_rad)
    delta_s_deg = math.degrees(math.asin(0.42565 * sin_ls)) + 0.25 * sin_ls
    delta_s_rad = math.radians(delta_s_deg)

    # Step D-2: Heliocentric distance (R_M in AU)
    r_m_au = 1.52367934 * (
        1.00436
        - 0.09309 * math.cos(m_rad)
        - 0.004336 * math.cos(2.0 * m_rad)
        - 0.00031 * math.cos(3.0 * m_rad)
        - 0.00003 * math.cos(4.0 * m_rad)
    )

    # Step D-3: Subsolar longitude & local hour angle (H)
    subsolar_lon_w = ((mtc_hours * 15.0) + eot_deg + 180.0) % 360.0
    subsolar_lon_e = (360.0 - subsolar_lon_w) % 360.0
    # Normalize East subsolar longitude into [-180, 180]
    if subsolar_lon_e > 180.0:
        subsolar_lon_e -= 360.0

    hour_angle_deg = (ltst_hours - 12.0) * 15.0
    hour_angle_rad = math.radians(hour_angle_deg)

    # Step D-4: Local Solar Zenith (Z) and Solar Elevation (E)
    lat_rad = math.radians(latitude_deg)
    cos_z = (
        math.sin(lat_rad) * math.sin(delta_s_rad)
        + math.cos(lat_rad) * math.cos(delta_s_rad) * math.cos(hour_angle_rad)
    )
    cos_z = max(-1.0, min(1.0, cos_z))
    zenith_deg = math.degrees(math.acos(cos_z))
    elevation_deg = 90.0 - zenith_deg

    # Step D-5: Local Solar Azimuth (A, clockwise from North [0, 360))
    y_az = -math.cos(delta_s_rad) * math.sin(hour_angle_rad)
    x_az = (
        math.cos(lat_rad) * math.sin(delta_s_rad)
        - math.sin(lat_rad) * math.cos(delta_s_rad) * math.cos(hour_angle_rad)
    )
    if abs(x_az) < 1e-12 and abs(y_az) < 1e-12:
        azimuth_deg = 0.0
    else:
        azimuth_deg = math.degrees(math.atan2(y_az, x_az)) % 360.0

    # Sunrise / Sunset & Polar continuous day/night check
    # cos(H0) = -tan(lat) * tan(delta_s)
    cos_lat = math.cos(lat_rad)
    cos_dec = math.cos(delta_s_rad)
    if abs(cos_lat) < 1e-12 or abs(cos_dec) < 1e-12:
        cos_h0 = -math.copysign(2.0, latitude_deg * delta_s_deg)
    else:
        cos_h0 = -math.tan(lat_rad) * math.tan(delta_s_rad)

    if cos_h0 <= -1.0:
        polar_day_state = "POLAR_CONTINUOUS_DAY"
        sunrise_ltst = None
        sunset_ltst = None
        daylight_mars_hours = 24.0
    elif cos_h0 >= 1.0:
        polar_day_state = "POLAR_CONTINUOUS_NIGHT"
        sunrise_ltst = None
        sunset_ltst = None
        daylight_mars_hours = 0.0
    else:
        polar_day_state = "NORMAL_DIURNAL"
        h0_deg = math.degrees(math.acos(cos_h0))
        half_day_hours = h0_deg / 15.0
        sunrise_ltst = (12.0 - half_day_hours) % 24.0
        sunset_ltst = (12.0 + half_day_hours) % 24.0
        daylight_mars_hours = 2.0 * half_day_hours

    daylight_earth_hours = daylight_mars_hours * MARS_SOL_RATIO

    # Perseverance Mission Sol (Landing: 2021-02-18T20:55:00Z, MSD ~ 52304.1476, lon 77.45089E)
    # Sol 0 starts at midnight LMST prior to landing (MSD_landing_midnight_jezero = 52303.78366)
    perseverance_landing_utc = datetime(2021, 2, 18, 20, 55, 0, tzinfo=UTC)
    if dt_utc < perseverance_landing_utc:
        perseverance_sol = None
    else:
        # Jezero landing site longitude 77.45089E -> +5.16339 hours from MTC
        jezero_sol_number = msd + (77.45089 / 360.0) - 52304.0
        perseverance_sol = max(0, int(math.floor(jezero_sol_number)))

    return Mars24Result(
        utc_iso=dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        latitude_deg=round(latitude_deg, 6),
        longitude_east_deg=round(longitude_east_deg, 6),
        longitude_west_deg=round(lon_w_norm, 6),
        tt_minus_utc_s=round(tt_minus_utc, 3),
        jd_ut=round(jd_ut, 7),
        jd_tt=round(jd_tt, 7),
        delta_t_j2000=round(delta_t_j2000, 7),
        mean_anomaly_deg=round(m_deg, 5),
        alpha_fms_deg=round(alpha_fms_deg, 5),
        perturbers_deg=round(pbs_deg, 5),
        equation_of_center_deg=round(v_minus_m_deg, 5),
        ls_deg=round(ls_deg, 5),
        eot_deg=round(eot_deg, 5),
        eot_hours=round(eot_hours, 5),
        msd=round(msd, 5),
        mtc_hours=round(mtc_hours, 5),
        mtc_hms=format_mars_hms(mtc_hours),
        lmst_hours=round(lmst_hours, 5),
        lmst_hms=format_mars_hms(lmst_hours),
        ltst_hours=round(ltst_hours, 5),
        ltst_hms=format_mars_hms(ltst_hours),
        solar_declination_deg=round(delta_s_deg, 5),
        heliocentric_distance_au=round(r_m_au, 6),
        subsolar_lon_east_deg=round(subsolar_lon_e, 5),
        subsolar_lon_west_deg=round(subsolar_lon_w, 5),
        hour_angle_deg=round(hour_angle_deg, 5),
        solar_zenith_deg=round(zenith_deg, 5),
        solar_elevation_deg=round(elevation_deg, 5),
        solar_azimuth_deg=round(azimuth_deg, 5),
        sunrise_ltst_hours=round(sunrise_ltst, 5) if sunrise_ltst is not None else None,
        sunset_ltst_hours=round(sunset_ltst, 5) if sunset_ltst is not None else None,
        daylight_mars_hours=round(daylight_mars_hours, 5),
        daylight_earth_hours=round(daylight_earth_hours, 5),
        polar_day_state=polar_day_state,
        is_daylight=elevation_deg > 0.0,
        mars_season_northern=_northern_season_from_ls(ls_deg),
        perseverance_mission_sol=perseverance_sol,
    )
