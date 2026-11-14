"""
Comprehensive Test Suite for MARSPath Mission Intelligence & Risk Fusion Engine.
Validates multi-source data fusion, spatial-temporal indexing, knowledge graph traversals,
causal risk propagation, and what-if scenario simulations.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app.intelligence.fusion.evidence_model import (
    ProvenanceKind,
    QualityTier,
)
from backend.app.intelligence.fusion.source_normalizer import UnifiedSourceNormalizer
from backend.app.intelligence.fusion.spatial_temporal_index import (
    SpatialTemporalIntelligenceIndex,
    distance_point_to_segment_m,
    haversine_mars_distance_m,
)
from backend.app.intelligence.graph.entities import GraphNodeType
from backend.app.intelligence.graph.knowledge_graph import (
    populate_knowledge_graph_from_mission,
)
from backend.app.intelligence.risk_propagation.propagation_engine import RiskPropagationEngine
from backend.app.intelligence.risk_propagation.scenarios import (
    ScenarioCreateRequest,
    ScenarioModifiers,
    scenario_manager,
)
from backend.app.main import app

client = TestClient(app)


class TestDataFusionAndEvidenceModel:
    """Validates multi-source planetary data normalization into unified evidence schemas."""

    def test_hirise_dtm_normalization(self):
        obs = UnifiedSourceNormalizer.normalize_hirise_dtm_observation(
            product_id="DTEEC_069176_1985_069822_1985_U01",
            resolution_m=1.0,
        )
        assert obs.source_id == "usgs_astrogeology"
        assert obs.instrument == "HiRISE"
        assert obs.spatial_resolution_m == 1.0
        assert obs.provenance_kind == ProvenanceKind.DERIVED
        assert obs.quality_tier == QualityTier.GOLD
        assert obs.doi == "10.5066/P9REJ9JN"
        assert obs.bbox is not None
        assert len(obs.bbox) == 4

    def test_meda_weather_normalization(self):
        from datetime import UTC, datetime
        obs_temp = UnifiedSourceNormalizer.normalize_meda_observation(
            sol=1050,
            timestamp_utc=datetime(2024, 2, 4, 14, 0, tzinfo=UTC),
            air_temp_c=-42.5,
            pressure_pa=745.0,
        )
        assert obs_temp.source_id == "pds_atmospheres"
        assert obs_temp.martian_sol == 1050
        assert obs_temp.provenance_kind == ProvenanceKind.MEASURED
        assert obs_temp.measurement_value["air_temperature_c"] == -42.5

    def test_themis_thermal_inertia_normalization(self):
        obs_ti = UnifiedSourceNormalizer.normalize_themis_observation(
            product_id="I12345678",
            lon=77.45,
            lat=18.42,
            thermal_inertia=120.0,
        )
        assert obs_ti.provenance_kind == ProvenanceKind.DERIVED
        assert obs_ti.measurement_value["thermal_inertia_tiu"] == 120.0
        assert "HIGH_SINKAGE_RISK_UNCONSOLIDATED_DUST" in obs_ti.quality_flags

    def test_spatial_temporal_indexing(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        all_obs = index.get_all()
        assert len(all_obs) >= 6

        # Query by bounding box covering delta fan
        results = index.query_observations(bbox=[77.30, 18.30, 77.50, 18.50])
        assert len(results) >= 4

        # Query by instrument
        hirise_results = index.query_observations(instrument="HiRISE")
        assert len(hirise_results) >= 2
        for r in hirise_results:
            assert "HiRISE" in r.instrument

        # Query by provenance kind
        measured_results = index.query_observations(provenance_kind="measured")
        assert len(measured_results) >= 3

        # Coverage gap detection
        gaps = index.detect_coverage_gaps()
        assert len(gaps) >= 1
        assert gaps[0].gap_id.startswith("gap_")

    def test_mars_spherical_distance(self):
        # Two points 1 degree apart along the equator on Mars
        d = haversine_mars_distance_m(0.0, 0.0, 1.0, 0.0)
        # Mars circumference = 2 * pi * 3396190 ~ 21,338,882 m; 1 deg ~ 59,274 m
        assert 59000.0 < d < 59500.0

        # Point to segment distance
        d_pt_seg = distance_point_to_segment_m(0.0, 0.5, 0.0, 0.0, 0.0, 1.0)
        assert d_pt_seg == pytest.approx(0.0, abs=1e-3)


class TestMissionKnowledgeGraph:
    """Validates multi-hop knowledge graph creation and causal BFS/DFS traversals."""

    def test_graph_population_and_connectivity(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        graph = populate_knowledge_graph_from_mission(observations=index.get_all())

        nodes = graph.get_all_nodes()
        edges = graph.get_all_edges()

        assert len(nodes) >= 15
        assert len(edges) >= 15

        # Check key entity types exist
        node_types = {n.node_type for n in nodes}
        assert GraphNodeType.DATASET in node_types
        assert GraphNodeType.OBSERVATION in node_types
        assert GraphNodeType.HAZARD in node_types
        assert GraphNodeType.ROUTE_SEGMENT in node_types

    def test_upstream_evidence_traversal(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        graph = populate_knowledge_graph_from_mission(observations=index.get_all())

        # Trace evidence for hazard node
        trace = graph.trace_upstream_evidence("hazard:neretva_steep_scarp", max_depth=5)
        assert trace is not None
        assert trace.target_node.node_id == "hazard:neretva_steep_scarp"
        assert len(trace.evidence_nodes) >= 1
        assert len(trace.causal_chain) >= 2
        assert "USGS HiRISE 1 m DTM" in trace.scientific_narrative or "evidence sources" in trace.scientific_narrative

    def test_downstream_impact_traversal(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        graph = populate_knowledge_graph_from_mission(observations=index.get_all())

        # Trace downstream impacts for HiRISE DTM observation
        dtm_obs = next(n for n in graph.get_all_nodes() if "dtm" in n.node_id.lower())
        impact = graph.trace_downstream_impacts(dtm_obs.node_id, max_depth=5)
        assert impact is not None
        assert impact.source_node.node_id == dtm_obs.node_id
        assert len(impact.downstream_paths) >= 1

    def test_subgraph_filtering(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        graph = populate_knowledge_graph_from_mission(observations=index.get_all())

        haz_subgraph = graph.query_subgraph(node_type="hazard", max_nodes=50)
        assert len(haz_subgraph.nodes) >= 1
        assert any(n.node_type == GraphNodeType.HAZARD for n in haz_subgraph.nodes)


class TestRiskPropagationAndScenarios:
    """Validates deterministic risk propagation and scenario what-if comparisons."""

    def test_route_risk_propagation(self):
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        sample_route = {
            "route_id": "traverse_alpha",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [77.4120, 18.4200, -2540.0],
                    [77.4180, 18.4240, -2532.0],
                    [77.4250, 18.4290, -2524.0],
                    [77.4350, 18.4350, -2510.0],
                ],
            },
        }
        res = RiskPropagationEngine.evaluate_route(
            route_data=sample_route,
            observations=index.get_all(),
            max_slope_ceiling_deg=14.0,
        )
        assert res.route_id == "traverse_alpha"
        assert res.evaluated_segments_count >= 1
        assert res.relative_route_effort_index >= 1.0
        assert 0.0 <= res.uncertainty_exposure_score <= 100.0
        assert len(res.segment_evaluations) >= 1
        assert "deterministic planning indicators" in res.scientific_disclaimer

    def test_scenario_creation_and_analysis(self):
        mgr = scenario_manager
        sc = mgr.create_scenario(
            ScenarioCreateRequest(
                name="Test Dust Ingress",
                description="Simulated test scenario",
                modifiers=ScenarioModifiers(
                    tau_atmospheric_increase=1.2,
                    max_slope_ceiling_deg=11.0,
                ),
            )
        )
        assert sc.scenario_id.startswith("scenario-")
        assert sc.modifiers.tau_atmospheric_increase == 1.2

        sample_route = {
            "route_id": "test_route",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [77.4120, 18.4200, -2540.0],
                    [77.4180, 18.4240, -2532.0],
                ],
            },
        }
        index = SpatialTemporalIntelligenceIndex.create_default_jezero_index()
        analysis = mgr.analyze_scenario(sc.scenario_id, sample_route, index.get_all())
        assert analysis.scenario_id == sc.scenario_id
        assert analysis.estimated_relative_effort > 0.0
        assert analysis.return_margin_feasibility in ("FEASIBLE", "MARGINAL", "UNFEASIBLE")

        comparison = mgr.compare_scenario(sc.scenario_id, sample_route, index.get_all())
        assert comparison.scenario_id == sc.scenario_id
        assert len(comparison.key_tradeoffs) >= 2


class TestFastAPIFusionEndpoints:
    """Validates HTTP endpoints exposed by the mission intelligence router."""

    def test_api_data_freshness_endpoint(self):
        r = client.get("/api/v1/intelligence/data-freshness")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert len(data["sources"]) >= 8
        assert len(data["coverage_gaps"]) >= 1

    def test_api_observations_spatial_query(self):
        r = client.get("/api/v1/intelligence/observations?bbox=77.30,18.30,77.50,18.50&limit=10")
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        # Check backward compatibility
        first = items[0]
        assert "observation_id" in first
        assert "instrument" in first
        assert "provenance_kind" in first
        assert "quality_tier" in first

    def test_api_graph_endpoints(self):
        # GET /graph
        r_graph = client.get("/api/v1/intelligence/graph?max_nodes=30")
        assert r_graph.status_code == 200
        subgraph = r_graph.json()
        assert len(subgraph["nodes"]) >= 5
        assert len(subgraph["edges"]) >= 5

        # Pick first node to test /graph/{node_id}
        node_id = subgraph["nodes"][0]["node_id"]
        r_node = client.get(f"/api/v1/intelligence/graph/{node_id}")
        assert r_node.status_code == 200
        assert r_node.json()["node_id"] == node_id

        # GET /graph/{node_id}/evidence
        r_ev = client.get(f"/api/v1/intelligence/graph/{node_id}/evidence")
        assert r_ev.status_code == 200
        assert "causal_chain" in r_ev.json()

        # GET /graph/{node_id}/impacts
        r_imp = client.get(f"/api/v1/intelligence/graph/{node_id}/impacts")
        assert r_imp.status_code == 200
        assert "downstream_paths" in r_imp.json()

    def test_api_scenarios_endpoints(self):
        # GET /scenarios
        r_list = client.get("/api/v1/intelligence/scenarios")
        assert r_list.status_code == 200
        scenarios = r_list.json()
        assert len(scenarios) >= 3

        sc_id = scenarios[0]["scenario_id"]

        # GET /scenarios/{id}
        r_get = client.get(f"/api/v1/intelligence/scenarios/{sc_id}")
        assert r_get.status_code == 200
        assert r_get.json()["scenario_id"] == sc_id

        # POST /scenarios/{id}/analyze
        r_analyze = client.post(f"/api/v1/intelligence/scenarios/{sc_id}/analyze", json={})
        assert r_analyze.status_code == 200
        analysis = r_analyze.json()
        assert "estimated_relative_effort" in analysis
        assert "return_margin_feasibility" in analysis

        # GET /scenarios/{id}/compare
        r_compare = client.get(f"/api/v1/intelligence/scenarios/{sc_id}/compare")
        assert r_compare.status_code == 200
        comparison = r_compare.json()
        assert "delta_relative_effort" in comparison
        assert "key_tradeoffs" in comparison

    def test_api_risk_propagation_endpoint(self):
        payload = {
            "route_data": {
                "route_id": "test_api_route",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [77.4120, 18.4200, -2540.0],
                        [77.4220, 18.4270, -2528.0],
                    ],
                },
            },
            "max_slope_ceiling_deg": 12.0,
            "max_roughness_limit": 0.8,
        }
        r = client.post("/api/v1/intelligence/risk-propagation", json=payload)
        assert r.status_code == 200
        res = r.json()
        assert res["route_id"] == "test_api_route"
        assert len(res["segment_evaluations"]) >= 1
        assert "relative_route_effort_index" in res
