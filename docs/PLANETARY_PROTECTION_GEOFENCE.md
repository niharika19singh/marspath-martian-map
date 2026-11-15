# MARSPath Planetary Protection Geofencing & Scout Reconnaissance

## 1. Regulatory Context & Zero-Fabrication Mandate

Planetary Protection protocols are established by the Committee on Space Research (COSPAR) and formalized by NASA in **NPR 8020.12D** (*Planetary Protection Provisions for Robotic Extraterrestrial Missions*) and NASA Policy Directive **NPD 8020.7**.

A **Martian Special Region** is defined as an environment where terrestrial organisms could replicate, or that has a high potential for the existence of extant Martian life. Specifically, regions meeting:
1. Temperature $T \ge -28^\circ\text{C}$ (245 K), and
2. Water activity $a_w \ge 0.5$.

MARSPath enforces strict scientific integrity:
- **Zero Fabrication:** An unverified spectral absorption hotspot is **never** presented as an officially designated Special Region.
- Clear categorization between authoritative restricted zones, scientific candidate areas, and simulation training drills.

---

## 2. Categorization of Geofenced Zones

| Category | Boundary Appearance | Authoritative Provenance | Human Access Policy | Robotic Scout Eligibility |
|---|---|---|---|---|
| **Official Restricted Zone** | Solid Red (`#ef4444`) with translucent fill | Verified COSPAR Category IVc candidate from PDS/CRISM (FRT00003E12) & HiRISE (ESP_036618_1985) | `STRICTLY_PROHIBITED` — Hard block; human route approval rejected | Yes — Authorized for sterilized robotic platforms |
| **Candidate Sensitive Region** | Solid Amber (`#f59e0b`) with translucent fill | Scientific candidate (CRISM HRL000040FF / SHERLOC Sol 240) showing Mg-carbonates & hydrated sulfates | `ASSESSMENT_REQUIRED` — Advisory warnings issued; standoff survey advised | Yes — Scout survey strongly recommended prior to approach |
| **Demonstration Scenario** | Dashed Purple (`#a855f7`) with translucent fill | Explicit hypothetical training drill (`SIM_SCENARIO_2026_BELVA_03`) for mission planning exercises | `SIMULATED_EXERCISE` — Procedural training; exercises avoidance & dispatch workflows | Yes — Full simulated reconnaissance sortie available |

---

## 3. Active Special Regions in Jezero Crater

### 3.1 Western Delta Scarp Potential Deep Aquifer Outflow (`ppz_jezero_delta_aquifer`)
- **Classification:** `official_restricted_zone`
- **Location:** Western Delta scarp ($77.428^\circ\text{E} \text{ to } 77.445^\circ\text{E}$, $18.450^\circ\text{N} \text{ to } 18.462^\circ\text{N}$).
- **Detection Dataset:** CRISM Targeted Observation `FRT00003E12` (18.2 m/px) & HiRISE `ESP_036618_1985` (0.25 m/px).
- **Astrobiological Risk:** Thick smectite clay layers with high biomarker preservation potential. Ingress by human crew with non-sterile life-support systems poses severe risk of irreversible forward biological contamination.
- **Enforcement Rule:** If an astronaut route intersects or terminates inside this zone, `human_route_approved` is deterministically forced to `False`.

### 3.2 Séítah Inter-Dune Carbonate & Hydrated Mineral Exposure (`ppz_seitah_carbonate_rsl`)
- **Classification:** `candidate_sensitive_region`
- **Location:** South Séítah aeolian corridor ($77.438^\circ\text{E} \text{ to } 77.455^\circ\text{E}$, $18.428^\circ\text{N} \text{ to } 18.439^\circ\text{N}$).
- **Detection Dataset:** CRISM `HRL000040FF` (36.4 m/px) & Perseverance SHERLOC Raman Sol 240 survey.
- **Astrobiological Status:** Displays $2.3\ \mu\text{m}$ and $2.5\ \mu\text{m}$ absorption bands indicative of hydrous alteration. It is NOT an officially designated Special Region because active water activity has not been experimentally confirmed in-situ.

### 3.3 Belva Crater Southern Rim Demonstration Standoff Zone (`ppz_belva_rim_ice_demo`)
- **Classification:** `demonstration_scenario`
- **Location:** Southern rim of Belva impact structure ($77.475^\circ\text{E} \text{ to } 77.498^\circ\text{E}$, $18.398^\circ\text{N} \text{ to } 18.412^\circ\text{N}$).
- **Rationale:** Synthetic training fixture exercising rapid handoff from human traverse planning to robotic standoff reconnaissance.

---

## 4. LineString Route Intersection Algorithm

Route LineStrings $\mathcal{L} = \{ P_0, P_1, \dots, P_m \}$ are checked against each zone polygon $\mathcal{P} = \{ V_0, V_1, \dots, V_k \}$:
1. **Point Containment:** Ray-casting algorithm checks whether each waypoint $P_i$ falls within polygon $\mathcal{P}$.
2. **Segment Edge Piercing:** For each consecutive waypoint segment $(P_i, P_{i+1})$, intersection with each polygon boundary segment $(V_j, V_{j+1})$ is evaluated using counter-clockwise orientation checks.
3. **Traverse Length Calculation:** Great-circle distances along pierced segments inside the polygon are summed on the Mars spheroid ($R_{\text{Mars}} = 3,396,190\text{ m}$).
4. **Policy Enforcement:**
   - If any intersected zone has classification `official_restricted_zone`:
     - `human_route_approved = False`
     - Policy violation added: `CRITICAL PLANETARY PROTECTION VIOLATION: Route intersects officially restricted Special Region... Reroute mandatory.`
     - Intersected segments highlighted on map in warning red.
   - If candidate sensitive regions are intersected:
     - `human_route_approved = True` (unless official violation present)
     - Advisory warning added; Scout Rover dispatch recommended.

---

## 5. Simulated Scout Rover Reconnaissance Handoff

When a special region is encountered or selected, flight controllers can execute:
`DISPATCH SCOUT ROVER RECONNAISSANCE`

This generates a simulated robotic scout reconnaissance sortie:
- **Platform:** Ingenuity-Class Aerial Scout / Sample Fetch Micro-Rover.
- **Bio-Cleanliness Level:** Planetary Protection Category IVb Post-Bakeout ($< 300\text{ spores/m}^2$).
- **Instrument Suite:** Alpha Particle X-Ray Spectrometer (APXS), Raman Bio-Signature Spectrometer, Microscopic Imager.
- **Mandatory Disclaimer:** *"MOCK MISSION SIMULATION ONLY. This conceptual reconnaissance request generates simulated robotic scout telemetry and does not interface with active NASA spacecraft operations."*
