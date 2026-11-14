# Mars Orbital Tracking & Astrodynamics Implementation

## 1. Mathematical Formulation

The orbital tracking engine calculates deterministic ephemeris positions and ground tracks for active Mars orbiters without requiring third-party C/Fortran SPICE libraries at runtime. The propagator incorporates two-body Keplerian dynamics with first-order secular perturbations caused by the Martian gravitational quadrupole moment ($J_2$).

### 1.1 Mars Physical & Gravitational Constants

- Gravitational Parameter: $\mu_{\text{Mars}} = 42,828.375214\text{ km}^3/\text{s}^2$
- Equatorial Radius: $R_{\text{eq}} = 3,396.19\text{ km}$
- Polar Radius: $R_{\text{pol}} = 3,376.20\text{ km}$
- Gravitational Zonal Harmonic: $J_2 = 1.96045 \times 10^{-3}$
- Mars Sideral Rotation Rate: $\omega_{\text{Mars}} = 7.088218 \times 10^{-5}\text{ rad/s}$ ($24^{\text{h}} 37^{\text{m}} 22.66^{\text{s}}$ per solar day / Sol)
- Prime Meridian Reference Epoch: J2000.0 (2000-01-01T12:00:00 UTC)
- Prime Meridian Angle at J2000.0: $W_0 = 176.630^\circ$

---

## 2. Keplerian Dynamics with $J_2$ Secular Drift

For an orbit specified by semi-major axis $a$, eccentricity $e$, inclination $i$, right ascension of the ascending node $\Omega_0$, argument of periapsis $\omega_0$, and mean anomaly $M_0$ at epoch $t_0$:

### 2.1 Mean Motion
$$n_0 = \sqrt{\frac{\mu_{\text{Mars}}}{a^3}}$$

### 2.2 Secular Drift Rates Due to $J_2$
The gravitational oblateness of Mars causes secular nodal precession ($\dot{\Omega}$) and apsidal precession ($\dot{\omega}$):
$$\dot{\Omega} = -\frac{3}{2} n_0 J_2 \left(\frac{R_{\text{eq}}}{p}\right)^2 \cos(i)$$
$$\dot{\omega} = \frac{3}{4} n_0 J_2 \left(\frac{R_{\text{eq}}}{p}\right)^2 \left(5 \cos^2(i) - 1\right)$$
where $p = a(1 - e^2)$ is the semi-latus rectum.

For sun-synchronous orbiters (such as MRO and 2001 Mars Odyssey), the inclination $i \approx 93^\circ$ is chosen so that $\dot{\Omega}$ precisely matches Mars' mean heliocentric orbital motion ($\sim 0.524^\circ/\text{day}$).

### 2.3 Kepler's Equation Solution
For elapsed time $\Delta t = t - t_0$:
$$M(t) = \left(M_0 + n_0 \Delta t\right) \pmod{2\pi}$$
$$\Omega(t) = \Omega_0 + \dot{\Omega} \Delta t$$
$$\omega(t) = \omega_0 + \dot{\omega} \Delta t$$

The eccentric anomaly $E$ is solved from Kepler's equation via Newton-Raphson iteration:
$$f(E) = E - e \sin(E) - M = 0$$
$$E_{k+1} = E_k - \frac{E_k - e \sin(E_k) - M}{1 - e \cos(E_k)}$$
converging to $|E_{k+1} - E_k| < 10^{-10}\text{ rad}$ within 3–4 iterations.

### 2.4 True Anomaly and Radial Distance
$$\nu = 2 \arctan\left(\sqrt{\frac{1+e}{1-e}} \tan\left(\frac{E}{2}\right)\right)$$
$$r = a(1 - e \cos(E))$$
$$u = \omega(t) + \nu \quad \text{(Argument of Latitude)}$$

---

## 3. Coordinate Transformation to Mars-Fixed Body Frame (IAU2000)

