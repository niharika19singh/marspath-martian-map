# MARSPath — Mars Exploration Route Intelligence and Science Planner

**Challenge Track:** *Interplanetary Survival Guide: Martian Map*  
**Team:** Niharika (Geospatial, Risk Scoring, Routing Engine, Backend API) & Kunal (React Frontend, Interactive Planetary Map, Mission UX)

---

## 🚀 Overview

MARSPath is an interplanetary routing intelligence and terrain assessment platform designed for Martian surface exploration missions (robotic rovers and future human extravehicular activities / EVA). Operating in the high-priority pilot region of **Jezero Crater** (`~77.58° E, ~18.38° N`), MARSPath ingests NASA orbital altimetry (MOLA, HRSC, CTX/HiRISE), models physical slope dynamics and terrain roughness, and computes multi-objective traversability corridors using bounded graph-search algorithms (A* and Dijkstra).

### Core Features
- **Mars Planetary Geodesy:** Accurate handling of IAU2000 Mars sphere coordinates (`IAU2000:49900`), planetocentric latitude, and positive-East longitude wrapping.
- **Physical Terrain Analysis:** Elevation, gradient, slope (degrees), and surface ruggedness (TRI) computed strictly in metric physical units with latitude convergence correction.
- **Explainable Multi-Mode Routing:**
  - `safety_first`: Strict slope ceilings (≤14°), heavy ruggedness aversion, avoiding uncharacterized terrain.
  - `balanced`: Optimal trade-off between physical distance, slope energy expenditure, and traversal time.
  - `science_first`: Maximizes traversal near high-value geological points of interest (delta deposits, carbonates, crater rims) while enforcing safety constraints.
- **Transparent Data Provenance & Ingestion:**
  - Automated cloud-native window extraction (`178 x 252` pixels, 200 m/px nominal resolution) directly from the USGS S3 archive (`Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`).
  - Strict separation between local SHA-256 file integrity (`local_integrity_verified`) and upstream source checksum authenticity (`source_checksum_verified`).
  - Five explicit validation states: `synthetic_test_fixture`, `incomplete_missing_genuine_dem`, `valid_numeric_raster_unverified_source`, `official_endpoint_retrieved_checksum_unverified` (for partial HTTP range extractions where the full 11.38 GB archive MD5 is not computed over all upstream bytes), and `verified_source` (reserved strictly for independently verified full-source checksums).

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
│   ├── Dockerfile          # Production container specification
│   ├── requirements.txt    # Production dependencies
│   ├── app/
│   │   ├── api/v1/         # Endpoints: health, layers, data/status, routes/plan
│   │   ├── core/           # Config, logging, exceptions
│   │   ├── data/           # Data manifest, providers, ingestion pipeline
│   │   ├── geospatial/     # CRS, raster loading, slope, roughness metrics
│   │   ├── routing/        # Graph builder, cost model, A*, Dijkstra, alternatives
│   │   ├── schemas/        # Pydantic v2 data models
│   │   └── services/       # Catalog, terrain, and routing business logic
│   └── tests/              # Comprehensive unit and integration pytest suite
├── frontend/               # Kunal's React & Planetary Map workspace
└── docs/                   # Architectural, CRS, data, and API documentation
```

---

## 🛰️ NASA / USGS Data Ingestion

To ingest the real Jezero Crater DEM directly from the authoritative USGS AWS S3 archive via HTTP range requests:

```bash
# Extract Jezero Crater corridor (77.15°E - 78.00°E, 18.10°N - 18.70°N)
python3 -m backend.app.data.ingestion
```

This creates:
- `backend/app/data/rasters/jezero_mola_hrsc_blended.tif` (~90 KB GeoTIFF, git-ignored)
- `backend/app/data/rasters/jezero_mola_hrsc_blended.tif.provenance.json` (cryptographic sidecar)

To run the backend with the verified real DEM:
```bash
export MARSPATH_USE_REAL_DEM=true
export MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false
uvicorn backend.app.main:app --reload
```

---

## 🧪 Testing and Quality Gate

```bash
# Run the complete test suite
pytest backend/tests/ -v

# Run linter
ruff check backend

# Verify bytecode compilation
python3 -m compileall backend/
```
