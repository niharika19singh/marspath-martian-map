# MARSPath Live Mars Intelligence Architecture

## 1. System Overview

The **Live Mars Intelligence** subsystem transforms MARSPath from a static route planning tool into a comprehensive, planetary-scale situational-awareness and mission-control platform. It delivers real-time orbital mechanics, spacecraft ephemeris propagation, dual-rover telemetry synchronization (NASA Mars 2020 *Perseverance* and Mars Science Laboratory *Curiosity*), high-resolution orbital observation cataloging, and unified scientific mission timelines—all geospatially registered onto the MARSPath cartographic canvas.

```
                      ┌────────────────────────────────────────┐
                      │    Upstream Planetary Data Sources     │
                      │  NASA PDS, NAIF SPICE, ESA PSA, DSN    │
                      └───────────────────┬────────────────────┘
                                          │
                                          ▼
                      ┌────────────────────────────────────────┐
                      │   Live Mars Intelligence Subsystem     │
                      │  (FastAPI Backend /app/intelligence)   │
                      ├───────────────────┬────────────────────┤
                      │ Orbital Propagator│ J2 Astrodynamics   │
                      │ Rover Service     │ M20 / MSL Sync     │
                      │ Imagery Catalog   │ HiRISE / CTX / HRSC│
                      │ Sync Engine       │ Multi-Source Event │
                      └───────────────────┬────────────────────┘
                                          │  REST API (/api/v1/intelligence/*)
                                          ▼
                      ┌────────────────────────────────────────┐
                      │    Mission Control Interface (UI)      │
                      ├───────────────────┬────────────────────┤
                      │ Intelligence Panel│ Orbiters/Rovers/Obs│
                      │ MapView Layers    │ Tracks / Footprints│
                      │ Client Fallback   │ Keplerian Engine   │
                      └────────────────────────────────────────┘
```

---

## 2. Scientific Constraints & Integrity Guarantees

Mars planetary operations are governed by immutable physics, physical communication delays, and orbital mechanics:

1. **No Continuous Live Video:** Earth-Mars round-trip light time varies between 6 and 44 minutes depending on orbital geometry. Deep Space Network (DSN) tracking passes, orbiter relay schedules (UHF relay passes), and archive release cycles dictate data availability. The system strictly avoids fabricating pseudo-realtime video or claiming sensor feeds that do not exist in reality.
2. **Explicit Data State Lifecycle:** Every entity, position, observation, and telemetry record explicitly declares its operational state:
   - `LIVE TELEMETRY`: Ground station currently tracking active downlink.
   - `LATEST AVAILABLE`: Most recent validated telemetry downlinked and archived by mission operations.
   - `HISTORICAL`: Validated historical mission archive data.
   - `PREDICTED`: Numerically or analytically propagated orbital ephemeris.
   - `PROCESSING`: Downlinked telemetry undergoing calibration or orthorectification.
   - `STALE`: Telemetry that has passed its expected downlink refresh window without update.
   - `SOURCE UNAVAILABLE`: Upstream data provider unreachable or undergoing maintenance.
3. **No Synthetic Fabrication:** Orbiters are placed according to high-precision $J_2$-perturbed Keplerian orbital equations fitted to NASA NAIF SPICE kernels. Rover positions reflect authentic published NASA/JPL rover waypoints with verified odometry, site/drive counters, and Martian Sols.
4. **Transparent Provenance:** All payloads include `provenance` metadata detailing source provider (e.g., `NASA/JPL-Caltech`, `ESA/ESOC`), dataset identifier, retrieval timestamp, uncertainty bounds, and archive citations.

---

## 3. Subsystem Architecture

### 3.1 Backend Components (`backend/app/intelligence/`)

| Module | Responsibility | Key Classes / Functions |
| :--- | :--- | :--- |
| `schemas.py` | Pydantic v2 domain models and enum definitions for all telemetry, ephemerides, observations, and sync responses. | `SpacecraftPosition`, `RoverPosition`, `OrbitalObservation`, `TimelineEvent`, `SyncResponse`, `DataFreshnessState` |
| `orbital.py` | High-precision astrodynamics propagator for Mars orbiters incorporating $J_2$ oblateness perturbations, Kepler's equation solver, and IAU2000 Mars rotational model. | `MarsOrbiterPropagator`, `ORBITER_ORBITAL_ELEMENTS` |
| `rover.py` | Telemetry, traverse history, and science observation manager for Perseverance (M20) and Curiosity (MSL). | `RoverIntelligenceService` |
| `imagery.py` | Catalog of orbital observation footprints (HiRISE, CTX, HRSC) with PDS product identifiers, spatial extents, and resolutions. | `ImageryCatalogService` |
| `service.py` | Facade orchestrating subsystem status, orbiter propagation, ground track generation, rover queries, observation catalogs, and timeline assembly. | `LiveMarsIntelligenceService` |

### 3.2 Frontend Architecture (`mission-ui/src/`)

| Component | Responsibility |
| :--- | :--- |
| `intelligence.js` | REST client connecting to backend `/api/v1/intelligence/*`, bundled with a standalone client-side Keplerian propagator and offline fallback catalog for resilient operation. |
| `IntelligencePanel.jsx` | Subsystem console featuring five interactive tabbed views: **Orbiters**, **Rovers**, **Footprints**, **Timeline**, and **Provenance**. |
| `MapView.jsx` | OpenLayers map renderer hosting four dedicated vector layers: `spacecraftLayer` (z:26), `groundTracksLayer` (z:12), `footprintsLayer` (z:11), and `curiosityLayer` (z:16). |
| `main.jsx` | Root state coordinator managing top-level navigation (`Rover history` \| `Route planner` \| `Live Mars Intelligence`), layer toggles, periodic orbiter position ticker (3.5s refresh), and viewport transitions. |

---

## 4. Provenance & Coordinate References

- **Planetary Reference Frame:** IAU2000:49900 (Mars East Longitude, Positive North, Aerocentric coordinates).
- **Metric Projection:** Mars equirectangular projection centered on Jezero Crater ($77.575^\circ\text{E}, 18.4^\circ\text{N}$) with $R_{\text{Mars}} = 3,396,190\text{ m}$.
- **Ellipsoid Reference:** Mars triaxial/biaxial reference areoid ($R_{\text{eq}} = 3396.19\text{ km}$, $R_{\text{pol}} = 3376.20\text{ km}$, $J_2 = 1.96045 \times 10^{-3}$).
