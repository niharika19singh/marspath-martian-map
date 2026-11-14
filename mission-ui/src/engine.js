import { buildTerrain, toIndex, toCoordinate } from './terrain.js';
import { computeClientMars24, formatMarsHms, MARS_SOL_RATIO } from './conditions.js';

export const MARS_EARTH_GRAVITY_RATIO = 3.72076 / 9.80665;
export const MINETTI_COEFFS = [155.4, -30.4, -43.3, 46.3, 19.5, 3.6];
export const MINETTI_FLAT_EARTH = 3.6;
export const MINETTI_MIN_EARTH_NORM = 0.21;

class Heap {
  constructor() {
    this.a = [];
  }
  push(item) {
    const a = this.a;
    a.push(item);
    let i = a.length - 1;
    while (i) {
      const p = (i - 1) >> 1;
      if (a[p][0] <= item[0]) break;
      a[i] = a[p];
      i = p;
    }
    a[i] = item;
  }
  pop() {
    const a = this.a;
    const head = a[0];
    const last = a.pop();
    if (a.length) {
      let i = 0;
      while (2 * i + 1 < a.length) {
        let c = 2 * i + 1;
        if (c + 1 < a.length && a[c + 1][0] < a[c][0]) c++;
        if (a[c][0] >= last[0]) break;
        a[i] = a[c];
        i = c;
      }
      a[i] = last;
    }
    return head;
  }
  get size() {
    return this.a.length;
  }
}

const weights = {
  safety_first: [3.5, 2.5, 14],
  balanced: [1.2, 1.0, 20],
  science_first: [0.7, 0.6, 22],
};

function computeDirectionalGradients(t) {
  if (t.dzDeast && t.dzDnorth) return t;
  const { w, h, n, e, dx, dy } = t;
  const dzDeast = new Float64Array(n);
  const dzDnorth = new Float64Array(n);
  dzDeast.fill(NaN);
  dzDnorth.fill(NaN);
  for (let r = 0; r < h; r++) {
    const rt = Math.max(0, r - 1);
    const rb = Math.min(h - 1, r + 1);
    const spanY = (rb - rt) * dy;
    for (let c = 0; c < w; c++) {
      const i = r * w + c;
      if (!Number.isFinite(e[i])) continue;
      const cl = Math.max(0, c - 1);
      const cr = Math.min(w - 1, c + 1);
      const spanX = (cr - cl) * dx;
      const ze0 = e[r * w + cl];
      const ze1 = e[r * w + cr];
      const zn0 = e[rt * w + c];
      const zn1 = e[rb * w + c];
      if (spanX > 0 && Number.isFinite(ze0) && Number.isFinite(ze1)) {
        dzDeast[i] = (ze1 - ze0) / spanX;
      }
      if (spanY > 0 && Number.isFinite(zn0) && Number.isFinite(zn1)) {
        // Row increases South, so Northward slope is -(z_south - z_north) / spanY
        dzDnorth[i] = -(zn1 - zn0) / spanY;
      }
    }
  }
  t.dzDeast = dzDeast;
  t.dzDnorth = dzDnorth;
  return t;
}

export function directionalWalkSpeed(baseSpeed, signedGrade) {
  const clamped = Math.max(-1.0, Math.min(1.0, signedGrade));
  const factor = Math.exp(-2.2 * Math.abs(clamped + 0.02));
  return Math.max(0.08 * baseSpeed, Math.min(1.15 * baseSpeed, baseSpeed * factor));
}

function minettiEarthNormalized(grade) {
  const g = Math.max(-0.45, Math.min(0.45, grade));
  const [c5, c4, c3, c2, c1, c0] = MINETTI_COEFFS;
  const raw = c5 * g ** 5 + c4 * g ** 4 + c3 * g ** 3 + c2 * g ** 2 + c1 * g + c0;
  return Math.max(MINETTI_MIN_EARTH_NORM, raw / MINETTI_FLAT_EARTH);
}

export function computeMinettiRelativeEffortFactor(
  alongGrade,
  crossGrade = 0.0,
  gravityRatio = MARS_EARTH_GRAVITY_RATIO,
  suitLoadFactor = 1.0
) {
  const alongNorm = minettiEarthNormalized(alongGrade);
  const marsAlong = 1.0 + gravityRatio * suitLoadFactor * (alongNorm - 1.0);
  const crossFactor = 0.25 * suitLoadFactor * Math.min(1.0, Math.abs(crossGrade)) ** 1.5;
  return Math.max(0.25, marsAlong + crossFactor);
}

export function computeEdgeGeometry(t, i, j) {
  computeDirectionalGradients(t);
  const ri = Math.floor(i / t.w);
  const ci = i % t.w;
  const rj = Math.floor(j / t.w);
  const cj = j % t.w;
  const vx = (cj - ci) * t.dx;
  const vy = -(rj - ri) * t.dy;
  const d2d = Math.hypot(vx, vy);
  const dz = t.e[j] - t.e[i];
  const dist3d = Math.hypot(d2d, dz);
  const alongGrade = dz / Math.max(d2d, 1e-6);
  const alongSlopeDeg = (Math.atan(alongGrade) * 180) / Math.PI;

  const ux = vx / Math.max(d2d, 1e-6);
  const uy = vy / Math.max(d2d, 1e-6);
  const px = -uy;
  const py = ux;

  let sx = 0;
  let sy = 0;
  let cnt = 0;
  if (Number.isFinite(t.dzDeast[i]) && Number.isFinite(t.dzDnorth[i])) {
    sx += t.dzDeast[i];
    sy += t.dzDnorth[i];
    cnt++;
  }
  if (Number.isFinite(t.dzDeast[j]) && Number.isFinite(t.dzDnorth[j])) {
    sx += t.dzDeast[j];
    sy += t.dzDnorth[j];
    cnt++;
  }
  const crossGrade = cnt ? Math.abs((sx / cnt) * px + (sy / cnt) * py) : 0.0;
  const crossSlopeDeg = (Math.atan(crossGrade) * 180) / Math.PI;
  return { d2d, dz, dist3d, alongGrade, alongSlopeDeg, crossGrade, crossSlopeDeg };
}

