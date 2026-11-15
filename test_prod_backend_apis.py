"""Comprehensive Backend API Acceptance Test Suite for MARSPath Production.
Target: https://marspath-backend.onrender.com
"""
import json
import time
import urllib.request
import urllib.error
import ssl

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

BASE_URL = "https://marspath-backend.onrender.com"

results = []

def test_endpoint(name, method, path, payload=None, expected_status=200):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
            duration = round((time.time() - start) * 1000, 1)
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            parsed = None
            if "application/json" in content_type:
                parsed = json.loads(body.decode("utf-8"))
            elif "application/pdf" in content_type:
                parsed = {"pdf_bytes": len(body)}
            else:
                parsed = {"text_bytes": len(body)}
            passed = (status == expected_status)
            results.append({
                "test": name,
                "method": method,
                "path": path,
                "status": status,
                "expected": expected_status,
                "passed": passed,
                "duration_ms": duration,
                "summary": str(parsed)[:160]
            })
            print(f"[{'PASS' if passed else 'FAIL'}] {name} ({method} {path}) -> {status} in {duration}ms")
            return parsed
    except urllib.error.HTTPError as e:
        duration = round((time.time() - start) * 1000, 1)
        body = e.read().decode("utf-8", errors="replace")
        passed = (e.code == expected_status)
        results.append({
            "test": name,
            "method": method,
            "path": path,
            "status": e.code,
            "expected": expected_status,
            "passed": passed,
            "duration_ms": duration,
            "summary": body[:160]
        })
        print(f"[{'PASS' if passed else 'FAIL'}] {name} ({method} {path}) -> {e.code} in {duration}ms")
        return body
    except Exception as e:
        duration = round((time.time() - start) * 1000, 1)
        results.append({
            "test": name,
            "method": method,
            "path": path,
            "status": 0,
            "expected": expected_status,
            "passed": False,
            "duration_ms": duration,
            "summary": str(e)[:160]
        })
        print(f"[FAIL] {name} ({method} {path}) -> ERROR: {e}")
        return None

print("=== STARTING MARSPATH PRODUCTION BACKEND API VERIFICATION ===")

# Core Health & Spec
test_endpoint("1. Health Check", "GET", "/health")
test_endpoint("2. OpenAPI JSON", "GET", "/openapi.json")

# Layers & Data Status
test_endpoint("3. Planetary Layers", "GET", "/api/v1/layers")
test_endpoint("4. Data Status", "GET", "/api/v1/data/status")
test_endpoint("5. Data-Sources Status", "GET", "/api/v1/data-sources/status")
test_endpoint("6. Data-Sources Catalogue", "GET", "/api/v1/data-catalogue")

# Conditions & Freshness
test_endpoint("7. Current Conditions (MEDA/Weather)", "GET", "/api/v1/conditions")
test_endpoint("8. Mission Intelligence Freshness", "GET", "/api/v1/intelligence/data-freshness")

# Cloud & AI
test_endpoint("9. AI Status", "GET", "/api/v1/ai/status")
test_endpoint("10. Cloud Status", "GET", "/api/v1/cloud/status")

# SPICE, Spacecraft, Weather, Traverses
test_endpoint("11. SPICE/NAIF Geometry", "GET", "/api/v1/data-sources/naif/geometry")
test_endpoint("12. Spacecraft Catalogue", "GET", "/api/v1/intelligence/spacecraft")
test_endpoint("13. MEDA Observations", "GET", "/api/v1/data-sources/meda/observations")
test_endpoint("14. THEMIS Observations", "GET", "/api/v1/data-sources/themis/observations")
test_endpoint("15. Science Targets", "GET", "/api/v1/routes/science-targets")
test_endpoint("16. Route Presets", "GET", "/api/v1/routes/presets")
test_endpoint("17. Perseverance Traverse History", "GET", "/api/v1/intelligence/rovers/perseverance/traverse")
test_endpoint("18. Curiosity Traverse History", "GET", "/api/v1/intelligence/rovers/curiosity/traverse")

# Route Planning - Valid Jezero Traverse
valid_route_req = {
    "start": {"lon": 77.4508, "lat": 18.4447},
    "destination": {"lon": 77.4395, "lat": 18.4310},
    "mode": "safety_first",
    "algorithm": "astar",
    "num_alternatives": 3,
    "include_return_leg": True,
    "max_eva_hours": 8.0,
    "constraints": {
        "max_slope_deg": 12.0,
        "max_tri_roughness": 0.6
    }
}
plan_res = test_endpoint("19. Route Plan - Valid Jezero Traverse", "POST", "/api/v1/routes/plan", valid_route_req)

# PDF Export
pdf_req = {
    "plan_data": plan_res if isinstance(plan_res, dict) else {},
    "ai_mission_intel": {
        "summary": "Verified safe corridor toward Séítah with 120.0m return margin.",
        "recommended_route_id": "primary"
    }
}
test_endpoint("20. PDF Mission Dossier Export", "POST", "/api/v1/routes/export/pdf", pdf_req)

# AI Mission Intelligence Endpoints
test_endpoint("21. AI Natural-Language Mission Planner", "POST", "/api/v1/ai/mission/plan-from-prompt", {
    "user_prompt": "Find a safe route from current rover position to Séítah prioritizing low slope"
})
test_endpoint("22. AI Candidate Route Comparison", "POST", "/api/v1/ai/routes/compare-candidates", {
    "routes": [
        {
            "route_id": "c1",
            "route_name": "Primary Corridor (A*)",
            "distance_km": 3.28,
            "total_cost": 4073.2,
            "max_slope_deg": 11.4,
            "roughness_tri": 0.42,
            "eva_duration_hours": 0.82,
            "return_feasibility": "FEASIBLE",
            "turnaround_buffer_min": 120.0,
            "monte_carlo_reliability_pct": 94.0
        }
    ],
    "mission_profile": "safety_first"
})
test_endpoint("23. AI Scientific Terrain Interpretation", "POST", "/api/v1/ai/terrain/interpret", {
    "location_name": "Séítah Ridge",
    "coordinates": {"lon": 77.4395, "lat": 18.4310}
})
test_endpoint("24. AI Executive Risk Briefing", "POST", "/api/v1/ai/mission/risk-briefing", {
    "selected_route": {
        "route_id": "primary",
        "route_name": "Primary Corridor (A*)",
        "distance_km": 3.28,
        "total_cost": 4073.2,
        "max_slope_deg": 11.4,
        "roughness_tri": 0.42,
        "eva_duration_hours": 0.82
    },
    "turnaround": {
        "is_feasible": True,
        "safe_turnaround_buffer_min": 120.0
    }
})

# Robustness & Negative Error Handling Tests
test_endpoint("25. Error Handling - Out of Bounds Coordinate Plan", "POST", "/api/v1/routes/plan", {
    "start": {"lon": 133.0, "lat": -18.0}, # Tharsis
    "destination": {"lon": 77.4395, "lat": 18.4310}
}, expected_status=422)

test_endpoint("26. Error Handling - Malformed / Missing Fields", "POST", "/api/v1/routes/plan", {
    "start": "not_an_object"
}, expected_status=422)

test_endpoint("27. Error Handling - Nonexistent Resource", "GET", "/api/v1/nonexistent-endpoint", expected_status=404)

print("\n=== SUMMARY ===")
passed_count = sum(1 for r in results if r["passed"])
print(f"Total Tests: {len(results)} | Passed: {passed_count} | Failed: {len(results) - passed_count}")

with open("/tmp/marspath_api_acceptance_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("Results saved to /tmp/marspath_api_acceptance_results.json")
