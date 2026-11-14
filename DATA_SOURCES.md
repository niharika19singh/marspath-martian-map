# MARSPath Data Sources & Provenance Manifest

All authoritative planetary datasets referenced or ingested by MARSPath are cataloged in [`backend/app/data/manifest.py`](backend/app/data/manifest.py). Routing calculations strictly consume numerical Digital Elevation Models (DEMs); visual orthomosaics are strictly display-only.

---

## 1. Numerical Elevation Models (DEMs — Used for Routing & Terrain Analysis)

### 1.1 USGS Mars HRSC-MOLA Blended Global DEM (200 m/px)
- **Product ID:** `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`
- **DOI:** `10.5066/P9P7W018`
- **Native Resolution:** `200.0 m/px` (`296.3735 px/deg`)
- **CRS / Datum:** `IAU2000:49900` (Mars 2000 Equirectangular, $R = 3,396,190\text{ m}$); Vertical Datum: `Mars Areoid (MOLA 0m reference datum)`
- **NoData Sentinel:** `-32768.0`
- **Coverage:** Global / Jezero regional envelope (`77.20°E–77.95°E`, `18.15°N–18.65°N` operational crop)
- **Role:** Regional/crater-wide fallback DEM and independent elevation source for `/api/v1/conditions`.
- **License:** Public Domain (NASA / USGS / ESA open planetary science data policy)

### 1.2 USGS Mars 2020 TRN HiRISE Digital Terrain Model (1 m/px native)
- **Product ID:** `JEZ_hirise_soc_006_DTM_MOLAtopography_DeltaGeoid_1m_Eqc_latTs0_lon0_blend40`
- **DOI:** `10.5066/P9REJ9JN`
- **Native Resolution:** `1.0 m/px` (automatically aggregated conservatively by integer block factor when a requested crop exceeds `MAX_GRID_CELLS`, e.g., `8.0 m/px` effective routing grid; both native and effective resolutions are disclosed)
- **CRS / Datum:** `IAU2000:49900`; Vertical Datum: `Mars 2000 MOLA Geoid (DeltaGeoid blend40)`
- **Coverage:** Full product footprint `77.2229331°E–77.583964°E`, `18.3067994°N–18.669315°N`; locally provisioned corridor window `77.3819891°E–77.4580081°E`, `18.3719875°N–18.4400097°N`
- **Role:** Primary high-resolution numerical elevation model for Jezero Western Delta / Perseverance landing corridor routing and directional slope analysis.
- **License:** Public Domain (USGS Astrogeology Science Center / NASA PDS)

### 1.3 Supplementary Local HiRISE DTMs (Catalog Reference)
- `DTEEC_045994_1985_046060_1985_U01` (`https://doi.org/10.17189/1519501`, `1.0096633 m/px`, `18.3053°N–18.5484°N`, `77.3834°E–77.5011°E`)
- `dem_hirise_jezero_delta_1m` (`ESP_037803_1985`, `1.0 m/px`)

---

## 2. Visual Basemap Imagery (OGC WMTS / Visualization Only)

> **Important:** None of the datasets in Section 2 contain elevation measurements; none are ever used to compute slope, roughness, return zones, or routes.

| Layer | Product ID | DOI / Origin | Native Resolution | Coverage | Format |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HiRISE 25 cm Ortho** | `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first` (`_dd` WMTS) | `10.5066/P9QJDP48` (USGS / NASA Mars Trek) | `0.25 m/px` | Jezero Delta / Landing Corridor | WMTS PNG (`z=0..17`), uint8 grayscale |
| **CTX 6 m Ortho** | `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` | `10.5066/P9GV1ND3` (USGS / NASA Mars Trek) | `6.0 m/px` | `77.1605°E–77.6992°E`, `18.2110°N–18.7212°N` | WMTS PNG (`z=0..13`), uint8 grayscale |
| **Viking MDIM 2.1 Color Mosaic** | `Mars_Viking_MDIM21_ClrMosaic_global_232m` | `10.5066/F71V5C67` (USGS / NASA Mars Trek) | `232.0 m/px` | Global Mars (`-180°..180°`, `-90°..90°`) | WMTS JPEG (`z=0..7`) |

---

## 3. Ephemeris, Climatology, and In-Situ Telemetry Sources

1. **NASA GISS Mars24 Solar Geometry (`backend/app/conditions/mars24.py` & `mission-ui/src/conditions.js`)**
   - Reference: Allison, M., & McEwen, M. (2000), *Planet. Space Sci.*, 48, 215–235 (`doi:10.1016/S0032-0633(99)00092-6`), and NASA GISS Mars24 Algorithm.
   - `kind`: `astronomical_exact` (Solar longitude $L_s$, Mars Sol Date, MTC, LMST, LTST, solar elevation/azimuth, sunrise/sunset LTST).
2. **Jezero Modelled Climatology (`backend/app/conditions/climate.py`)**
   - Diurnal + seasonal harmonic model calibrated to Mars Climate Database (MCD v6.1) and Mars 2020 MEDA Year-1 baseline (Rodriguez-Manfredi et al. 2021, Newman et al. 2022, Martinez et al. 2023).
   - `kind`: `modelled_climatology`.
3. **NASA PDS Perseverance MEDA Observations (`urn:nasa:pds:mars2020_meda`)**
   - Released surface air/ground temperature and pressure telemetry snapshots carrying Sol, UTC timestamp, `pds_product_id`, `pds_lidvid`, and sensor flags.
   - `kind`: `measured_observation`.

---

## 4. Scientific Weighting & Ancillary Context Layers (Catalogued in `manifest.py`)

- **CRISM Mineralogy MTR3** (`10.17189/1519498`, `18.0 m/px`, Mars Reconnaissance Orbiter): Hyperspectral summary parameters for biosignature-relevant clay/carbonate POIs.
- **THEMIS Nighttime IR Thermal Inertia** (`10.17189/1519495`, `100.0 m/px`, 2001 Mars Odyssey): Surface blockiness vs. fine dust thermal proxy.
