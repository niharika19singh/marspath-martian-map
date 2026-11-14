/**
 * Mars Now, NASA GISS Mars24 Solar Geometry, and Conditions Client.
 *
 * Implements the canonical Allison & McEwen (2000) Mars24 algorithm for
 * high-precision real-time Martian solar coordinates and connects to
 * the backend GET /api/v1/conditions endpoint with graceful client fallback.
 */

import { AUTHORITATIVE_MARS_TERRAIN_CATALOG } from './wmts_capabilities.js';

// Historical leap-second step table (effective UTC date -> TAI - UTC seconds)
// TT - UTC = (TAI - UTC) + 32.184 s
const LEAP_SECONDS = [
  { ts: Date.UTC(1972, 0, 1), offset: 10.0 },
  { ts: Date.UTC(1972, 6, 1), offset: 11.0 },
  { ts: Date.UTC(1973, 0, 1), offset: 12.0 },
  { ts: Date.UTC(1974, 0, 1), offset: 13.0 },
  { ts: Date.UTC(1975, 0, 1), offset: 14.0 },
  { ts: Date.UTC(1976, 0, 1), offset: 15.0 },
  { ts: Date.UTC(1977, 0, 1), offset: 16.0 },
  { ts: Date.UTC(1978, 0, 1), offset: 17.0 },
  { ts: Date.UTC(1979, 0, 1), offset: 18.0 },
  { ts: Date.UTC(1980, 0, 1), offset: 19.0 },
  { ts: Date.UTC(1981, 6, 1), offset: 20.0 },
  { ts: Date.UTC(1982, 6, 1), offset: 21.0 },
  { ts: Date.UTC(1983, 6, 1), offset: 22.0 },
  { ts: Date.UTC(1985, 6, 1), offset: 23.0 },
  { ts: Date.UTC(1988, 0, 1), offset: 24.0 },
  { ts: Date.UTC(1990, 0, 1), offset: 25.0 },
  { ts: Date.UTC(1991, 0, 1), offset: 26.0 },
  { ts: Date.UTC(1992, 6, 1), offset: 27.0 },
  { ts: Date.UTC(1993, 6, 1), offset: 28.0 },
  { ts: Date.UTC(1994, 6, 1), offset: 29.0 },
  { ts: Date.UTC(1996, 0, 1), offset: 30.0 },
  { ts: Date.UTC(1997, 6, 1), offset: 31.0 },
  { ts: Date.UTC(1999, 0, 1), offset: 32.0 },
  { ts: Date.UTC(2006, 0, 1), offset: 33.0 },
  { ts: Date.UTC(2009, 0, 1), offset: 34.0 },
  { ts: Date.UTC(2012, 6, 1), offset: 35.0 },
  { ts: Date.UTC(2015, 6, 1), offset: 36.0 },
  { ts: Date.UTC(2017, 0, 1), offset: 37.0 },
];

const PERTURBERS = [
  [0.0071, 2.2353, 49.409],
  [0.0057, 2.7543, 168.173],
  [0.0039, 1.1177, 191.837],
  [0.0037, 15.7866, 21.736],
  [0.0021, 2.1354, 15.704],
  [0.0020, 2.4694, 95.528],
  [0.0018, 32.8493, 49.095],
];

export const MARS_SOL_RATIO = 1.0274912517;

export function getTtMinusUtcSeconds(date) {
  const ts = typeof date === 'number' ? date : date.getTime();
  let tai = 10.0;
  for (const row of LEAP_SECONDS) {
    if (ts >= row.ts) tai = row.offset;
    else break;
  }
  return tai + 32.184;
}

