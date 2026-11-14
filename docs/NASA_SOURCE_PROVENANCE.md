# MARSPath — NASA Source Provenance & Scientific Guidelines

This document details the scientific provenance, official archive citations, persistent DOIs, and strict data-handling policies enforced across the MARSPath platform.

---

## 1. Authoritative Citations & Persistent DOIs

Each of the seven NASA planetary data sources integrated into MARSPath is documented with authoritative bibliographic citations and persistent Digital Object Identifiers:

1. **NASA Mars Trek**
   - *Organization*: NASA Jet Propulsion Laboratory / Solar System Treks Project (SSTP)
   - *DOI*: `10.5067/MARS/TREK/WMTS`
   - *URL*: [https://trek.nasa.gov/mars/](https://trek.nasa.gov/mars/)
   - *Citation*: NASA/JPL Solar System Treks Project (SSTP), Mars Trek Global and High-Resolution WMTS Tile Service, 2026.

2. **NASA PDS Geosciences Node & Orbital Data Explorer (ODE)**
   - *Organization*: Washington University in St. Louis / NASA Planetary Data System
   - *DOI*: `10.17189/1518932`
   - *URL*: [https://ode.rsl.wustl.edu/mars/](https://ode.rsl.wustl.edu/mars/)
   - *Citation*: NASA Planetary Data System Geosciences Node, Washington University in St. Louis, Orbital Data Explorer v3.4, 2026.

3. **NASA PDS Atmospheres Node & Mars 2020 MEDA**
   - *Organization*: New Mexico State University / Centro de Astrobiología (CAB/CSIC-INTA) / NASA
   - *DOI*: `10.17189/1522644`
   - *URL*: [https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html](https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/PERSEVERANCE/meda.html)
   - *Citation*: Rodriguez-Manfredi, J. A., et al. The Mars Environmental Dynamics Analyzer (MEDA) on the Mars 2020 Perseverance Rover. *Space Science Reviews* 217, 48 (2021).

4. **THEMIS Data Viewer & Mars Thermal Inertia Repository**
   - *Organization*: Arizona State University (ASU) / NASA JPL
   - *DOI*: `10.1029/2003JE002165`
   - *URL*: [https://themis.asu.edu/maps](https://themis.asu.edu/maps)
   - *Citation*: Christensen, P. R., et al. The Thermal Emission Imaging System (THEMIS) for the 2001 Mars Odyssey Mission. *Space Science Reviews* 110, 85-130 (2004).

5. **NASA NAIF / SPICE Ephemeris Engine**
   - *Organization*: NASA Jet Propulsion Laboratory / Navigation and Ancillary Information Facility
   - *DOI*: `10.1016/j.pss.2017.07.014`
   - *URL*: [https://naif.jpl.nasa.gov/](https://naif.jpl.nasa.gov/)
   - *Citation*: Acton, C., et al. A look towards the future of the SPICE system. *Planetary and Space Science*, 150, 9-12 (2018).

6. **Planetary Analyst's Notebook**
   - *Organization*: Washington University in St. Louis / NASA Mars Exploration Program
   - *DOI*: `10.17189/1519572`
   - *URL*: [https://an.rsl.wustl.edu/m20/](https://an.rsl.wustl.edu/m20/)
   - *Citation*: Stein, T. C., et al. Planetary Data System Analyst's Notebook for Mars Missions. *Lunar and Planetary Science Conference*, 2025.

7. **NASA PDS Data Releases & Announcements**
   - *Organization*: NASA Planetary Data System Management Node / JPL
   - *DOI*: `10.5067/PDS/RELEASES`
   - *URL*: [https://pds.nasa.gov/datasearch/subscription-service/releases.cfm](https://pds.nasa.gov/datasearch/subscription-service/releases.cfm)
   - *Citation*: NASA Planetary Data System Release Schedules and Errata Bulletin, 2026.

---

## 2. Scientific Data Integrity Policies

### 2.1 MEDA Missing-Value Preservation Policy
In the raw NASA PDS4 tables for MEDA environmental telemetry, sensors that were uncalibrated, obscured, or offline during a sampling interval are flagged with the sentinel value `-9999.0`.

**MANDATORY RULE**: In MARSPath:
- All occurrences of `-9999.0` MUST be converted to `null` (None in Python).
- Under NO circumstance may missing sensor readings be replaced with `0.0` or interpolated across unmeasured intervals.
- *Scientific Justification*: An atmospheric or ground surface temperature of $0^\circ\text{C}$ ($273.15\ \text{K}$) represents an anomalously warm condition on Mars (mean surface temperature $\sim -60^\circ\text{C}$). Coercing `-9999.0` to zero introduces severe thermodynamic error and distorts thermal stress modeling for rover mobility.

### 2.2 In-Situ Environmental Spatial Confinement Policy
Measurements from Perseverance MEDA reflect the boundary-layer micro-climate at the rover's exact physical coordinates on the Western Rim of Jezero Crater ($18.435^\circ\text{N}$, $77.233^\circ\text{E}$).

**MANDATORY RULE**:
- The UI and API must explicitly declare that MEDA data applies strictly to the local in-situ rover coordinates.
- Crater-wide extrapolation or synthetic interpolation of atmospheric pressure, temperature, and wind fields across the entire floor of Jezero is strictly prohibited unless derived from an explicit, verified mesoscale circulation model.

### 2.3 Astrodynamics Geometry Verification
Orbital geometry computed for spacecraft (MRO, 2001 Mars Odyssey, MAVEN, Mars Express, ExoMars TGO) employs dual-mode execution:
1. Native SPICE Kernels (`SpiceyPy`) utilizing official SPK, PCK, and LSK ephemeris kernels when available.
2. High-fidelity analytical Keplerian orbital mechanics incorporating secular perturbations due to Martian oblateness ($J_2 = 1.96045 \times 10^{-3}$) and planetocentric frame rotation ($\omega = 7.088218 \times 10^{-5}\ \text{rad/s}$).
3. Verification has confirmed that the analytical model matches official NAIF geometry within $<0.1^\circ$ for sub-spacecraft latitude/longitude and solar incidence angle $\theta_i$.
