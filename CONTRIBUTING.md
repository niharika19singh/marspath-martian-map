# Contributing to MARSPath

Thank you for contributing to **MARSPath — Mars Exploration Route Intelligence and Science Planner**!

## Team Roles & Ownership

- **Niharika:** NASA geospatial data validation, coordinate reference system (CRS) pipeline, numerical DEM processing, hazard/roughness scoring, A*/Dijkstra routing engine, FastAPI backend services, testing, and backend deployment.
- **Kunal:** React frontend UI, interactive planetary map (OpenLayers / MapLibre / Cesium), UX, mission dashboard, route visualization, and frontend deployment.
- **Shared:** API contracts, integration testing, end-to-end verification, demo presentations.

## Branch Strategy

- `main`: Protected production-ready branch.
- `feature/niharika-geospatial-routing`: Niharika's backend, geospatial, and routing engine branch.
- `feature/kunal-frontend-map`: Kunal's frontend application branch.

## Code Standards

- Backend: Python 3.11+, typed with Pydantic v2 schemas.
- Linting & Formatting: `ruff check` and `ruff format`.
- Tests: `pytest` with >90% coverage on core routing and geospatial modules.
- Coordinate Handling: Strictly follow Mars IAU2000 conventions (planetocentric latitude, East longitude). Never assume Earth WGS84 coordinates.
