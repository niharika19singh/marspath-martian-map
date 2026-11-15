# MARSPath — 3 Priority Features Implementation Specification

**Sprint:** 3 Priority Features Implementation Sprint  
**Branch:** `feature/fast-astronaut-survival-upgrades`  
**Target:** MARSPath Jezero Crater Astronaut Survivability & Mission Planning Platform  
**Target Completion:** November 15, 2026 — 11:59 PM IST  
**Status:** COMPLETE & VERIFIED  

---

## 1. Feature 1: Astronaut Suit HUD Mode + Web Speech API Hazard Alerts

### 1.1 Objective & Architectural Pattern
Transforms the standard planetary GIS interface into a high-contrast astronaut visor / field-tablet overlay without blocking interactive map navigation, coordinate placement, or routing inspection.

### 1.2 Component Structure: `SuitHudOverlay.jsx` & `audio_alerts.js`
- **Single Mode Toggle:** Accessible via primary Mission Control header (`btn-suit-hud-toggle`) as `Suit HUD`.
- **Floating Field HUD:** Anchored at the top of the viewport with semi-transparent glassmorphic styling (`rgba(9, 14, 20, 0.92)` with `backdrop-filter: blur(16px)` and subtle emerald border glow).
- **Displayed Telemetry Metrics:**
  1. **Suit Oxygen:** $O_2$ remaining percentage (`simulatedO2Pct%`) with `[SIMULATED]` analog badge and dynamic color tiering (green $\ge 25\%$, critical red $< 25\%$).
  2. **Suit Battery:** Remaining percentage (`simulatedBatteryPct%`) with `[SIMULATED]` analog badge representing thermal and $CO_2$ scrubber life-support electrical loads.
  3. **Mission Elapsed Time (MET):** Live formatted timer (`HH:MM:SS`) tracking elapsed traverse time on Sol 2026.
  4. **Current Route Hazard Level:** Dynamic hazard indicator (`NOMINAL`, `MODERATE HAZARD`, `CRITICAL HAZARD`) reflecting corridor slope gradients and geofence proximity.
  5. **Distance Remaining:** Outbound transit distance formatted in meters or kilometers.
  6. **Estimated Return Time:** Derived from on-foot walk-back Dijkstra model with emergency resource margin percentage.
  7. **Mission Safety Status:** Prominent status badge (`GO FOR EVA`, `CAUTION — RESTRICTED`, `ABORT / REROUTE MANDATORY`).

### 1.3 Web Speech API Audio Hazard Alerts
Implemented in `audio_alerts.js` using browser-native `window.speechSynthesis` and `SpeechSynthesisUtterance`:
- **Audio Enable/Disable Control:** Visible toggle in HUD header (`🔊 AUDIO ALERTS ON` / `🔇 AUDIO ALERTS OFF`), defaults to muted to respect user-gesture requirements.
- **Deduplication Cooldown:** Identical alert keys enforce a 15-second cooldown period, preventing repetitive audio loops.
- **Severity-Based Utterances:**
  - *Terrain Hazard:* `"Terrain hazard detected ahead. Steep corridor gradient."`
  - *Return Ceiling Exceeded:* `"Return safety limit exceeded. Reconsider the route."`
  - *Suit Consumables Low:* `"Simulated suit oxygen reserve is low."` / `"Simulated suit battery reserve is low."`
  - *Planetary Protection Breach:* `"Planetary protection restricted buffer breached. Human ingress prohibited."`
  - *Solar Storm Event:* `"Solar storm radiation spike. Seek topographic shelter."`
- **Graceful Fallbacks:** If speech synthesis is unsupported or muted, the HUD displays a visible, high-contrast animated alert ticker with corresponding severity styling.

---

## 2. Feature 2: Marswalk Survivability Score + Solar Storm Scenario

### 2.1 Transparent 5-Factor Weighted Formula
Derives a 0–100 decision-support index grounded in human terramechanics and NASA analog traverse models:

$$\text{Score} = 100 \times \Big( 0.25 \cdot \text{SlopeSafety} + 0.25 \cdot \text{TerrainSafety} + 0.20 \cdot \text{TimeSafety} + 0.20 \cdot \text{ReturnSafety} + 0.10 \cdot \text{DistanceSafety} \Big)$$

All 5 factors are normalized strictly to $[0.0, 1.0]$:

| Factor | Weight | Normalization Formula | Physical / Operational Assumption |
| :--- | :---: | :--- | :--- |
| **SlopeSafety** | $25\%$ | $\max(0, \min(1, 1 - \frac{\max(0, \theta_{\text{slope}} - 1.5)}{12.5}))$ | $14.0^\circ$ maximum suited astronaut walking limit; metabolic workload scales non-linearly above $6^\circ$. |
| **TerrainSafety** | $25\%$ | $\max(0, \min(1, 1 - \frac{\max(0, \text{TRI} - 0.10)}{0.50}))$ | Sub-meter basalt blockiness and tripping hazard; nominal baseline $\le 0.10\text{ m}$. |
| **TimeSafety** | $20\%$ | $\max(0, \min(1, 1 - \frac{T_{\text{traverse}}}{T_{\text{budget}}}))$ | Transit duration consumed relative to configured $8.0\text{h}$ life-support budget. |
| **ReturnSafety** | $20\%$ | $\max(0, \min(1, \frac{\text{Margin}_{\text{pct}}}{100.0}))$ | Emergency on-foot return margin derived from backward-Dijkstra walk-back model ($\le 3.5\text{h}$). |
| **DistanceSafety** | $10\%$ | $\max(0, \min(1, 1 - \frac{D_{\text{km}}}{5.0}))$ | Radial distance relative to $5.0\text{ km}$ nominal autonomous pedestrian corridor. |

