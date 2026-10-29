# MARSPath — Mars Exploration Route Intelligence and Science Planner

**Challenge Track:** *Interplanetary Survival Guide: Martian Map*  
**Team:** Niharika (Geospatial, Risk Scoring, Routing Engine, Backend API) & Kunal (React Frontend, Interactive Planetary Map, Mission UX)

---

## 🚀 Overview

MARSPath is an interplanetary routing intelligence and terrain assessment platform designed for Martian surface exploration missions (robotic rovers and future human extravehicular activities / EVA). Operating in the high-priority pilot region of **Jezero Crater** (`~77.58° E, ~18.38° N`), MARSPath ingests NASA orbital altimetry (MOLA, HRSC, CTX/HiRISE), models physical slope dynamics and terrain roughness, and computes multi-objective traversability corridors using bounded graph-search algorithms (A* and Dijkstra).

### Core Features
- **Mars Planetary Geodesy:** Accurate handling of IAU2000 Mars sphere coordinates, planetocentric latitude, and East longitude wrapping.
- **Physical Terrain Analysis:** Elevation, gradient, slope (degrees), and surface ruggedness computed strictly in metric physical units.
- **Explainable Multi-Mode Routing:**
  - `safety_first`: Strict slope ceilings, heavy ruggedness aversion, avoiding uncharacterized terrain.
  - `balanced`: Optimal trade-off between physical distance, slope energy expenditure, and traversal time.
  - `science_first`: Maximizes traversal near high-value geological points of interest (delta deposits, carbonates, crater rims) while enforcing safety constraints.
- **Transparent Data Provenance:** Clear reporting of whether calculations use real NASA DEM products or high-fidelity deterministic synthetic test fixtures.

---

## 🏗️ Repository Layout

```text
marspath-martian-map/
├── README.md               # Main project overview and setup
├── LICENSE                 # MIT Open-Source License
├── CONTRIBUTING.md          # Team contribution guidelines
├── pyproject.toml          # Root Python configuration
├── render.yaml             # Render deployment blueprint
├── backend/                # Niharika's FastAPI & Geospatial Engine
│   ├── app/
│   │   ├── api/v1/         # Endpoints: health, layers, data/status, routes/plan
│   │   ├── core/           # Config, logging, exceptions
│   │   ├── geospatial/     # CRS, raster loading, slope, roughness metrics
│   │   ├── routing/        # Graph builder, cost model, A*, Dijkstra
│   │   ├── schemas/        # Pydantic v2 data models
│   │   └── services/       # Catalog, terrain, and routing business logic
│   └── tests/              # Unit and integration pytest suite
├── frontend/               # Kunal's React & Planetary Map workspace
└── docs/                   # Architectural, CRS, data, and API documentation
```
