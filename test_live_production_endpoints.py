"""Direct Verification of Required Live Backend Endpoints on Render Production.
Target: https://marspath-backend.onrender.com
"""
import json
import urllib.request
import urllib.error
import ssl
import time

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

BASE_URL = "https://marspath-backend.onrender.com"

endpoints_to_test = [
    ("Health Check", "GET", "/health", None),
    ("Route Planning", "POST", "/api/v1/routes/plan", {
        "start": {"lon": 77.45, "lat": 18.44},
        "destination": {"lon": 77.47, "lat": 18.46},
        "algorithm": "astar",
        "weight_slope": 0.4,
        "weight_roughness": 0.3,
        "weight_radiation": 0.3
    }),
    ("Current Conditions (MEDA)", "GET", "/api/v1/conditions", None),
    ("Orbital Observations", "GET", "/api/v1/intelligence/observations", None),
    ("Knowledge Graph", "GET", "/api/v1/intelligence/graph", None),
    ("Data Freshness", "GET", "/api/v1/intelligence/data-freshness", None),
    ("List Mission Scenarios", "GET", "/api/v1/intelligence/scenarios", None),
    ("Analyze Scenario (Dust Storm)", "POST", "/api/v1/intelligence/scenarios/scenario-dust-storm-tau-1-5/analyze", {}),
    ("Compare Scenario vs Baseline", "GET", "/api/v1/intelligence/scenarios/scenario-dust-storm-tau-1-5/compare", None),
    ("Risk Propagation Engine", "POST", "/api/v1/intelligence/risk-propagation", {
        "route_id": "test-eva-corridor",
        "coordinates": [[77.45, 18.44], [77.46, 18.45], [77.47, 18.46]]
    })
]

print("=== TESTING REQUIRED LIVE PRODUCTION ENDPOINTS ON RENDER ===")
all_passed = True
for name, method, path, payload in endpoints_to_test:
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
            dur = round((time.time() - start) * 1000, 1)
            raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            print(f"[PASS] {name} ({method} {path}) -> {resp.status} in {dur}ms")
            # Print brief preview of key fields
            if "status" in parsed:
                print(f"       status: {parsed['status']}")
            if "routes" in parsed:
                print(f"       routes returned: {len(parsed['routes'])}")
            if "nodes" in parsed:
                print(f"       graph nodes: {len(parsed['nodes'])}, edges: {len(parsed.get('edges', []))}")
            if "observations" in parsed:
                print(f"       observations: {len(parsed['observations'])}")
            if isinstance(parsed, list):
                print(f"       items: {len(parsed)}")
            if "scenario_name" in parsed:
                print(f"       scenario_name: {parsed['scenario_name']}")
            if "overall_traversability_state" in parsed:
                print(f"       traversability: {parsed['overall_traversability_state']}, risk_index: {parsed.get('aggregate_risk_index')}")
    except Exception as e:
        all_passed = False
        print(f"[FAIL] {name} ({method} {path}) -> ERROR: {e}")

print("=============================================================")
print("FINAL LIVE ENDPOINTS RESULT:", "ALL PASS" if all_passed else "SOME FAILED")
