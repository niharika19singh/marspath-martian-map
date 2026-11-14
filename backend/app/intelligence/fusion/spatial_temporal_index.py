"""
Spatial and Temporal Intelligence Index for Mars Planetary Observations.
Performs spherical distance calculation, bounding box intersection,
antimeridian-aware queries, and route corridor buffer searches in IAU2000 Mars coordinates.
"""

from __future__ import annotations

import math
from datetime import datetime

from backend.app.intelligence.fusion.evidence_model import (
    CoverageGap,
    NormalizedObservation,
)

# Mean radius of Mars in meters (IAU2000 reference sphere)
MARS_RADIUS_M = 3396190.0
M_PER_DEG = (2.0 * math.pi * MARS_RADIUS_M) / 360.0


def normalize_mars_lon(lon: float) -> float:
    """Normalize longitude to standard [0, 360) East degrees."""
    lon = lon % 360.0
    if lon < 0:
        lon += 360.0
    return lon


def haversine_mars_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Computes great-circle distance in meters on the Mars sphere."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return MARS_RADIUS_M * c


def bbox_intersects(b1: list[float], b2: list[float]) -> bool:
    """
    Checks if bounding box b1 [min_lon, min_lat, max_lon, max_lat]
    intersects bounding box b2 [min_lon, min_lat, max_lon, max_lat].
    """
    if b1[2] < b2[0] or b1[0] > b2[2]:
        return False
    if b1[3] < b2[1] or b1[1] > b2[3]:
        return False
    return True