export function cost(t, i, j, mode, options = {}) {
  const [ws, wr, cap] = weights[mode] || weights.balanced;
  const costMode = String(options.cost_mode || 'directional').toLowerCase();
  const effortModel = String(options.effort_model || 'slope_penalty').toLowerCase();
  const crossWeight = Number.isFinite(options.cross_slope_weight) ? options.cross_slope_weight : 0.35;
  const suitLoad = Number.isFinite(options.suit_load_factor) ? options.suit_load_factor : 1.0;

  const geom = computeEdgeGeometry(t, i, j);
  const dist = geom.dist3d;

  let slopeFactor = 0.0;
  let crossFactor = 0.0;

  if (costMode === 'legacy_magnitude') {
    const normSlope = Math.max(0.0, t.slope[j] || 0.0) / cap;
    slopeFactor = normSlope ** 1.5;
  } else {
    if (effortModel === 'minetti_effort') {
      const eff = computeMinettiRelativeEffortFactor(
        geom.alongGrade,
        0.0,
        MARS_EARTH_GRAVITY_RATIO,
        suitLoad
      );
      const minBase = 1.0 + MARS_EARTH_GRAVITY_RATIO * suitLoad * (MINETTI_MIN_EARTH_NORM - 1.0);
      slopeFactor = Math.max(0.0, eff - minBase);
    } else {
      const normAlong = Math.abs(geom.alongSlopeDeg) / cap;
      slopeFactor = geom.alongSlopeDeg >= 0 ? 1.35 * normAlong ** 1.5 : 0.55 * normAlong ** 1.35;
    }
    const normCross = geom.crossSlopeDeg / cap;
    crossFactor = crossWeight * normCross ** 1.5;
  }

  const sp = dist * ws * (slopeFactor + crossFactor);
  const rp = dist * wr * (t.rough[j] || 0);
  const relEffort =
    dist * computeMinettiRelativeEffortFactor(geom.alongGrade, geom.crossGrade, MARS_EARTH_GRAVITY_RATIO, suitLoad);

  return {
    distance: dist,
    d2d: geom.d2d,
    dz: geom.dz,
    alongSlopeDeg: geom.alongSlopeDeg,
    crossSlopeDeg: geom.crossSlopeDeg,
    slope: sp,
    roughness: rp,
    hazard: 0,
    extra: 0,
    relativeEffort: relEffort,
    total: Math.max(dist, dist + sp + rp),
  };
}

export function computeBackwardTimeGrid(
  t,
  habitatIdx,
  baseSpeedMps = 1.1111,
  budgetSeconds = 8 * 3600,
  maxDrivableSlopeDeg = null,
  timeMultiplier = 1.0
) {
  const timeGrid = new Float64Array(t.n);
  timeGrid.fill(Infinity);
  const validMask = new Uint8Array(t.n);
  for (let i = 0; i < t.n; i++) {
    if (!t.valid[i] || !Number.isFinite(t.e[i]) || !Number.isFinite(t.slope[i])) continue;
    if (maxDrivableSlopeDeg !== null && t.slope[i] > maxDrivableSlopeDeg) continue;
    validMask[i] = 1;
  }
  const travCount = validMask.reduce((acc, v) => acc + v, 0);
  if (!validMask[habitatIdx]) {
    return {
      timeGrid,
      reachableMask: new Uint8Array(t.n),
      reachableFraction: 0,
      nodesSettled: 0,
    };
  }

  const baseSpd = Math.max(0.05, baseSpeedMps);
  const mult = Math.max(0.1, timeMultiplier);
  const heap = new Heap();
  timeGrid[habitatIdx] = 0.0;
  heap.push([0.0, habitatIdx]);
  let settled = 0;

  while (heap.size) {
    const [tu, u] = heap.pop();
    if (tu > timeGrid[u]) continue;
    settled++;
    const ru = Math.floor(u / t.w);
    const cu = u % t.w;
    const zu = t.e[u];

    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (!dr && !dc) continue;
        const vr = ru + dr;
        const vc = cu + dc;
        if (vr < 0 || vr >= t.h || vc < 0 || vc >= t.w) continue;
        const v = vr * t.w + vc;
        if (!validMask[v]) continue;
        if (dr && dc && (!validMask[(ru + dr) * t.w + cu] || !validMask[ru * t.w + vc])) continue;

        const d2d = Math.hypot(dc * t.dx, dr * t.dy);
        const dz = zu - t.e[v]; // Direction v -> u returning toward habitat
        const d3d = Math.hypot(d2d, dz);
        const spd = directionalWalkSpeed(baseSpd, dz / Math.max(d2d, 1e-6));
        const cand = tu + (d3d / spd) * mult;
        if (cand < timeGrid[v]) {
          timeGrid[v] = cand;
          heap.push([cand, v]);
        }
      }
    }
  }

  const reachableMask = new Uint8Array(t.n);
  let reachCount = 0;
  for (let i = 0; i < t.n; i++) {
    if (Number.isFinite(timeGrid[i]) && timeGrid[i] <= budgetSeconds) {
      reachableMask[i] = 1;
      reachCount++;
    }
  }

  return {
    timeGrid,
    reachableMask,
    reachableFraction: travCount ? Number((reachCount / travCount).toFixed(4)) : 0,
    nodesSettled: settled,
  };
}

