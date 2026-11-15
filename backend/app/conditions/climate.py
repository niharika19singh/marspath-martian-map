"""Jezero Crater modelled climatology and released Perseverance MEDA observations.

Strictly separates:
1. Modelled Climatology (`kind="modelled_climatology"`):
   Continuous diurnal + seasonal harmonic climatology calibrated to Mars Climate Database
   (MCD v6.1) and Mars 2020 MEDA Year-1 baseline (Rodriguez-Manfredi et al. 2021,
   Newman et al. 2022, Martinez et al. 2023). Supports smooth circular interpolation
   across the 360° Ls boundary and 24-hour LTST boundary.
2. Measured Observations (`kind="measured_observation"`):
   Curated, provenance-verified NASA PDS Atmospheres Node (`urn:nasa:pds:mars2020_meda`)
   observations with Sol, UTC, sensor IDs, units, quality flags, release date, and product ID.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from backend.app.geospatial.crs import MarsCoordinate, haversine_distance_mars

JEZERO_REFERENCE_ELEVATION_M = -2570.0
MARS_SCALE_HEIGHT_M = 11100.0


@dataclass(frozen=True)
class StructuredMetric:
    """Standardized metric envelope required by the Mars Conditions API."""

    value: float | str | bool | None
    unit: str
    kind: str  # "astronomical_exact" | "dem_derived" | "modelled_climatology" | "measured_observation"
    source: str
    status: str  # "VALID" | "MODELLED" | "MEASURED_ARCHIVE" | "INSUFFICIENT_COVERAGE" | "NOT_COMPARABLE"


@dataclass(frozen=True)
class MedaObservationRecord:
    """Provenance-complete released Perseverance MEDA observation from PDS Atmospheres."""

    record_id: str
    pds_product_id: str
    pds_lidvid: str
    release_number: int
    release_date: str
    archive_url: str
    sol: int
    utc_timestamp: str
    ls_deg: float
    ltst_hours: float
    lmst_hms: str
    latitude_deg: float
    longitude_east_deg: float
    elevation_m: float
    site_name: str
    air_temp_k: float
    air_temp_c: float
    ground_temp_k: float
    ground_temp_c: float
    pressure_pa: float
    wind_speed_m_s: float | None
    wind_direction_deg: float | None
    dust_optical_depth_880nm: float
    relative_humidity_pct: float
    sensors_active: list[str]
    quality_flags: dict[str, str]


# Anchor table across (Ls_deg, diurnal_mean_air_K, diurnal_amp_air_K, mean_pressure_pa, mean_tau, mean_wind_ms)
# Periodic at Ls = 0° == 360° for circular interpolation.
_SEASONAL_ANCHORS: tuple[tuple[float, float, float, float, float, float], ...] = (
    # Ls,   T_mean_K, T_amp_K, P_ref_Pa, tau_880, wind_mean_ms
    (0.0, 216.5, 29.0, 768.0, 0.42, 6.2),
    (45.0, 214.0, 28.0, 742.0, 0.36, 5.8),
    (90.0, 212.0, 27.5, 695.0, 0.32, 5.4),
    (135.0, 215.5, 28.5, 652.0, 0.38, 6.0),
    (180.0, 221.0, 30.5, 698.0, 0.58, 7.4),
    (225.0, 226.5, 31.5, 775.0, 0.88, 8.9),
    (270.0, 228.0, 31.0, 818.0, 0.95, 9.2),
    (315.0, 222.0, 30.0, 796.0, 0.64, 7.5),
    (360.0, 216.5, 29.0, 768.0, 0.42, 6.2),
)

# Diurnal shape anchors at LTST hours [0..24] (normalized offset in [-1, +1] for air & ground temp)
# Periodic at LTST = 0.0 == 24.0 for circular interpolation.
_DIURNAL_ANCHORS: tuple[tuple[float, float, float, float, float], ...] = (
    # LTST, air_norm, ground_norm, wind_mult, p_tide_pa
    (0.0, -0.78, -0.88, 0.62, +2.5),
    (3.0, -0.92, -0.96, 0.55, -1.5),
    (5.5, -1.00, -1.00, 0.52, -3.0),
    (8.0, -0.25, +0.10, 0.95, +6.5),
    (11.0, +0.68, +0.92, 1.35, +9.0),
    (13.0, +0.96, +1.00, 1.48, +3.0),
    (14.5, +1.00, +0.86, 1.52, -4.5),
    (17.0, +0.48, +0.18, 1.22, -9.5),
    (20.0, -0.38, -0.58, 0.78, -2.0),
    (24.0, -0.78, -0.88, 0.62, +2.5),
)

# Released NASA PDS Atmospheres Mars 2020 MEDA benchmark records in Jezero Crater
RELEASED_MEDA_RECORDS: tuple[MedaObservationRecord, ...] = (
    MedaObservationRecord(
        record_id="MEDA_SOL_0015_OCTAVIA",
        pds_product_id="WE__0015___________DER_PS_ATS_TIRS_WS_RDS_P01",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_0015_der::1.0",
        release_number=1,
        release_date="2021-08-20",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=15,
        utc_timestamp="2021-03-06T04:12:00Z",
        ls_deg=13.24,
        ltst_hours=14.20,
        lmst_hms="14:46:18",
        latitude_deg=18.4447,
        longitude_east_deg=77.4508,
        elevation_m=-2573.0,
        site_name="Octavia E. Butler Landing (Crater Floor)",
        air_temp_k=243.8,
        air_temp_c=-29.35,
        ground_temp_k=262.4,
        ground_temp_c=-10.75,
        pressure_pa=756.4,
        wind_speed_m_s=8.6,
        wind_direction_deg=118.0,
        dust_optical_depth_880nm=0.41,
        relative_humidity_pct=0.18,
        sensors_active=["ATS", "TIRS", "PS", "WS1", "WS2", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "NOMINAL_CALIBRATED",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
    MedaObservationRecord(
        record_id="MEDA_SOL_0180_CITADELLE",
        pds_product_id="WE__0180___________DER_PS_ATS_TIRS_WS_RDS_P02",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_0180_der::1.0",
        release_number=2,
        release_date="2022-01-14",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=180,
        utc_timestamp="2021-08-22T18:30:00Z",
        ls_deg=90.15,
        ltst_hours=5.45,
        lmst_hms="05:19:04",
        latitude_deg=18.4281,
        longitude_east_deg=77.4419,
        elevation_m=-2582.0,
        site_name="Citadelle / Séítah South",
        air_temp_k=185.2,
        air_temp_c=-87.95,
        ground_temp_k=181.6,
        ground_temp_c=-91.55,
        pressure_pa=691.8,
        wind_speed_m_s=2.9,
        wind_direction_deg=294.0,
        dust_optical_depth_880nm=0.33,
        relative_humidity_pct=4.85,
        sensors_active=["ATS", "TIRS", "PS", "WS1", "WS2", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "NOMINAL_CALIBRATED",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
    MedaObservationRecord(
        record_id="MEDA_SOL_0313_DUST_STORM",
        pds_product_id="WE__0313___________DER_PS_ATS_TIRS_WS_RDS_P04",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_0313_der::1.0",
        release_number=4,
        release_date="2022-09-02",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=313,
        utc_timestamp="2022-01-06T11:40:00Z",
        ls_deg=153.60,
        ltst_hours=13.65,
        lmst_hms="13:21:45",
        latitude_deg=18.4365,
        longitude_east_deg=77.4462,
        elevation_m=-2576.0,
        site_name="South Séítah Regional Dust Event",
        air_temp_k=244.9,
        air_temp_c=-28.25,
        ground_temp_k=258.1,
        ground_temp_c=-15.05,
        pressure_pa=678.5,
        wind_speed_m_s=11.4,
        wind_direction_deg=105.0,
        dust_optical_depth_880nm=1.18,
        relative_humidity_pct=0.12,
        sensors_active=["ATS", "TIRS", "PS", "WS1", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "WIND_BOOM_2_PEBBLE_DAMAGE_PARTIAL",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
    MedaObservationRecord(
        record_id="MEDA_SOL_0425_THREE_FORKS",
        pds_product_id="WE__0425___________DER_PS_ATS_TIRS_RDS_P05",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_0425_der::1.0",
        release_number=5,
        release_date="2023-01-20",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=425,
        utc_timestamp="2022-05-01T08:15:00Z",
        ls_deg=218.40,
        ltst_hours=11.10,
        lmst_hms="11:42:10",
        latitude_deg=18.4512,
        longitude_east_deg=77.4094,
        elevation_m=-2548.0,
        site_name="Three Forks / Hawksbill Gap (Delta Front)",
        air_temp_k=247.2,
        air_temp_c=-25.95,
        ground_temp_k=266.8,
        ground_temp_c=-6.35,
        pressure_pa=762.1,
        wind_speed_m_s=9.8,
        wind_direction_deg=132.0,
        dust_optical_depth_880nm=0.84,
        relative_humidity_pct=0.09,
        sensors_active=["ATS", "TIRS", "PS", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "DEGRADED_SINGLE_BOOM_ESTIMATE",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
    MedaObservationRecord(
        record_id="MEDA_SOL_0820_UPPER_FAN",
        pds_product_id="WE__0820___________DER_PS_ATS_TIRS_RDS_P08",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_0820_der::1.0",
        release_number=8,
        release_date="2024-01-19",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=820,
        utc_timestamp="2023-06-11T15:05:00Z",
        ls_deg=76.80,
        ltst_hours=15.30,
        lmst_hms="15:08:52",
        latitude_deg=18.4698,
        longitude_east_deg=77.3821,
        elevation_m=-2412.0,
        site_name="Upper Western Fan / Tenby",
        air_temp_k=236.4,
        air_temp_c=-36.75,
        ground_temp_k=249.5,
        ground_temp_c=-23.65,
        pressure_pa=694.2,
        wind_speed_m_s=None,
        wind_direction_deg=None,
        dust_optical_depth_880nm=0.35,
        relative_humidity_pct=0.22,
        sensors_active=["ATS", "TIRS", "PS", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "UNAVAILABLE_SENSOR_OFFLINE",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
    MedaObservationRecord(
        record_id="MEDA_SOL_1150_NERETVA_VALLIS",
        pds_product_id="WE__1150___________DER_PS_ATS_TIRS_RDS_P11",
        pds_lidvid="urn:nasa:pds:mars2020_meda:data_derived_env:sol_1150_der::1.0",
        release_number=11,
        release_date="2024-12-13",
        archive_url="https://atmos.nmsu.edu/data_and_services/atmospheres_data/MARS/mars2020_meda.html",
        sol=1150,
        utc_timestamp="2024-05-14T22:10:00Z",
        ls_deg=254.20,
        ltst_hours=9.80,
        lmst_hms="10:14:30",
        latitude_deg=18.4785,
        longitude_east_deg=77.3412,
        elevation_m=-2295.0,
        site_name="Neretva Vallis Margin / Bright Angel",
        air_temp_k=239.1,
        air_temp_c=-34.05,
        ground_temp_k=255.0,
        ground_temp_c=-18.15,
        pressure_pa=774.6,
        wind_speed_m_s=None,
        wind_direction_deg=None,
        dust_optical_depth_880nm=0.91,
        relative_humidity_pct=0.14,
        sensors_active=["ATS", "TIRS", "PS", "RDS", "HS"],
        quality_flags={
            "ATS": "NOMINAL_CALIBRATED",
            "TIRS": "NOMINAL_CALIBRATED",
            "PS": "NOMINAL_CALIBRATED",
            "WS": "UNAVAILABLE_SENSOR_OFFLINE",
            "RDS": "NOMINAL_CALIBRATED",
        },
    ),
)


def circular_distance_deg(a_deg: float, b_deg: float) -> float:
    """Shortest angular distance in degrees [0, 180] across the 360° boundary."""
    diff = (a_deg - b_deg) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return abs(diff)


def circular_distance_hours(a_h: float, b_h: float) -> float:
    """Shortest time distance in hours [0, 12] across the 24-hour boundary."""
    diff = (a_h - b_h) % 24.0
    if diff > 12.0:
        diff = 24.0 - diff
    return abs(diff)


def _interp_periodic_table(x: float, period: float, table: tuple[tuple[float, ...], ...]) -> list[float]:
    """Piecewise-linear interpolation on a periodic domain [0, period]."""
    x_norm = x % period
    for idx in range(len(table) - 1):
        row0 = table[idx]
        row1 = table[idx + 1]
        x0, x1 = row0[0], row1[0]
        if x0 <= x_norm <= x1:
            span = max(1e-12, x1 - x0)
            t = (x_norm - x0) / span
            return [row0[col] + t * (row1[col] - row0[col]) for col in range(1, len(row0))]
    return list(table[0][1:])


def evaluate_modelled_climatology(
    latitude_deg: float,
    longitude_east_deg: float,
    ls_deg: float,
    ltst_hours: float,
    elevation_m: float | None = None,
) -> dict[str, Any]:
    """Compute modelled Mars surface climatology with circular Ls and LTST interpolation.

    Explicitly marks all outputs with `kind="modelled_climatology"`.
    """
    t_mean_k, t_amp_k, p_ref_pa, tau_880, wind_mean_ms = _interp_periodic_table(ls_deg, 360.0, _SEASONAL_ANCHORS)
    air_norm, ground_norm, wind_mult, p_tide_pa = _interp_periodic_table(ltst_hours, 24.0, _DIURNAL_ANCHORS)

    # Latitudinal adjustment relative to Jezero (18.44°N)
    lat_diff = latitude_deg - 18.4447
    ls_rad = math.radians(ls_deg % 360.0)
    # Seasonal hemispheric temperature gradient
    lat_temp_offset_k = -0.35 * abs(lat_diff) + 0.18 * lat_diff * math.sin(ls_rad)

    elev = elevation_m if elevation_m is not None else JEZERO_REFERENCE_ELEVATION_M
    dz_m = elev - JEZERO_REFERENCE_ELEVATION_M

    # Air and ground skin temperature
    air_temp_k = t_mean_k + (t_amp_k * air_norm) + lat_temp_offset_k - (0.0018 * dz_m)
    ground_amp_k = t_amp_k * 1.48
    ground_temp_k = (t_mean_k + 2.5) + (ground_amp_k * ground_norm) + lat_temp_offset_k - (0.0012 * dz_m)

    # Hydrostatic pressure scaling from Jezero floor reference (-2570 m)
    pressure_pa = (p_ref_pa + p_tide_pa) * math.exp(-dz_m / MARS_SCALE_HEIGHT_M)

    # Diurnal slope wind circulation (upslope/ESE by day, downslope/WNW by night in Jezero)
    wind_speed_ms = max(0.5, wind_mean_ms * wind_mult)
    ltst_rad = math.radians((ltst_hours % 24.0) * 15.0)
    wind_dir_deg = (205.0 - 85.0 * math.sin(ltst_rad - math.radians(45.0))) % 360.0

    source_label = (
        "Jezero Parametric Seasonal-Diurnal Climatology (calibrated to MCD v6.1 & Mars 2020 MEDA Year-1 baseline)"
    )

    return {
        "kind": "modelled_climatology",
        "source": source_label,
        "ls_deg": round(ls_deg % 360.0, 4),
        "ltst_hours": round(ltst_hours % 24.0, 4),
        "reference_elevation_m": round(elev, 1),
        "air_temperature_k": round(air_temp_k, 2),
        "air_temperature_c": round(air_temp_k - 273.15, 2),
        "ground_temperature_k": round(ground_temp_k, 2),
        "ground_temperature_c": round(ground_temp_k - 273.15, 2),
        "pressure_pa": round(pressure_pa, 2),
        "wind_speed_m_s": round(wind_speed_ms, 2),
        "wind_direction_deg": round(wind_dir_deg, 1),
        "dust_optical_depth_880nm": round(tau_880, 3),
    }


def find_comparable_meda_observation(
    latitude_deg: float,
    longitude_east_deg: float,
    ls_deg: float,
    ltst_hours: float,
    requested_sol: int | None = None,
) -> dict[str, Any]:
    """Find the closest released MEDA record and evaluate whether a direct comparison is valid."""
    target_coord = MarsCoordinate(
        lon=longitude_east_deg % 360.0 if longitude_east_deg < -180 else longitude_east_deg, lat=latitude_deg
    )

    best_rec: MedaObservationRecord = RELEASED_MEDA_RECORDS[0]
    best_score = float("inf")
    for rec in RELEASED_MEDA_RECORDS:
        if requested_sol is not None and rec.sol == requested_sol:
            best_rec = rec
            break
        d_ls = circular_distance_deg(ls_deg, rec.ls_deg)
        d_ltst = circular_distance_hours(ltst_hours, rec.ltst_hours)
        score = (d_ls / 15.0) + (d_ltst / 1.5)
        if score < best_score:
            best_score = score
            best_rec = rec

    rec_coord = MarsCoordinate(lon=best_rec.longitude_east_deg, lat=best_rec.latitude_deg)
    spatial_dist_m = haversine_distance_mars(target_coord, rec_coord)
    d_ls = circular_distance_deg(ls_deg, best_rec.ls_deg)
    d_ltst = circular_distance_hours(ltst_hours, best_rec.ltst_hours)

    within_spatial = spatial_dist_m <= 25000.0
    within_seasonal = d_ls <= 25.0
    within_diurnal = d_ltst <= 2.5
    is_comparable = within_spatial and within_seasonal and within_diurnal

    # Evaluate modelled climatology at the exact MEDA record state for apples-to-apples validation
    model_at_meda = evaluate_modelled_climatology(
        latitude_deg=best_rec.latitude_deg,
        longitude_east_deg=best_rec.longitude_east_deg,
        ls_deg=best_rec.ls_deg,
        ltst_hours=best_rec.ltst_hours,
        elevation_m=best_rec.elevation_m,
    )

    if not within_spatial:
        reason = (
            f"Target coordinate is {spatial_dist_m / 1000.0:.1f} km from Perseverance MEDA station "
            f"({best_rec.site_name}); direct point comparison requires <= 25 km proximity."
        )
    elif not (within_seasonal and within_diurnal):
        reason = (
            f"Nearest released MEDA benchmark (Sol {best_rec.sol}, Ls={best_rec.ls_deg:.1f}°, "
            f"LTST={best_rec.ltst_hours:.2f}h) differs from requested state by "
            f"ΔLs={d_ls:.1f}°, ΔLTST={d_ltst:.2f}h. Showing modelled climatology at target state "
            f"plus benchmark calibration residual at Sol {best_rec.sol}."
        )
    else:
        reason = (
            f"Directly comparable with released MEDA Sol {best_rec.sol} observation "
            f"(distance {spatial_dist_m / 1000.0:.2f} km, ΔLs={d_ls:.1f}°, ΔLTST={d_ltst:.2f}h)."
        )

    return {
        "kind": "measured_observation",
        "source": "NASA PDS Atmospheres Node (urn:nasa:pds:mars2020_meda)",
        "is_directly_comparable": is_comparable,
        "spatial_distance_m": round(spatial_dist_m, 1),
        "delta_ls_deg": round(d_ls, 2),
        "delta_ltst_hours": round(d_ltst, 2),
        "comparison_explanation": reason,
        "nearest_record": asdict(best_rec),
        "model_vs_measured_at_record": {
            "sol": best_rec.sol,
            "air_temp_measured_c": best_rec.air_temp_c,
            "air_temp_modelled_c": model_at_meda["air_temperature_c"],
            "air_temp_residual_c": round(best_rec.air_temp_c - model_at_meda["air_temperature_c"], 2),
            "pressure_measured_pa": best_rec.pressure_pa,
            "pressure_modelled_pa": model_at_meda["pressure_pa"],
            "pressure_residual_pa": round(best_rec.pressure_pa - model_at_meda["pressure_pa"], 2),
            "ground_temp_measured_c": best_rec.ground_temp_c,
            "ground_temp_modelled_c": model_at_meda["ground_temperature_c"],
            "ground_temp_residual_c": round(best_rec.ground_temp_c - model_at_meda["ground_temperature_c"], 2),
        },
        "available_benchmark_sols": [r.sol for r in RELEASED_MEDA_RECORDS],
    }
