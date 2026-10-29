import math
from typing import Any, Dict, List
import numpy as np
from backend.app.data.providers.base import BaseRasterProvider
from backend.app.geospatial.crs import get_mars_crs_info
from backend.app.geospatial.raster_loader import RasterData, RasterMetadata
from backend.app.schemas.coordinates import BoundingBox, CRSInfo, MarsCoordinate
from backend.app.schemas.mission import ScienceTarget


class SyntheticTerrainProvider(BaseRasterProvider):
    """
    Deterministic synthetic Martian terrain model for Jezero Crater pilot testing.
    Explicitly labeled as synthetic test data.
    Faithfully simulates major topographic features of Jezero Crater:
    - 45 km diameter impact crater with raised rim (-2100m) and flat floor (-2560m)
    - Western delta fan deposit with stepped sedimentary scarps
    - Western rim breach (Neretva Vallis paleoriver channel)
    - Nested impact craters (Belva) and rough terrain (Séítah)
    """

    def __init__(self, rows: int = 250, cols: int = 375):
        self.rows = rows
        self.cols = cols
        self.min_lon = 77.20
        self.max_lon = 77.95
        self.min_lat = 18.15
        self.max_lat = 18.65
        self.center_lon = 77.58
        self.center_lat = 18.38
        self._raster_data: RasterData | None = None
        self._science_targets = self._init_science_targets()

    def _init_science_targets(self) -> List[ScienceTarget]:
        return [
            ScienceTarget(
                id="poi_delta_front",
                name="Jezero Western Delta Front",
                target_type="river_delta_strata",
                coordinate=MarsCoordinate(lon=77.44, lat=18.42),
                scientific_priority=3.0,
                description="Fine-grained clay-bearing mudstones and delta deposits sampled by Perseverance rover.",
            ),
            ScienceTarget(
                id="poi_seitah",
                name="Séítah Layered Bedrock",
                target_type="olivine_cumulate",
                coordinate=MarsCoordinate(lon=77.48, lat=18.37),
                scientific_priority=2.5,
                description="Rough, fractured olivine-rich igneous rock and sand dunes on crater floor.",
            ),
            ScienceTarget(
                id="poi_belva_crater",
                name="Belva Crater Rim Ejecta",
                target_type="impact_excavation",
                coordinate=MarsCoordinate(lon=77.53, lat=18.41),
                scientific_priority=2.0,
                description="1 km diameter nested impact crater excavating deep floor bedrock.",
            ),
            ScienceTarget(
                id="poi_kodiak_butte",
                name="Kodiak Butte (Delta Outlier)",
                target_type="sedimentary_butte",
                coordinate=MarsCoordinate(lon=77.41, lat=18.39),
                scientific_priority=2.2,
                description="Isolated mesa displaying diagnostic deltaic bottomset and foreset beds.",
            ),
            ScienceTarget(
                id="poi_neretva_breach",
                name="Neretva Vallis Inlet Breach",
                target_type="inflow_valley",
                coordinate=MarsCoordinate(lon=77.34, lat=18.43),
                scientific_priority=2.8,
                description="Ancient river valley cutting through the western crater rim wall.",
            ),
        ]

    def _generate_terrain(self) -> np.ndarray:
        """Procedurally computes deterministic Jezero Crater elevation matrix in meters."""
        lons = np.linspace(self.min_lon, self.max_lon, self.cols)
        lats = np.linspace(self.max_lat, self.min_lat, self.rows)  # North to South
        lon_grid, lat_grid = np.meshgrid(lons, lats)

        # Distance from Jezero crater center in degrees
        dx_deg = (lon_grid - self.center_lon) * math.cos(math.radians(self.center_lat))
        dy_deg = lat_grid - self.center_lat
        dist_deg = np.sqrt(dx_deg**2 + dy_deg**2)
        dist_km = dist_deg * 59.274  # kilometers from crater center

        # Base regional Mars crust elevation: -2100m
        elev = np.full((self.rows, self.cols), -2100.0, dtype=np.float32)

        # Crater bowl profile (radius ~ 22.5 km)
        crater_radius_km = 22.5
        bowl_mask = dist_km < crater_radius_km

        # Floor depth: -2560m; rim crest: -2050m (approx 500m rim wall)
        # Sigmoid / smooth transition from rim to floor
        wall_norm = np.clip((dist_km - 15.0) / 7.5, 0.0, 1.0)
        crater_profile = -2560.0 + (510.0 * (wall_norm**2))
        elev[bowl_mask] = crater_profile[bowl_mask]

        # Raised rim crest outer slope
        outer_mask = (dist_km >= crater_radius_km) & (dist_km <= 28.0)
        outer_falloff = 1.0 - ((dist_km[outer_mask] - crater_radius_km) / 5.5)
        elev[outer_mask] = -2100.0 + (50.0 * outer_falloff)

        # Western Delta Fan (centered around 77.42°E, 18.42°N, spreading eastward)
        delta_dx = (lon_grid - 77.40) * math.cos(math.radians(18.42))
        delta_dy = lat_grid - 18.42
        delta_dist_km = np.sqrt(delta_dx**2 + delta_dy**2) * 59.274
        delta_mask = (delta_dist_km < 6.5) & (lon_grid > 77.36)
        # Delta elevation rises ~60m above crater floor (-2500m to -2540m)
        elev[delta_mask] += (65.0 * (1.0 - (delta_dist_km[delta_mask] / 6.5))).astype(np.float32)

        # Belva Crater (nested impact crater at 77.53°E, 18.41°N, radius 0.6 km)
        belva_dx = (lon_grid - 77.53) * math.cos(math.radians(18.41))
        belva_dy = lat_grid - 18.41
        belva_dist_km = np.sqrt(belva_dx**2 + belva_dy**2) * 59.274
        belva_mask = belva_dist_km < 0.65
        elev[belva_mask] -= (80.0 * (1.0 - (belva_dist_km[belva_mask] / 0.65)**2)).astype(np.float32)

        # Western Breach: Neretva Vallis gorge cutting through rim
        vallis_mask = (np.abs(lat_grid - 18.43) < 0.015) & (lon_grid >= 77.25) & (lon_grid <= 77.38)
        elev[vallis_mask] = np.minimum(elev[vallis_mask], -2480.0)

        # Add deterministic micro-topography noise using trigonometric harmonics
        noise = (
            2.5 * np.sin(lon_grid * 350.0) * np.cos(lat_grid * 350.0)
            + 1.2 * np.sin(lon_grid * 700.0 + lat_grid * 600.0)
        ).astype(np.float32)
        elev += noise

        return elev

    def get_dem_raster(self) -> RasterData:
        if self._raster_data is None:
            elev = self._generate_terrain()
            deg_per_px_lon = (self.max_lon - self.min_lon) / self.cols
            deg_per_px_lat = (self.max_lat - self.min_lat) / self.rows
            meta = RasterMetadata(
                width=self.cols,
                height=self.rows,
                min_lon=self.min_lon,
                min_lat=self.min_lat,
                max_lon=self.max_lon,
                max_lat=self.max_lat,
                deg_per_px_lon=deg_per_px_lon,
                deg_per_px_lat=deg_per_px_lat,
                nodata_value=-9999.0,
                crs_str="IAU2000:49900",
                is_synthetic=True,
            )
            self._raster_data = RasterData(elev, meta)
        return self._raster_data

    def get_bounds(self) -> BoundingBox:
        return BoundingBox(
            min_lon=self.min_lon,
            min_lat=self.min_lat,
            max_lon=self.max_lon,
            max_lat=self.max_lat,
        )

    def get_crs_info(self) -> CRSInfo:
        return get_mars_crs_info()

    def get_provenance(self) -> Dict[str, Any]:
        return {
            "mode": "synthetic_test_fixture",
            "pilot_region": "Jezero Crater, Mars",
            "model_description": "Deterministic procedural simulation of Jezero Crater morphology (rim, delta, floor, Belva)",
            "nominal_resolution_meters": round(((self.max_lon - self.min_lon) / self.cols) * 56250.0, 1),
            "reference_datum": "Mars IAU2000 Sphere (R=3,396,190m)",
            "official_source_counterpart": "MOLA/HRSC Blended DEM & CTX/HiRISE Jezero Mosaic",
            "intended_use": "Deterministic algorithm verification, test suite execution, frontend integration sandbox",
            "warning": "Do NOT use synthetic test data for operational flight planning or genuine mission risk assessment.",
        }

    def is_synthetic(self) -> bool:
        return True

    def get_science_targets(self) -> List[ScienceTarget]:
        return self._science_targets