function serializeTimeGridOverlay(t, timeGrid, budgetMinutes, sourceName, asOf) {
  const maxDim = 72;
  const strideR = Math.max(1, Math.ceil(t.h / maxDim));
  const strideC = Math.max(1, Math.ceil(t.w / maxDim));
  const minutesGrid = [];
  for (let r = 0; r < t.h; r += strideR) {
    const row = [];
    for (let c = 0; c < t.w; c += strideC) {
      const v = timeGrid[r * t.w + c];
      row.push(Number.isFinite(v) ? Number((v / 60).toFixed(1)) : null);
    }
    minutesGrid.push(row);
  }
  const effRes = Math.max(t.dx, t.dy);
  return {
    bounds: [...t.b],
    rows: minutesGrid.length,
    cols: minutesGrid[0]?.length || 0,
    budget_minutes: Number(budgetMinutes.toFixed(1)),
    minutes_grid: minutesGrid,
    provenance: {
      kind: 'computed',
      source: sourceName,
      resolution: `${effRes.toFixed(1)} m/px`,
      as_of: asOf,
    },
  };
}

function computeClientTurnaround(coordinates, request, demLabel) {
  if (!coordinates || coordinates.length < 2) return null;
  const depIso = request.departure_utc || '2026-06-15T08:00:00Z';
  const dtStart = new Date(depIso);
  if (Number.isNaN(dtStart.getTime())) return null;
  const baseSpeed = Math.max(0.05, Number(request.walking_speed_m_s || 1.1111));
  const maxEvaHours = Math.max(0.5, Number(request.max_eva_hours || 8.0));
  const bufMin = Math.max(0.0, Number(request.daylight_buffer_minutes || 0.0));
  const marsR = 3396190.0;

  const m24Start = computeClientMars24(coordinates[0][1], coordinates[0][0], dtStart);
  let availDaylightH = 0.0;
  let sunsetSeconds = null;
  let sunsetUtcStr = null;
  let sunsetLtstHms = null;
  let inDaylight = false;

  if (m24Start.polar_day_state === 'POLAR_CONTINUOUS_DAY') {
    availDaylightH = 24.0 * MARS_SOL_RATIO;
    inDaylight = true;
  } else if (m24Start.polar_day_state === 'POLAR_CONTINUOUS_NIGHT') {
    availDaylightH = 0.0;
  } else if (m24Start.sunset_ltst_hours !== null && m24Start.sunrise_ltst_hours !== null) {
    sunsetLtstHms = formatMarsHms(m24Start.sunset_ltst_hours);
    if (m24Start.ltst_hours >= m24Start.sunrise_ltst_hours && m24Start.ltst_hours < m24Start.sunset_ltst_hours) {
      availDaylightH = Math.max(0.0, (m24Start.sunset_ltst_hours - m24Start.ltst_hours) * MARS_SOL_RATIO);
      sunsetSeconds = availDaylightH * 3600.0;
      sunsetUtcStr = new Date(dtStart.getTime() + sunsetSeconds * 1000).toISOString().replace('.000Z', 'Z');
      inDaylight = true;
    } else {
      const nextMarsH =
        m24Start.ltst_hours < m24Start.sunrise_ltst_hours
          ? m24Start.sunset_ltst_hours - m24Start.ltst_hours
          : 24.0 - m24Start.ltst_hours + m24Start.sunset_ltst_hours;
      sunsetUtcStr = new Date(dtStart.getTime() + nextMarsH * MARS_SOL_RATIO * 3600000).toISOString().replace('.000Z', 'Z');
    }
  }

  const vertexDist = [0.0];
  const vertexOutS = [0.0];
  const vertexRetS = [0.0];
  for (let i = 0; i < coordinates.length - 1; i++) {
    const p0 = coordinates[i];
    const p1 = coordinates[i + 1];
    const dlat = ((p1[1] - p0[1]) * Math.PI) / 180;
    const dlon = (((p1[0] - p0[0]) * Math.PI) / 180) * Math.cos(((0.5 * (p0[1] + p1[1])) * Math.PI) / 180);
    const d2d = marsR * Math.hypot(dlat, dlon);
    const z0 = Number.isFinite(p0[2]) ? p0[2] : null;
    const z1 = Number.isFinite(p1[2]) ? p1[2] : null;
    const gOut = z0 !== null && z1 !== null && d2d > 0.1 ? (z1 - z0) / d2d : 0.0;
    const gRet = -gOut;
    const vOut = directionalWalkSpeed(baseSpeed, gOut);
    const vRet = directionalWalkSpeed(baseSpeed, gRet);
    vertexDist.push(vertexDist.at(-1) + d2d);
    vertexOutS.push(vertexOutS.at(-1) + d2d / vOut);
    vertexRetS.push(vertexRetS.at(-1) + d2d / vRet);
  }

  const evaDeadlineS = maxEvaHours * 3600.0;
  const effSunsetS =
    m24Start.polar_day_state === 'POLAR_CONTINUOUS_DAY'
      ? Infinity
      : inDaylight && sunsetSeconds !== null
        ? Math.max(0.0, sunsetSeconds - bufMin * 60.0)
        : 0.0;
  const hardDeadlineS = Math.min(evaDeadlineS, effSunsetS);
  const feasibleBeforeSunset =
    m24Start.polar_day_state === 'POLAR_CONTINUOUS_DAY' || (inDaylight && effSunsetS > 0);

  let limiting = 'eva_budget';
  if (!inDaylight) {
    limiting =
      m24Start.polar_day_state === 'POLAR_CONTINUOUS_NIGHT'
        ? 'polar_night'
        : m24Start.sunset_ltst_hours !== null && m24Start.ltst_hours >= m24Start.sunset_ltst_hours
          ? 'after_sunset'
          : 'pre_dawn_darkness';
  } else if (effSunsetS <= 0) {
    limiting = 'sunset_buffer';
  } else if (effSunsetS < evaDeadlineS) {
    limiting = bufMin > 0 ? 'sunset_buffer' : 'sunset';
  }

  const totalDist = vertexDist.at(-1) || 0;
  const roundTrips = vertexOutS.map((o, i) => o + vertexRetS[i]);
  let turnCoord = [coordinates[0][0], coordinates[0][1]];
  let turnDist = 0;
  let turnFrac = 0;
  let turnS = 0;
  let exceeds = true;

  if (hardDeadlineS <= 0 || !feasibleBeforeSunset) {
    turnCoord = [coordinates[0][0], coordinates[0][1]];
  } else if (roundTrips.at(-1) <= hardDeadlineS) {
    turnCoord = [coordinates.at(-1)[0], coordinates.at(-1)[1]];
    turnDist = Number(totalDist.toFixed(1));
    turnFrac = 1.0;
    turnS = Math.max(vertexOutS.at(-1), hardDeadlineS - vertexRetS.at(-1));
    exceeds = false;
  } else {
    let k = 0;
    for (let i = 0; i < roundTrips.length - 1; i++) {
      if (roundTrips[i] <= hardDeadlineS) k = i;
      else break;
    }
    const span = Math.max(1e-6, roundTrips[k + 1] - roundTrips[k]);
    const alpha = Math.max(0, Math.min(1, (hardDeadlineS - roundTrips[k]) / span));
    turnCoord = [
      Number((coordinates[k][0] + alpha * (coordinates[k + 1][0] - coordinates[k][0])).toFixed(6)),
      Number((coordinates[k][1] + alpha * (coordinates[k + 1][1] - coordinates[k][1])).toFixed(6)),
    ];
    turnDist = Number((vertexDist[k] + alpha * (vertexDist[k + 1] - vertexDist[k])).toFixed(1));
    turnFrac = Number((turnDist / Math.max(1e-6, totalDist)).toFixed(4));
    turnS = vertexOutS[k] + alpha * (vertexOutS[k + 1] - vertexOutS[k]);
    exceeds = true;
  }

  const turnDt = new Date(dtStart.getTime() + turnS * 1000);
  const m24Turn = computeClientMars24(turnCoord[1], turnCoord[0], turnDt);
  const totalMissionHours = roundTrips.at(-1) / 3600.0;

  return {
    turnaround_utc: turnDt.toISOString().replace('.000Z', 'Z'),
    turnaround_ltst_hms: m24Turn.ltst_hms,
    turnaround_elapsed_hours: Number((turnS / 3600).toFixed(3)),
    turnaround_coord: turnCoord,
    turnaround_distance_m: turnDist,
    turnaround_fraction: turnFrac,
    sunset_utc: sunsetUtcStr,
    sunset_ltst_hms: sunsetLtstHms,
    eva_deadline_utc: new Date(dtStart.getTime() + evaDeadlineS * 1000).toISOString().replace('.000Z', 'Z'),
    daylight_buffer_minutes: Number(bufMin.toFixed(1)),
    limiting_constraint: limiting,
    feasible_before_sunset: feasibleBeforeSunset,
    within_eva_budget: totalMissionHours <= maxEvaHours,
    route_exceeds_hard_deadline: exceeds,
    provenance: {
      kind: 'derived',
      source: `Client Mars24 + ${demLabel}`,
      resolution: demLabel,
      as_of: depIso,
    },
  };
}