1. **Inertial Direction Cosines (Perifocal to Inertial Equatorial):**
   $$x_{\text{inertial}} = r \left(\cos(\Omega) \cos(u) - \sin(\Omega) \sin(u) \cos(i)\right)$$
   $$y_{\text{inertial}} = r \left(\sin(\Omega) \cos(u) + \cos(\Omega) \sin(u) \cos(i)\right)$$
   $$z_{\text{inertial}} = r \left(\sin(u) \sin(i)\right)$$

2. **Aerocentric Latitude:**
   $$\phi = \arcsin\left(\frac{z_{\text{inertial}}}{r}\right) = \arcsin(\sin(u) \sin(i))$$

3. **Mars Prime Meridian Rotation:**
   The angle of the Mars prime meridian relative to the inertial frame is given by:
   $$W(t) = \left(W_0 + \omega_{\text{Mars}} \Delta t_{\text{J2000}}\right) \pmod{2\pi}$$

4. **Aerocentric East Longitude:**
   $$\lambda_{\text{inertial}} = \operatorname{atan2}(y_{\text{inertial}}, x_{\text{inertial}})$$
   $$\lambda = \left(\lambda_{\text{inertial}} - W(t)\right) \pmod{2\pi} \in [-180^\circ, +180^\circ]$$

5. **Altitude Above Reference Areoid:**
   The reference surface radius at latitude $\phi$ is:
   $$R_{\text{surf}}(\phi) = \sqrt{\frac{(R_{\text{eq}}^2 \cos\phi)^2 + (R_{\text{pol}}^2 \sin\phi)^2}{(R_{\text{eq}} \cos\phi)^2 + (R_{\text{pol}} \sin\phi)^2}}$$
   $$h = \max(0, r - R_{\text{surf}}(\phi))$$

6. **Orbital Heading (Ground Track Azimuth):**
   $$v_{\text{North}} = \cos(u) \sin(i)$$
   $$v_{\text{East}} = \cos(i) - \frac{\omega_{\text{Mars}}}{n_0}$$
   $$\theta = (\operatorname{atan2}(v_{\text{East}}, v_{\text{North}}) \times 180 / \pi + 360) \pmod{360^\circ}$$

---

## 4. Tracked Spacecraft Specifications

| Spacecraft | Agency | Orbit Class | Semi-Major Axis ($a$) | Eccentricity ($e$) | Inclination ($i$) | Altitude Range | Primary Instruments |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **MRO** | NASA / JPL | Sun-synchronous | $3,656.0\text{ km}$ | 0.0085 | $93.0^\circ$ | $250 - 320\text{ km}$ | HiRISE, CTX, CRISM, MARCI, SHARAD |
| **Odyssey** | NASA / JPL | Sun-synchronous | $3,788.0\text{ km}$ | 0.0078 | $93.1^\circ$ | $390 - 450\text{ km}$ | THEMIS, GRS |
| **MAVEN** | NASA / GSFC | Elliptical Aeronomy | $6,546.0\text{ km}$ | 0.4630 | $75.0^\circ$ | $150 - 6,200\text{ km}$ | NGIMS, IUVS, SWEA, SWIA, MAG |
| **Mars Express** | ESA / ESOC | Eccentric Polar | $8,596.0\text{ km}$ | 0.5750 | $86.6^\circ$ | $300 - 10,100\text{ km}$ | HRSC, OMEGA, MARSIS, SPICAM |
| **Trace Gas Orbiter** | ESA / Roscosmos | Circular Science | $3,796.0\text{ km}$ | 0.0012 | $74.0^\circ$ | $390 - 410\text{ km}$ | CaSSIS, NOMAD, ACS, FREND |

---

## 5. Ground Track Multi-Segment Anti-Meridian Handling

When generating ground tracks over 120-minute windows, the ground track crosses the Martian anti-meridian ($\pm 180^\circ$). The rendering pipeline breaks the line string whenever $|\lambda_k - \lambda_{k-1}| > 180^\circ$, avoiding artificial cross-planetary chord lines and rendering clean, physically accurate orbital passes.
