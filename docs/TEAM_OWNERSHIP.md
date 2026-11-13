# MARSPath Team Ownership & Integration Process

## 👥 Ownership Division

### Niharika Singh
- **Scope:** NASA planetary data ingestion, coordinate reference systems (CRS), raster processing, slope & roughness calculations, hazard modeling, A* & Dijkstra routing algorithms, FastAPI backend services, testing, Docker/Render deployment.
- **Owned Files & Directories:**
  - `backend/` (All submodules, schemas, algorithms, services, tests, Dockerfile)
  - `render.yaml`
  - `docs/API_CONTRACT.md`, `docs/DATA_SOURCES.md`, `docs/COORDINATE_SYSTEMS.md`, `docs/ROUTING_MODEL.md`, `docs/DEPLOYMENT.md`
  - `.github/workflows/backend-ci.yml`

### Kunal
- **Scope:** React frontend application, interactive Martian planetary map (OpenLayers / Leaflet / MapLibre / Cesium), user experience, route visualization, mission dashboard, frontend deployment (Vercel / Netlify / Render Static).
- **Owned Files & Directories:**
  - `frontend/` (All React components, styling, map layers, dashboard views, package.json)
  - `frontend/README.md`
  - `.github/workflows/frontend-ci.yml` (future)

### Shared
- **Scope:** Root `README.md`, `CONTRIBUTING.md`, `LICENSE`, end-to-end smoke testing, final hackathon presentation and demo.

---

## 🔄 API Change Protocol

To prevent breaking either team member's work:
1. **Never alter existing fields in `RoutePlanRequest` or `RoutePlanResponse` without updating `docs/API_CONTRACT.md` first.**
2. **Backward-compatible changes:** New fields added to responses should be optional or carry safe default values.
3. **Coordinate modifications:** Any change in Mars coordinate units, bounding coordinates, or datum parameters must be accompanied by an update in `backend/app/geospatial/crs.py` and `docs/COORDINATE_SYSTEMS.md`.

---

## 🌿 Git & Pull Request Expectations

1. **Branching Model:**
   - `main`: Clean, verified code only. Protected against direct force-pushes.
   - `feature/niharika-geospatial-routing`: Niharika's backend feature development.
   - `feature/kunal-frontend-map`: Kunal's frontend UI and map development.
2. **Pull Requests:**
   - All feature branches merge into `main` via PRs after CI tests pass.
   - PR titles follow conventional commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
