# Verified NASA, ESA, and USGS Planetary Data Sources & Ingestion Pipeline

This document details the scientific datasets evaluated and supported for **MARSPath** in the **Jezero Crater** pilot region (`18.38°N, 77.58°E`), the cloud-native ingestion pipeline, and the provenance verification design.

---

## 1. Primary Digital Elevation Model (DEM) & Authoritative Ingestion

### A. USGS Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2
- **Official Product Name:** `Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2`
- **Product ID:** `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`
- **Instruments:** ESA Mars Express High Resolution Stereo Camera (HRSC) + NASA Mars Global Surveyor Mars Orbiter Laser Altimeter (MOLA).
- **Publisher:** USGS Astrogeology Science Center / NASA PDS Geosciences Node / DLR / ESA (Fergason et al., 2018).
- **Official Landing Page:** [USGS Astropedia Mars HRSC MOLA Blended DEM 200m](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200m)
- **Authoritative Direct Download URL:** [USGS Planetary Maps](https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif) (redirects to AWS S3: `https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif`)
- **Authoritative Published Full-Archive MD5 Checksum:** `e98092a06bea74d5ec9a704dcd1fe318` (applies to the full 11.38 GB global file)
- **Official PDS3 Label:** [PDS3 LBL Archive](https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/99f5a18a-b4fb-4e87-8417-7408d8440651/download/mars_hrsc_mola_blenddem_global_200mp_v2_pds3.lbl)
- **Official ISIS3 Label:** [ISIS3 LBL Archive](https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/mars_hrsc_mola_blenddem_global_200mp_v2.lbl)
- **Global Coverage:** 90°N to -90°S, -180°E to +180°E / 0°E to 360°E ($53,347 \times 106,694$ pixels, 11.38 GB).
- **Nominal Spatial Resolution:** 200.0 meters/pixel ($296.3735\text{ pixels/degree}$; $0.00337412\text{ deg/px}$).
- **Horizontal CRS:** `IAU2000:49900` / `ESRI:104971` (`GCS_Mars_2000_Sphere`) Simple Cylindrical / Equirectangular on Mars 2000 Sphere ($R=3,396,190\text{ m}$), positive-East longitude, planetocentric latitude.
- **Vertical Datum:** Mars MOLA Areoid 0-meter reference datum.
- **Elevation Units & Range:** 16-bit signed integer meters relative to the areoid.
- **NoData Value:** `-32768.0`.
- **Scientific Caveats & USGS Warnings:**
  - **200 m/px Regional Scale:** Supports regional corridor terrain assessment across Jezero Crater, **not** metre-scale boulder/obstacle detection or flight-grade rover navigation.
  - **Blending & Thermal-Modelling Origin:** USGS notes this dataset was originally constructed to derive global thermal inertia (for THEMIS) where smooth regional transitions were prioritized over local topographic accuracy. Blending HRSC stereo models with MOLA laser altimetry introduces seam artifacts, registration offsets, and smoothing inconsistencies across transition boundaries.

### B. HiRISE Digital Terrain Model (DTM) — Jezero Western Delta (Optional Local High-Resolution Source)
- **Catalog Product ID:** `dem_hirise_jezero_delta_1m`
- **Reference Stereo Pair:** `HiRISE DTM ESP_037803_1985 / ESP_037869_1985`
- **Instrument:** NASA Mars Reconnaissance Orbiter (MRO) High Resolution Imaging Science Experiment (HiRISE).
- **Publisher:** University of Arizona / NASA PDS Geosciences Node.
- **Official URL:** `https://www.uahirise.org/dtm/dtm.php?ID=ESP_037803_1985`
- **Spatial Coverage:** `18.35°N` to `18.46°N`, `77.38°E` to `77.47°E` (~6 km × 18 km localized corridor covering the Jezero Western Delta front and scarp).
- **Resolution:** ~1.0 meter/pixel numerical elevation (`0.15 m/px` to `25.0 m/px` supported local high-resolution range).
- **Configuration & Provisioning:**
  - Controlled via `MARSPATH_USE_HIRISE_DEM=true|false` (default `false`) and `MARSPATH_HIRISE_DEM_PATH=backend/app/data/rasters/hirise_jezero_delta_dtm.tif`.
  - Optional: when `MARSPATH_USE_HIRISE_DEM=false` or when a route extends outside the HiRISE footprint, MARSPath automatically uses the regional MOLA–HRSC 200 m/px DEM without failing startup.
- **Honest Provenance & Unverified Local Status:**
  - Unless an authoritative upstream SHA-256 or MD5 checksum is independently verified against `DATA_CATALOG_MANIFEST`, a locally supplied HiRISE GeoTIFF is classified as `valid_numeric_raster_unverified_source` (`data_mode = "real_unverified_source"`, `source_checksum_verified = false`, `official_product_id = null`, `evidence_passport.quality_tier = "unverified"`).
  - MARSPath **never** fabricates HiRISE checksums, URLs, or `verified_source` status for unauthenticated local HiRISE files.
