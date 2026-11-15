"""
Graph Entities & Relationships Schema for the MARSPath Mission Knowledge Graph.
Defines 12 standard node types and 12 directed relationship types with full provenance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GraphNodeType(str, Enum):
    """The 12 standard entity types of the Mars Mission Knowledge Graph."""

    OBSERVATION = "OBSERVATION"
    DATASET = "DATASET"
    TERRAIN_REGION = "TERRAIN_REGION"
    TERRAIN_CELL = "TERRAIN_CELL"
    HAZARD = "HAZARD"
    ROUTE = "ROUTE"
    ROUTE_SEGMENT = "ROUTE_SEGMENT"
    SCIENCE_TARGET = "SCIENCE_TARGET"
    ROVER_POSITION = "ROVER_POSITION"
    MISSION_ASSET = "MISSION_ASSET"
    OPERATIONAL_CONSTRAINT = "OPERATIONAL_CONSTRAINT"
    MISSION_SCENARIO = "MISSION_SCENARIO"


class GraphRelationType(str, Enum):
    """The 12 directed relationship types connecting mission knowledge entities."""

    OBSERVED_BY = "OBSERVED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    COVERS = "COVERS"
    INTERSECTS = "INTERSECTS"
    NEAR = "NEAR"
    AFFECTS = "AFFECTS"
    CONSTRAINS = "CONSTRAINS"
    DEPENDS_ON = "DEPENDS_ON"
    LOCATED_IN = "LOCATED_IN"
    SAMPLED_BY = "SAMPLED_BY"
    VALID_DURING = "VALID_DURING"
    ALTERNATIVE_TO = "ALTERNATIVE_TO"


class GraphNode(BaseModel):
    """A node in the Mars Mission Knowledge Graph representing a scientific or operational entity."""

    node_id: str = Field(..., description="Unique node identifier (e.g. obs:hirise_001, seg:rt1_004)")
    node_type: GraphNodeType = Field(..., description="Entity classification")
    label: str = Field(..., description="Human-readable title or callout")
    description: str | None = Field(None, description="Detailed description")
    spatial_extent: dict[str, Any] | None = Field(None, description="GeoJSON geometry or Point [lon, lat]")
    bbox: list[float] | None = Field(None, description="[min_lon, min_lat, max_lon, max_lat]")
    timestamp_utc: datetime | None = Field(None, description="Associated UTC timestamp")
    sol: int | None = Field(None, description="Associated Martian sol")
    provenance_source: str | None = Field(None, description="Originating dataset, mission, or tool")
    properties: dict[str, Any] = Field(default_factory=dict, description="Domain-specific metrics, scores, or flags")


class GraphEdge(BaseModel):
    """A directed edge in the Mars Mission Knowledge Graph representing a causal, spatial, or operational relation."""

    edge_id: str = Field(..., description="Unique edge identifier")
    source_node_id: str = Field(..., description="Tail node ID")
    target_node_id: str = Field(..., description="Head node ID")
    relation_type: GraphRelationType = Field(..., description="Semantic relationship type")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Calculation confidence or evidence strength [0.0, 1.0]")
    provenance_basis: str = Field(..., description="Mathematical or observational derivation rationale")
    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When this relationship was established"
    )
    properties: dict[str, Any] = Field(default_factory=dict, description="Extended relationship attributes")


class SubgraphResponse(BaseModel):
    """A bounded view or query result of the Mission Knowledge Graph."""

    nodes_count: int
    edges_count: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    traversal_depth: int | None = None
    root_node_id: str | None = None
    query_context: dict[str, Any] = Field(default_factory=dict)


class EvidenceTrace(BaseModel):
    """Upstream provenance trace demonstrating why a mission consequence exists."""

    target_node: GraphNode
    causal_chain: list[str] = Field(..., description="Ordered list of node IDs from root observation to target")
    evidence_nodes: list[GraphNode] = Field(..., description="All supporting observation and dataset nodes")
    connecting_edges: list[GraphEdge] = Field(..., description="Edges linking the evidence chain")
    explanation: str = Field(..., description="Human and scientific narrative explaining the chain")
    scientific_narrative: str | None = Field(None, description="Detailed narrative alias")


class ImpactTrace(BaseModel):
    """Downstream impact trace demonstrating how a hazard or condition affects the mission."""

    root_node: GraphNode
    source_node: GraphNode | None = Field(None, description="Alias for root_node")
    affected_nodes: list[GraphNode] = Field(..., description="Impacted route segments, assets, or constraints")
    connecting_edges: list[GraphEdge] = Field(..., description="Edges linking root to impacted entities")
    mission_impact_summary: str = Field(..., description="Summary of mission consequences")
    downstream_paths: list[list[str]] = Field(default_factory=list, description="All trace path sequences")
