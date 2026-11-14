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
```

---

## Component Descriptions

1. **API Layer (`backend/app/api/`):** Thin REST endpoints validating incoming Pydantic schemas, enforcing planetary CRS rules, and handling exceptions.
2. **Geospatial Processing Engine (`backend/app/geospatial/`):** Converts planetary coordinates into local metric coordinates, crops subgrids around the mission corridor, and calculates physical slope gradients and roughness metrics strictly in meters.
3. **Data Provider Layer (`backend/app/data/providers/`):** Manages raster ingestion with graceful fallback to high-fidelity deterministic synthetic models when raw NASA files are not locally present.
4. **Routing Engine (`backend/app/routing/`):** Builds an 8-connected graph with strict diagonal corner-cutting prevention and executes bounded A* searches with admissible Euclidean heuristics.