- **Vertical Datum & Stereo DTM Caveats:**
  - HiRISE stereo DTMs are typically controlled to MOLA altimetry profiles or local stereo bundle adjustments; unless an explicit Mars vertical datum is embedded in the GeoTIFF tags and verified, the vertical datum is reported as `"Unspecified / Unverified Local Mars Vertical Reference"` and explicitly disclosed in `source_limitations`.
  - Stereo correlation can contain local interpolation artifacts over featureless sand, steep shadows, or scarp overhangs, and even ~1 m/px DTMs do **not** resolve sub-meter rocks, sharp wheel-scale hazards, or soil bearing capacity (`obstacle_detection_capable = false`).

---

## 1.5 Multi-Resolution Terrain Source Selection & Single-Source Invariant

MARSPath implements a resolution-aware, **single-source** terrain architecture (`TerrainSourceSelector` in `backend/app/services/terrain_source_service.py`):

1. **Single-Source Invariant (No Cross-DEM Mosaicking or NoData Patching):**
   - Every route planning request (`POST /api/v1/routes/plan`) executes on **one** consistent analysis grid derived from **one** selected elevation source (`dem_hirise_jezero_delta_1m` **or** `dem_mola_hrsc_jezero_200m`).
   - MARSPath **never** stitches or mosaics partially overlapping HiRISE and MOLA–HRSC rasters into a composite grid and **never** fills HiRISE `NoData` cells with MOLA–HRSC values, avoiding artificial seam cliffs (~10–50 m vertical registration offsets between local stereo DTMs and regional blended altimetry) and resolution discontinuity artifacts.
2. **Corridor Containment Rule:**
   - HiRISE is selected only when `MARSPATH_USE_HIRISE_DEM=true`, the local HiRISE GeoTIFF passes all geospatial/metric validations, and 100% of the padded mission corridor (`start`, `destination`, all `science_waypoints`, and the surrounding padding buffer) falls inside the HiRISE geographic and native pixel bounds with sufficient valid observation coverage ($\ge 50\%$ valid corridor cells and non-NoData endpoints).
   - If any part of the padded corridor extends outside the HiRISE footprint, MARSPath selects the regional MOLA–HRSC 200 m/px DEM for the entire request and records the structured reason in `source_selection`.
3. **Adaptive Resolution & Conservative Hazard-Preserving Block Aggregation:**
   - When a corridor lies entirely within HiRISE and native cells $\le \text{MAX\_GRID\_CELLS}$ ($250,000$), routing runs at native HiRISE resolution (`aggregation_factor = 1`, `resolution_mode = "native"`).
   - When native cells $> \text{MAX\_GRID\_CELLS}$, MARSPath computes $k = \lceil\sqrt{N_{\text{native}} / \text{MAX\_GRID\_CELLS}}\rceil$. If the aggregated resolution $k \cdot \text{res}_{\text{native}}$ remains strictly finer than MOLA–HRSC ($< 0.95 \cdot \text{res}_{\text{mola}}$), MARSPath applies conservative $k \times k$ block aggregation (`mean_elevation_strict_nodata_max_subgrid_slope_roughness`), propagating any `NoData` pixel as `NaN` (never `0.0`) and preserving the maximum native sub-block slope and roughness as a lower bound during traversability and risk evaluation.
   - If required aggregation would make effective resolution no better than MOLA–HRSC ($\ge 0.95 \cdot \text{res}_{\text{mola}}$), HiRISE is rejected (`rejected_aggregated_resolution_no_better_than_regional`) and MOLA–HRSC is selected.

---

## 2. Cloud-Native Ingestion Pipeline & Live Validation Results

Because the global USGS DEM is 11.38 GB, committing it to Git is prohibited. MARSPath provides a reproducible ingestion pipeline (`backend/app/data/ingestion.py`) that streams the Jezero Crater sub-window via GDAL `/vsicurl/` HTTP Range requests directly from the official USGS S3 archive:

```bash
# Run the ingestion CLI against the official USGS S3 endpoint
PYTHONPATH=.:.deps python3 -m backend.app.data.ingestion
```

