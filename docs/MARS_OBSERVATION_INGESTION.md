# Mars Observation Ingestion & Footprint Catalog Architecture

## 1. Overview

The **Mars Observation Ingestion** subsystem manages the ingestion, spatial indexing, footprint polygon extraction, and rendering composition of high-resolution orbital remote sensing datasets. It unifies observations across NASA and ESA Mars missions, allowing mission planners to inspect genuine satellite image footprints, spatial resolutions, acquisition epochs, and PDS/PSA archive products.

---

## 2. Remote Sensing Instrument Specifications

| Instrument | Spacecraft | Spectral Bands | Nadir Resolution | Typical Footprint Swath | PDS / PSA Archive Node |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HiRISE** (High Resolution Imaging Science Experiment) | MRO | RED (visible), BG (blue-green), NIR | $0.25 - 0.30\text{ m/px}$ | $\sim 5 - 6\text{ km}$ wide | NASA PDS Cartography and Imaging Sciences Node (IMG) |
| **CTX** (Context Camera) | MRO | Panchromatic ($500 - 800\text{ nm}$) | $5.0 - 6.0\text{ m/px}$ | $\sim 30\text{ km}$ wide | NASA PDS Geosciences Node |
| **HRSC** (High Resolution Stereo Camera) | Mars Express | Panchromatic Stereo + 4 Colors | $10.0 - 15.0\text{ m/px}$ | $\sim 50\text{ km}$ wide | ESA Planetary Science Archive (PSA) |
| **THEMIS** (Thermal Emission Imaging System) | 2001 Mars Odyssey | 5 VIS + 9 IR thermal bands | $18\text{ m/px}$ (VIS), $100\text{ m/px}$ (IR) | $\sim 32\text{ km}$ wide | NASA PDS Imaging Node / ASU Mars Space Flight Facility |

---

## 3. Cataloged Planetary Observation Footprints

The system indexes calibrated observations with exact georeferenced bounding polygons in the IAU2000 Mars East coordinate frame:

### 3.1 Observation `ESP_069176_1985` (MRO HiRISE)
- **Target:** Jezero Crater Western Delta Fan and Sinuous Inverted Channels
- **Acquisition UTC:** 2021-04-18T10:14:22Z (Martian Sol 57)
- **Center Coordinates:** $77.365^\circ\text{E}, 18.435^\circ\text{N}$
- **Ground Resolution:** $0.25\text{ m/pixel}$
- **Dimensions:** $2,675 \times 2,304\text{ pixels}$
- **Bounding Polygon:**
  $[[77.267962, 18.354526], [77.497559, 18.354526], [77.497559, 18.542117], [77.267962, 18.542117], [77.267962, 18.354526]]$
- **PDS Product ID:** `ESP_069176_1985_RED`
- **Citation:** [https://www.uahirise.org/ESP_069176_1985](https://www.uahirise.org/ESP_069176_1985)

### 3.2 Observation `P01_001426_1985_XN_18N282W` (MRO CTX)
- **Target:** Regional Jezero Crater Floor and Wall Terraces Context
- **Acquisition UTC:** 2006-11-13T22:04:11Z
- **Center Coordinates:** $77.525^\circ\text{E}, 18.385^\circ\text{N}$
- **Ground Resolution:** $6.0\text{ m/pixel}$
- **Bounding Polygon:**
  $[[77.100, 18.050], [77.950, 18.080], [77.900, 18.720], [77.050, 18.690], [77.100, 18.050]]$
- **PDS Product ID:** `P01_001426_1985_XN_18N282W`

### 3.3 Observation `H5273_0000_ND3` (MEX HRSC)
- **Target:** Jezero Crater and Nili Fossae Regional Context
- **Acquisition UTC:** 2008-01-24T18:32:04Z
- **Center Coordinates:** $77.450^\circ\text{E}, 18.400^\circ\text{N}$
- **Ground Resolution:** $12.5\text{ m/pixel}$
- **PSA Product ID:** `H5273_0000_ND3`

---

## 4. Multi-Resolution Map Layer Composition & Radiometric Blending

To eliminate hard rectangular boundaries and blurry grey artifacts, MARSPath applies a three-tier rendering pipeline:

1. **Regional Context Layer:** Continuous regional CTX mosaic (`/mission-data/jezero-imagery.jpg`, $6\text{ m/px}$) provides complete, gap-free coverage across the entire map extent.
2. **HiRISE Delta Inset (`jezero-hirise.webp`):**
   - **Smooth-Step Euclidean Distance Transform:** An alpha feathering mask of 56-pixel radius smoothly ramps opacity from $0.0$ at the image boundary to $1.0$ in the interior:
     $$\alpha(d) = 3\left(\frac{d}{R}\right)^2 - 2\left(\frac{d}{R}\right)^3, \quad 0 \le d \le R = 56\text{ px}$$
   - **Radiometric Albedo Equalization:** A -5.0 luminance offset balances the HiRISE mean albedo ($121.2$) with the surrounding CTX mosaic ($126.3$), eliminating contrast discontinuities.
3. **Layer Ordering & Fallback Guarantee:**
   - In both `hirise` and `imagery` basemap modes, the regional CTX imagery layer remains active at `zIndex: 2`.
   - The feathered HiRISE inset renders on top at `zIndex: 3`.
   - In areas outside the HiRISE coverage footprint, the high-resolution CTX mosaic is directly visible without procedural grey voids.
