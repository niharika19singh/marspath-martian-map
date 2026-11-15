# NASA Surface POV Imagery Provenance & Verification

**Subsystem:** Authentic Ground-Level Optical Imagery Catalogue  
**Platform:** Mars 2020 Perseverance Rover (Mastcam-Z & Navcam)  
**Primary Archive:** NASA JPL / Caltech Planetary Data System (PDS) Photojournal  
**Authenticity Policy:** 100% Genuine NASA Planetary Products — Zero Generative AI Martian Landscapes.

---

## 1. Provenance Registry

Every ground photo presented in the MARSPath interface is catalogued with its authentic NASA JPL Photojournal ID, imaging instrument, acquisition Sol, and exact surface coordinates.

| NASA Product ID | Landmark Name | Sol | Instrument / Camera | Jezero Coordinates | NASA Photojournal URL |
|:---:|:---|:---:|:---|:---:|:---|
| **PIA24487** | Octavia E. Butler Landing | 1 | Mastcam-Z (360° Panorama) | 18.4447°N, 77.4508°E | [PIA24487 Catalog](https://photojournal.jpl.nasa.gov/catalog/PIA24487) |
| **PIA24836** | Kodiak Butte Remnant | 64 | Mastcam-Z (110mm Telephoto) | 18.4140°N, 77.4250°E | [PIA24836 Catalog](https://photojournal.jpl.nasa.gov/catalog/PIA24836) |
| **PIA25439** | Hawksbill Gap Delta Scarp | 412 | Mastcam-Z (Focus Merge) | 18.4468°N, 77.3980°E | [PIA25439 Catalog](https://photojournal.jpl.nasa.gov/catalog/PIA25439) |
| **PIA24839** | South Séítah Olivine Unit | 200 | Mastcam-Z & Navcam | 18.4320°N, 77.4420°E | [PIA24839 Catalog](https://photojournal.jpl.nasa.gov/catalog/PIA24839) |
| **PIA25828** | Belva Impact Crater | 802 | Mastcam-Z (152-Image Mosaic) | 18.5130°N, 77.3820°E | [PIA25828 Catalog](https://photojournal.jpl.nasa.gov/catalog/PIA25828) |

---

## 2. Scientific & Terramechanics Context

### 2.1 PIA24487 — Octavia E. Butler Landing (Crater Floor)
- **Geologic Context:** Touchdown location on the smooth olivine-bearing crater floor unit (Máaz formation).
- **Terramechanics:** Low slope gradient ($<2.0^\circ$), firm basaltic regolith pavement, high thermal inertia ($>380\text{ tiu}$). Minimal boot sinkage ($<1.5\text{ cm}$). Optimal baseline walking.

### 2.2 PIA24836 — Kodiak Butte (Delta Remnant)
- **Geologic Context:** Isolated erosional remnant displaying distinct Gilbert-type deltaic architecture: top-set, steeply dipping fore-set, and bottom-set sandstone beds.
- **Terramechanics:** Flank slopes exceed $18^\circ\text{--}25^\circ$, far surpassing suited human walking limits ($14.0^\circ$). Serves as a prominent visual orientation beacon visible across $>15\text{ km}$.

### 2.3 PIA25439 — Hawksbill Gap (Delta Front Scarp)
- **Geologic Context:** Layered, fine-grained mudstones deposited in quiet lacustrine delta waters. Sample extraction site for ancient biosignatures (Amalik core).
- **Terramechanics:** Moderately steep stepped scarps ($6^\circ\text{--}11^\circ$). Stepped bedding provides natural human climbing terraces and overhangs for radiation sheltering.

### 2.4 PIA24839 — South Séítah (Layered Igneous Terrain)
- **Geologic Context:** Heavily fractured olivine cumulate bedrock interspersed with active aeolian sand dunes and coarse megaripples.
- **Terramechanics:** High-risk terrain. Loose dune slip (thermal inertia $\approx 190\text{ tiu}$) causes severe boot sinkage ($>5\text{ cm}$) and high metabolic exertion; inter-dune swales offer radiation shielding.

### 2.5 PIA25828 — Belva Impact Crater (Catastrophic Outflow Escarpment)
- **Geologic Context:** 0.9-kilometer-wide impact crater excavating deep delta strata, revealing boulder-rich catastrophic flood conglomerates with meter-scale rounded boulders.
- **Terramechanics:** Steep vertical wall exposures ($>30^\circ$); designated primary topographic radiation shelter providing up to 68% overhead proton flux attenuation.

---

## 3. Endpoints & UI Integration

- **Backend Route:** `GET /api/v1/routes/surface-imagery` (supports spatial filtering with `?lat=...&lon=...&max_distance_m=...`)
- **Backend Individual:** `GET /api/v1/routes/surface-imagery/{landmark_id}`
- **Frontend Component:** `mission-ui/src/SurfacePovViewer.jsx`
- **Data Catalogue:** `mission-ui/src/surface_imagery.js` & `backend/app/data/surface_imagery.py`
