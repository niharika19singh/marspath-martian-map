# MARSPath Frontend (Kunal's Workspace)

Welcome Kunal! This directory is dedicated to your React frontend application, interactive planetary map, and mission control UI.

## Integration & Getting Started

1. **API Contract:** Full REST API schemas, request/response examples, and coordinate conventions are documented in [`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).
2. **Team Responsibilities:** See [`docs/TEAM_OWNERSHIP.md`](../docs/TEAM_OWNERSHIP.md).
3. **Local Backend Server:** The backend runs at `http://localhost:8000` by default.
   - Swagger / OpenAPI Docs: `http://localhost:8000/docs`
   - Health check: `GET http://localhost:8000/health`
   - Map layers: `GET http://localhost:8000/api/v1/layers`
   - Data status: `GET http://localhost:8000/api/v1/data/status`
   - Route planner: `POST http://localhost:8000/api/v1/routes/plan`

## Martian Coordinate System Reminder

- Mars coordinates use **East Longitude** (0° to 360° or -180° to +180°) and **Planetocentric Latitude** (-90° to +90°).
- The pilot area is **Jezero Crater**:
  - Center: `~77.58° E, ~18.38° N`
  - Longitude range: `77.20° E` to `77.95° E`
  - Latitude range: `18.15° N` to `18.65° N`
- A sample mock route JSON is provided at `backend/app/data/fixtures/sample_route_response.json` for frontend testing before the backend is booted.