### 2.2 Score Interpretation Tiers
- **80–100:** *Higher modeled survivability* (Green `#00e676`) — Nominal traverse conditions, minimal metabolic exertion, ample return margin.
- **60–79:** *Moderate modeled survivability* (Lime `#a3e635`) — Acceptable corridors requiring pace monitoring.
- **40–59:** *Elevated modeled risk* (Amber `#f59e0b`) — Elevated terrain slope, roughness, or tight return margins.
- **0–39:** *Low modeled survivability* (Red `#ef4444`) — Severe exertion, return ceiling breach, or acute environmental hazard.

### 2.3 Solar Storm Scenario Toggle (`Solar Storm Scenario — OFF / ON`)
- **Prominent Banner:** Displays simulated solar-storm alert:
  `[SIMULATED SCENARIO ONLY — NASA ANALOG DRILL] SOLAR PARTICLE EVENT (SPE CLASS X2.5) ACTIVE`
- **Acute Radiation Flux Modeling:** Injects an unshielded radiation penalty ($-28.0\text{ pts}$ based on $\sim 48.5\text{ mSv/h}$ acute proton flux).
- **Topographic Shelter Proximity Mitigation:** Corridors within $1,200\text{ m}$ of designated Jezero natural shelters (Western Rim Overhang, Belva Terraces, Séítah Swale) receive up to $+16.0\text{ pts}$ shielding bonus.
- **Return Envelope Tightening:** Derates the safe-return emergency limit by **$30\%$** (from $3.5\text{h}$ to $2.45\text{h}$) and reduces the safe turnaround buffer.
- **Dynamic Interaction:** State updates occur instantly without page reloads, adjusting scores and visual alerts in real time.

---

## 3. Feature 3: Planetary Protection Geofence + Perseverance POV Images

### 3.1 Robot-Only Buffer Layer: `Planetary Protection — Robot-Only Buffer`
Integrated as an independent layer toggle on the map and layer manager, rendering distinct boundaries according to authoritative COSPAR/NASA policy:
- **Official Restricted Zone (Red Solid `#ef4444`):** Western Delta Scarp Deep Aquifer Outflow (CRISM FRT00003E12 / HiRISE ESP_036618_1985). Strictly bars human crew routing (`human_route_approved: false`).
- **Candidate Sensitive Area (Amber Solid `#f59e0b`):** Séítah Inter-Dune Carbonate Outcrop (CRISM HRL000040FF / SHERLOC Sol 240). Requires advance bio-barrier assessment.
- **Demonstration Scenario (Purple Dashed `#a855f7`):** Belva Crater Southern Rim Drill Scenario.
- **Floating Map Legend:** Displays exact color swatches, boundary stroke styles, and provenance policy note (*"Authoritative CRISM/HiRISE hydration provenance · NASA NPR 8020.12D"*).
- **Route Breach Alert Banner & Highlighting:** When a planned route intersects a buffer, the breached segment is highlighted in bold red dashed line (`#ef4444dd`, width 6, dash [8, 6]), and a prominent map banner advises selecting an alternative route.

### 3.2 Authentic NASA Perseverance Waypoint Surface POV Imagery
Embedded within the map inspection flow via `WaypointPovPopup.jsx`:
- **Authoritative Provenance:** Sourced from NASA JPL / Caltech Planetary Data System (PDS) Photojournal. Zero synthetic or AI-generated imagery.
- **Contextual Matching (`getContextualRoverImage`):** Resolves images matching either the waypoint Sol or closest geographic rover position:
  1. *Sol 1:* Octavia E. Butler Landing (`PIA24487`, Mastcam-Z 360° Panorama).
  2. *Sol 64:* Kodiak Butte Delta Remnant (`PIA24836`, Mastcam-Z 110mm Telephoto).
  3. *Sol 200:* South Séítah Layered Bedrock (`PIA24839`, Mastcam-Z & Navcam).
  4. *Sol 412:* Hawksbill Gap Delta Scarp (`PIA25439`, Mastcam-Z Multi-Filter).
  5. *Sol 802:* Belva Impact Crater Escarpment (`PIA25828`, Mastcam-Z Super-Mosaic).
- **Metadata Display:** Image ID, Instrument Camera, Acquisition Sol, Official NASA Photojournal link, and Attribution (`NASA/JPL-Caltech/ASU/MSSS`).
- **Resilience:** Includes loading spinner, `onError` image fallback, and mobile-friendly responsive layout.
