import math
from collections.abc import Generator

import numpy as np

from backend.app.geospatial.terrain_metrics import compute_directional_gradients
from backend.app.routing.cost_model import (
    DEFAULT_CROSS_SLOPE_WEIGHT,
    DEFAULT_SUIT_LOAD_FACTOR,
    MARS_EARTH_GRAVITY_RATIO,
    CostMode,
    EffortModel,
    calculate_edge_cost,
)
from backend.app.schemas.mission import OptimizationMode

# 8-connected grid direction vectors: (d_row, d_col)
# First 4 are orthogonal; next 4 are diagonal
NEIGHBORS_8 = [
    (-1, 0),  # North
    (1, 0),  # South
    (0, -1),  # West
    (0, 1),  # East
    (-1, -1),  # North-West
    (-1, 1),  # North-East
    (1, -1),  # South-West
    (1, 1),  # South-East
]


def directional_walk_speed_m_s(base_speed_m_s: float, signed_grade: float) -> float:
    """
    Slope-adjusted walking speed (m/s) accounting for direction of travel along grade dz/d2d.
    Uphill (grade > 0) slows pace; gentle downhill (~-0.05) slightly assists; steep downhill slows for braking.
    """
    g = max(-1.0, min(1.0, float(signed_grade)))
    factor = math.exp(-2.8 * abs(g + 0.04)) * 1.12
    return max(0.08 * base_speed_m_s, min(1.15 * base_speed_m_s, base_speed_m_s * factor))


