import heapq
import math
import time

from backend.app.core.exceptions import ComputationalBoundExceededError, UnreachableDestinationError
from backend.app.routing.graph_builder import TerrainGridGraph


def euclidean_heuristic(r: int, c: int, dest_r: int, dest_c: int, dx: float, dy: float) -> float:
    """
    Admissible and consistent Euclidean distance heuristic in physical meters.
    h(u, v) <= true_cost(u, v) because true_cost >= dist_3d >= dist_2d.
    """
    dx_meters = (c - dest_c) * dx
    dy_meters = (r - dest_r) * dy
    return math.sqrt(dx_meters**2 + dy_meters**2)


def astar_search(
    graph: TerrainGridGraph,
    start: tuple[int, int],
    dest: tuple[int, int],
    max_expansions: int = 150000,
    penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] | None = None,
) -> tuple[list[tuple[int, int]], float, int, float]:
    """
    Runs A* graph search from start to destination on the terrain graph.

    Returns:
        (path_nodes, total_cost, nodes_expanded, elapsed_seconds)
    """
    start_time = time.perf_counter()

    if start == dest:
        return [start], 0.0, 0, 0.0

    start_r, start_c = start
    dest_r, dest_c = dest

    # Priority queue storing (f_score, g_score, (r, c))
    h0 = euclidean_heuristic(start_r, start_c, dest_r, dest_c, graph.dx, graph.dy)
    open_set: list[tuple[float, float, tuple[int, int]]] = [(h0, 0.0, start)]

    # g_score[node] = cheapest known cost from start to node
    g_score: dict[tuple[int, int], float] = {start: 0.0}

    # parent pointers for path reconstruction
    came_from: dict[tuple[int, int], tuple[int, int]] = {}

    closed_set: set[tuple[int, int]] = set()
    nodes_expanded = 0

    while open_set:
        f, current_g, current = heapq.heappop(open_set)

        if current in closed_set:
            continue

        closed_set.add(current)
        nodes_expanded += 1

        if nodes_expanded > max_expansions:
            raise ComputationalBoundExceededError(
                f"A* search exceeded safety expansion ceiling of {max_expansions} states.",
                dimensions=(graph.cols, graph.rows),
                max_allowed=max_expansions,
            )

        # Target reached!
        if current == dest:
            elapsed = time.perf_counter() - start_time
            # Reconstruct path
            path = [dest]
            curr = dest
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return path, current_g, nodes_expanded, elapsed

        curr_r, curr_c = current

        for neighbor, edge_cost, _, _, _, _ in graph.get_valid_neighbors(
            curr_r, curr_c, penalized_edges
        ):
            if neighbor in closed_set:
                continue

            tentative_g = current_g + edge_cost

            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = current
                nr, nc = neighbor
                h = euclidean_heuristic(nr, nc, dest_r, dest_c, graph.dx, graph.dy)
                f_score = tentative_g + h
                heapq.heappush(open_set, (f_score, tentative_g, neighbor))

    elapsed = time.perf_counter() - start_time
    raise UnreachableDestinationError(
        f"No traversable Martian corridor exists between {start} and {dest} with current constraints.",
        start=start,
        dest=dest,
    )
