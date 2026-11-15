# MARSPath Astronaut Walk-Back Safety Model

## 1. Executive Summary & Objective

In human Mars surface operations, vehicular mobility failure (e.g. pressurized rover power failure, wheel actuator motor seizure, or excessive slip immobilization) creates an acute survival crisis. The crew must be able to return to their habitat base entirely on foot using life-support resources contained within their Extravehicular Mobility Units (xEMU).

MARSPath implements a rigorous **Dual-Radius Safety Envelope** system:
- **Envelope A: Rover-Assisted Range:** Represents the nominal mission operations area under vehicle mobility constraints.
- **Envelope B: On-Foot Walk-Back Range:** Represents the area from which astronauts can safely return to habitat base on foot within emergency life-support ceilings.

Crucially, **neither envelope is an arbitrary circle**. Both are derived deterministically using backward-Dijkstra reachability sweeps over the underlying high-resolution Mars Digital Elevation Model (DEM).

---

## 2. Mathematical Mobility Formulations

### 2.1 Vehicle Mobility Profile (Envelope A)
- **Chassis:** Pressurized Exploration Vehicle (PEV) with high-compliance metallic spring wheels.
- **Velocity ($v_{\text{rover}}$):** Nominal traversing speed $2.7778\text{ m/s} = 10.0\text{ km/h}$.
- **Drivable Slope Cutoff ($\theta_{\text{max, rover}}$):** $14.0^\circ$ (exceeding this angle creates severe wheel spin and rollovers).
- **Time Budget ($T_{\text{mission}}$):** Full nominal EVA budget (e.g. $8.0\text{ hours} = 28,800\text{ s}$).
- **Map Representation:** Translucent cyan overlay (`#00d2ff`, `rgba(0, 210, 255, 0.22)`).

### 2.2 Suited Pedestrian Mobility Profile (Envelope B)
- **Suit Profile:** Exploration Extravehicular Mobility Unit (xEMU) with pressurized joint impedance ($P_{\text{suit}} \approx 29.6\text{ kPa}$).
- **Nominal Pedestrian Velocity ($v_0$):** $1.1111\text{ m/s} = 4.0\text{ km/h}$.
- **Slope Traversability Cutoff ($\theta_{\text{max, walk}}$):** $20.0^\circ$.
- **Emergency Life-Support Walk Budget ($T_{\text{walk, max}}$):** Configured emergency walk-back limit (default $3.5\text{ hours} = 12,600\text{ s}$, providing a mandatory emergency oxygen and battery buffer).
- **Map Representation:** Translucent green overlay (`#00e676`, `rgba(0, 230, 118, 0.24)`).

### 2.3 Energetic Grade & Velocity Penalty
Walking on Martian terrain ($g_{\text{Mars}} = 3.72\text{ m/s}^2 \approx 0.38g_\oplus$) under suited load is governed by the Minetti metabolic cost equation adjusted for planetary gravity:

$$W_{\text{walk}}(i) = 280.5 i^5 - 58.7 i^4 - 289.2 i^3 + 74.5 i^2 + 19.1 i + 3.55 \quad [\text{J}/(\text{kg}\cdot\text{m})]$$

where $i = \tan(\theta) = \frac{\Delta z}{d_{\text{2D}}}$ is the signed incline grade.

On positive inclines (uphill), suited traversing speed decreases exponentially:

$$v_{\text{walk}}(i) = v_0 \cdot \exp\left(-3.5 \cdot \max(0, i)\right) \cdot \left(1.0 - 0.15 \cdot \min(1.0, \text{TRI})\right)$$

where $\text{TRI}$ is the Terrain Ruggedness Index. A conservative $15\%$ fatigue multiplier is compounded into step durations.

---

## 3. Backward-Dijkstra Reachability Solver

To calculate the envelope from habitat base node $h = (r_h, c_h)$, reverse-edge Dijkstra sweeps through the cropped DEM grid:
1. Initialize travel time grid $T(u) = \infty$ for all cells, with $T(h) = 0.0$.
2. For each settled cell $u$ with known return time $T(u)$, examine incoming neighbor $v \to u$.
3. Directional elevation step: $\Delta z_{v \to u} = z(u) - z(v)$.
4. Effective step time $\Delta t_{v \to u} = \frac{d_{\text{3D}}(v, u)}{v_{\text{walk}}(i_{v \to u})} \cdot \mu_{\text{fatigue}}$.
5. If $T(u) + \Delta t_{v \to u} < T(v)$, update $T(v)$ and push to priority queue.
6. Untraversable cells (slopes $> \theta_{\text{max}}$ or NoData) remain $\infty$ and are strictly excluded.

The reachability masks are defined by:
- $\text{Mask}_{\text{rover}} = \{ (r, c) \mid T_{\text{rover}}(r, c) \le T_{\text{rover, max}} \}$
- $\text{Mask}_{\text{walk}} = \{ (r, c) \mid T_{\text{walk}}(r, c) \le T_{\text{walk, max}} \}$

---

## 4. Feasibility Status Classifications

When a mission destination or route alternative is evaluated:
1. **SAFE WITHIN CONFIGURED LIMIT:**
   - Walk-back duration $T_{\text{walk}} \le 2.5\text{h}$.
   - Emergency resource reserve margin $\ge 30\%$.
   - Terrain difficulty MILD or MODERATE.
2. **LIMITED MARGIN:**
   - Walk-back duration $2.5\text{h} < T_{\text{walk}} \le 3.5\text{h}$, or emergency reserve margin between $10\%$ and $30\%$.
   - Advisory issued: crew must monitor metabolic pacing and avoid steep ascents.
3. **WALK-BACK LIMIT EXCEEDED:**
   - Walk-back duration $T_{\text{walk}} > 3.5\text{h}$ or destination not reachable on foot within emergency budget.
   - Prominent Warning: `"DESTINATION EXCEEDS CONFIGURED ON-FOOT WALK-BACK LIMIT."`
4. **DATA UNAVAILABLE:**
   - If destination or corridor falls outside valid DEM bounds or contains NoData rasters.
