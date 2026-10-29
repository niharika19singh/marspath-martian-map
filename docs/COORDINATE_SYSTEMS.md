# Martian Coordinate Reference Systems & Planetary Geodesy

Planetary mapping on Mars requires strict adherence to international astronomical standards. Applying terrestrial Earth geodesy (such as WGS84 or standard Web Mercator) to Mars produces massive spatial distortion and erroneous physical distance calculations.

---

## 1. Geodetic Definition: IAU 2000 Mars

MARSPath implements the **IAU 2000 Mars Sphere** standard (`IAU2000:49900`):

- **Volumetric Mean Radius ($R$):** $3,396,190.0\text{ meters}$ (~$3,396.19\text{ km}$).
- **Equatorial Radius ($a$):** $3,396,190.0\text{ meters}$.
- **Polar Radius ($b$):** $3,376,200.0\text{ meters}$.
- **Mars Circumference:** $2\pi R \approx 21,338,891\text{ meters}$.

---

## 2. Coordinate Conventions

### Longitude: Positive East
- Longitude on Mars is defined as increasing **Eastward** from the Martian Prime Meridian (which passes through the center of crater Airy-0).
- Range accepted: `[0°, 360°)` or `[-180°, +180°)`.
- Backend standard: All internal calculations normalize longitude into `[0°, 360°)`.

### Latitude: Planetocentric
- **Planetocentric latitude** is the angle between the equatorial plane and a vector from the planet center to the point on the surface.
- Range: `[-90.0°, +90.0°]`.

---

## 3. Physical Ground Distance Calculations

### Latitude Metric Conversion
Because lines of latitude are parallel circles, the physical ground distance corresponding to 1 degree of planetocentric latitude on the Mars sphere is constant everywhere:
$$\Delta y = \frac{2 \pi R}{360} = \frac{21,338,891\text{ m}}{360} \approx 59,274.69\text{ meters / degree}$$

### Longitude Metric Conversion
Lines of longitude converge toward the poles. The physical distance for 1 degree of East longitude at latitude $\phi$ is:
$$\Delta x(\phi) = \Delta y \cdot \cos(\phi) = 59,274.69 \cdot \cos(\phi)\text{ meters / degree}$$

At the **Jezero Crater pilot center** ($\phi \approx 18.38^\circ\text{N}$):
$$\cos(18.38^\circ) \approx 0.9490$$
$$\Delta x(18.38^\circ) \approx 59,274.69 \times 0.9490 \approx 56,251.68\text{ meters / degree}$$

### Great-Circle Haversine Formula
For arbitrary points on the Mars sphere:
$$a = \sin^2\left(\frac{\Delta \phi}{2}\right) + \cos(\phi_1)\cos(\phi_2)\sin^2\left(\frac{\Delta \lambda}{2}\right)$$
$$d = 2 R \cdot \text{atan2}(\sqrt{a}, \sqrt{1 - a})$$

---

## 4. Local Metric Projection

For corridor graph routing, MARSPath uses an **Equirectangular Metric Projection** centered on the pilot reference point $(\lambda_0, \phi_0)$:
$$x = R \cdot (\lambda - \lambda_0)_{\text{radians}} \cdot \cos(\phi_0)$$
$$y = R \cdot (\phi - \phi_0)_{\text{radians}}$$

Inverse transformation:
$$\lambda = \lambda_0 + \frac{x}{R \cdot \cos(\phi_0)} \cdot \frac{180}{\pi}$$
$$\phi = \phi_0 + \frac{y}{R} \cdot \frac{180}{\pi}$$

Both transformations are verified via automated round-trip tests in `backend/tests/unit/test_crs.py`.
