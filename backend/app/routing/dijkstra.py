import heapq
import time
from typing import Dict, List, Optional, Set, Tuple
from backend.app.core.exceptions import ComputationalBoundExceededError, UnreachableDestinationError
from backend.app.routing.graph_builder import TerrainGridGraph


def dijkstra_search(
    graph: TerrainGridGraph,
    start: Tuple[int, int],
    dest: Tuple[int, int],
    max_expansions: int = 150000,
    penalized_edges: Optional[Dict[Tuple[Tuple[int, int], Tuple[int, int]], float]] = None,
) -> Tuple[List[Tuple[int, int]], float, int, float]:
    """
    Reference Dijkstra shortest path algorithm on the terrain graph.
    Used as an analytical baseline to verify A* optimality.

    Returns:
        (path_nodes, total_cost, nodes_expanded, elapsed_seconds)
    """
    start_time = time.perf_counter()

    if start == dest:
        return [start], 0.0, 0, 0.0

    # Priority queue storing (cost, (r, c))
    open_set: List[Tuple[float, Tuple[int, int]]] = [(0.0, start)]
    distances: Dict[Tuple[int, int], float] = {start: 0.0}
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    visited: Set[Tuple[int, int]] = set()
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

        for neighbor, edge_cost, _, _, _, _ in graph.get_valid_neighbors(curr_r, curr_c, penalized_edges):
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
