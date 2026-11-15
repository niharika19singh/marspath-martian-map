# MARSPath RF Line-of-Sight & Relay Shadow Analysis

## 1. Overview & Operational Principles

Astronaut surface traverses in Jezero Crater rely on two complementary RF communication architectures:
1. **Direct Habitat-to-Astronaut Link:** High-frequency line-of-sight (UHF/microwave) communication directly between the Base Habitat antenna mast and the astronaut's suit transceiver.
2. **Proximity-1 Orbital Relay Constellation:** UHF communication to overhead orbiters, relaying telemetry and voice packets through NASA's Deep Space Network (DSN) to mission control.

Topographic relief—specifically crater rims, steep delta scarps ($> 60\text{ m}$ drops), and ejecta ridges—creates **RF communication shadows** where direct line-of-sight is lost.

---

## 2. Line-of-Sight Geometry on the Martian Spheroid

Due to Mars's smaller radius ($R_{\text{Mars}} = 3,396,190\text{ m}$ vs $R_{\oplus} = 6,371,000\text{ m}$), the geometric distance to the horizon is significantly shorter than on Earth:

$$d_{\text{horizon}} = \sqrt{2 R_{\text{Mars}} h + h^2} \approx 2.6 \sqrt{h\ [\text{meters}]} \quad [\text{km}]$$

For an astronaut ($h_{\text{suit}} = 2.0\text{ m}$) communicating with a habitat mast ($h_{\text{mast}} = 10.0\text{ m}$):
- Theoretical flat-terrain geometric radio horizon: $d \approx 2.6(\sqrt{2} + \sqrt{10}) \approx 2.6(1.414 + 3.162) \approx 11.9\text{ km}$.
- In rugged crater terrain, terrain obstacles (delta scarps, basalt ridges) occlude the link at much shorter distances ($< 3.0\text{ km}$).

When the direct path from habitat base to astronaut is obstructed by topography, the link status is classified as:
- **`CONNECTED`:** Direct unobstructed line-of-sight.
- **`POTENTIAL_OBSTRUCTION`:** Traverse is shielded by crater topography or high local slopes ($> 10^\circ$).
- **`CONFIRMED_BLACKOUT`:** Confirmed shadow where both direct habitat LOS and active orbiter passes are unavailable.

---

## 3. Verified Mars Relay Constellation Fleet

MARSPath tracks 5 verified Mars orbiters with operational proximity UHF relay payloads:

| Spacecraft | Relay Payload | Frequency Band | Orbital Inclination | Operational Altitude | Primary Pass Period |
|---|---|---|---|---|---|
| **Mars Reconnaissance Orbiter (MRO)** | Electra Software Defined Radio | UHF 390–450 MHz (Proximity-1) | $92.8^\circ$ (Sun-synchronous polar) | 290 km | ~1.87 hours |
| **ExoMars Trace Gas Orbiter (TGO)** | Dual Redundant Electra Transponders | UHF 390–450 MHz | $74.0^\circ$ | 400 km | ~2.0 hours |
| **2001 Mars Odyssey** | CE-505 UHF Relay Subsystem | UHF 401.58 MHz | $93.1^\circ$ | 400 km | ~2.0 hours |
| **MAVEN** | Electra UHF Transponder | UHF 401.58 MHz | $75.0^\circ$ | 150–6,000 km | ~4.5 hours |
| **Mars Express (MEX)** | Melcom UHF Relay Link | UHF 401.5 MHz | $86.3^\circ$ | 300–10,000 km | ~6.7 hours |

An orbiter is considered available for proximity contact when its elevation angle over Jezero Crater exceeds the terrain horizon elevation mask ($\theta_{\text{elev}} \ge 10.0^\circ$).
