"""
Mission Knowledge Graph Implementation.
Provides in-memory indexing, multi-hop BFS/DFS provenance traversal,
spatial relationship linking, and causal impact propagation.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from backend.app.intelligence.fusion.evidence_model import NormalizedObservation
from backend.app.intelligence.fusion.spatial_temporal_index import (
    bbox_intersects,
    distance_point_to_segment_m,
)
from backend.app.intelligence.graph.entities import (
    EvidenceTrace,
    GraphEdge,
    GraphNode,
    GraphNodeType,
    GraphRelationType,
    ImpactTrace,
    SubgraphResponse,
)


class MissionKnowledgeGraph:
    """Core knowledge graph engine supporting multi-hop provenance and impact tracing."""

    def __init__(self) -> None:
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._out_edges: dict[str, list[str]] = {}  # node_id -> [edge_ids]
        self._in_edges: dict[str, list[str]] = {}   # node_id -> [edge_ids]

    def add_node(self, node: GraphNode) -> None:
        self._nodes[node.node_id] = node
        if node.node_id not in self._out_edges:
            self._out_edges[node.node_id] = []
        if node.node_id not in self._in_edges:
            self._in_edges[node.node_id] = []

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges[edge.edge_id] = edge
        if edge.source_node_id not in self._out_edges:
            self._out_edges[edge.source_node_id] = []
        if edge.target_node_id not in self._in_edges:
            self._in_edges[edge.target_node_id] = []

        self._out_edges[edge.source_node_id].append(edge.edge_id)
        self._in_edges[edge.target_node_id].append(edge.edge_id)

    def get_node(self, node_id: str) -> GraphNode | None:
        return self._nodes.get(node_id)

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        return self._edges.get(edge_id)

    def get_all_nodes(self) -> list[GraphNode]:
        return list(self._nodes.values())

    def get_all_edges(self) -> list[GraphEdge]:
        return list(self._edges.values())

    def get_out_edges(self, node_id: str) -> list[GraphEdge]:
        edge_ids = self._out_edges.get(node_id, [])
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def get_in_edges(self, node_id: str) -> list[GraphEdge]:
        edge_ids = self._in_edges.get(node_id, [])
        return [self._edges[eid] for eid in edge_ids if eid in self._edges]

    def trace_upstream_evidence(self, node_id: str, max_depth: int = 5) -> EvidenceTrace | None:
        """
        Traces upstream from an operational entity (e.g. RouteSegment or Hazard)
        back to the underlying observations and datasets.
        """
        root = self.get_node(node_id)
        if not root:
            return None

        visited_nodes: set[str] = {node_id}
        causal_path: list[str] = [node_id]
        evidence_nodes: list[GraphNode] = []
        connecting_edges: list[GraphEdge] = []

        # BFS queue: (current_node_id, current_depth)
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # In upstream tracing, inspect incoming and outgoing edges for supporting evidence
            candidate_edges = self.get_in_edges(curr_id) + self.get_out_edges(curr_id)
            for edge in candidate_edges:
                neighbor_id = edge.source_node_id if edge.target_node_id == curr_id else edge.target_node_id
                connecting_edges.append(edge)
                if neighbor_id not in visited_nodes:
                    visited_nodes.add(neighbor_id)
                    neighbor_node = self.get_node(neighbor_id)
                    if neighbor_node:
                        if neighbor_node.node_type in (GraphNodeType.OBSERVATION, GraphNodeType.DATASET):
                            evidence_nodes.append(neighbor_node)
                        causal_path.append(neighbor_id)
                        queue.append((neighbor_id, depth + 1))

        # Build scientific narrative
        obs_names = [n.label for n in evidence_nodes if n.node_type == GraphNodeType.OBSERVATION]
        narrative = (
            f"Entity '{root.label}' ({root.node_type.value}) is supported by {len(evidence_nodes)} evidence sources "
            f"across {len(connecting_edges)} verified relationship links. "
            f"Primary backing observations: {', '.join(obs_names[:3]) if obs_names else 'Numerical DEM raster derivation'}."
        )

        return EvidenceTrace(
            target_node=root,
            causal_chain=causal_path,
            evidence_nodes=evidence_nodes,
            connecting_edges=connecting_edges,
            explanation=narrative,
            scientific_narrative=narrative,
        )

    def trace_downstream_impacts(self, node_id: str, max_depth: int = 5) -> ImpactTrace | None:
        """
        Traces downstream from an observation or hazard to identify all impacted
        route segments, operational constraints, or mission assets.
        """
        root = self.get_node(node_id)
        if not root:
            return None

        visited_nodes: set[str] = {node_id}
        impacted_nodes: list[GraphNode] = []
        connecting_edges: list[GraphEdge] = []

        queue: deque[tuple[str, int]] = deque([(node_id, 0)])

        while queue:
            curr_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            candidate_edges = self.get_out_edges(curr_id) + self.get_in_edges(curr_id)
            for edge in candidate_edges:
                neighbor_id = edge.target_node_id if edge.source_node_id == curr_id else edge.source_node_id
                connecting_edges.append(edge)
                if neighbor_id not in visited_nodes:
                    visited_nodes.add(neighbor_id)
                    neighbor_node = self.get_node(neighbor_id)
                    if neighbor_node:
                        if neighbor_node.node_type in (
                            GraphNodeType.ROUTE_SEGMENT,
                            GraphNodeType.ROUTE,
                            GraphNodeType.MISSION_ASSET,
                            GraphNodeType.OPERATIONAL_CONSTRAINT,
                            GraphNodeType.HAZARD,
                        ):
                            impacted_nodes.append(neighbor_node)
                        queue.append((neighbor_id, depth + 1))

        summary = (
            f"Root '{root.label}' ({root.node_type.value}) propagates downstream to {len(impacted_nodes)} "
            f"mission entities ({sum(1 for n in impacted_nodes if n.node_type == GraphNodeType.ROUTE_SEGMENT)} route segments, "
            f"{sum(1 for n in impacted_nodes if n.node_type == GraphNodeType.OPERATIONAL_CONSTRAINT)} constraints)."
        )

        return ImpactTrace(
            root_node=root,
            source_node=root,
            affected_nodes=impacted_nodes,
            connecting_edges=connecting_edges,
            mission_impact_summary=summary,
            downstream_paths=[[root.node_id, n.node_id] for n in impacted_nodes],
        )

    def query_subgraph(
        self,
        node_types: list[GraphNodeType] | None = None,
        node_type: str | None = None,
        route_id: str | None = None,
        bbox: list[float] | None = None,
        limit: int = 100,
        max_depth: int = 3,
        root_node_id: str | None = None,
        max_nodes: int | None = None,
    ) -> SubgraphResponse:
        """Filters nodes and edges based on bounding box, route, or node types with bounded limit."""
        effective_limit = max_nodes or limit
        type_filters: list[str] = []
        if node_types:
            type_filters.extend([t.value.lower() if hasattr(t, "value") else str(t).lower() for t in node_types])
        if node_type:
            type_filters.append(node_type.lower())

        if root_node_id and root_node_id in self._nodes:
            # Subgraph rooted at specific node
            visited: set[str] = {root_node_id}
            queue = deque([(root_node_id, 0)])
            selected_edges: list[GraphEdge] = []

            while queue:
                cid, d = queue.popleft()
                if d >= max_depth:
                    continue
                # Traverse outgoing and incoming
                neighbors = []
                for e in self.get_out_edges(cid):
                    selected_edges.append(e)
                    neighbors.append(e.target_node_id)
                for e in self.get_in_edges(cid):
                    selected_edges.append(e)
                    neighbors.append(e.source_node_id)

                for nid in neighbors:
                    if nid not in visited and len(visited) < effective_limit:
                        visited.add(nid)
                        queue.append((nid, d + 1))

            sub_nodes = [self._nodes[nid] for nid in visited if nid in self._nodes]
            return SubgraphResponse(
                nodes_count=len(sub_nodes),
                edges_count=len(selected_edges),
                nodes=sub_nodes,
                edges=selected_edges,
                traversal_depth=max_depth,
                root_node_id=root_node_id,
            )

        # Global query with filters
        matching_nodes: list[GraphNode] = []
        for n in self._nodes.values():
            if type_filters and n.node_type.value.lower() not in type_filters:
                continue
            if route_id and n.properties.get("route_id") and n.properties.get("route_id") != route_id:
                continue
            if bbox and n.bbox:
                if not bbox_intersects(n.bbox, bbox):
                    continue
            matching_nodes.append(n)
            if len(matching_nodes) >= effective_limit:
                break

        node_ids_set = {n.node_id for n in matching_nodes}
        matching_edges: list[GraphEdge] = [
            e for e in self._edges.values()
            if e.source_node_id in node_ids_set or e.target_node_id in node_ids_set
        ]
        # Include any endpoint nodes so edges are not dangling
        for e in matching_edges:
            for ep in (e.source_node_id, e.target_node_id):
                if ep not in node_ids_set and ep in self._nodes:
                    node_ids_set.add(ep)
                    matching_nodes.append(self._nodes[ep])

        return SubgraphResponse(
            nodes_count=len(matching_nodes),
            edges_count=len(matching_edges),
            nodes=matching_nodes,
            edges=matching_edges,
            traversal_depth=None,
            root_node_id=None,
        )


def populate_knowledge_graph_from_mission(
    graph: MissionKnowledgeGraph | None = None,
    route: dict[str, Any] | None = None,
    observations: list[NormalizedObservation] | None = None,
    science_targets: list[dict[str, Any]] | None = None,
    mission_id: str = "jezero_delta_expedition",
) -> MissionKnowledgeGraph:
    """
    Constructs an explicit Mission Knowledge Graph connecting datasets, observations,
    terrain regions, hazards, route segments, and operational constraints.
    """
    graph = graph if graph is not None else MissionKnowledgeGraph()
    observations = observations or []

    # 1. Dataset Nodes
    ds_hirise = GraphNode(
        node_id="ds:usgs_hirise_dtm_1m",
        node_type=GraphNodeType.DATASET,
        label="USGS HiRISE 1 m DTM (Jezero Crater)",
        description="High-resolution 1 m/px stereo DEM covering the western Jezero fan and delta.",
        provenance_source="USGS Astrogeology (DOI: 10.5066/P9REJ9JN)",
        properties={"resolution_m": 1.0, "format": "GeoTIFF", "quality_tier": "GOLD"},
    )
    ds_mola = GraphNode(
        node_id="ds:usgs_mola_hrsc_200m",
        node_type=GraphNodeType.DATASET,
        label="USGS MOLA-HRSC Blended DEM (200 m/px)",
        description="Regional blended topographic reference model for Mars Jezero Quadrangle.",
        provenance_source="USGS Astrogeology (DOI: 10.5066/P907276M)",
        properties={"resolution_m": 200.0, "format": "GeoTIFF", "quality_tier": "SILVER"},
    )
    ds_themis = GraphNode(
        node_id="ds:themis_night_ir",
        node_type=GraphNodeType.DATASET,
        label="2001 Mars Odyssey THEMIS Nighttime Infrared",
        description="Surface thermal inertia mapping bedrock vs uncompacted dust mobility hazards.",
        provenance_source="NASA/ASU THEMIS Data Viewer",
        properties={"resolution_m": 100.0, "quality_tier": "GOLD"},
    )
    ds_meda = GraphNode(
        node_id="ds:m2020_meda",
        node_type=GraphNodeType.DATASET,
        label="Mars 2020 Perseverance MEDA Calibrated Archive",
        description="In-situ surface atmospheric weather and solar radiation records.",
        provenance_source="NASA PDS Atmospheres Node",
        properties={"quality_tier": "GOLD"},
    )
    for ds in (ds_hirise, ds_mola, ds_themis, ds_meda):
        graph.add_node(ds)

    # 2. Add Normalized Observations & connect to Datasets
    for obs in observations:
        obs_node = GraphNode(
            node_id=f"obs:{obs.observation_id}",
            node_type=GraphNodeType.OBSERVATION,
            label=obs.title or obs.observation_id,
            description=obs.description,
            spatial_extent=obs.geometry,
            bbox=obs.bbox,
            timestamp_utc=obs.timestamp_utc,
            sol=obs.martian_sol,
            provenance_source=obs.source_id,
            properties={
                "instrument": obs.instrument,
                "measurement_type": obs.measurement_type,
                "measurement_value": obs.measurement_value,
                "units": obs.units,
                "resolution_m": obs.spatial_resolution_m,
                "provenance_kind": obs.provenance_kind.value,
                "quality_tier": obs.quality_tier.value,
            },
        )
        graph.add_node(obs_node)

        # Link to respective Dataset
        parent_ds = (
            "ds:usgs_hirise_dtm_1m" if "hirise" in obs.instrument.lower()
            else "ds:usgs_mola_hrsc_200m" if "mola" in obs.instrument.lower()
            else "ds:themis_night_ir" if "themis" in obs.instrument.lower()
            else "ds:m2020_meda" if "meda" in obs.instrument.lower()
            else None
        )
        if parent_ds:
            graph.add_edge(
                GraphEdge(
                    edge_id=f"e:derived_{obs_node.node_id}_{parent_ds}",
                    source_node_id=obs_node.node_id,
                    target_node_id=parent_ds,
                    relation_type=GraphRelationType.DERIVED_FROM,
                    confidence=1.0,
                    provenance_basis="Observation cataloged and derived from authoritative mission dataset bundle.",
                )
            )

    # 2b. Terrain Regions
    region_neretva = GraphNode(
        node_id="region:neretva_vallis_fan",
        node_type=GraphNodeType.TERRAIN_REGION,
        label="Neretva Vallis Delta Fan",
        description="Fluvial deltaic depositional fan rich in smectite and carbonate bearing strata.",
        spatial_extent={"type": "Polygon", "coordinates": [[[77.38, 18.40], [77.46, 18.40], [77.46, 18.46], [77.38, 18.46], [77.38, 18.40]]]},
        bbox=[77.38, 18.40, 77.46, 18.46],
        properties={"geology": "Delta front siltstone", "relief_m": 85.0},
    )
    graph.add_node(region_neretva)

    # 2c. Hazard Nodes
    hazard_scarp = GraphNode(
        node_id="hazard:neretva_steep_scarp",
        node_type=GraphNodeType.HAZARD,
        label="Neretva Delta Front Scarp (Slope > 18°)",
        description="Steep erosional escarpment with localized relief exceeding rover pitch stability thresholds.",
        spatial_extent={"type": "Point", "coordinates": [77.425, 18.429]},
        bbox=[77.424, 18.428, 77.426, 18.430],
        properties={"hazard_type": "STEEP_SLOPE", "severity": "HIGH", "max_slope_deg": 19.4},
    )
    graph.add_node(hazard_scarp)

    # Link hazard to HiRISE DTM dataset via DERIVED_FROM
    graph.add_edge(
        GraphEdge(
            edge_id="e:hazard_derived_hirise_dtm",
            source_node_id=hazard_scarp.node_id,
            target_node_id=ds_hirise.node_id,
            relation_type=GraphRelationType.DERIVED_FROM,
            confidence=0.98,
            provenance_basis="Slope derivative calculated from 1 m USGS HiRISE DTM raster.",
        )
    )
    # Link hazard to region via LOCATED_IN
    graph.add_edge(
        GraphEdge(
            edge_id="e:hazard_located_in_neretva",
            source_node_id=hazard_scarp.node_id,
            target_node_id=region_neretva.node_id,
            relation_type=GraphRelationType.LOCATED_IN,
            confidence=1.0,
            provenance_basis="Feature georeferenced within Neretva Vallis delta deposit boundary.",
        )
    )

    # 3. Operational Constraints Nodes
    c_slope = GraphNode(
        node_id="c:slope_ceiling_14deg",
        node_type=GraphNodeType.OPERATIONAL_CONSTRAINT,
        label="14.0° Planetary Traverse Slope Ceiling",
        description="Wheel-slip limitation preventing uphill spin or downhill slide on martian regolith.",
        properties={"max_slope_deg": 14.0, "strictness": "BLOCKING"},
    )
    c_eva = GraphNode(
        node_id="c:eva_budget_8h",
        node_type=GraphNodeType.OPERATIONAL_CONSTRAINT,
        label="8.0 h Maximum EVA Time Budget",
        description="Life-support and battery limit requiring mission return before expiration.",
        properties={"max_eva_hours": 8.0, "strictness": "CONSTRAINING"},
    )
    c_rescue = GraphNode(
        node_id="c:rescue_threshold_30m",
        node_type=GraphNodeType.OPERATIONAL_CONSTRAINT,
        label="30 Minute Contingency Rescue Window",
        description="Maximum travel time for rescue rover intervention from base habitat.",
        properties={"rescue_threshold_minutes": 30.0, "strictness": "MONITORED"},
    )
    for c in (c_slope, c_eva, c_rescue):
        graph.add_node(c)

    # Link hazard to slope constraint
    graph.add_edge(
        GraphEdge(
            edge_id="e:hazard_violates_slope_ceiling",
            source_node_id=hazard_scarp.node_id,
            target_node_id=c_slope.node_id,
            relation_type=GraphRelationType.CONSTRAINS,
            confidence=1.0,
            provenance_basis="Scarp slope of 19.4° exceeds 14.0° planetary traverse limit.",
        )
    )

    # 4. Route and Route Segments (if route is provided or default active route)
    active_route = route or {
        "route_id": "primary",
        "name": "Jezero Western Delta Traverse",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [77.4120, 18.4200, -2540.0],
                [77.4180, 18.4240, -2532.0],
                [77.4250, 18.4290, -2524.0],
                [77.4310, 18.4330, -2518.0],
                [77.4380, 18.4370, -2510.0],
                [77.4440, 18.4410, -2502.0],
                [77.4510, 18.4460, -2494.0],
                [77.4570, 18.4500, -2485.0],
            ],
        },
        "summary": {"total_distance_meters": 3120.0, "risk_category": "NOMINAL"},
    }

    if active_route and active_route.get("geometry") and active_route["geometry"].get("coordinates"):
        coords = active_route["geometry"]["coordinates"]
        route_id = active_route.get("route_id", "primary")
        route_node = GraphNode(
            node_id=f"route:{route_id}",
            node_type=GraphNodeType.ROUTE,
            label=f"Traverse Plan: {active_route.get('name', route_id)}",
            description=f"Multi-objective route covering {len(coords)} coordinates.",
            spatial_extent=active_route.get("geometry"),
            properties={
                "route_id": route_id,
                "total_distance_m": active_route.get("summary", {}).get("total_distance_meters", 0.0),
                "total_cost": active_route.get("total_cost", 0.0),
                "risk_category": active_route.get("summary", {}).get("risk_category", "LOW_RISK"),
            },
        )
        graph.add_node(route_node)

        # Connect constraints to Route
        graph.add_edge(
            GraphEdge(
                edge_id=f"e:constrains_slope_{route_node.node_id}",
                source_node_id=c_slope.node_id,
                target_node_id=route_node.node_id,
                relation_type=GraphRelationType.CONSTRAINS,
                confidence=1.0,
                provenance_basis="Traversability engine restricts maximum slope gradient across route nodes.",
            )
        )
        graph.add_edge(
            GraphEdge(
                edge_id=f"e:constrains_eva_{route_node.node_id}",
                source_node_id=c_eva.node_id,
                target_node_id=route_node.node_id,
                relation_type=GraphRelationType.CONSTRAINS,
                confidence=1.0,
                provenance_basis="Return-time constraint monitors outbound + return mission duration against EVA budget.",
            )
        )

        # Decompose route into segments (up to 12 representative segments for responsive graph traversal)
        step = max(1, len(coords) // 10)
        seg_indices = list(range(0, len(coords) - 1, step))
        if seg_indices[-1] != len(coords) - 2:
            seg_indices.append(len(coords) - 2)

        for i, idx in enumerate(seg_indices):
            p1 = coords[idx]
            p2 = coords[min(idx + step, len(coords) - 1)]
            seg_node = GraphNode(
                node_id=f"seg:{route_id}_step_{i+1}",
                node_type=GraphNodeType.ROUTE_SEGMENT,
                label=f"Route Segment {i+1} ({route_id})",
                description=f"Traverse segment from ({p1[0]:.4f}, {p1[1]:.4f}) to ({p2[0]:.4f}, {p2[1]:.4f}).",
                spatial_extent={"type": "LineString", "coordinates": [p1, p2]},
                bbox=[min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])],
                properties={
                    "route_id": route_id,
                    "segment_index": i + 1,
                    "start_coord": [p1[0], p1[1]],
                    "end_coord": [p2[0], p2[1]],
                },
            )
            graph.add_node(seg_node)

            # Link segment to parent Route via DEPENDS_ON / DERIVED_FROM
            graph.add_edge(
                GraphEdge(
                    edge_id=f"e:seg_to_route_{seg_node.node_id}",
                    source_node_id=seg_node.node_id,
                    target_node_id=route_node.node_id,
                    relation_type=GraphRelationType.DEPENDS_ON,
                    confidence=1.0,
                    provenance_basis="Segment forms integral link in end-to-end mission traverse plan.",
                )
            )

            # Check if any observation intersects this segment
            for obs in observations:
                if obs.bbox and bbox_intersects(obs.bbox, seg_node.bbox or []):
                    # Check distance
                    is_hit = False
                    if obs.geometry.get("type") == "Point":
                        pt = obs.geometry["coordinates"]
                        dist = distance_point_to_segment_m(pt[0], pt[1], p1[0], p1[1], p2[0], p2[1])
                        is_hit = dist <= 200.0
                    else:
                        is_hit = True

                    if is_hit:
                        obs_node_id = f"obs:{obs.observation_id}"
                        rel = (
                            GraphRelationType.AFFECTS
                            if "hazard" in obs.measurement_type or "themis" in obs.source_id
                            else GraphRelationType.COVERS
                        )
                        graph.add_edge(
                            GraphEdge(
                                edge_id=f"e:rel_{obs_node_id}_{seg_node.node_id}",
                                source_node_id=obs_node_id,
                                target_node_id=seg_node.node_id,
                                relation_type=rel,
                                confidence=0.95,
                                provenance_basis="Spatial intersection verified between observation extent and route segment corridor.",
                            )
                        )

    # 5. Science Targets Nodes
    if science_targets:
        for st in science_targets:
            st_id = st.get("target_id", "target")
            st_node = GraphNode(
                node_id=f"target:{st_id}",
                node_type=GraphNodeType.SCIENCE_TARGET,
                label=st.get("name", st_id),
                description=st.get("scientific_rationale"),
                spatial_extent={"type": "Point", "coordinates": [st["lon"], st["lat"]]},
                bbox=[st["lon"] - 0.001, st["lat"] - 0.001, st["lon"] + 0.001, st["lat"] + 0.001],
                properties={
                    "science_value_points": st.get("science_value_points", 50.0),
                    "geologic_unit": st.get("geologic_unit"),
                    "instruments": st.get("instruments", []),
                },
            )
            graph.add_node(st_node)

    return graph
