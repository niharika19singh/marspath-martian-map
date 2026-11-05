# Verified NASA, ESA, and USGS Planetary Data Sources & Ingestion Pipeline

This document details the scientific datasets evaluated and supported for **MARSPath** in the **Jezero Crater** pilot region (`18.38°N, 77.58°E`).

---

## 1. Primary Digital Elevation Model (DEM) & Authoritative Ingestion

### A. USGS Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2
- **Official Product Name:** `Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2`
- **Product ID:** `Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2`
- **Instruments:** ESA Mars Express High Resolution Stereo Camera (HRSC) + NASA Mars Global Surveyor Mars Orbiter Laser Altimeter (MOLA).
- **Publisher:** USGS Astrogeology Science Center / NASA PDS Geosciences Node / DLR / ESA.
- **Official Landing Page:** [USGS Astropedia Mars HRSC MOLA Blended DEM 200m](https://astrogeology.usgs.gov/search/map/mars_mgs_mola_mex_hrsc_blended_dem_global_200mp)
- **Authoritative Direct Download URL:** [USGS Planetary Maps](https://planetarymaps.usgs.gov/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif) (redirects to AWS S3: `https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif`)
- **Authoritative Published MD5 Checksum:** `e98092a06bea74d5ec9a704dcd1fe318`
- **Official PDS3 Label:** [PDS3 LBL Archive](https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/99f5a18a-b4fb-4e87-8417-7408d8440651/download/mars_hrsc_mola_blenddem_global_200mp_v2_pds3.lbl)
- **Official ISIS3 Label:** [ISIS3 LBL Archive](https://astrogeology.usgs.gov/ckan/dataset/6c177b5f-97af-4d70-adc3-92cf362b9890/resource/9b3025b4-484e-47b1-a782-d88abc387cc1/download/mars_hrsc_mola_blenddem_global_200mp_v2.lbl)
- **Global Coverage:** 90°N to -90°S, 0°E to 360°E (53,347 x 106,694 pixels, 11.38 GB).
- **Spatial Resolution:** 200.0 meters/pixel ($296.3735\text{ pixels/degree}$).
- **Horizontal CRS:** IAU2000:49900 Simple Cylindrical / Equirectangular on Mars 2000 Sphere ($R=3,396,190\text{ m}$).
- **Vertical Datum:** Mars MOLA Areoid 0-meter reference datum.
- **Elevation Units & Range:** 16-bit signed integer meters relative to the areoid (Jezero basin elevations: $-2,816\text{ m}$ to $-1,522\text{ m}$).
- **NoData Value:** `-32768.0`.
- **License / Attribution:** Public Domain (NASA / USGS / ESA Open Planetary Science Policy).

### B. HiRISE Digital Terrain Model (DTM) — Jezero Western Delta (Local High-Res Corridor)
- **Official Name:** `HiRISE DTM ESP_037803_1985 / ESP_037869_1985`
- **Instrument:** NASA Mars Reconnaissance Orbiter (MRO) High Resolution Imaging Science Experiment (HiRISE).
- **Publisher:** University of Arizona / NASA PDS Geosciences Node.
- **Official URL:** `https://www.uahirise.org/dtm/dtm.php?ID=ESP_037803_1985`
- **Spatial Coverage:** 18.35°N - 18.46°N, 77.38°E - 77.47°E (~6 km x 18 km corridor along delta scarp).
- **Resolution:** 1.0 meter/pixel elevation, 0.25 meter/pixel orthorectified image.
- **Data Type:** Numerical elevation in physical meters.
- **Limitations:** Localized spatial coverage; unsuitable as a stand-alone regional map, but ideal for delta scarp ascent corridors.

---

## 2. Ingestion Pipeline & Cloud-Native Windowing

Because the global USGS DEM is 11.38 GB, committing or holding the full globe in cloud server memory is impractical and prohibited. MARSPath includes a reproducible cloud-native ingestion engine (`backend/app/data/ingestion.py`) that extracts the Jezero Crater corridor via HTTP range requests (`/vsicurl/`) directly from the authoritative USGS S3 archive:

```bash
# Run the automated ingestion CLI
python3 -m backend.app.data.ingestion
```

### What the Ingestion Pipeline Does:
1. **Remote Cloud-Windowing:** Connects to `https://asc-pds-services.s3.us-west-2.amazonaws.com/mosaic/Mars/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2.tif` using GDAL `/vsicurl/` range requests, streaming only the scanlines covering Jezero Crater ($77.15^\circ\text{E}-78.00^\circ\text{E}, 18.10^\circ\text{N}-18.70^\circ\text{N}$).
2. **Local GeoTIFF Output:** Writes a clean local GeoTIFF ($178 \times 252$ pixels, ~90 KB) to `backend/app/data/rasters/jezero_mola_hrsc_blended.tif` with intact Mars 2000 IAU2000:49900 CRS and MOLA Areoid metadata.
3. **Cryptographic Checksumming:** Calculates the SHA-256 digest of the extracted raster.
4. **Authoritative Provenance Sidecar:** Generates `jezero_mola_hrsc_blended.provenance.json` recording the upstream USGS product ID, upstream archive URL, upstream MD5 checksum (`e98092a06bea74d5ec9a704dcd1fe318`), local SHA-256 hash, spatial bounds, elevation statistics, and timestamp.

---

## 3. Hardened Provenance Verification Architecture

MARSPath enforces strict separation between numerical array integrity, metadata consistency, and authentic cryptographic provenance. A raster is **never** certified as genuine NASA data simply because it has valid dimensions, plausible elevations, or self-asserted metadata tags.

### Distinct Validation States:
| Validation Status | Data Mode | Condition & Verification Evidence |
| :--- | :--- | :--- |
| `synthetic_test_fixture` | `synthetic_test_fixture` | Default local development mode using procedural mathematical Jezero topography. |
| `incomplete_missing_genuine_dem` | `synthetic_fallback` | `MARSPATH_USE_REAL_DEM=true` was requested, but the DEM was missing or corrupt and synthetic fallback was permitted. |
| `valid_numeric_raster_unverified_source` | `real_unverified_source` | Real raster passed 2D numerical and Jezero spatial checks, but has **no cryptographic chain of custody** (unregistered SHA-256 or unauthenticated metadata tags). |
| `verified_source` | `real` | Real raster whose SHA-256 matches a registered catalog entry OR whose cryptographic provenance sidecar links to the verified upstream USGS MD5 (`e98092a06bea74d5ec9a704dcd1fe318`). |

> [!IMPORTANT]
> Spoofed or manually added TIFF tags (e.g., `PRODUCT_ID="JEZERO_HRSC_MOLA_blended_DEM"`) only grant metadata consistency and are categorized as `valid_numeric_raster_unverified_source`. Independent cryptographic verification is mandatory for `verified_source`.

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
