"""
Central Mission Intelligence & Risk Fusion Hub.
Coordinates the Spatial-Temporal Index, Freshness Auditing, Knowledge Graph,
Risk Propagation, and Scenario Simulation engines.
"""

from __future__ import annotations

from typing import Any

from backend.app.intelligence.fusion.evidence_model import (
    DataFreshnessReport,
    NormalizedObservation,
)
from backend.app.intelligence.fusion.freshness_service import DataFreshnessService
from backend.app.intelligence.fusion.spatial_temporal_index import (
    SpatialTemporalIntelligenceIndex,
)
from backend.app.intelligence.graph.entities import (
    EvidenceTrace,
    GraphNode,
    ImpactTrace,
    SubgraphResponse,
)
from backend.app.intelligence.graph.knowledge_graph import (
    populate_knowledge_graph_from_mission,
)
from backend.app.intelligence.risk_propagation.propagation_engine import (
    RiskPropagationEngine,
    RouteRiskPropagationResult,
)
from backend.app.intelligence.risk_propagation.scenarios import (
    MissionScenario,
    ScenarioAnalysisResult,
    ScenarioComparisonReport,
    ScenarioCreateRequest,
    scenario_manager,
)


class MissionIntelligenceHub:
    """Singleton coordinating planetary intelligence services."""

    _instance: MissionIntelligenceHub | None = None

    def __init__(self) -> None:
        self.index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        self.freshness_service = DataFreshnessService(index=self.index)
        self.graph = populate_knowledge_graph_from_mission(
            observations=self.index.get_all(),
            route=None,
        )
        self.scenarios = scenario_manager

    @classmethod
    def get_instance(cls) -> MissionIntelligenceHub:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_data_freshness(self) -> DataFreshnessReport:
        return self.freshness_service.audit_sources_health()

    def query_observations(
        self,
        bbox: list[float] | None = None,
        min_sol: int | None = None,
        max_sol: int | None = None,
        min_ls: float | None = None,
        max_ls: float | None = None,
        instrument: str | None = None,
        provenance_kind: str | None = None,
        quality_tier: str | None = None,
        measurement_type: str | None = None,
        limit: int = 50,
    ) -> list[NormalizedObservation]:
        return self.index.query_observations(
            bbox=bbox,
            min_sol=min_sol,
            max_sol=max_sol,
            min_ls=min_ls,
            max_ls=max_ls,
            instrument=instrument,
            provenance_kind=provenance_kind,
            quality_tier=quality_tier,
            measurement_type=measurement_type,
            limit=limit,
        )

    def get_graph_subgraph(
        self,
        node_type: str | None = None,
        max_nodes: int = 100,
    ) -> SubgraphResponse:
        return self.graph.query_subgraph(node_type=node_type, max_nodes=max_nodes)

    def get_graph_node(self, node_id: str) -> GraphNode | None:
        return self.graph.get_node(node_id)

    def trace_node_evidence(self, node_id: str, max_depth: int = 5) -> EvidenceTrace | None:
        return self.graph.trace_upstream_evidence(node_id, max_depth=max_depth)

    def trace_node_impacts(self, node_id: str, max_depth: int = 5) -> ImpactTrace | None:
        return self.graph.trace_downstream_impacts(node_id, max_depth=max_depth)

    def evaluate_route_risk(
        self,
        route_data: dict[str, Any],
        max_slope_ceiling_deg: float = 14.0,
        max_roughness_limit: float = 0.85,
    ) -> RouteRiskPropagationResult:
        # Also sync new route into the knowledge graph
        self.graph = populate_knowledge_graph_from_mission(
            observations=self.index.get_all(),
            route=route_data,
        )
        return RiskPropagationEngine.evaluate_route(
            route_data=route_data,
            observations=self.index.get_all(),
            max_slope_ceiling_deg=max_slope_ceiling_deg,
            max_roughness_limit=max_roughness_limit,
        )

    def list_scenarios(self) -> list[MissionScenario]:
        return self.scenarios.list_scenarios()

    def get_scenario(self, scenario_id: str) -> MissionScenario | None:
        return self.scenarios.get_scenario(scenario_id)

    def create_scenario(self, req: ScenarioCreateRequest) -> MissionScenario:
        return self.scenarios.create_scenario(req)

    def analyze_scenario(
        self,
        scenario_id: str,
        route_data: dict[str, Any] | None = None,
    ) -> ScenarioAnalysisResult:
        route = route_data or self._get_default_jezero_route()
        return self.scenarios.analyze_scenario(
            scenario_id=scenario_id,
            route_data=route,
            observations=self.index.get_all(),
        )

    def compare_scenario(
        self,
        scenario_id: str,
        baseline_route_data: dict[str, Any] | None = None,
    ) -> ScenarioComparisonReport:
        route = baseline_route_data or self._get_default_jezero_route()
        return self.scenarios.compare_scenario(
            scenario_id=scenario_id,
            baseline_route_data=route,
            observations=self.index.get_all(),
        )

    def _get_default_jezero_route(self) -> dict[str, Any]:
        return {
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
        }