class TerrainGridGraph:
    """
    8-connected terrain graph over a cropped Martian DEM.
    Enforces physical distance metrics, diagonal corner-cutting prevention,
    directional along-track and cross-slope geometry, return-time blocking masks,
    and traversability constraints.
    """

    def __init__(
        self,
        elevation: np.ndarray,
        slope_deg: np.ndarray,
        roughness: np.ndarray,
        traversable_mask: np.ndarray,
        dx_meters: float,
        dy_meters: float,
        mode: OptimizationMode = OptimizationMode.BALANCED,
        cost_mode: str = CostMode.DIRECTIONAL.value,
        effort_model: str = EffortModel.SLOPE_PENALTY.value,
        cross_slope_weight: float = DEFAULT_CROSS_SLOPE_WEIGHT,
        gravity_ratio: float = MARS_EARTH_GRAVITY_RATIO,
        suit_load_factor: float = DEFAULT_SUIT_LOAD_FACTOR,
        dz_deast: np.ndarray | None = None,
        dz_dnorth: np.ndarray | None = None,
        return_blocked_mask: np.ndarray | None = None,
    ):
        self.elevation = elevation
        self.slope_deg = slope_deg
        self.roughness = roughness
        self.traversable = traversable_mask
        self.dx = dx_meters
        self.dy = dy_meters
        self.mode = mode
        self.cost_mode = str(cost_mode or CostMode.DIRECTIONAL.value).lower()
        self.effort_model = str(effort_model or EffortModel.SLOPE_PENALTY.value).lower()
        self.cross_slope_weight = float(cross_slope_weight)
        self.gravity_ratio = float(gravity_ratio)
        self.suit_load_factor = float(suit_load_factor)
        self.return_blocked_mask = return_blocked_mask
        self.rows, self.cols = elevation.shape

        # Precalculate orthogonal and diagonal 2D distances
        self.dist_orth_x = dx_meters
        self.dist_orth_y = dy_meters
        self.dist_diag = math.sqrt(dx_meters**2 + dy_meters**2)

        if dz_deast is None or dz_dnorth is None:
            nodata_mask = np.isnan(elevation)
            self.dz_deast, self.dz_dnorth = compute_directional_gradients(
                elevation, dx_meters, dy_meters, nodata_mask=nodata_mask
            )
        else:
            self.dz_deast = dz_deast
            self.dz_dnorth = dz_dnorth

    def is_in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def compute_edge_geometry(self, r: int, c: int, nr: int, nc: int) -> tuple[float, float, float, float, float]:
        """
        Returns (d2d, delta_z, dist_3d, along_slope_deg, cross_slope_deg) for directed step (r,c)->(nr,nc).
        """
        dr = nr - r
        dc = nc - c
        vx = dc * self.dx
        vy = -dr * self.dy  # Row increases South; physical North vector is -dr * dy
        d2d = math.hypot(vx, vy)
        delta_z = float(self.elevation[nr, nc]) - float(self.elevation[r, c])
        dist_3d = math.sqrt(d2d**2 + delta_z**2)

        along_grade = delta_z / max(d2d, 1e-6)
        along_slope_deg = math.degrees(math.atan(along_grade))

        # Project local DEM gradient onto unit perpendicular vector (-vy/d2d, vx/d2d)
        ux = vx / max(d2d, 1e-6)
        uy = vy / max(d2d, 1e-6)
        px = -uy
        py = ux

        gx0 = float(self.dz_deast[r, c])
        gy0 = float(self.dz_dnorth[r, c])
        gx1 = float(self.dz_deast[nr, nc])
        gy1 = float(self.dz_dnorth[nr, nc])

        grads: list[tuple[float, float]] = []
        if not math.isnan(gx0) and not math.isnan(gy0):
            grads.append((gx0, gy0))
        if not math.isnan(gx1) and not math.isnan(gy1):
            grads.append((gx1, gy1))

        if grads:
            mean_gx = sum(g[0] for g in grads) / len(grads)
            mean_gy = sum(g[1] for g in grads) / len(grads)
            cross_grade = abs((mean_gx * px) + (mean_gy * py))
            cross_slope_deg = math.degrees(math.atan(cross_grade))
        else:
            cross_slope_deg = 0.0

        return d2d, delta_z, dist_3d, along_slope_deg, cross_slope_deg

    def edge_cost(
        self, r: int, c: int, nr: int, nc: int, extra_penalty: float = 0.0
    ) -> tuple[float, float, float, float, float, dict[str, float]]:
        """Computes directed edge cost and geometric attributes using graph cost_mode & effort_model."""
        d2d, delta_z, dist_3d, along_slope_deg, cross_slope_deg = self.compute_edge_geometry(r, c, nr, nc)
        slope = float(self.slope_deg[nr, nc])
        rough = float(self.roughness[nr, nc])
        cost, breakdown = calculate_edge_cost(
            distance_3d=dist_3d,
            slope_deg=slope,
            roughness=rough,
            delta_z=delta_z,
            mode=self.mode,
            extra_penalty=extra_penalty,
            along_slope_deg=along_slope_deg,
            cross_slope_deg=cross_slope_deg,
            d2d=d2d,
            cost_mode=self.cost_mode,
            effort_model=self.effort_model,
            cross_slope_weight=self.cross_slope_weight,
            gravity_ratio=self.gravity_ratio,
            suit_load_factor=self.suit_load_factor,
        )
        return cost, dist_3d, slope, rough, delta_z, breakdown

    def get_valid_neighbors(
        self, r: int, c: int, penalized_edges: dict | None = None
    ) -> Generator[tuple[tuple[int, int], float, float, float, float, float], None, None]:
        """
        Yields traversable neighbors:
        ((nr, nc), edge_cost, step_dist_3d, step_slope, step_rough, delta_z)
        """
        for dr, dc in NEIGHBORS_8:
            nr, nc = r + dr, c + dc

            if not self.is_in_bounds(nr, nc):
                continue

            if not self.traversable[nr, nc]:
                continue

            if self.return_blocked_mask is not None and not self.return_blocked_mask[nr, nc]:
                continue

            # Diagonal corner-cutting check:
            if dr != 0 and dc != 0:
                if not self.traversable[r + dr, c] or not self.traversable[r, c + dc]:
                    continue
                if self.return_blocked_mask is not None and (
                    not self.return_blocked_mask[r + dr, c] or not self.return_blocked_mask[r, c + dc]
                ):
                    continue

            extra_pen = 0.0
            if penalized_edges and ((r, c), (nr, nc)) in penalized_edges:
                extra_pen = penalized_edges[((r, c), (nr, nc))]

            cost, dist_3d, slope, rough, delta_z, _ = self.edge_cost(r, c, nr, nc, extra_penalty=extra_pen)
            yield (nr, nc), cost, dist_3d, slope, rough, delta_z
