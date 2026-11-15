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
- **Transparent Data Provenance & Multi-Resolution Terrain Selection:**
  - Automated cloud-native window extraction (`178 x 252` pixels, 200 m/px nominal resolution) directly from the USGS S3 archive (`Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`) as the default regional Jezero DEM.
  - Optional localized high-resolution **HiRISE Jezero Western Delta DTM** (~1 m/px, `18.35°N–18.46°N, 77.38°E–77.47°E`) via `MARSPATH_USE_HIRISE_DEM=true` and `MARSPATH_HIRISE_DEM_PATH`, with automatic single-source corridor selection, projected-to-geographic Mars CRS alignment, and conservative hazard-preserving block aggregation when a HiRISE corridor exceeds `MAX_GRID_CELLS`.
  - Strict separation between local SHA-256 file integrity (`local_integrity_verified`) and upstream source checksum authenticity (`source_checksum_verified`).
  - Five explicit validation states: `synthetic_test_fixture`, `incomplete_missing_genuine_dem`, `valid_numeric_raster_unverified_source`, `official_endpoint_retrieved_checksum_unverified` (for partial HTTP range extractions where the full 11.38 GB archive MD5 is not computed over all upstream bytes), and `verified_source` (reserved strictly for independently verified full-source checksums).
- **Multi-Resolution Planetary GIS Hierarchy & Seamless Inset Engine:**
  - **Deterministic Multi-Tier Streaming:** Continuous NASA Viking MDIM 2.1 global color mosaic ($232\text{ m/px}$, $>800\text{ m/px}$ resolution) ensures 100% global planet coverage without unrendered patches; regional USGS CTX 6 m orthomosaic ($10.5066/\text{P9GV1ND3}$, $25\text{–}800\text{ m/px}$) activates over Jezero Crater; local USGS HiRISE 25 cm orthomosaic ($10.5066/\text{P9QJDP48}$, $<25\text{ m/px}$) activates over the western delta corridor.
  - **Screen-Pixel Edge Feathering:** Dedicated OpenLayers layer containers (`.ol-layer-ctx`, `.ol-layer-hirise`) execute an alpha gradient postrender feather ($48\text{–}64\text{ px}$, `destination-out`), dissolving high-resolution rectangular borders smoothly into the surrounding basemap without knife-edge seams or invented pixels.
  - **Tone Harmonization:** Grayscale CTX/HiRISE insets undergo visualization-only tone harmonization (`contrast(1.05) brightness(0.97) sepia(0.12) hue-rotate(-12deg)`), balancing panchromatic imagery against the Martian surface albedo while preserving authentic scientific image contrast.
  - **Complete NoData Transparency:** All analytical DEM overlays (return zones, rescue-time maps, slope and roughness rasters) strictly mask unreached, nonfinite, or NoData cells with zero alpha ($\alpha = 0$), completely eliminating rectangular grey haze over the terrain.
  - **Coverage Boundary Control:** Footprint extents are hidden by default and render crisp, non-occluding dashed boundary outlines only upon explicit operator selection in the Layers menu.
- **Astronaut EVA Survival & Field Navigation Suite:**
  - **Marswalk Survivability Score (MSS, 0–100):** Operational index modeling suited human metabolic cost (Minetti formulation adapted to Martian gravity $g=3.72\text{ m/s}^2$), PLSS consumables reserves, sunset abort margins, THEMIS regolith sinkage, and space radiation exposure.
  - **Astronaut Visor HUD / Field Tablet Mode:** Tactical heads-up display overlay with gyro-stabilized heading tape, live simulated PLSS life-support gauges, and companion rover assistance prompts.
  - **Solar Particle Event (SPE) Space Weather Stress Testing:** Simulates acute $\approx 48.5\text{ mSv/h}$ solar proton storms with dynamic routing to natural topographic shelters (Western Rim Delta Escarpment, Belva Impact Terraces, Séítah Swale).
  - **Authentic NASA Ground Optical Grounding:** 100% genuine NASA Perseverance Mastcam-Z and Navcam surface photography catalogue (PIA24487, PIA24836, PIA25439, PIA24839, PIA25828) with direct NASA JPL Photojournal links—zero generative AI Martian landscapes.
  - **Calibrated Atmospheric Telemetry:** Live and historical in-situ telemetry from NASA PDS MEDA sensor suites (Sol 15 benchmark: $-29.4^\circ\text{C}$ air, $756.4\text{ Pa}$ pressure, $\tau = 0.41$).
  - **Deterministic Safety Mandate:** Heuristics and AI recommendations strictly advisory; cannot override deterministic engineering limits ($14.0^\circ$ slope ceiling).
- **Mission Intelligence & Risk Fusion Subsystem (Aureum AI / Verity Inspired):**
  - **Multi-Source Evidence Fusion:** Normalizes orbital imagery (HiRISE, CTX), altimetry (MOLA, HRSC), thermal inertia (THEMIS), in-situ meteorology (MEDA), and orbital geometry (SPICE) with explicit quality tiers (`GOLD`, `SILVER`, `BRONZE`) and provenance kinds (`MEASURED`, `MODELED`, `DERIVED`).
  - **Geospatial Mission Knowledge Graph:** 12 entity types and 12 relation types supporting multi-hop upstream evidence discovery (back to NASA PDS/USGS DOIs) and downstream impact tracing.
  - **Causal Risk Propagation:** Evaluates route segments deterministically, computing traversability status (`PASSABLE`, `MARGINAL`, `IMPASSABLE`), relative effort index, hazard exposures, and causal chains.
  - **What-If Scenario Simulation:** Parametric perturbation engine testing atmospheric dust opacity ($\tau$), power budget reductions, slope ceilings, and wheel degradation with side-by-side baseline comparison reports.
  - **Operational Data Freshness & Coverage Auditing:** Monitors latency, connectivity, and coverage across 8 NASA data archives, pinpointing low-resolution fallback zones.

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

To run the backend with the verified real DEM (and optional localized HiRISE DTM when provisioned):
```bash
export MARSPATH_USE_REAL_DEM=true
export MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false
# Optional: enable localized HiRISE Jezero Western Delta DTM (~1 m/px)
export MARSPATH_USE_HIRISE_DEM=false
export MARSPATH_HIRISE_DEM_PATH=backend/app/data/rasters/hirise_jezero_delta_dtm.tif
uvicorn backend.app.main:app --reload
```

### Docker Container Deployment
```bash
# Build production image with build-time DEM provisioning
docker build -f backend/Dockerfile -t marspath-backend .

# Run container (verification-only, fail-closed runtime)
docker run -p 8000:8000 marspath-backend
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

---

## 🌐 Live Production Deployment

- **Single Public Application URL:** [https://marspath.vercel.app](https://marspath.vercel.app)
- **Interactive Mission Control:** [https://marspath.vercel.app/mission-control/](https://marspath.vercel.app/mission-control/)
- **Authoritative Backend API:** [https://marspath-backend.onrender.com](https://marspath-backend.onrender.com) (transparently proxied via `https://marspath.vercel.app/api/`)
- **Planetary Data Readiness Gate:** [https://marspath.vercel.app/api/v1/data/status](https://marspath.vercel.app/api/v1/data/status)
- **Service Health Check:** [https://marspath.vercel.app/health](https://marspath.vercel.app/health)
