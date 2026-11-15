# MARSPath System Architecture

```mermaid
flowchart TD
    subgraph Frontend["Kunal's Frontend (React / OpenLayers)"]
        UI[Mission Control UI]
        Map[Interactive Mars Map]
        LayersUI[Layer & Hazard Selector]
    end

    subgraph API["FastAPI Backend (Niharika)"]
        Router[API Gateway / Routers]
        HealthEP["GET /health"]
        LayersEP["GET /api/v1/layers"]
        StatusEP["GET /api/v1/data/status"]
        RouteEP["POST /api/v1/routes/plan"]
    end

    subgraph Geospatial["Geospatial & CRS Engine"]
        CRS[Mars IAU2000 Geodesy]
        Cropper[Corridor Bounding Box Cropper]
        SlopeCalc[Physical Gradient & Slope Engine]
        RoughCalc[Terrain Ruggedness Index TRI]
        Traversability[Hazard & Slope Mask Builder]
    end

    subgraph Routing["Routing Engine"]
        Graph[8-Connected Grid Graph]
        CostModel[Multi-Factor Cost Model]
        AStar[Bounded A* Search]
        Dijkstra[Reference Dijkstra Baseline]
        Alternatives[Multi-Alternative Diversion Engine]
    end

    subgraph DataLayer["Data Layer"]
        Provider[Provider Abstraction]
        RealDEM[(MOLA-HRSC Blended GeoTIFF)]
        SyntheticDEM[(Deterministic Jezero Pilot Model)]
        SciencePOIs[(Jezero Science Targets)]
    end

    UI -->|Route Request| RouteEP
    Map -->|Fetch Layers| LayersEP
    LayersUI -->|Fetch Data Status| StatusEP

    RouteEP --> Router
    Router --> Cropper
    Cropper --> CRS
    Cropper --> Provider
    Provider --> RealDEM
    Provider --> SyntheticDEM
    Provider --> SciencePOIs

    Cropper --> SlopeCalc
    Cropper --> RoughCalc
    SlopeCalc --> Traversability
    RoughCalc --> Traversability

    Traversability --> Graph
    Graph --> CostModel
    CostModel --> AStar
    CostModel --> Dijkstra
    AStar --> Alternatives

    Alternatives -->|GeoJSON Route Corridor & Scorecard| RouteEP
    RouteEP -->|JSON Response| UI

    subgraph AIIntelligence["AI Mission Intelligence Layer"]
        AIEngine["Mission Intelligence Engine"]
        Landmarks["Jezero Landmark & Boundary Registry"]
        NLPlanner["Natural-Language Mission Planner"]
        CandidateComp["AI Multi-Criteria Candidate Comparison"]
        TerrainInterp["Scientific Terrain Interpreter (Measured/Derived/Proxy)"]
        RiskBriefing["Executive Risk Briefing & Contingency Corridors"]
        SafetyMandate["Deterministic Safety Mandate (Non-Override Shield)"]
        GeminiProv["Google Gemini Provider"]
        AzureProv["Microsoft Azure AI Foundry Provider"]
    end

    UI -->|Natural Language Prompt| NLPlanner
    NLPlanner --> Landmarks
    NLPlanner --> SafetyMandate
    NLPlanner --> RouteEP
    RouteEP --> CandidateComp
    CandidateComp --> AIEngine
    AIEngine --> TerrainInterp
    AIEngine --> RiskBriefing
    AIEngine --> GeminiProv
    AIEngine --> AzureProv
    AIEngine -->|Section 6 AI Dossier| PDFExport["PDF Export Service (ReportLab)"]
```

---

## Component Descriptions

1. **API Layer (`backend/app/api/`):** Thin REST endpoints validating incoming Pydantic schemas, enforcing planetary CRS rules, and handling exceptions.
2. **Geospatial Processing Engine (`backend/app/geospatial/`):** Converts planetary coordinates into local metric coordinates, crops subgrids around the mission corridor, and calculates physical slope gradients and roughness metrics strictly in meters.
3. **Data Provider Layer (`backend/app/data/providers/`):** Manages raster ingestion with graceful fallback to high-fidelity deterministic synthetic models when raw NASA files are not locally present.
4. **Routing Engine (`backend/app/routing/`):** Builds an 8-connected graph with strict diagonal corner-cutting prevention and executes bounded A* searches with admissible Euclidean heuristics.
5. **AI Mission Intelligence Layer (`backend/app/intelligence/`, `backend/app/integrations/ai/`):** Translates natural-language mission prompts into validated routing requests against authoritative Jezero landmarks, compares candidate route corridors with exact numeric grounding, classifies scientific evidence (measured, derived, proxy), structures executive risk briefings with contingency corridors, and enforces the mandatory rule that AI guidance can never override deterministic engineering safety limits (14.0° slope ceiling).
