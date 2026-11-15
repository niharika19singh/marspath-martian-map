"""DEM-based terrain shadow and horizon obstruction analysis for Mars surface coordinates.

Performs numerical ray-marching across the validated Mars DEM along the solar azimuth
vector to determine whether a surface point is:
1. BELOW_HORIZON: Sun is at or below the mathematical horizon (solar_elevation_deg <= 0).
2. TERRAIN_SHADOWED: Sun is above the mathematical horizon, but obstructed by terrain relief
   along the solar azimuth direction (horizon_angle_deg >= solar_elevation_deg) or self-shadowed
   by local slope facing away from the Sun.
3. ILLUMINATED: Sun is above both the mathematical horizon and all sampled terrain obstructions.
4. INSUFFICIENT_DEM_COVERAGE: Target point lies outside the validated DEM extent or on a NoData cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

from backend.app.core.config import get_settings
from backend.app.geospatial.crs import MARS_VOLUMETRIC_RADIUS_METERS as MARS_RADIUS_M


@dataclass(frozen=True)
class TerrainShadowResult:
    """Result of numeric DEM ray-marching shadow analysis."""

    shadow_state: str  # "ILLUMINATED" | "TERRAIN_SHADOWED" | "BELOW_HORIZON" | "INSUFFICIENT_DEM_COVERAGE"
    is_illuminated: bool
    is_terrain_shadowed: bool
    is_below_horizon: bool
    has_dem_coverage: bool
    solar_elevation_deg: float
    solar_azimuth_deg: float
    observer_elevation_m: float | None
    max_horizon_angle_deg: float | None
    blocking_distance_m: float | None
    blocking_elevation_m: float | None
    blocking_lon_deg: float | None
    blocking_lat_deg: float | None
    effective_solar_clearance_deg: float | None
    local_slope_deg: float | None
    local_aspect_deg: float | None
    surface_incidence_deg: float | None
    ray_march_distance_m: float
    valid_samples_count: int
    nodata_samples_count: int
    dem_source_id: str
    dem_resolution_m: float | None
    explanation: str


class DemShadowAnalyzer:
    """Caches the validated Jezero DEM array in memory for fast ray-marching."""

    def __init__(self, dem_path: Path | None = None) -> None:
        if dem_path is not None:
            self._dem_path = dem_path
        else:
            cfg = get_settings()
            p = Path(cfg.DEM_PATH)
            if not p.is_absolute():
                repo_root = Path(__file__).resolve().parents[3]
                p = repo_root / p
            self._dem_path = p
        self._loaded = False
        self._elevation: np.ndarray | None = None
        self._nodata_mask: np.ndarray | None = None
        self._bounds: tuple[float, float, float, float] | None = None  # (min_lon, min_lat, max_lon, max_lat)
        self._res_lon_deg: float = 0.0
        self._res_lat_deg: float = 0.0
        self._res_x_m: float = 200.0
        self._res_y_m: float = 200.0
        self._source_id: str = "jezero_mola_hrsc_200m"

    def _ensure_loaded(self) -> bool:
        if self._loaded and self._elevation is not None:
            return True
        if not self._dem_path or not self._dem_path.exists():
            return False

        with rasterio.open(self._dem_path) as src:
            raw = src.read(1).astype(np.float64)
            nodata_val = src.nodata
            mask = ~np.isfinite(raw)
            if nodata_val is not None:
                mask |= np.isclose(raw, float(nodata_val), rtol=1e-5, atol=1e-3)
            mask |= raw < -15000.0
            mask |= raw > 30000.0

            transform = src.transform
            crs = src.crs
            height, width = raw.shape

            # Determine if raster is in meters (Equirectangular) or degrees
            if crs and not crs.is_geographic and abs(transform.a) > 1.0:
                # Meter-projected Mars Equirectangular (sphere radius 3396190 m)
                deg_per_meter = math.degrees(1.0 / MARS_RADIUS_M)
                min_lon = transform.c * deg_per_meter
                max_lon = (transform.c + width * transform.a) * deg_per_meter
                max_lat = transform.f * deg_per_meter
                min_lat = (transform.f + height * transform.e) * deg_per_meter
                self._res_x_m = abs(transform.a)
                self._res_y_m = abs(transform.e)
                self._res_lon_deg = self._res_x_m * deg_per_meter
                self._res_lat_deg = self._res_y_m * deg_per_meter
            else:
                min_lon = float(src.bounds.left)
                min_lat = float(src.bounds.bottom)
                max_lon = float(src.bounds.right)
                max_lat = float(src.bounds.top)
                self._res_lon_deg = abs(transform.a)
                self._res_lat_deg = abs(transform.e)
                mid_lat_rad = math.radians(0.5 * (min_lat + max_lat))
                m_per_deg_lat = math.radians(1.0) * MARS_RADIUS_M
                m_per_deg_lon = m_per_deg_lat * math.cos(mid_lat_rad)
                self._res_x_m = self._res_lon_deg * m_per_deg_lon
                self._res_y_m = self._res_lat_deg * m_per_deg_lat

            self._elevation = raw
            self._nodata_mask = mask
            self._bounds = (min_lon, min_lat, max_lon, max_lat)
            self._loaded = True
            return True

    def _lonlat_to_rowcol(self, lon_deg: float, lat_deg: float) -> tuple[int, int] | None:
        if not self._bounds or self._elevation is None:
            return None
        min_lon, min_lat, max_lon, max_lat = self._bounds
        if not (min_lon <= lon_deg <= max_lon and min_lat <= lat_deg <= max_lat):
            return None
        height, width = self._elevation.shape
        col = int((lon_deg - min_lon) / max(self._res_lon_deg, 1e-12))
        row = int((max_lat - lat_deg) / max(self._res_lat_deg, 1e-12))
        col = max(0, min(width - 1, col))
        row = max(0, min(height - 1, row))
        return row, col

    def _compute_local_slope_aspect(self, row: int, col: int) -> tuple[float, float]:
        """Compute local slope (deg) and aspect (deg clockwise from North) using a 3x3 window."""
        assert self._elevation is not None and self._nodata_mask is not None
        h, w = self._elevation.shape
        r0 = max(0, row - 1)
        r1 = min(h - 1, row + 1)
        c0 = max(0, col - 1)
        c1 = min(w - 1, col + 1)

        z_center = float(self._elevation[row, col])

        def _val(r: int, c: int) -> float:
            if self._nodata_mask[r, c]:
                return z_center
            return float(self._elevation[r, c])

        dz_dx = (_val(row, c1) - _val(row, c0)) / (max(1, c1 - c0) * self._res_x_m)
        # Row index increases southward, so North is r0 and South is r1
        dz_dy = (_val(r0, col) - _val(r1, col)) / (max(1, r1 - r0) * self._res_y_m)

        slope_rad = math.atan(math.hypot(dz_dx, dz_dy))
        slope_deg = math.degrees(slope_rad)

        # Aspect: downslope direction clockwise from North
        if abs(dz_dx) < 1e-12 and abs(dz_dy) < 1e-12:
            aspect_deg = 0.0
        else:
            aspect_deg = math.degrees(math.atan2(-dz_dx, -dz_dy)) % 360.0
        return slope_deg, aspect_deg

    def evaluate_shadow(
        self,
        latitude_deg: float,
        longitude_east_deg: float,
        solar_elevation_deg: float,
        solar_azimuth_deg: float,
        max_distance_m: float = 25000.0,
    ) -> TerrainShadowResult:
        """Ray-march from (latitude_deg, longitude_east_deg) toward solar_azimuth_deg."""
        if not self._ensure_loaded() or self._elevation is None or self._nodata_mask is None:
            is_below = solar_elevation_deg <= 0.0
            return TerrainShadowResult(
                shadow_state="BELOW_HORIZON" if is_below else "INSUFFICIENT_DEM_COVERAGE",
                is_illuminated=False,
                is_terrain_shadowed=False,
                is_below_horizon=is_below,
                has_dem_coverage=False,
                solar_elevation_deg=round(solar_elevation_deg, 4),
                solar_azimuth_deg=round(solar_azimuth_deg, 4),
                observer_elevation_m=None,
                max_horizon_angle_deg=None,
                blocking_distance_m=None,
                blocking_elevation_m=None,
                blocking_lon_deg=None,
                blocking_lat_deg=None,
                effective_solar_clearance_deg=None,
                local_slope_deg=None,
                local_aspect_deg=None,
                surface_incidence_deg=None,
                ray_march_distance_m=0.0,
                valid_samples_count=0,
                nodata_samples_count=0,
                dem_source_id=self._source_id,
                dem_resolution_m=None,
                explanation="Validated regional DEM file is not available on disk.",
            )

        rc = self._lonlat_to_rowcol(longitude_east_deg, latitude_deg)
        if rc is None:
            min_lon, min_lat, max_lon, max_lat = self._bounds or (0, 0, 0, 0)
            return TerrainShadowResult(
                shadow_state="INSUFFICIENT_DEM_COVERAGE",
                is_illuminated=False,
                is_terrain_shadowed=False,
                is_below_horizon=solar_elevation_deg <= 0.0,
                has_dem_coverage=False,
                solar_elevation_deg=round(solar_elevation_deg, 4),
                solar_azimuth_deg=round(solar_azimuth_deg, 4),
                observer_elevation_m=None,
                max_horizon_angle_deg=None,
                blocking_distance_m=None,
                blocking_elevation_m=None,
                blocking_lon_deg=None,
                blocking_lat_deg=None,
                effective_solar_clearance_deg=None,
                local_slope_deg=None,
                local_aspect_deg=None,
                surface_incidence_deg=None,
                ray_march_distance_m=0.0,
                valid_samples_count=0,
                nodata_samples_count=0,
                dem_source_id=self._source_id,
                dem_resolution_m=round(0.5 * (self._res_x_m + self._res_y_m), 2),
                explanation=(
                    f"Coordinate ({longitude_east_deg:.4f}°E, {latitude_deg:.4f}°N) is outside "
                    f"the validated Jezero DEM coverage [{min_lon:.3f}°E..{max_lon:.3f}°E, "
                    f"{min_lat:.3f}°N..{max_lat:.3f}°N]."
                ),
            )

        row0, col0 = rc
        if bool(self._nodata_mask[row0, col0]):
            return TerrainShadowResult(
                shadow_state="INSUFFICIENT_DEM_COVERAGE",
                is_illuminated=False,
                is_terrain_shadowed=False,
                is_below_horizon=solar_elevation_deg <= 0.0,
                has_dem_coverage=False,
                solar_elevation_deg=round(solar_elevation_deg, 4),
                solar_azimuth_deg=round(solar_azimuth_deg, 4),
                observer_elevation_m=None,
                max_horizon_angle_deg=None,
                blocking_distance_m=None,
                blocking_elevation_m=None,
                blocking_lon_deg=None,
                blocking_lat_deg=None,
                effective_solar_clearance_deg=None,
                local_slope_deg=None,
                local_aspect_deg=None,
                surface_incidence_deg=None,
                ray_march_distance_m=0.0,
                valid_samples_count=0,
                nodata_samples_count=1,
                dem_source_id=self._source_id,
                dem_resolution_m=round(0.5 * (self._res_x_m + self._res_y_m), 2),
                explanation="Target coordinate falls on a NoData pixel in the DEM.",
            )

        z0 = float(self._elevation[row0, col0])
        slope_deg, aspect_deg = self._compute_local_slope_aspect(row0, col0)

        # Compute surface incidence angle between local normal and solar vector
        zenith_rad = math.radians(90.0 - solar_elevation_deg)
        slope_rad = math.radians(slope_deg)
        az_diff_rad = math.radians(solar_azimuth_deg - aspect_deg)
        cos_inc = math.cos(zenith_rad) * math.cos(slope_rad) + math.sin(zenith_rad) * math.sin(slope_rad) * math.cos(
            az_diff_rad
        )
        cos_inc = max(-1.0, min(1.0, cos_inc))
        incidence_deg = math.degrees(math.acos(cos_inc))

        # March along solar azimuth vector across the DEM grid
        step_m = max(50.0, min(self._res_x_m, self._res_y_m))
        az_rad = math.radians(solar_azimuth_deg)
        # Unit step in East (dx) and North (dy) meters
        ux_m = math.sin(az_rad)
        uy_m = math.cos(az_rad)

        lat_rad = math.radians(latitude_deg)
        m_per_deg_lat = math.radians(1.0) * MARS_RADIUS_M
        m_per_deg_lon = m_per_deg_lat * max(0.05, math.cos(lat_rad))

        max_horizon_deg = -90.0
        blocking_dist_m: float | None = None
        blocking_elev_m: float | None = None
        blocking_lon: float | None = None
        blocking_lat: float | None = None
        valid_samples = 0
        nodata_samples = 0
        marched_m = 0.0

        num_steps = int(max_distance_m // step_m)
        for step_idx in range(1, num_steps + 1):
            dist_m = step_idx * step_m
            sample_lon = longitude_east_deg + (ux_m * dist_m) / m_per_deg_lon
            sample_lat = latitude_deg + (uy_m * dist_m) / m_per_deg_lat

            sample_rc = self._lonlat_to_rowcol(sample_lon, sample_lat)
            if sample_rc is None:
                break
            marched_m = dist_m
            s_row, s_col = sample_rc
            if s_row == row0 and s_col == col0:
                continue

            if bool(self._nodata_mask[s_row, s_col]):
                nodata_samples += 1
                continue

            valid_samples += 1
            z_sample = float(self._elevation[s_row, s_col])
            # Planetary curvature drop over distance dist_m on Mars sphere
            curvature_drop_m = (dist_m * dist_m) / (2.0 * MARS_RADIUS_M)
            dz_effective = (z_sample - curvature_drop_m) - z0
            horizon_angle_deg = math.degrees(math.atan2(dz_effective, dist_m))

            if horizon_angle_deg > max_horizon_deg:
                max_horizon_deg = horizon_angle_deg
                blocking_dist_m = dist_m
                blocking_elev_m = z_sample
                blocking_lon = sample_lon
                blocking_lat = sample_lat

        if valid_samples == 0:
            max_horizon_deg = 0.0

        clearance_deg = solar_elevation_deg - max_horizon_deg
        res_m = round(0.5 * (self._res_x_m + self._res_y_m), 2)

        if solar_elevation_deg <= 0.0:
            state = "BELOW_HORIZON"
            is_illum = False
            is_terr_shadow = False
            is_below = True
            explanation = (
                f"Sun is below the local mathematical horizon (elevation {solar_elevation_deg:.2f}°). "
                f"Maximum terrain horizon along azimuth {solar_azimuth_deg:.1f}° is {max_horizon_deg:.2f}°."
            )
        elif solar_elevation_deg <= max_horizon_deg or incidence_deg >= 90.0:
            state = "TERRAIN_SHADOWED"
            is_illum = False
            is_terr_shadow = True
            is_below = False
            if solar_elevation_deg <= max_horizon_deg and blocking_dist_m is not None:
                explanation = (
                    f"Sun is above the mathematical horizon ({solar_elevation_deg:.2f}°), but obstructed "
                    f"by terrain relief ({max_horizon_deg:.2f}° horizon angle at {blocking_dist_m / 1000.0:.2f} km "
                    f"along azimuth {solar_azimuth_deg:.1f}°, elevation {blocking_elev_m:.1f} m)."
                )
            else:
                explanation = (
                    f"Sun is above the mathematical horizon ({solar_elevation_deg:.2f}°), but local slope "
                    f"({slope_deg:.2f}° facing {aspect_deg:.1f}°) self-shadows the surface "
                    f"(incidence angle {incidence_deg:.2f}° >= 90°)."
                )
        else:
            state = "ILLUMINATED"
            is_illum = True
            is_terr_shadow = False
            is_below = False
            explanation = (
                f"Surface is directly illuminated: solar elevation {solar_elevation_deg:.2f}° clears "
                f"maximum terrain horizon ({max_horizon_deg:.2f}°) by {clearance_deg:.2f}° "
                f"(local incidence angle {incidence_deg:.2f}°)."
            )

        return TerrainShadowResult(
            shadow_state=state,
            is_illuminated=is_illum,
            is_terrain_shadowed=is_terr_shadow,
            is_below_horizon=is_below,
            has_dem_coverage=True,
            solar_elevation_deg=round(solar_elevation_deg, 4),
            solar_azimuth_deg=round(solar_azimuth_deg, 4),
            observer_elevation_m=round(z0, 2),
            max_horizon_angle_deg=round(max_horizon_deg, 4),
            blocking_distance_m=round(blocking_dist_m, 1) if blocking_dist_m is not None else None,
            blocking_elevation_m=round(blocking_elev_m, 2) if blocking_elev_m is not None else None,
            blocking_lon_deg=round(blocking_lon, 5) if blocking_lon is not None else None,
            blocking_lat_deg=round(blocking_lat, 5) if blocking_lat is not None else None,
            effective_solar_clearance_deg=round(clearance_deg, 4),
            local_slope_deg=round(slope_deg, 3),
            local_aspect_deg=round(aspect_deg, 2),
            surface_incidence_deg=round(incidence_deg, 3),
            ray_march_distance_m=round(marched_m, 1),
            valid_samples_count=valid_samples,
            nodata_samples_count=nodata_samples,
            dem_source_id=self._source_id,
            dem_resolution_m=res_m,
            explanation=explanation,
        )


_default_analyzer: DemShadowAnalyzer | None = None


def get_dem_shadow_analyzer() -> DemShadowAnalyzer:
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = DemShadowAnalyzer()
    return _default_analyzer
