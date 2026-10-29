# MARSPath Backend — Geospatial Intelligence & Routing Engine

This directory contains the Python FastAPI backend, planetary geospatial processing engine, and multi-objective routing intelligence service for **MARSPath**.

## Architecture & Capabilities

- **Planetary Coordinate Reference System (CRS):** Implements Mars IAU2000 Sphere (`IAU2000:49900`), Planetocentric latitude [-90°, +90°], and East longitude [0°, 360°) wrapping with Equirectangular local metric projection.
- **Physical Terrain Metrics:** 2D gradient, slope in degrees, and localized Terrain Ruggedness Index (TRI) computed strictly in physical meters.
- **Explainable Routing Engine:** Bounded A* search with an admissible Euclidean distance heuristic, 8-connected grid connectivity, strict diagonal corner-cutting prevention, and validation against reference Dijkstra searches.
- **Optimization Modes:**
  - `safety_first`: 14° slope ceiling, 3.5x slope weight, 2.5x roughness weight.
  - `balanced`: 20° slope ceiling, 1.2x slope weight, 1.0x roughness weight.
  - `science_first`: 22° slope ceiling, science waypoint proximity rewards.
- **Provider Abstraction:** Dynamic switching between real NASA MOLA/HRSC GeoTIFF DEMs and deterministic synthetic test fixtures for Jezero Crater.

---

## 🛠️ Local Setup & Execution

### 1. Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### 2. Installation
```bash
# In the repository root:
pip install -r backend/requirements.txt
```

### 3. Running the Server
```bash
# Start backend on http://localhost:8000
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Interactive OpenAPI Docs
Once running, navigate to:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### 5. Running Tests
```bash
PYTHONPATH=. pytest backend/tests/ -v
```

---

## 📡 Key Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health, version, and scientific data readiness |
| `GET` | `/api/v1/layers` | Configured elevation, slope, roughness, and imagery layers |
| `GET` | `/api/v1/data/status` | Planetary DEM status, coverage fraction, and provenance |
| `POST` | `/api/v1/routes/plan` | Multi-objective Martian route optimization |