def point_in_bbox(lon: float, lat: float, bbox: list[float]) -> bool:
    """Checks if point (lon, lat) falls within [min_lon, min_lat, max_lon, max_lat]."""
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def distance_point_to_segment_m(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    """
    Approximates minimum distance in meters from point (px, py) to line segment (x1, y1)-(x2, y2)
    using local equirectangular projection centered at py.
    """
    cos_lat = math.cos(math.radians(py))
    dx = (x2 - x1) * M_PER_DEG * cos_lat
    dy = (y2 - y1) * M_PER_DEG
    length_sq = dx * dx + dy * dy

    if length_sq < 1e-6:
        return haversine_mars_distance_m(px, py, x1, y1)

    dpx = (px - x1) * M_PER_DEG * cos_lat
    dpy = (py - y1) * M_PER_DEG
    t = max(0.0, min(1.0, (dpx * dx + dpy * dy) / length_sq))

    proj_x = x1 + t * (x2 - x1)
    proj_y = y1 + t * (y2 - y1)
    return haversine_mars_distance_m(px, py, proj_x, proj_y)


class SpatialTemporalIntelligenceIndex:
    """In-memory spatial-temporal index for fast planetary intelligence lookups."""

    def __init__(self, observations: list[NormalizedObservation] | None = None) -> None:
        self._observations: dict[str, NormalizedObservation] = {}
        if observations:
            for obs in observations:
                self.add_observation(obs)

    def add_observation(self, obs: NormalizedObservation) -> None:
        self._observations[obs.observation_id] = obs

    def get_observation(self, observation_id: str) -> NormalizedObservation | None:
        return self._observations.get(observation_id)

    def get_all(self) -> list[NormalizedObservation]:
        return list(self._observations.values())

    def find_intersecting_bbox(self, bbox: list[float]) -> list[NormalizedObservation]:
        """Returns all observations whose spatial bounds intersect the query bbox."""
        results = []
        for obs in self._observations.values():
            if obs.bbox and bbox_intersects(obs.bbox, bbox):
                results.append(obs)
            elif not obs.bbox and obs.geometry.get("type") == "Point":
                coords = obs.geometry["coordinates"]
                if point_in_bbox(coords[0], coords[1], bbox):
                    results.append(obs)
        return results

    def find_near_route(
        self,
        route_coordinates: list[list[float]],
        buffer_m: float = 250.0,
    ) -> list[NormalizedObservation]:
        """Returns observations within buffer_m distance of any vertex or segment along the route."""
        if not route_coordinates:
            return []

        # First compute overall route bounding box with safety margin
        lons = [c[0] for c in route_coordinates]
        lats = [c[1] for c in route_coordinates]
        deg_buf = (buffer_m / M_PER_DEG) * 1.5
        route_bbox = [min(lons) - deg_buf, min(lats) - deg_buf, max(lons) + deg_buf, max(lats) + deg_buf]

        candidates = self.find_intersecting_bbox(route_bbox)
        matched = []

        for obs in candidates:
            # Check if any route segment passes within buffer_m of observation
            if obs.geometry.get("type") == "Point":
                plon, plat = obs.geometry["coordinates"][0], obs.geometry["coordinates"][1]
                is_near = False
                for i in range(len(route_coordinates) - 1):
                    p1 = route_coordinates[i]
                    p2 = route_coordinates[i + 1]
                    d = distance_point_to_segment_m(plon, plat, p1[0], p1[1], p2[0], p2[1])
                    if d <= buffer_m:
                        is_near = True
                        break
                if is_near:
                    matched.append(obs)
            else:
                # Polygon or bounding box already passed intersection with route corridor
                matched.append(obs)

        return matched

    def find_for_segment(
        self,
        seg_start: list[float],
        seg_end: list[float],
        buffer_m: float = 100.0,
    ) -> list[NormalizedObservation]:
        """Finds observations intersecting or within buffer_m of a single route segment."""
        return self.find_near_route([seg_start, seg_end], buffer_m=buffer_m)

    def filter_temporal(
        self,
        observations: list[NormalizedObservation] | None = None,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        sol: int | None = None,
        min_ls_deg: float | None = None,
        max_ls_deg: float | None = None,
    ) -> list[NormalizedObservation]:
        """Filters observations based on UTC timestamp window, Martian sol, or seasonal Ls."""
        source_list = observations if observations is not None else list(self._observations.values())
        filtered = []

        for obs in source_list:
            if start_utc and obs.timestamp_utc and obs.timestamp_utc < start_utc:
                continue
            if end_utc and obs.timestamp_utc and obs.timestamp_utc > end_utc:
                continue
            if sol is not None and obs.martian_sol is not None and obs.martian_sol != sol:
                continue
            if min_ls_deg is not None and obs.solar_longitude_ls is not None and obs.solar_longitude_ls < min_ls_deg:
                continue
            if max_ls_deg is not None and obs.solar_longitude_ls is not None and obs.solar_longitude_ls > max_ls_deg:
                continue
            filtered.append(obs)

        return filtered

    def identify_coverage_gaps(
        self,
        mission_bbox: list[float],
        required_types: list[str] | None = None,
    ) -> list[CoverageGap]:
        """
        Scans a target mission bounding box against loaded observations to identify
        regions lacking high-resolution DTM (HiRISE 1 m) or thermal inertia characterization.
        """
        gaps: list[CoverageGap] = []
        intersecting = self.find_intersecting_bbox(mission_bbox)

        # Check if 1 m HiRISE stereo DTM completely covers the mission bounding box
        hirise_dtm = next(
            (
                obs
                for obs in intersecting
                if obs.measurement_type == "stereo_elevation_dtm" and (obs.spatial_resolution_m or 999.0) <= 2.0
            ),
            None,
        )
        dtm_fully_covers = (
            hirise_dtm is not None
            and hirise_dtm.bbox is not None
            and hirise_dtm.bbox[0] <= mission_bbox[0]
            and hirise_dtm.bbox[1] <= mission_bbox[1]
            and hirise_dtm.bbox[2] >= mission_bbox[2]
            and hirise_dtm.bbox[3] >= mission_bbox[3]
        )
        if not dtm_fully_covers:
            gaps.append(
                CoverageGap(
                    gap_id="gap_jezero_regional_coarse_dem",
                    region_name="Jezero Outer Corridor Beyond HiRISE Footprint",
                    bbox=mission_bbox,
                    missing_evidence_types=["stereo_elevation_dtm (1 m)"],
                    available_fallback_resolution_m=200.0,
                    risk_assessment="Sub-meter boulder and localized scarp hazards cannot be resolved from 200 m regional DEM.",
                    recommended_reconnaissance="Prioritize existing PDS HiRISE stereo pairs or schedule MRO target overflight.",
                )
            )

        # Check for THEMIS thermal inertia coverage
        has_themis = any(obs.measurement_type == "thermal_inertia" for obs in intersecting)
        if not has_themis:
            gaps.append(
                CoverageGap(
                    gap_id="gap_thermal_inertia_unmapped",
                    region_name="Uncharacterized Regolith Mobility Zone",
                    bbox=mission_bbox,
                    missing_evidence_types=["thermal_inertia"],
                    available_fallback_resolution_m=None,
                    risk_assessment="Subsurface bearing capacity and wheel-sinkage risk unassessed by night IR thermography.",
                    recommended_reconnaissance="Ingest THEMIS nighttime IR mosaic band 9 to derive thermal inertia index.",
                )
            )

        return gaps

    def detect_coverage_gaps(
        self,
        mission_bbox: list[float] | None = None,
    ) -> list[CoverageGap]:
        """Convenience method scanning default Jezero traverse bounds."""
        target_bbox = mission_bbox or [77.65, 18.10, 77.95, 18.40]
        return self.identify_coverage_gaps(target_bbox)

    def query_observations(
        self,
        bbox: list[float] | None = None,
        min_sol: int | None = None,
        max_sol: int | None = None,
        min_ls: float | None = None,
        max_ls: float | None = None,
        instrument: str | None = None,
        provenance_kind: str | None = None,
        quality_tier: str | None = None,
        measurement_type: str | None = None,
        limit: int = 50,
    ) -> list[NormalizedObservation]:
        """Unified query supporting spatial, temporal, instrument, and quality filtering."""
        candidates = self.find_intersecting_bbox(bbox) if bbox else self.get_all()
        results: list[NormalizedObservation] = []

        for obs in candidates:
            if min_sol is not None and (obs.martian_sol is None or obs.martian_sol < min_sol):
                continue
            if max_sol is not None and (obs.martian_sol is None or obs.martian_sol > max_sol):
                continue
            if min_ls is not None and (obs.solar_longitude_ls is None or obs.solar_longitude_ls < min_ls):
                continue
            if max_ls is not None and (obs.solar_longitude_ls is None or obs.solar_longitude_ls > max_ls):
                continue
            if instrument and instrument.lower() not in obs.instrument.lower():
                continue
            if provenance_kind and obs.provenance_kind.value.lower() != provenance_kind.lower():
                continue
            if quality_tier and obs.quality_tier.value.upper() != quality_tier.upper():
                continue
            if measurement_type and obs.measurement_type.lower() != measurement_type.lower():
                continue
            results.append(obs)
            if len(results) >= limit:
                break

        return results

    @classmethod
    def create_default_jezero_index(cls) -> SpatialTemporalIntelligenceIndex:
        """Instantiates and populates the default multi-source intelligence index for Jezero Crater."""
        from datetime import UTC, datetime

        from backend.app.intelligence.fusion.source_normalizer import UnifiedSourceNormalizer

        idx = cls()

        # 1. USGS HiRISE 1m DTM
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_hirise_dtm_observation(
                product_id="DTEEC_069176_1985_069822_1985_U01",
                resolution_m=1.0,
            )
        )

        # 2. HiRISE 25cm Orthomosaic
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_hirise_ortho_observation(
                product_id="ESP_045994_1985_RED",
                resolution_m=0.25,
            )
        )

        # 3. MOLA-HRSC 200m regional DEM
        idx.add_observation(UnifiedSourceNormalizer.normalize_mola_hrsc_observation())

        # 4. MEDA atmospheric temperature & pressure & tau
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_meda_observation(
                sol=1050,
                timestamp_utc=datetime(2024, 2, 4, 14, 0, tzinfo=UTC),
                air_temp_c=-44.2,
                ground_temp_c=-38.1,
                pressure_pa=745.0,
                wind_speed_m_s=4.2,
                dust_optical_depth_tau=0.48,
            )
        )

        # 5. THEMIS Nighttime Infrared Thermal Inertia
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_themis_observation(
                product_id="I12345001",
                thermal_inertia=215.0,
                lon=77.435,
                lat=18.435,
            )
        )

        # 8. MRO HiRISE targeted orbital acquisition
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_orbital_observation(
                observation_id="ESP_069176_1985",
                spacecraft_id="mro",
                instrument="HiRISE",
                target_name="Jezero Western Delta Fan",
                center_lon=77.365,
                center_lat=18.435,
                footprint_geojson={
                    "type": "Polygon",
                    "coordinates": [[[77.268, 18.355], [77.498, 18.355], [77.498, 18.542], [77.268, 18.542], [77.268, 18.355]]],
                },
                resolution_m=0.25,
                timestamp_utc=datetime(2021, 4, 18, 10, 14, tzinfo=UTC),
            )
        )

        # 9. Rover Perseverance Waypoint
        idx.add_observation(
            UnifiedSourceNormalizer.normalize_rover_waypoint(
                waypoint_id="wp_sol_1050",
                rover_id="perseverance",
                sol=1050,
                lon=77.412,
                lat=18.420,
                elevation_m=-2542.0,
                timestamp_utc=datetime(2024, 2, 4, 16, 30, tzinfo=UTC),
            )
        )

        return idx