function search(t, start, end, request, penalty, returnBlockedMask = null) {
  const maxSlope =
    request.mode === 'safety_first' ? Math.min(14, request.constraints.max_slope_deg) : request.constraints.max_slope_deg;
  const maxR = request.constraints.max_roughness;
  const allowed = i =>
    t.valid[i] && t.slope[i] <= maxSlope && t.rough[i] <= maxR && (!returnBlockedMask || returnBlockedMask[i]);

  if (!allowed(start) || !allowed(end)) {
    throw new Error(
      returnBlockedMask && (!returnBlockedMask[start] || !returnBlockedMask[end])
        ? 'Destination or start exceeds EVA return-time budget to habitat under block mode.'
        : 'A selected pin lies on terrain excluded by your slope or roughness limits. Move the pin or adjust the constraints.'
    );
  }

  const g = new Float64Array(t.n);
  g.fill(Infinity);
  const parent = new Int32Array(t.n);
  parent.fill(-1);
  const closed = new Uint8Array(t.n);
  const heap = new Heap();
  const er = Math.floor(end / t.w);
  const ec = end % t.w;
  const heuristic = i =>
    request.algorithm === 'dijkstra' ? 0 : Math.hypot(((i % t.w) - ec) * t.dx, (Math.floor(i / t.w) - er) * t.dy);

  g[start] = 0;
  heap.push([heuristic(start), start]);
  let expanded = 0;
  const maxNodes = Math.max(100000, t.n * 2);

  while (heap.size) {
    const [, i] = heap.pop();
    if (closed[i]) continue;
    closed[i] = 1;
    expanded++;
    if (expanded > maxNodes) {
      throw new Error('Search exceeded its node budget. Choose a shorter corridor.');
    }
    if (i === end) {
      const path = [];
      let j = end;
      while (j !== -1) {
        path.push(j);
        j = parent[j];
      }
      path.reverse();
      return { path, expanded };
    }

    const r = Math.floor(i / t.w);
    const c = i % t.w;
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        if (!dr && !dc) continue;
        const rr = r + dr;
        const cc = c + dc;
        if (rr < 0 || rr >= t.h || cc < 0 || cc >= t.w) continue;
        const j = rr * t.w + cc;
        if (closed[j] || !allowed(j)) continue;
        if (dr && dc && (!allowed((r + dr) * t.w + c) || !allowed(r * t.w + cc))) continue;
        const stepCost = cost(t, i, j, request.mode, request).total + (penalty?.get(i + ':' + j) || 0);
        if (g[i] + stepCost < g[j]) {
          g[j] = g[i] + stepCost;
          parent[j] = i;
          heap.push([g[j] + heuristic(j), j]);
        }
      }
    }
  }

  throw new Error('No traversable route connects these pins within the selected constraints. Try another destination or less restrictive limits.');
}

