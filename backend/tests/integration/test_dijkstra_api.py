from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_dijkstra_routing_api():
    """Verifies that selecting algorithm='dijkstra' executes Dijkstra search via API."""
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
        "algorithm": "dijkstra",
        "mode": "balanced",
        "num_alternatives": 2,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Dijkstra" in data["stats"]["algorithm_used"]
    assert len(data["routes"]) == 2
    primary = data["routes"][0]
    assert primary["total_cost"] > 0
    assert len(primary["geometry"]["coordinates"]) > 2
    # Check 3D coordinates
    assert len(primary["geometry"]["coordinates"][0]) == 3


def test_algorithm_comparison_api():
    """Verifies that selecting algorithm='compare' evaluates both A* and Dijkstra and emits comparison report."""
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "crs_identifier": "IAU2000:49900",
        "algorithm": "compare",
        "mode": "balanced",
        "num_alternatives": 1,
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Comparative Benchmark" in data["stats"]["algorithm_used"]

    comparison = data.get("algorithm_comparison")
    assert comparison is not None, "Must return algorithm_comparison report in compare mode"

    astar_metrics = comparison["astar"]
    dijkstra_metrics = comparison["dijkstra"]

    assert astar_metrics["algorithm"] == "A*"
    assert dijkstra_metrics["algorithm"] == "Dijkstra"

    # Both must find paths
    assert astar_metrics["total_cost"] > 0
    assert dijkstra_metrics["total_cost"] > 0

    # Costs must be identical (within tolerance)
    assert comparison["costs_equal"] is True
    assert comparison["optimality_verified"] is True
    assert comparison["cost_difference"] <= 0.05

    # Dijkstra expands >= A* nodes
    assert dijkstra_metrics["nodes_expanded"] >= astar_metrics["nodes_expanded"]
    assert comparison["node_expansion_ratio"] >= 1.0
    assert isinstance(comparison["comparison_statement"], str)
    assert len(comparison["comparison_statement"]) > 10


def test_invalid_algorithm_rejected():
    """Verifies that unsupported algorithm strings are rejected with 422."""
    payload = {
        "start": {"lon": 77.40, "lat": 18.39},
        "destination": {"lon": 77.44, "lat": 18.42},
        "algorithm": "genetic_algorithm_fake",
    }
    response = client.post("/api/v1/routes/plan", json=payload)
    assert response.status_code == 422
