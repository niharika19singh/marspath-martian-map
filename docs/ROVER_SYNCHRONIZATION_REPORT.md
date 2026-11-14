# Mars Rover Telemetry & Traverse Synchronization Report

## 1. Executive Summary

The Live Mars Intelligence subsystem unifies real-time and historical telemetry for the two active NASA surface roving laboratories on Mars:

1. **Perseverance (Mars 2020):** Exploring Jezero Crater's western fan delta and crater rim margin carbonate unit (Sol 0 through Sol 2022+).
2. **Curiosity (Mars Science Laboratory - MSL):** Ascending Mount Sharp (Aeolis Mons) through the Upper Gediz Vallis Ridge in Gale Crater (Sol 0 through Sol 4400+).

Both rover datasets are geospatially synchronized with the Mars cartographic engine, supporting interactive selection, odometry audits, elevation profile reconstruction, and surface science observation inspection.

---

## 2. Active Surface Laboratory Comparison

| Telemetry Attribute | NASA Mars 2020 (*Perseverance*) | NASA MSL (*Curiosity*) |
| :--- | :--- | :--- |
| **Landing Site** | Octavia E. Butler Landing, Jezero Crater | Bradbury Landing, Gale Crater |
| **Coordinates** | $77.23322^\circ\text{E}, 18.43559^\circ\text{N}$ | $137.35820^\circ\text{E}, -4.68810^\circ\text{N}$ |
| **Current Elevation** | $-1,936.37\text{ m}$ (relative to MOLA datum) | $-4,085.00\text{ m}$ (relative to MOLA datum) |
| **Current Sol** | **Sol 2022+** | **Sol 4400+** |
| **Total Odometry** | **$45,245.71\text{ m}$ ($45.25\text{ km}$)** | **$33,150.00\text{ m}$ ($33.15\text{ km}$)** |
| **Latest Drive Leg** | $22.06\text{ m}$ (Western Rim Margin) | $28.50\text{ m}$ (Upper Gediz Vallis) |
| **Heading** | $284.5^\circ$ (West-Northwest) | $222.0^\circ$ (Southwest) |
| **Active Instruments** | Mastcam-Z, SuperCam, PIXL, SHERLOC, MEDA, RIMFAX, MOXIE | Mastcam, ChemCam, APXS, MAHLI, CheMin, SAM, RAD, DAN, REMS |
| **Current Mission Phase** | Crater Rim Campaign / Margin Carbonates | Mount Sharp Ascent / Gediz Vallis Water History |
| **Data Freshness State** | `LATEST AVAILABLE` | `LATEST AVAILABLE` |
| **Geospatial Uncertainty**| $\pm 0.15\text{ m}$ (Visual Odometry & Navcam Bundle) | $\pm 0.25\text{ m}$ (Visual Odometry & HiRISE Localization) |

---

## 3. Traverse Data Architecture

### 3.1 Perseverance Traverse Dataset
- **Geometry Format:** GeoJSON FeatureCollection (`/mission-data/perseverance-traverse.geojson`).
- **Waypoints Format:** GeoJSON array (`/mission-data/perseverance-waypoints.geojson`).
- **Features:** 559 original drive segments spanning 36,661 vertices.
- **Filtering:** Dynamic Sol cutoff slider (`solCut`) allows visual reconstruction of the rover's journey from landing (Sol 0) to current Sol.

### 3.2 Curiosity Gale Crater Dataset
- **Traverse Dataset:** GeoJSON FeatureCollection (`/mission-data/curiosity-traverse.geojson`).
- **Waypoints Dataset:** GeoJSON FeatureCollection (`/mission-data/curiosity-waypoints.geojson`).
- **Key Milestones:**
  1. *Bradbury Landing:* Sol 0, $137.4417^\circ\text{E}, -4.5895^\circ\text{N}$, $0\text{ m}$ odometry.
  2. *Yellowknife Bay (First Drill - John Klein):* Sol 182, $137.4560^\circ\text{E}, -4.5910^\circ\text{N}$, $720\text{ m}$ odometry.
  3. *Kimberley Waypoint:* Sol 590, $137.3980^\circ\text{E}, -4.6320^\circ\text{N}$, $6,450\text{ m}$ odometry.
  4. *Pahrump Hills (Base of Mt. Sharp):* Sol 753, $137.3820^\circ\text{E}, -4.6540^\circ\text{N}$, $9,200\text{ m}$ odometry.
  5. *Vera Rubin Ridge Entry:* Sol 1812, $137.3650^\circ\text{E}, -4.7120^\circ\text{N}$, $17,250\text{ m}$ odometry.
  6. *Glen Torridon (Clay-Bearing Unit):* Sol 2300, $137.3840^\circ\text{E}, -4.7280^\circ\text{N}$, $20,800\text{ m}$ odometry.
  7. *Marker Band Valley:* Sol 3550, $137.3710^\circ\text{E}, -4.7080^\circ\text{N}$, $28,450\text{ m}$ odometry.
  8. *Upper Gediz Vallis Ridge (Current Position):* Sol 4400, $137.3582^\circ\text{E}, -4.6881^\circ\text{N}$, $33,150\text{ m}$ odometry.

---

## 4. Scientific Observations & Instrument Integration

The rover intelligence service links physical surface coordinates to verified observational science targets:

1. **Perseverance `M20_SOL2022_MASTCAMZ_01`:**
   - Instrument: Mastcam-Z Multispectral Stereo Camera
   - Target: *Jezero Crater Rim Margin Carbonate Unit* ($77.23322^\circ\text{E}, 18.43559^\circ\text{N}$)
   - Science Context: Investigating ancient stromatolitic and lacustrine carbonate precipitates along the inner rim terracing.
2. **Perseverance `M20_SOL2018_SUPERCAM_LIBS_04`:**
   - Instrument: SuperCam Laser-Induced Breakdown Spectroscopy (LIBS)
   - Target: *Altered Olivine-Rich Boulder Float* ($77.23410^\circ\text{E}, 18.43480^\circ\text{N}$)
   - Science Context: Elemental composition and organic detection via Raman and luminescence spectroscopy.
3. **Curiosity `MSL_SOL4400_CHEMCAM_LIBS_01`:**
   - Instrument: ChemCam Remote Micro-Imager (RMI) & LIBS
   - Target: *Gediz Vallis Debris Flow Boulders* ($137.35820^\circ\text{E}, -4.68810^\circ\text{N}$)
   - Science Context: Geochemical characterization of late-stage violent water and debris flow deposits on Mount Sharp.