### Validated Jezero Crater Extract Specifications
- **Extracted Window Indices:** `col_off=76212, row_off=21131, width=252, height=178`
- **Raster Dimensions:** $178 \text{ rows} \times 252 \text{ cols}$ ($44,856$ cells)
- **Geographic Coverage:** `77.1485°E` to `77.9988°E`, `18.1009°N` to `18.7015°N`
- **Physical Pixel Dimensions at Jezero ($18.40^\circ\text{N}$):** $\Delta x = 189.77\text{ m}$, $\Delta y = 200.00\text{ m}$
- **Valid Data Coverage:** $44,856 / 44,856$ cells ($100.0\%$, $0$ nodata cells)
- **Elevation Statistics:** $\min = -2,816.0\text{ m}$, $\max = -1,522.0\text{ m}$, $\text{mean} = -2,424.77\text{ m}$
- **Local Raster SHA-256:** `03845eeebd5965a288d8835c414632773d18ee3b392b38cf40d0467154c0f029`
- **Extracted Float32 Array SHA-256:** `e9a823c7ee00f68e6b5985425b90e574e30638f6223d07010bc75f98214f3074`

---

## 3. Hardened Provenance Verification Architecture

MARSPath strictly separates **local file SHA-256 integrity** (`local_integrity_verified`) from **authoritative upstream source authenticity** (`source_checksum_verified`).

- **No Blind Sidecar Trust:** A provenance sidecar JSON is never trusted to grant `verified_source` merely because `local_file_sha256` matches the local file and `source_md5` contains the known catalog string (`e98092a06bea74d5ec9a704dcd1fe318`).
- **No Unverified Local Ingestion Promotion:** Passing a synthetic or unverified local GeoTIFF through `ingest_jezero_dem` hashes the local source bytes, detects that they do not match any catalog checksum in `DATA_CATALOG_MANIFEST`, and classifies the output as `valid_numeric_raster_unverified_source` with `source_product_id: None`.
- **Honest Partial Range Extraction Reporting:** Because USGS publishes `e98092a06bea74d5ec9a704dcd1fe318` for the entire 11.38 GB global file rather than a clipped sub-window, a partial HTTP range extraction via `/vsicurl/` cannot verify the full-archive MD5 over all upstream bytes and is reported as `official_endpoint_retrieved_checksum_unverified`.

### What Each Verification Status Proves and Does Not Prove

| Validation Status | Data Mode | What It Proves | What It Does NOT Prove |
| :--- | :--- | :--- | :--- |
| `verified_source` | `real` | The full source bytes were independently hashed (SHA-256 or MD5) and matched an authoritative checksum in `DATA_CATALOG_MANIFEST` (either directly on the loaded file, or on a local full-product source file whose extracted window pixels match the loaded file). | Metre-scale obstacle safety below sensor resolution. |
| `official_endpoint_retrieved_checksum_unverified` | `real_official_endpoint_unverified_checksum` | Retrieved via `/vsicurl/` HTTP Range extraction from the official USGS endpoint, passes Mars `IAU2000:49900` georeferencing and Jezero elevation checks, matches the deterministic USGS Jezero window array digest, and passes local SHA-256 integrity verification (`local_integrity_verified: true`). | Full 11.38 GB upstream file MD5 verification (`source_checksum_verified: false`), because only the Jezero sub-window byte ranges were streamed. |
| `valid_numeric_raster_unverified_source` | `real_unverified_source` | Valid 2D numeric elevation raster with supported Mars CRS, valid pixel resolution, and plausible Martian elevations over Jezero Crater. | NASA/ESA/USGS source authenticity. Assigned to arbitrary local files, unverified local ingestions, forged sidecars, tampered files (`local_integrity_verified: false`), or unauthenticated TIFF tags. |
| `synthetic_test_fixture` | `synthetic_test_fixture` | Deterministic procedural mathematical terrain model active (`MARSPATH_USE_REAL_DEM=false`). | Real Martian topography. |
| `incomplete_missing_genuine_dem` | `synthetic_fallback` | `MARSPATH_USE_REAL_DEM=true` was requested with synthetic fallback permitted, and the DEM file was missing or failed validation. | Real-data readiness (`real_dem_loaded: false`). |

---

## 4. Contextual & Basemap Datasets

### A. NASA Solar System Treks — Mars Trek WMTS
- **Publisher:** NASA Jet Propulsion Laboratory (JPL)
- **Service Endpoint:** `https://trek.nasa.gov/tiles/Mars/EQ/...`
- **Format:** XYZ / WMTS PNG image tiles.
- **Usage:** Served via `GET /api/v1/layers` as `mars_trek_imagery_basemap` for visual display in the frontend map. **Never** used for elevation, slope, or routing calculations.

### B. CRISM Targeted Mineralogy (MTR3)
- **Publisher:** JHU Applied Physics Laboratory / NASA PDS Geosciences Node
- **Spatial Resolution:** ~18 meters/pixel.
- **Parameters:** Smectite clays (BD1900), Carbonates (D2300), Olivine index.
- **Usage:** Used to designate and weight high-value science waypoints (Delta front, Belva crater, Séítah) during `science_first` routing.
