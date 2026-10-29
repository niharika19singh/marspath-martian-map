# Verified NASA, ESA, and USGS Planetary Data Sources

This document details the scientific datasets evaluated for **MARSPath** in the **Jezero Crater** pilot region (`18.38°N, 77.58°E`).

---

## 1. High-Resolution Digital Elevation Models (DEMs)

### A. HRSC & MOLA Blended DEM (50m & 200m Jezero Mosaic)
- **Official Name:** `JEZERO_HRSC_MOLA_blended_DEM`
- **Instruments:** ESA Mars Express High Resolution Stereo Camera (HRSC) + NASA Mars Global Surveyor Mars Orbiter Laser Altimeter (MOLA).
- **Publisher:** USGS Astrogeology Science Center / PDS Geosciences Node.
- **Official URL:** `https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZERO_HRSC_MOLA_blended_DEM`
- **Spatial Coverage:** MC-11E quadrant (17.5°N - 19.5°N, 76.5°E - 78.5°E), covering the entire Jezero Crater basin and surrounding Nili Fossae crust.
- **Resolution:** 50.0 meters/pixel (blended mosaic) and 200.0 meters/pixel (regional base).
- **Data Type:** **True numerical elevation** (32-bit floating point, meters relative to Mars areoid datum).
- **Format:** GeoTIFF / USGS ISIS3 `.cub`.
- **License / Attribution:** Public Domain (NASA / ESA Open Planetary Science Policy).
- **Usage in MARSPath:** Master regional raster for physical gradient, slope, and roughness modeling.

### B. HiRISE Digital Terrain Model (DTM) — Jezero Western Delta
- **Official Name:** `HiRISE DTM ESP_037803_1985 / ESP_037869_1985`
- **Instrument:** NASA Mars Reconnaissance Orbiter (MRO) High Resolution Imaging Science Experiment (HiRISE).
- **Publisher:** University of Arizona / NASA PDS Geosciences Node.
- **Official URL:** `https://www.uahirise.org/dtm/dtm.php?ID=ESP_037803_1985`
- **Spatial Coverage:** 18.35°N - 18.46°N, 77.38°E - 77.47°E (~6 km x 18 km corridor along delta scarp).
- **Resolution:** 1.0 meter/pixel elevation, 0.25 meter/pixel orthorectified image.
- **Data Type:** Numerical elevation in physical meters.
- **Limitations:** Extremely localized spatial coverage; unsuitable as a stand-alone regional map, but ideal for delta scarp ascent corridors.

---

## 2. Visible Imagery & Basemaps (Context Only)

### A. NASA Solar System Treks — Mars Trek WMTS
- **Publisher:** NASA Jet Propulsion Laboratory (JPL)
- **Service Endpoint:** `https://trek.nasa.gov/tiles/Mars/EQ/...`
- **Format:** XYZ / WMTS PNG tiles.
- **Crucial Distinction:** **IMAGERY ONLY.** Contains zero numerical elevation values. MARSPath exposes this as a visual basemap in `/api/v1/layers` for Kunal's map display, but **NEVER calculates slopes or routing costs from image grayscale values**.

### B. CTX Jezero Crater Controlled Image Mosaic (6m/px)
- **Publisher:** Murray Lab, Caltech / NASA PDS Cartography Node
- **URL:** `https://murray-lab.caltech.edu/CTX/tiles/beta/Jezero.html`
- **Resolution:** 6.0 meters/pixel.
- **Data Type:** 8-bit visible radiance image. Visual verification only.

---

## 3. Compositional & Thermal Hazard Context

### A. CRISM Targeted Mineralogy (MTR3)
- **Publisher:** JHU Applied Physics Laboratory / NASA PDS Geosciences Node
- **Spatial Resolution:** ~18 meters/pixel.
- **Parameters:** Clay index (BD1900, D2300), Carbonates, Olivine index.
- **Role in MARSPath:** Defines the coordinates and priorities of scientific points of interest (Delta front, Belva crater, Séítah formation) for the `science_first` routing mode.

### B. THEMIS Nighttime Infrared Global Mosaic
- **Publisher:** Arizona State University / NASA PDS
- **Spatial Resolution:** 100 meters/pixel.
- **Role in MARSPath:** Proxy for surface thermal inertia and rock/boulder abundance.

---

## 4. Real Data Setup Instructions

To load real USGS/NASA DEM data into MARSPath:
1. Download `JEZERO_HRSC_MOLA_blended_DEM.tif` from USGS Astropedia.
2. Place the file at:
   `backend/app/data/rasters/jezero_mola_hrsc_blended.tif`
3. Set environment variables:
   ```bash
   MARSPATH_USE_REAL_DEM=true
   MARSPATH_ALLOW_SYNTHETIC_FALLBACK=false
   ```
4. Restart the backend. `/api/v1/data/status` will report `data_mode: "real"`.