export function formatMarsHms(hours) {
  if (!Number.isFinite(hours)) return '—';
  const norm = ((hours % 24.0) + 24.0) % 24.0;
  const totSec = Math.round(norm * 3600.0) % 86400;
  const hh = Math.floor(totSec / 3600);
  const mm = Math.floor((totSec % 3600) / 60);
  const ss = totSec % 60;
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`;
}

export function computeClientMars24(latitudeDeg, longitudeEastDeg, dateInput = new Date()) {
  const date = typeof dateInput === 'string' ? new Date(dateInput) : dateInput;
  const lat = Math.max(-90.0, Math.min(90.0, latitudeDeg));
  const lonE = ((longitudeEastDeg % 360.0) + 360.0) % 360.0;
  const lonW = (360.0 - lonE) % 360.0;

  const epochMs = date.getTime();
  const jdUt = 2440587.5 + epochMs / 86400000.0;
  const ttMinusUtc = getTtMinusUtcSeconds(date);
  const jdTt = jdUt + ttMinusUtc / 86400.0;
  const deltaT = jdTt - 2451545.0;

  const mDeg = ((19.3871 + 0.52402073 * deltaT) % 360.0 + 360.0) % 360.0;
  const mRad = (mDeg * Math.PI) / 180.0;

  const alphaFms = ((270.3871 + 0.524038496 * deltaT) % 360.0 + 360.0) % 360.0;

  let pbs = 0.0;
  for (const [amp, tau, phi] of PERTURBERS) {
    const arg = ((0.985626 * deltaT) / tau + phi) * (Math.PI / 180.0);
    pbs += amp * Math.cos(arg);
  }

  const vMinusM =
    (10.691 + 3.0e-7 * deltaT) * Math.sin(mRad) +
    0.623 * Math.sin(2.0 * mRad) +
    0.05 * Math.sin(3.0 * mRad) +
    0.005 * Math.sin(4.0 * mRad) +
    0.0005 * Math.sin(5.0 * mRad) +
    pbs;

  const lsDeg = ((alphaFms + vMinusM) % 360.0 + 360.0) % 360.0;
  const lsRad = (lsDeg * Math.PI) / 180.0;

  const eotDeg =
    2.861 * Math.sin(2.0 * lsRad) -
    0.071 * Math.sin(4.0 * lsRad) +
    0.002 * Math.sin(6.0 * lsRad) -
    vMinusM;
  const eotHours = eotDeg / 15.0;

  const msd = (deltaT - 4.5) / MARS_SOL_RATIO + 44796.0 - 0.0009626;
  const mtcHours = ((24.0 * msd) % 24.0 + 24.0) % 24.0;
  const lmstHours = ((mtcHours - lonW / 15.0) % 24.0 + 24.0) % 24.0;
  const ltstHours = ((lmstHours + eotHours) % 24.0 + 24.0) % 24.0;

  const sinLs = Math.sin(lsRad);
  const deltaSDeg = (Math.asin(0.42565 * sinLs) * 180.0) / Math.PI + 0.25 * sinLs;
  const deltaSRad = (deltaSDeg * Math.PI) / 180.0;

  const hourAngleDeg = (ltstHours - 12.0) * 15.0;
  const hourAngleRad = (hourAngleDeg * Math.PI) / 180.0;

  const latRad = (lat * Math.PI) / 180.0;
  const cosZ = Math.max(
    -1.0,
    Math.min(
      1.0,
      Math.sin(latRad) * Math.sin(deltaSRad) +
        Math.cos(latRad) * Math.cos(deltaSRad) * Math.cos(hourAngleRad)
    )
  );
  const zenithDeg = (Math.acos(cosZ) * 180.0) / Math.PI;
  const elevationDeg = 90.0 - zenithDeg;

  const yAz = -Math.cos(deltaSRad) * Math.sin(hourAngleRad);
  const xAz =
    Math.cos(latRad) * Math.sin(deltaSRad) -
    Math.sin(latRad) * Math.cos(deltaSRad) * Math.cos(hourAngleRad);
  let azimuthDeg = 0.0;
  if (Math.abs(xAz) > 1e-12 || Math.abs(yAz) > 1e-12) {
    azimuthDeg = ((Math.atan2(yAz, xAz) * 180.0) / Math.PI + 360.0) % 360.0;
  }

  const daylightState =
    elevationDeg > 0 ? 'DAYLIGHT' : elevationDeg > -6.0 ? 'TWILIGHT' : 'NIGHT';

  // Perseverance mission sol relative to landing Feb 18, 2021
  const landingUtc = Date.UTC(2021, 1, 18, 20, 55, 0);
  let perseveranceSol = null;
  if (epochMs >= landingUtc) {
    const jezeroSolNum = msd + 77.45089 / 360.0 - 52304.0;
    perseveranceSol = Math.max(0, Math.floor(jezeroSolNum));
  }

  // Compute exact spherical-astronomy sunrise / sunset LTST hours
  const cosH0 = -Math.tan(latRad) * Math.tan(deltaSRad);
  let polarDayState = 'NORMAL';
  let sunriseLtstHours = null;
  let sunsetLtstHours = null;
  if (cosH0 <= -1.0) {
    polarDayState = 'POLAR_CONTINUOUS_DAY';
  } else if (cosH0 >= 1.0) {
    polarDayState = 'POLAR_CONTINUOUS_NIGHT';
  } else {
    const h0Hours = (Math.acos(cosH0) * 180.0) / Math.PI / 15.0;
    sunriseLtstHours = Number((12.0 - h0Hours).toFixed(4));
    sunsetLtstHours = Number((12.0 + h0Hours).toFixed(4));
  }

  return {
    utc_iso: date.toISOString(),
    latitude_deg: Number(lat.toFixed(6)),
    longitude_east_deg: Number(lonE.toFixed(6)),
    msd: Number(msd.toFixed(5)),
    mtc_hms: formatMarsHms(mtcHours),
    lmst_hms: formatMarsHms(lmstHours),
    ltst_hms: formatMarsHms(ltstHours),
    ltst_hours: Number(ltstHours.toFixed(4)),
    ls_deg: Number(lsDeg.toFixed(3)),
    solar_elevation_deg: Number(elevationDeg.toFixed(2)),
    solar_azimuth_deg: Number(azimuthDeg.toFixed(2)),
    solar_declination_deg: Number(deltaSDeg.toFixed(3)),
    sunrise_ltst_hours: sunriseLtstHours,
    sunset_ltst_hours: sunsetLtstHours,
    polar_day_state: polarDayState,
    daylight_state: daylightState,
    is_daylight: elevationDeg > 0,
    perseverance_mission_sol: perseveranceSol,
  };
}

export function classifyTerrainStatus(lat, lon, activeTerrain) {
  const lonNorm = ((lon % 360.0) + 360.0) % 360.0;
  const hb = AUTHORITATIVE_MARS_TERRAIN_CATALOG.hirise_dtm_1m.bounds;
  const mb = activeTerrain?.b || AUTHORITATIVE_MARS_TERRAIN_CATALOG.mola_hrsc_dem_200m.bounds;

  if (lonNorm >= hb[0] && lonNorm <= hb[2] && lat >= hb[1] && lat <= hb[3]) {
    return {
      tier: 'hirise_1m',
      label: 'High-resolution DTM (1 m)',
      dataset: 'USGS Mars 2020 HiRISE DTM',
      doi: '10.5066/P9REJ9JN',
      resolution_m: 1.0,
      covered: true,
    };
  }

  if (lonNorm >= mb[0] && lonNorm <= mb[2] && lat >= mb[1] && lat <= mb[3]) {
    return {
      tier: 'mola_200m',
      label: 'Global MOLA fallback (200 m)',
      dataset: 'USGS MOLA-HRSC 200m DEM',
      doi: '10.5066/P907276M',
      resolution_m: 200.0,
      covered: true,
    };
  }

  return {
    tier: 'out_of_bounds',
    label: 'Out of bounds',
    dataset: null,
    doi: null,
    resolution_m: null,
    covered: false,
  };
}

export async function fetchMarsConditions({
  lat,
  lon,
  utc,
  sol,
  apiUrl = '',
  signal,
}) {
  const normLon = Number((((lon % 360.0) + 360.0) % 360.0).toFixed(5));
  const normLat = Number(lat.toFixed(5));
  const baseOrigin =
    (apiUrl && apiUrl.trim()) ||
    (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
  const url = new URL('/api/v1/conditions', baseOrigin);
  url.searchParams.set('lat', normLat);
  url.searchParams.set('lon', normLon);
  if (utc) url.searchParams.set('utc', utc);
  if (sol !== undefined && sol !== null) url.searchParams.set('sol', sol);

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: { Accept: 'application/json' },
    signal,
  });

  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`Conditions request failed (${res.status}): ${errText || res.statusText}`);
  }

  return res.json();
}
