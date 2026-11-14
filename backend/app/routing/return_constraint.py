"""Backward-Dijkstra return-time reachability and rescue-time map calculations.

Both analyses reuse the exact same reverse-edge Dijkstra solver on the active DEM corridor:
- Return-time constraint: minimum time for an EVA walker to return from any cell v to habitat h.
- Rescue-time map: minimum time for a pressurized rescue vehicle (drivable slopes only) to reach any cell
  or extract from any cell back to habitat, flagging segments exceeding a configurable rescue threshold.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.app.geospatial.raster_loader import RasterMetadata
from backend.app.routing.graph_builder import NEIGHBORS_8, directional_walk_speed_m_s


@dataclass
class BackwardTimeGridResult:
    """Result of a backward Dijkstra travel-time sweep from the habitat node."""

    time_seconds_grid: np.ndarray
    reachable_mask: np.ndarray
    nodes_settled: int
    budget_seconds: float
    reachable_cell_count: int
    traversable_cell_count: int
    reachable_fraction: float


def compute_backward_time_grid(
    elevation: np.ndarray,
    slope_deg: np.ndarray,
    traversable_mask: np.ndarray,
    dx_meters: float,
    dy_meters: float,
    habitat_node: tuple[int, int],
    base_speed_m_s: float = 1.1111,
    budget_seconds: float = 8.0 * 3600.0,
    max_drivable_slope_deg: float | None = None,
    time_multiplier: float = 1.0,
) -> BackwardTimeGridResult:
    """
    Runs backward Dijkstra from `habitat_node = (hab_r, hab_c)` computing minimum
    travel time `T(cell -> habitat_node)` across the corridor grid.

    Reverse-edge directionality: when settling node `u` whose best known return time to habitat is `t[u]`,
    each incoming neighbor `v` uses directional elevation change `z[u] - z[v]` along step `v -> u`!
    No-data or untraversable cells remain `np.inf` and NEVER count as reachable/safe.
    """
    rows, cols = elevation.shape
    hab_r, hab_c = habitat_node
    n_cells = rows * cols

    valid_mask = traversable_mask.copy()
    valid_mask &= ~np.isnan(elevation) & ~np.isnan(slope_deg)
    if max_drivable_slope_deg is not None:
        valid_mask &= slope_deg <= float(max_drivable_slope_deg)

    time_flat = np.full(n_cells, np.inf, dtype=np.float64)
    if not (0 <= hab_r < rows and 0 <= hab_c < cols) or not bool(valid_mask[hab_r, hab_c]):
        time_grid = time_flat.reshape(rows, cols)
        return BackwardTimeGridResult(
            time_seconds_grid=time_grid,
            reachable_mask=np.zeros((rows, cols), dtype=bool),
            nodes_settled=0,
            budget_seconds=budget_seconds,
            reachable_cell_count=0,
            traversable_cell_count=int(np.count_nonzero(valid_mask)),
            reachable_fraction=0.0,
        )

    elev_f = elevation.astype(np.float64, copy=False)
    valid_flat = valid_mask.ravel()
    dx = float(dx_meters)
    dy = float(dy_meters)
    d_diag = math.hypot(dx, dy)
    base_spd = max(0.05, float(base_speed_m_s))
    mult = max(0.1, float(time_multiplier))

    # Precompute neighbor offsets + horizontal step distance
    step_specs: list[tuple[int, int, float, bool]] = []
    for dr, dc in NEIGHBORS_8:
        d2d = d_diag if (dr != 0 and dc != 0) else (dy if dr != 0 else dx)
        step_specs.append((dr, dc, d2d, dr != 0 and dc != 0))

    hab_idx = hab_r * cols + hab_c
    time_flat[hab_idx] = 0.0
    heap: list[tuple[float, int]] = [(0.0, hab_idx)]
    settled = 0

    while heap:
        t_u, u_idx = heapq.heappop(heap)
        if t_u > time_flat[u_idx]:
            continue
        settled += 1
        r = u_idx // cols
        c = u_idx % cols
        z_u = float(elev_f[r, c])

        for dr, dc, d2d, is_diag in step_specs:
            # Incoming neighbor v moving v -> u (same grid neighborhood symmetry)
            vr = r + dr
            vc = c + dc
            if not (0 <= vr < rows and 0 <= vc < cols):
                continue
            v_idx = vr * cols + vc
            if not valid_flat[v_idx]:
                continue
            if is_diag:
                if not (valid_flat[(r + dr) * cols + c] and valid_flat[r * cols + (c + dc)]):
                    continue

            z_v = float(elev_f[vr, vc])
            dz_v_to_u = z_u - z_v
            d3d = math.hypot(d2d, dz_v_to_u)
            signed_grade = dz_v_to_u / max(d2d, 1e-6)
            spd = directional_walk_speed_m_s(base_spd, signed_grade)
            step_time_s = (d3d / spd) * mult
            cand = t_u + step_time_s
            if cand < time_flat[v_idx]:
                time_flat[v_idx] = cand
                heapq.heappush(heap, (cand, v_idx))

    time_grid = time_flat.reshape(rows, cols)
    reachable_mask = np.isfinite(time_grid) & (time_grid <= float(budget_seconds))
    trav_count = int(np.count_nonzero(valid_mask))
    reach_count = int(np.count_nonzero(reachable_mask))
    frac = round(reach_count / max(trav_count, 1), 4)

    return BackwardTimeGridResult(
        time_seconds_grid=time_grid,
        reachable_mask=reachable_mask,
        nodes_settled=settled,
        budget_seconds=budget_seconds,
        reachable_cell_count=reach_count,
        traversable_cell_count=trav_count,
        reachable_fraction=frac,
    )


def serialize_time_grid_overlay(
    time_seconds_grid: np.ndarray,
    meta: RasterMetadata,
    budget_minutes: float,
    max_dim: int = 72,
    as_of: str | None = None,
    source_name: str = "DEM Backward Dijkstra",
    resolution_m: float = 200.0,
) -> dict[str, Any]:
    """
    Downsamples a backward-Dijkstra time grid into a compact UI overlay matrix (`null` for unreachable/nodata).
    Preserves strict 'no invented numbers' discipline: infinite/NaN cells serialize as None.
    """
    rows, cols = time_seconds_grid.shape
    stride_r = max(1, math.ceil(rows / max_dim))
    stride_c = max(1, math.ceil(cols / max_dim))

    sampled_rows = list(range(0, rows, stride_r))
    sampled_cols = list(range(0, cols, stride_c))
    values_min: list[list[float | None]] = []
    for r in sampled_rows:
        row_vals: list[float | None] = []
        for c in sampled_cols:
            v = float(time_seconds_grid[r, c])
            row_vals.append(round(v / 60.0, 1) if math.isfinite(v) else None)
        values_min.append(row_vals)

    return {
        "bounds": [
            round(meta.min_lon, 6),
            round(meta.min_lat, 6),
            round(meta.max_lon, 6),
            round(meta.max_lat, 6),
        ],
        "rows": len(sampled_rows),
        "cols": len(sampled_cols),
        "budget_minutes": round(float(budget_minutes), 1),
        "minutes_grid": values_min,
        "provenance": {
            "kind": "computed",
            "source": source_name,
            "resolution": f"{round(resolution_m, 1)} m/px",
            "as_of": as_of,
        },
    }
