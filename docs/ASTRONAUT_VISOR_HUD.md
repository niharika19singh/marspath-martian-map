# Astronaut Visor HUD & Field Tablet Mode (AVH-01)

**Subsystem:** Human-Centered Field Navigation Display & Telemetry Overlay  
**Design Standard:** High-Contrast Tactical Martian Dark Glass (`#08120e`), Sub-second React 19 State Propagation, Apollo/Artemis EVA Analog Architecture.

---

## 1. Overview & Purpose

The **Astronaut Visor HUD** transforms the MARSPath desktop geospatial interface into a tactical, high-contrast, field-operable navigation HUD suitable for heads-up visor projection or ruggedized forearm field tablets during dismounted Martian EVAs.

```
+-----------------------------------------------------------------------------------------+
| [🥽 ASTRONAUT FIELD VISOR HUD]       ▼ 284° M-TRUE (WNW)        [⚡ SIMULATE SPE] [✕ EXIT] |
| EVA-01 · PERSEVERANCE SCOUT      BEARING: 284° · TARGET: Séítah Swale                     |
+-----------------------------------------------------------------------------------------+
|  PLSS CONSUMABLES (SIM)  |    MARSWALK SURVIVABILITY    |  TRAVERSE & ENVIRONMENT       |
|  O₂ Reserve: 6.2h (78%)  |             [ 85 ]           |  Distance: 1.42 km            |
|  ==================[   ] |             / 100            |  Walk Time: 51 min            |
|  Battery: 86%            |           OPTIMAL            |  Max Slope: 4.2° (14° ceiling)|
|  ====================[ ] |                              |  Atmosphere: 756.4 Pa / -29°C  |
|  Metabolic: 310 Watts    |  - Slope Exertion: 0 pts     |  Comms: Direct LOS Nominal    |
|  Turnaround: +120m buffer|  - TRI Ruggedness: 0 pts     |                               |
|                          |  - Consumables: 0 pts        |  TOPOGRAPHIC SHELTER:         |
|  ⚠️ Simulated parameters |  - Radiation Flux: Nominal   |  - Séítah Swale: 638m (55% att)|
+-----------------------------------------------------------------------------------------+
```

---

## 2. Key Interface Modules

### 2.1 Central Gyro-Stabilized Heading Tape
- **Target Bearing Angle:** Continuously computed from current astronaut coordinates to selected waypoint or science destination:
  $$\beta = \operatorname{atan2}\left(\sin(\Delta\lambda)\cos(\phi_2), \cos(\phi_1)\sin(\phi_2) - \sin(\phi_1)\cos(\phi_2)\cos(\Delta\lambda)\right)$$
- **Tape Markers:** 360° compass strip with cardinal points (`N`, `NE`, `E`, `SE`, `S`, `SW`, `W`, `NW`) smoothly clamped within a $\pm 70^\circ$ peripheral FOV.

### 2.2 Simulated PLSS Consumables Stack
Provides real-time metabolic and life support feedback (explicitly badged with `SIMULATED ASSUMPTIONS` to preserve scientific integrity):
- **O₂ Reserve Percentage & Remaining Hours:** Scaled from an assumed 8.0-hour primary PLSS tank under Minetti human grade scaling.
- **Suit Battery Reserve:** Models electrical heating and lithium-hydroxide (LiOH) $\text{CO}_2$ scrubbing power drain.
- **Metabolic Exertion Rate (Watts):** Dynamically computed as $W = 280 + \max(0, \theta - 2)^{1.6} \times 22\text{ W}$.
- **Sunset Abort Margin:** Real-time countdown to local solar dusk using high-precision Allison & McEwen (2000) Mars24 ephemeris.

### 2.3 Central Marswalk Survivability Index
- Prominent 140px circular glowing gauge displaying composite score (0–100) and operational category (`OPTIMAL`, `GOOD`, `MODERATE`, `MARGINAL`, `CRITICAL`).
- Contributing penalty breakdown itemizing points deducted for slope, roughness, life support, regolith sinkage, and radiation flux.
- Topographic shelter proximity bonus awarded when operating near natural cliff overhangs.

### 2.4 Companion Rover Assistance Protocol
When corridor slope exceeds $9.0^\circ$ or surface roughness exceeds $0.5\text{ m}$, the HUD automatically trips a tactical warning:
> **COMPANION ROVER ASSIST RECOMMENDED:** Terrain slope ($11.2^\circ$) exceeds solo walking comfort. Request Perseverance forward scout or winch assist line.

---

## 3. Operational Activation

1. **Header Action:** Click `🥽 VISOR HUD` in the top Mission Control bar.
2. **Keyboard Shortcut:** Open Command Palette (`Ctrl+K`) $\to$ type `Astronaut Visor HUD` $\to$ `Enter`.
3. **Route Candidate HUD:** Click `🥽 Visor HUD` on any candidate corridor card.
4. **Exit Visor:** Click `✕ EXIT VISOR` to return seamlessly to standard mission planning view.
