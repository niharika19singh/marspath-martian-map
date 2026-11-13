import heapq
import time

from backend.app.core.exceptions import (
    ComputationalBoundExceededError,
    RoutingTimeoutError,
    UnreachableDestinationError,
)
from backend.app.routing.graph_builder import TerrainGridGraph

DIJKSTRA_TIMEOUT_CHECK_INTERVAL_NODES: int = 200


def dijkstra_search(
    graph: TerrainGridGraph,
    start: tuple[int, int],
    dest: tuple[int, int],
    max_expansions: int = 150000,
    penalized_edges: dict[tuple[tuple[int, int], tuple[int, int]], float] | None = None,
    timeout_seconds: float | None = None,
    deadline: float | None = None,
    overall_start_time: float | None = None,
) -> tuple[list[tuple[int, int]], float, int, float]:
    """
    Dijkstra shortest path algorithm on the terrain graph (equivalent to A* with h(u) = 0).
    Guarantees optimal minimum-cost traversal. Used both as a standalone routing option
    and as an analytical baseline to verify A* optimality.

    Returns:
        (path_nodes, total_cost, nodes_expanded, elapsed_seconds)
    """
    start_time = time.perf_counter()
    effective_deadline = (
        deadline
        if deadline is not None
        else (start_time + timeout_seconds if timeout_seconds is not None else None)
    )
    base_start_time = overall_start_time if overall_start_time is not None else start_time

    if effective_deadline is not None and time.perf_counter() > effective_deadline:
        now = time.perf_counter()
        elapsed = now - base_start_time
        limit_sec = (
            timeout_seconds
            if timeout_seconds is not None
            else (effective_deadline - base_start_time)
        )
        raise RoutingTimeoutError(
            f"Dijkstra search exceeded routing timeout of {limit_sec:.2f}s (elapsed: {elapsed:.2f}s).",
            timeout_seconds=limit_sec,
            elapsed_seconds=elapsed,
        )

    if start == dest:
        return [start], 0.0, 0, 0.0

    # Priority queue storing (cost, (r, c))
    open_set: list[tuple[float, tuple[int, int]]] = [(0.0, start)]
    distances: dict[tuple[int, int], float] = {start: 0.0}
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    visited: set[tuple[int, int]] = set()
    nodes_expanded = 0

    while open_set:
        current_dist, current = heapq.heappop(open_set)

        if current in visited:
            continue

        visited.add(current)
        nodes_expanded += 1

        if nodes_expanded > max_expansions:
            raise ComputationalBoundExceededError(
                f"Dijkstra search exceeded safety expansion ceiling of {max_expansions} states.",
                dimensions=(graph.cols, graph.rows),
                max_allowed=max_expansions,
            )

        if effective_deadline is not None and (
            nodes_expanded % DIJKSTRA_TIMEOUT_CHECK_INTERVAL_NODES == 0
        ):
            now = time.perf_counter()
            if now > effective_deadline:
                elapsed = now - base_start_time
                limit_sec = (
                    timeout_seconds
                    if timeout_seconds is not None
                    else (effective_deadline - base_start_time)
                )
                raise RoutingTimeoutError(
                    f"Dijkstra search exceeded routing timeout of {limit_sec:.2f}s (elapsed: {elapsed:.2f}s).",
                    timeout_seconds=limit_sec,
                    elapsed_seconds=elapsed,
                )

        if current == dest:
            elapsed = time.perf_counter() - start_time
            path = [dest]
            curr = dest
            while curr in came_from:
                curr = came_from[curr]
                path.append(curr)
            path.reverse()
            return path, current_dist, nodes_expanded, elapsed

        curr_r, curr_c = current

        for neighbor, edge_cost, _, _, _, _ in graph.get_valid_neighbors(
            curr_r, curr_c, penalized_edges
        ):
            if neighbor in visited:
                continue

            tentative_dist = current_dist + edge_cost

            if tentative_dist < distances.get(neighbor, float("inf")):
                distances[neighbor] = tentative_dist
                came_from[neighbor] = current
                heapq.heappush(open_set, (tentative_dist, neighbor))

    elapsed = time.perf_counter() - start_time
    raise UnreachableDestinationError(
        f"Dijkstra found no traversable corridor between {start} and {dest}.",
        start=start,
        dest=dest,
    )