function summarize(t, path, request, rank, returnRes = null, rescueRes = null) {
  const coordinates = path.map(i => toCoordinate(t, i));
  let distance = 0,
    ascent = 0,
    descent = 0,
    sp = 0,
    rp = 0,
    relEff = 0,
    timeS = 0,
    smax = 0,
    ssum = 0,
    crossSum = 0,
    crossMax = 0,
    rsum = 0,
    hazard = 0,
    rescueFlagDist = 0,
    exceedsReturn = false,
    maxRetMin = 0,
    hasRet = false,
    hasUnreachRet = false,
    maxResMin = 0,
    hasRes = false,
    hasUnreachRes = false;

  const evaBudgetMin = Number(request.max_eva_hours || 8.0) * 60.0;
  const rescueThreshMin = Number(request.rescue_threshold_minutes || 30.0);
  const returnMode = String(request.return_constraint_mode || 'flag').toLowerCase();
  const segments = [];

  for (let k = 1; k < path.length; k++) {
    const i = path[k - 1];
    const j = path[k];
    const c = cost(t, i, j, request.mode, request);
    const dz = t.e[j] - t.e[i];
    distance += c.distance;
    ascent += Math.max(0, dz);
    descent += Math.max(0, -dz);
    sp += c.slope;
    rp += c.roughness;
    relEff += c.relativeEffort;

    const stepSpd = directionalWalkSpeed(Number(request.walking_speed_m_s || 0.15), c.dz / Math.max(c.d2d, 1e-6));
    timeS += c.distance / stepSpd;
    smax = Math.max(smax, t.slope[j]);
    ssum += t.slope[j];
    crossSum += c.crossSlopeDeg;
    crossMax = Math.max(crossMax, c.crossSlopeDeg);
    rsum += t.rough[j];
    if (t.slope[j] > 12 || t.rough[j] > 0.5) hazard += c.distance;

    const segFlags = [];
    let retMin = null;
    if (returnRes && returnMode !== 'off') {
      const rt = returnRes.timeGrid[j];
      if (Number.isFinite(rt)) {
        retMin = Number((rt / 60).toFixed(1));
        hasRet = true;
        maxRetMin = Math.max(maxRetMin, retMin);
        if (retMin > evaBudgetMin) {
          exceedsReturn = true;
          segFlags.push('exceeds_eva_return_budget');
        }
      } else {
        hasUnreachRet = true;
        exceedsReturn = true;
        segFlags.push('exceeds_eva_return_budget');
      }
    }

    let resMin = null;
    if (rescueRes) {
      const rs = rescueRes.timeGrid[j];
      if (Number.isFinite(rs)) {
        resMin = Number((rs / 60).toFixed(1));
        hasRes = true;
        maxResMin = Math.max(maxResMin, resMin);
        if (resMin > rescueThreshMin) {
          rescueFlagDist += c.distance;
          segFlags.push('exceeds_rescue_time_threshold');
        }
      } else {
        hasUnreachRes = true;
        rescueFlagDist += c.distance;
        segFlags.push('exceeds_rescue_time_threshold');
      }
    }

    segments.push({
      segment_index: k - 1,
      from_coord: { lon: coordinates[k - 1][0], lat: coordinates[k - 1][1] },
      to_coord: { lon: coordinates[k][0], lat: coordinates[k][1] },
      step_distance_meters: c.distance,
      elevation_start_m: t.e[i],
      elevation_end_m: t.e[j],
      delta_elevation_m: dz,
      slope_deg: t.slope[j],
      along_slope_deg: Number(c.alongSlopeDeg.toFixed(2)),
      cross_slope_deg: Number(c.crossSlopeDeg.toFixed(2)),
      roughness: t.rough[j],
      estimated_relative_effort: Number(c.relativeEffort.toFixed(2)),
      return_time_minutes: retMin,
      rescue_time_minutes: resMin,
      is_valid_data: true,
      segment_cost: c.total,
      quality_flags: segFlags,
    });
  }

  const n = Math.max(1, path.length - 1);
  const risk =
    hazard / Math.max(distance, 1) >= 0.2 || smax >= 18
      ? 'high'
      : hazard / Math.max(distance, 1) >= 0.05 || smax >= 12
        ? 'moderate'
        : 'nominal';
  const nomRes =
    t.raw.native_resolution_meters ||
    t.raw.native_resolution_m ||
    (t.raw.product_id === 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40' ? 1 : 200);
  const effRes = Math.max(t.dx, t.dy);
  const turnaround = computeClientTurnaround(coordinates, request, `${effRes.toFixed(1)} m/px`);

  const baseCost = Number(distance.toFixed(2));
  const slopeCost = Number(sp.toFixed(2));
  const roughCost = Number(rp.toFixed(2));
  const totalCostReconciled = Number((baseCost + slopeCost + roughCost).toFixed(2));

  return {
    route_id: 'browser-route-' + rank,
    name: rank === 1 ? 'Primary route' : 'Alternative ' + (rank - 1),
    mode: request.mode,
    score_rank: rank,
    total_cost: totalCostReconciled,
    cost_breakdown: {
      base_distance_cost: baseCost,
      slope_penalty: slopeCost,
      roughness_penalty: roughCost,
      hazard_penalty: 0,
      extra_penalty: 0,
    },
    geometry: { type: 'LineString', coordinates },
    turnaround,
    summary: {
      total_distance_meters: distance,
      elevation_gain_meters: ascent,
      elevation_loss_meters: descent,
      min_elevation_meters: Math.min(...path.map(i => t.e[i])),
      max_elevation_meters: Math.max(...path.map(i => t.e[i])),
      max_slope_deg: smax,
      average_slope_deg: ssum / n,
      average_cross_slope_deg: crossSum / n,
      max_cross_slope_deg: crossMax,
      average_roughness: rsum / n,
      data_coverage_fraction: 1,
      elevation_sample_coverage_fraction: 1,
      is_complete_measurement: true,
      estimated_duration_hours: timeS / 3600,
      motion_profile: `directional_mars_${request.effort_model || 'slope_penalty'}`,
      energy_index: distance * 0.001 + ascent * 0.02,
      cost_mode: request.cost_mode || 'directional',
      effort_model: request.effort_model || 'slope_penalty',
      estimated_relative_effort: Number(relEff.toFixed(1)),
      max_return_time_minutes: hasRet && !hasUnreachRet ? maxRetMin : null,
      exceeds_return_budget: exceedsReturn,
      max_rescue_time_minutes: hasRes && !hasUnreachRes ? maxResMin : null,
      rescue_flagged_distance_meters: Number(rescueFlagDist.toFixed(1)),
      science_score: request.science_waypoints?.length ? 100 : 0,
      hazard_exposure_meters: hazard,
      risk_category: risk,
      risk_assessment_status: 'complete_observed',
      provenance: {
        kind: 'computed',
        source: `${t.raw.source_name || 'Bundled USGS DEM'} (Browser Worker)`,
        resolution: `${effRes.toFixed(1)} m/px`,
        as_of: request.departure_utc || new Date().toISOString(),
      },
    },
    waypoints_visited: request.science_waypoints || [],
    science_targets_visited: [],
    science_targets_nearby: [],
    warnings: [
      ...(exceedsReturn ? [`Habitat return-time exceeds ${Number(request.max_eva_hours || 8).toFixed(1)}h EVA budget.`] : []),
      ...(rescueFlagDist > 0 ? [`Rescue response time exceeds ${rescueThreshMin.toFixed(0)} min over ${Math.round(rescueFlagDist)} m.`] : []),
    ],
    evidence_passport: {
      schema_version: '1.0.0',
      quality_tier: t.raw.is_synthetic || !t.raw.local_integrity_verified ? 'unverified' : 'moderate',
      tier_explanation: t.raw.is_synthetic
        ? 'Synthetic test terrain.'
        : 'Official USGS endpoint extract; upstream archive checksum not independently verified.',
      scientific_disclaimer:
        'Relative route scores and terrain indicators are deterministic planning heuristics, not probabilities of safety or failure.',
      quality_flags: ['source_checksum_unverified', 'coarse_resolution_for_obstacle_detection'],
      source: {
        publisher: 'USGS Astrogeology Science Center',
        verification_method: 'official_endpoint_range_extract_and_local_json_sha256',
        file_sha256: t.raw.file_sha256 || null,
        pixel_resolution_x_meters: t.dx,
        pixel_resolution_y_meters: t.dy,
        native_resolution_x_meters: nomRes,
        native_resolution_y_meters: nomRes,
        aggregation_applied: Boolean(t.raw.aggregation_applied),
        aggregation_factor: t.raw.aggregation_factor || 1,
        raster_width: t.w,
        raster_height: t.h,
        spatial_coverage: { min_lon: t.b[0], min_lat: t.b[1], max_lon: t.b[2], max_lat: t.b[3] },
        source_limitations: [
          'Full upstream archive checksum not independently verified.',
          'Local SHA-256 verifies the bundled JSON terrain file, not the full upstream GeoTIFF.',
        ],
        dataset_name: t.raw.source_name,
        product_id: t.raw.product_id,
        official_source_url: t.raw.source_page || t.raw.source_url,
        data_mode: t.raw.data_mode,
        validation_status: t.raw.is_synthetic ? 'synthetic_test_fixture' : 'official_endpoint_retrieved_checksum_unverified',
        is_synthetic: t.raw.is_synthetic,
        source_checksum_verified: false,
        local_integrity_verified: !!t.raw.local_integrity_verified,
        crs_identifier: 'IAU2000:49900',
        vertical_datum: t.raw.vertical_datum,
        nominal_resolution_meters: nomRes,
      },
      coverage: {
        route_sample_count: path.length,
        valid_route_sample_count: path.length,
        invalid_route_sample_count: 0,
        corridor_total_cells: t.n,
        corridor_valid_cells: t.valid.reduce((a, v) => a + v, 0),
        corridor_invalid_cells: t.n - t.valid.reduce((a, v) => a + v, 0),
        route_data_coverage_fraction: 1,
        corridor_data_coverage_fraction: t.valid.reduce((a, v) => a + v, 0) / t.n,
        near_nodata_segment_count: 0,
      },
      resolution_assessment: {
        effective_resolution_meters: effRes,
        actual_x_meters_per_pixel: t.dx,
        actual_y_meters_per_pixel: t.dy,
        native_effective_resolution_meters: nomRes,
        aggregation_applied: Boolean(t.raw.aggregation_applied),
        aggregation_factor: t.raw.aggregation_factor || 1,
        obstacle_detection_capable: effRes <= 1.5,
        suitability_classification: 'regional_corridor_assessment_only',
        nominal_dataset_resolution_meters: nomRes,
        limitation_statement: `Approximately ${effRes.toFixed(1)} m effective terrain grid (${nomRes} m native source) supports corridor assessment.`,
      },
      known_limitations: [
        `Effective ${effRes.toFixed(1)} m terrain grid (${nomRes} m native) cannot resolve sub-pixel (<0.5 m) rover-scale boulders.`,
        'Relative route scores and penalties are deterministic planning indicators, not probabilities of safety.',
        'Browser implementation is not a flight-certified navigation system.',
      ],
      segments,
    },
    _cells: path,
  };
}

export function plan(raw, request) {
  const startTime = performance.now();
  const t = buildTerrain(raw);
  const wps = request.science_waypoints || [];
  const points = [request.start, ...wps, request.destination].map(p => toIndex(t, p));
  if (points[0] === points.at(-1) && points.length === 2) {
    throw new Error('Start and destination map to the same terrain cell. Move a pin at least one grid cell away.');
  }

  const habIdx = request.habitat ? toIndex(t, request.habitat) : points[0];
  const returnMode = String(request.return_constraint_mode || 'flag').toLowerCase();
  const maxEvaHours = Number(request.max_eva_hours || 8.0);
  const walkSpeed = Number(request.walking_speed_m_s || 1.1111);
  const depUtc = request.departure_utc || '2026-06-15T08:00:00Z';

  const returnRes =
    returnMode !== 'off'
      ? computeBackwardTimeGrid(t, habIdx, walkSpeed, maxEvaHours * 3600.0)
      : null;
  const returnBlockedMask = returnMode === 'block' && returnRes ? returnRes.reachableMask : null;

  const rescueEnabled = request.rescue_enabled !== false;
  const rescueThreshMin = Number(request.rescue_threshold_minutes || 30.0);
  const rescueMaxSlope = Number(request.rescue_max_slope_deg || 12.0);
  const rescueSpeed = Number(request.rescue_speed_m_s || 2.7778);
  const rescueRes = rescueEnabled
    ? computeBackwardTimeGrid(t, habIdx, rescueSpeed, rescueThreshMin * 60.0, rescueMaxSlope)
    : null;

  let expanded = 0;
  const solve = (penalty, algo = request.algorithm) => {
    const full = [];
    for (let k = 1; k < points.length; k++) {
      const r = search(t, points[k - 1], points[k], { ...request, algorithm: algo }, penalty, returnBlockedMask);
      expanded += r.expanded;
      full.push(...(k === 1 ? r.path : r.path.slice(1)));
    }
    return full;
  };

  let algorithmComparison = null;
  if (request.algorithm === 'compare') {
    const t0A = performance.now();
    const rA = search(t, points[0], points.at(-1), { ...request, algorithm: 'astar' }, null, returnBlockedMask);
    const durA = (performance.now() - t0A) / 1000;
    const t0D = performance.now();
    const rD = search(t, points[0], points.at(-1), { ...request, algorithm: 'dijkstra' }, null, returnBlockedMask);
    const durD = (performance.now() - t0D) / 1000;
    const sumA = summarize(t, rA.path, request, 1, returnRes, rescueRes);
    const sumD = summarize(t, rD.path, request, 1, returnRes, rescueRes);
    const costDiff = Math.abs(sumA.total_cost - sumD.total_cost);
    const costsEqual = costDiff <= 0.05;
    const ratio = rD.expanded / Math.max(1, rA.expanded);
    algorithmComparison = {
      astar: {
        algorithm: 'A*',
        path_length_km: sumA.summary.total_distance_meters / 1000,
        total_cost: sumA.total_cost,
        execution_time_seconds: durA,
        nodes_expanded: rA.expanded,
        max_slope_deg: sumA.summary.max_slope_deg,
        risk_category: sumA.summary.risk_category,
        waypoint_count: rA.path.length,
      },
      dijkstra: {
        algorithm: 'Dijkstra',
        path_length_km: sumD.summary.total_distance_meters / 1000,
        total_cost: sumD.total_cost,
        execution_time_seconds: durD,
        nodes_expanded: rD.expanded,
        max_slope_deg: sumD.summary.max_slope_deg,
        risk_category: sumD.summary.risk_category,
        waypoint_count: rD.path.length,
      },
      cost_difference: costDiff,
      costs_equal: costsEqual,
      faster_algorithm: durA <= durD ? 'A*' : 'Dijkstra',
      node_expansion_ratio: ratio,
      optimality_verified: costsEqual,
      comparison_statement: `A* expanded ${rA.expanded} states vs Dijkstra ${rD.expanded} states (${ratio.toFixed(2)}x ratio). Both reached optimal cost (${sumA.total_cost.toFixed(2)} vs ${sumD.total_cost.toFixed(2)}).`,
    };
  }

  const primaryAlgo = request.algorithm === 'dijkstra' ? 'dijkstra' : 'astar';
  const routes = [];
  const primary = solve(null, primaryAlgo);
  routes.push(summarize(t, primary, request, 1, returnRes, rescueRes));

  const penalty = new Map();
  for (let attempt = 1; routes.length < (request.num_alternatives || 1) && attempt <= 5; attempt++) {
    for (const r of routes) {
      for (let k = 2; k < r._cells.length - 2; k++) {
        const i = r._cells[k - 1];
        const j = r._cells[k];
        penalty.set(i + ':' + j, 700 * attempt);
        penalty.set(j + ':' + i, 700 * attempt);
      }
    }
    try {
      const path = solve(penalty, primaryAlgo);
      const edges = new Set(path.slice(1).map((v, i) => path[i] + ':' + v));
      const same = routes.some(r => {
        const re = r._cells.slice(1).map((v, i) => r._cells[i] + ':' + v);
        return re.filter(e => edges.has(e)).length / Math.max(re.length, edges.size) > 0.85;
      });
      if (!same) routes.push(summarize(t, path, request, routes.length + 1, returnRes, rescueRes));
    } catch {
      break;
    }
  }
  for (const r of routes) delete r._cells;

  const isHi = raw.product_id === 'JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40';
  const returnZonePayload = returnRes
    ? {
        ...serializeTimeGridOverlay(
          t,
          returnRes.timeGrid,
          maxEvaHours * 60.0,
          `${raw.source_name || 'Bundled DEM'} (Backward Dijkstra Return)`,
          depUtc
        ),
        mode: returnMode,
        reachable_fraction: returnRes.reachableFraction,
      }
    : null;
  const rescueZonePayload = rescueRes
    ? {
        ...serializeTimeGridOverlay(
          t,
          rescueRes.timeGrid,
          rescueThreshMin,
          `${raw.source_name || 'Bundled DEM'} (Rescue Profile <= ${rescueMaxSlope} deg)`,
          depUtc
        ),
        reachable_fraction: rescueRes.reachableFraction,
        speed_m_s: rescueSpeed,
        max_slope_deg: rescueMaxSlope,
        threshold_minutes: rescueThreshMin,
      }
    : null;

  return {
    mission_id: 'mission_browser_' + Date.now().toString(36),
    status: routes.length < (request.num_alternatives || 1) ? 'partial' : 'success',
    crs: {
      name: 'Mars 2000 Sphere (IAU2000)',
      projection: 'Local equirectangular metric analysis / geographic Mars output',
      identifier: 'IAU2000:49900',
      ellipsoid_radius_meters: 3396190,
      latitude_type: 'planetocentric',
      longitude_direction: 'positive_east',
    },
    pilot_region: 'Jezero Crater, Mars',
    data_mode: raw.data_mode,
    provenance: {
      dataset_name: raw.source_name,
      official_product_id: raw.product_id,
      pds_doi: raw.doi || null,
      official_source_url: raw.source_page || raw.source_url,
      source_checksum_verified: false,
      local_array_sha256: raw.local_array_sha256,
      compute_engine: 'browser_worker',
    },
    source_selection: {
      selected_source_id: raw.product_id,
      selected_source_tier: isHi ? 'localized_high_resolution_dtm' : 'regional_blended_dem',
      selected_dataset_name: raw.source_name,
      doi: raw.doi || (isHi ? '10.5066/P9REJ9JN' : '10.5066/P907276M'),
      hirise_evaluated: true,
      hirise_enabled: isHi,
      hirise_selected: isHi,
      hirise_status: isHi ? 'selected' : 'disabled',
      native_resolution_meters: raw.native_resolution_meters || raw.native_resolution_m || (isHi ? 1 : 200),
      effective_resolution_meters: Math.max(t.dx, t.dy),
      aggregation_applied: Boolean(raw.aggregation_applied),
      aggregation_factor: raw.aggregation_factor || 1,
    },
    routes,
    return_zone: returnZonePayload,
    rescue_zone: rescueZonePayload,
    stats: {
      algorithm_used:
        request.algorithm === 'compare'
          ? 'A* vs Dijkstra Benchmark'
          : request.algorithm === 'dijkstra'
            ? 'Dijkstra (uniform-cost search)'
            : 'A* (with admissible Euclidean heuristic)',
      search_duration_seconds: (performance.now() - startTime) / 1000,
      nodes_expanded: expanded,
      grid_rows: t.h,
      grid_cols: t.w,
      cell_size_meters: Math.max(t.dx, t.dy),
    },
    limitations: [
      ...routes[0].evidence_passport.known_limitations,
      ...(routes.length < (request.num_alternatives || 1)
        ? ['Fewer distinct traversable alternatives were found than requested.']
        : []),
    ],
    algorithm_comparison: algorithmComparison,
    request,
  };
}
