import math
from collections.abc import Generator

import numpy as np

from backend.app.routing.cost_model import calculate_edge_cost
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


class TerrainGridGraph:
    """
    8-connected terrain graph over a cropped Martian DEM.
    Enforces physical distance metrics, diagonal corner-cutting prevention,
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
    ):
        self.elevation = elevation
        self.slope_deg = slope_deg
        self.roughness = roughness
        self.traversable = traversable_mask
        self.dx = dx_meters
        self.dy = dy_meters
        self.mode = mode
        self.rows, self.cols = elevation.shape

        # Precalculate orthogonal and diagonal 2D distances
        self.dist_orth_x = dx_meters
        self.dist_orth_y = dy_meters
        self.dist_diag = math.sqrt(dx_meters**2 + dy_meters**2)

    def is_in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_valid_neighbors(
        self, r: int, c: int, penalized_edges: dict | None = None
    ) -> Generator[tuple[tuple[int, int], float, float, float, float, float], None, None]:
        """
        Yields traversable neighbors:
        ((nr, nc), edge_cost, step_dist_3d, step_slope, step_rough, delta_z)
        """
        z_curr = float(self.elevation[r, c])

        for dr, dc in NEIGHBORS_8:
            nr, nc = r + dr, c + dc

            if not self.is_in_bounds(nr, nc):
                continue

            # Must be traversable
            if not self.traversable[nr, nc]:
                continue

            # Diagonal corner-cutting check:
            # If moving diagonally, both orthogonal adjacent cells must also be traversable!
            # Prevents cutting through thin cliff corners or hazardous walls.
            if dr != 0 and dc != 0:
                if not self.traversable[r + dr, c] or not self.traversable[r, c + dc]:
                    continue
                d2d = self.dist_diag
            elif dr != 0:
                d2d = self.dist_orth_y
            else:
                d2d = self.dist_orth_x

            z_next = float(self.elevation[nr, nc])
            delta_z = z_next - z_curr
            dist_3d = math.sqrt(d2d**2 + delta_z**2)

            slope = float(self.slope_deg[nr, nc])
            rough = float(self.roughness[nr, nc])

            extra_pen = 0.0
            if penalized_edges and ((r, c), (nr, nc)) in penalized_edges:
                extra_pen = penalized_edges[((r, c), (nr, nc))]

            cost, _ = calculate_edge_cost(
                distance_3d=dist_3d,
                slope_deg=slope,
                roughness=rough,
                delta_z=delta_z,
                mode=self.mode,
                extra_penalty=extra_pen,
            )

            yield (nr, nc), cost, dist_3d, slope, rough, delta_z
