"""
Source Normalizer for MARSPath Unified Data Fusion.
Extracts, adapts, and standardizes multi-mission datasets into normalized observations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.app.intelligence.fusion.evidence_model import (
    NormalizedObservation,
    ProvenanceKind,
    QualityTier,
)


def _compute_bbox(coords: list[Any]) -> list[float] | None:
    """Extract [min_lon, min_lat, max_lon, max_lat] from coordinate pairs."""
    flat_lons: list[float] = []
    flat_lats: list[float] = []

    def _walk(item: Any):
        if isinstance(item, (list, tuple)):
            if len(item) >= 2 and isinstance(item[0], (int, float)) and isinstance(item[1], (int, float)):
                flat_lons.append(float(item[0]))
                flat_lats.append(float(item[1]))
            else:
                for sub in item:
                    _walk(sub)

    _walk(coords)
    if not flat_lons or not flat_lats:
        return None
    return [min(flat_lons), min(flat_lats), max(flat_lons), max(flat_lats)]


class UnifiedSourceNormalizer:
    """Normalizes raw connector records and geospatial products into standard observations."""

    @staticmethod
    def normalize_hirise_dtm_observation(
        product_id: str = "DTEEC_045994_1985_046060_1985_U01",
        bbox: list[float] | None = None,
        resolution_m: float = 1.0,
    ) -> NormalizedObservation:
        default_bbox = bbox or [77.385, 18.365, 77.465, 18.465]
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [default_bbox[0], default_bbox[1]],
                    [default_bbox[2], default_bbox[1]],
                    [default_bbox[2], default_bbox[3]],
                    [default_bbox[0], default_bbox[3]],
                    [default_bbox[0], default_bbox[1]],
                ]
            ],
        }
        return NormalizedObservation(
            observation_id=f"obs_hirise_dtm_{product_id}",
            source_id="usgs_astrogeology",
            dataset_id="USGS_HIRISE_TRN_DTM_WINDOW_JEZERO",
            instrument="HiRISE",
            measurement_type="stereo_elevation_dtm",
            measurement_value={"native_resolution_m": 1.0, "vertical_accuracy_m": 0.25},
            units="m",
            geometry=geometry,
            bbox=default_bbox,
            crs="IAU2000:49900",
            timestamp_utc=datetime(2016, 7, 14, 10, 22, tzinfo=UTC),
            spatial_resolution_m=resolution_m,
            vertical_datum="Mars Areoid (MOLA)",
            provenance_kind=ProvenanceKind.DERIVED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["PHOTOGRAMMETRIC_STEREO", "BUNDLE_ADJUSTED_TO_HRSC"],
            uncertainty_info={"vertical_sigma_m": 0.25, "horizontal_accuracy_m": 0.5},
            doi="10.5066/P9REJ9JN",
            official_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_dtm_1m",
            title="USGS HiRISE 1 m Digital Terrain Model (Jezero Crater)",
            description="1.0 m/pixel stereo photogrammetric DTM derived from MRO HiRISE stereo pairs ESP_045994_1985 and ESP_046060_1985.",
            metadata={"product_id": product_id, "mission": "Mars 2020 Terrain Relative Navigation"},
        )

    @staticmethod
    def normalize_hirise_ortho_observation(
        product_id: str = "ESP_045994_1985_RED",
        bbox: list[float] | None = None,
        resolution_m: float = 0.25,
    ) -> NormalizedObservation:
        default_bbox = bbox or [77.380, 18.360, 77.470, 18.470]
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [default_bbox[0], default_bbox[1]],
                    [default_bbox[2], default_bbox[1]],
                    [default_bbox[2], default_bbox[3]],
                    [default_bbox[0], default_bbox[3]],
                    [default_bbox[0], default_bbox[1]],
                ]
            ],
        }
        return NormalizedObservation(
            observation_id=f"obs_hirise_ortho_{product_id}",
            source_id="pds_geosciences",
            dataset_id="HIRISE_JEZERO_ORTHOMOSAIC_25CM",
            instrument="HiRISE",
            measurement_type="orthoimage_reflectance",
            measurement_value={"native_resolution_m": 0.25},
            units="I/F reflectance",
            geometry=geometry,
            bbox=default_bbox,
            crs="IAU2000:49900",
            timestamp_utc=datetime(2016, 7, 14, 10, 22, tzinfo=UTC),
            spatial_resolution_m=resolution_m,
            provenance_kind=ProvenanceKind.MEASURED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["CALIBRATED_RADIANCE", "ORTHORECTIFIED"],
            uncertainty_info={"geometric_residual_m": 0.35},
            doi="10.5066/P9QJDP48",
            official_url="https://astrogeology.usgs.gov/search/map/Mars/Mars2020/JEZ_hirise_soc_006_orthoMosaic_25cm",
            title="HiRISE Jezero Delta 25 cm Controlled Orthomosaic",
            description="Controlled, map-projected high-resolution visual imagery orthorectified to HiRISE TRN DTM.",
            metadata={"product_id": product_id},
        )

    @staticmethod
    def normalize_mola_hrsc_observation() -> NormalizedObservation:
        bbox = [77.0, 18.0, 78.0, 19.0]
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [bbox[0], bbox[1]],
                    [bbox[2], bbox[1]],
                    [bbox[2], bbox[3]],
                    [bbox[0], bbox[3]],
                    [bbox[0], bbox[1]],
                ]
            ],
        }
        return NormalizedObservation(
            observation_id="obs_mola_hrsc_blend_200m",
            source_id="usgs_astrogeology",
            dataset_id="USGS_MOLA_HRSC_BLENDED_DEM_GLOBAL",
            instrument="MOLA/HRSC",
            measurement_type="digital_elevation_model",
            measurement_value={"pixel_resolution_m": 200.0},
            units="m",
            geometry=geometry,
            bbox=bbox,
            crs="IAU2000:49900",
            spatial_resolution_m=200.0,
            vertical_datum="Mars Areoid (MOLA)",
            provenance_kind=ProvenanceKind.DERIVED,
            quality_tier=QualityTier.SILVER,
            quality_flags=["REGIONAL_MOSAIC", "HRSC_BLENDED_MOLA"],
            uncertainty_info={"vertical_sigma_m": 3.0, "horizontal_accuracy_m": 100.0},
            doi="10.5066/P907276M",
            official_url="https://astrogeology.usgs.gov/search/map/Mars/Topography/HRSC_MOLA_Blend/Mars_HRSC_MOLA_BlendDEM_Global_200mp_v2",
            title="USGS MOLA-HRSC Blended Digital Elevation Model (200 m/px)",
            description="Regional/global blended topographic model combining Mars Express HRSC photogrammetry with Mars Global Surveyor MOLA precision altimetry.",
            metadata={"product_id": "MarsHRSC_MOLA_BlendDEM_Global_200mp_v2"},
        )

    @staticmethod
    def normalize_meda_observation(
        sol: int,
        timestamp_utc: datetime,
        air_temp_c: float | None = None,
        ground_temp_c: float | None = None,
        pressure_pa: float | None = None,
        wind_speed_m_s: float | None = None,
        dust_optical_depth_tau: float | None = None,
        lon: float = 77.4508,
        lat: float = 18.4447,
    ) -> NormalizedObservation:
        geometry = {"type": "Point", "coordinates": [lon, lat]}
        measurement_payload: dict[str, Any] = {}
        if air_temp_c is not None:
            measurement_payload["air_temperature_c"] = air_temp_c
        if ground_temp_c is not None:
            measurement_payload["ground_temperature_c"] = ground_temp_c
        if pressure_pa is not None:
            measurement_payload["atmospheric_pressure_pa"] = pressure_pa
        if wind_speed_m_s is not None:
            measurement_payload["wind_speed_m_s"] = wind_speed_m_s
        if dust_optical_depth_tau is not None:
            measurement_payload["dust_optical_depth_tau"] = dust_optical_depth_tau

        return NormalizedObservation(
            observation_id=f"obs_meda_sol_{sol}_{timestamp_utc.strftime('%H%M%S')}",
            source_id="pds_atmospheres",
            dataset_id="M2020_MEDA_CALIBRATED_ENV_DATA",
            instrument="MEDA",
            measurement_type="in_situ_meteorology",
            measurement_value=measurement_payload,
            units="composite",
            geometry=geometry,
            bbox=[lon - 0.001, lat - 0.001, lon + 0.001, lat + 0.001],
            crs="IAU2000:49900",
            timestamp_utc=timestamp_utc,
            martian_sol=sol,
            validity_start_utc=timestamp_utc,
            validity_end_utc=datetime.fromtimestamp(timestamp_utc.timestamp() + 3600, tz=UTC),
            spatial_resolution_m=1.0,
            provenance_kind=ProvenanceKind.MEASURED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["IN_SITU_CALIBRATED", "LEVEL_4_DERIVED"],
            uncertainty_info={
                "temperature_accuracy_c": 1.0,
                "pressure_accuracy_pa": 2.5,
                "wind_accuracy_m_s": 0.5,
            },
            doi="10.17189/1519500",
            official_url="https://pds-atmospheres.nmsu.edu/data_and_services/atmospheres_data/MARS/mars_2020/meda.html",
            title=f"Perseverance MEDA In-Situ Meteorology (Sol {sol})",
            description="Calibrated surface temperature, pressure, wind, and aerosol opacity collected by MEDA on Mars 2020.",
            metadata={"sol": sol},
        )

    @staticmethod
    def normalize_themis_observation(
        product_id: str,
        thermal_inertia: float,
        lon: float,
        lat: float,
        width_deg: float = 0.02,
        height_deg: float = 0.02,
    ) -> NormalizedObservation:
        min_lon = lon - width_deg / 2
        max_lon = lon + width_deg / 2
        min_lat = lat - height_deg / 2
        max_lat = lat + height_deg / 2
        bbox = [min_lon, min_lat, max_lon, max_lat]
        geometry = {
            "type": "Polygon",
            "coordinates": [
                [
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat],
                ]
            ],
        }
        # Classify traversability sinkage / mobility hazard based on thermal inertia
        if thermal_inertia < 150.0:
            hazard_flag = "HIGH_SINKAGE_RISK_UNCONSOLIDATED_DUST"
        elif thermal_inertia < 250.0:
            hazard_flag = "MODERATE_TRACTION_FINE_REGOLITH"
        else:
            hazard_flag = "OPTIMAL_TRACTION_CONSOLIDATED_BEDROCK"

        return NormalizedObservation(
            observation_id=f"obs_themis_{product_id}",
            source_id="themis",
            dataset_id="ODY_THEMIS_NIGHTTIME_THERMAL_INERTIA",
            instrument="THEMIS-IR",
            measurement_type="thermal_inertia",
            measurement_value={
                "thermal_inertia_tiu": thermal_inertia,
                "traversability_classification": hazard_flag,
            },
            units="J m^-2 K^-1 s^-1/2 (tiu)",
            geometry=geometry,
            bbox=bbox,
            crs="IAU2000:49900",
            spatial_resolution_m=100.0,
            provenance_kind=ProvenanceKind.DERIVED,
            quality_tier=QualityTier.GOLD,
            quality_flags=[hazard_flag, "DERIVED_FROM_NIGHT_IR"],
            uncertainty_info={"thermal_inertia_sigma_tiu": 15.0},
            doi="10.1029/2003JE002165",
            official_url="https://themis.asu.edu/",
            title=f"THEMIS Thermal Inertia Observation [{product_id}]",
            description="Derived thermal inertia indicating surface particle size, bedrock fraction, and rover sinkage susceptibility.",
            metadata={"thermal_inertia": thermal_inertia, "product_id": product_id},
        )

    @staticmethod
    def normalize_orbital_observation(
        observation_id: str,
        spacecraft_id: str,
        instrument: str,
        target_name: str,
        center_lon: float,
        center_lat: float,
        footprint_geojson: dict[str, Any] | None,
        resolution_m: float,
        timestamp_utc: datetime,
    ) -> NormalizedObservation:
        geom = footprint_geojson or {"type": "Point", "coordinates": [center_lon, center_lat]}
        bbox = _compute_bbox(geom.get("coordinates", [])) or [
            center_lon - 0.01,
            center_lat - 0.01,
            center_lon + 0.01,
            center_lat + 0.01,
        ]

        return NormalizedObservation(
            observation_id=f"obs_orbit_{observation_id}",
            source_id="naif_spice",
            dataset_id=f"{spacecraft_id.upper()}_{instrument}_ORBITAL_OBS",
            instrument=instrument,
            measurement_type="targeted_orbital_observation",
            measurement_value={"target_name": target_name, "center_lon": center_lon, "center_lat": center_lat},
            units=None,
            geometry=geom,
            bbox=bbox,
            crs="IAU2000:49900",
            timestamp_utc=timestamp_utc,
            spatial_resolution_m=resolution_m,
            provenance_kind=ProvenanceKind.MEASURED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["SPICE_TARGETED", "ORBITAL_FOOTPRINT_VERIFIED"],
            uncertainty_info={"along_track_pointing_error_m": 12.0},
            title=f"{spacecraft_id.upper()} {instrument} Overflight [{target_name}]",
            description=f"High-resolution targeted orbital acquisition by {spacecraft_id.upper()} over {target_name}.",
            metadata={"spacecraft_id": spacecraft_id, "instrument": instrument},
            spacecraft_id=spacecraft_id,
            spacecraft_name=f"Mars Spacecraft ({spacecraft_id.upper()})",
            target_name=target_name,
            acquisition_utc=timestamp_utc.isoformat() if timestamp_utc else None,
            center_lon=center_lon,
            center_lat=center_lat,
            spatial_resolution_m_per_px=resolution_m,
            footprint_geojson=geom,
            pds_product_id=observation_id,
            source_url="https://ode.rsl.wustl.edu/mars/",
            processing_status="PDS_VALIDATED",
        )

    @staticmethod
    def normalize_rover_waypoint(
        waypoint_id: str,
        rover_id: str,
        sol: int,
        lon: float,
        lat: float,
        elevation_m: float | None = None,
        timestamp_utc: datetime | None = None,
        site_name: str | None = None,
    ) -> NormalizedObservation:
        geom = {"type": "Point", "coordinates": [lon, lat]}
        return NormalizedObservation(
            observation_id=f"obs_rover_wp_{rover_id}_{waypoint_id}",
            source_id="planetary_notebook",
            dataset_id=f"{rover_id.upper()}_SURFACE_OPERATIONS_TRAVERSE",
            instrument="HAZCAM/NAVCAM",
            measurement_type="rover_surface_position",
            measurement_value={"site_name": site_name or f"Sol {sol} Site", "elevation_m": elevation_m},
            units="m",
            geometry=geom,
            bbox=[lon - 0.0001, lat - 0.0001, lon + 0.0001, lat + 0.0001],
            crs="IAU2000:49900",
            timestamp_utc=timestamp_utc,
            martian_sol=sol,
            spatial_resolution_m=0.05,
            vertical_datum="Mars Areoid (MOLA)",
            provenance_kind=ProvenanceKind.MEASURED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["ROVER_LOCALIZATION_VALIDATED", "SITE_DRIVE_CONFIRMED"],
            uncertainty_info={"rover_position_accuracy_m": 0.15},
            doi="10.17189/1519565",
            official_url="https://an.rsl.wustl.edu/",
            title=f"{rover_id.capitalize()} Surface Position · Sol {sol} ({site_name or waypoint_id})",
            description=f"Verified ground localization waypoint of the {rover_id.capitalize()} rover.",
            metadata={"rover_id": rover_id, "sol": sol},
        )

    @staticmethod
    def normalize_route_hazard_observation(
        hazard_id: str,
        hazard_type: str,
        severity: str,
        geometry: dict[str, Any],
        measured_slope_deg: float | None = None,
        measured_roughness: float | None = None,
        source_dem_name: str = "USGS HiRISE 1 m DTM",
        source_doi: str = "10.5066/P9REJ9JN",
    ) -> NormalizedObservation:
        bbox = _compute_bbox(geometry.get("coordinates", []))
        values: dict[str, Any] = {"hazard_type": hazard_type, "severity": severity}
        if measured_slope_deg is not None:
            values["slope_deg"] = measured_slope_deg
        if measured_roughness is not None:
            values["roughness"] = measured_roughness

        return NormalizedObservation(
            observation_id=f"obs_hazard_{hazard_id}",
            source_id="marspath_terrain_analyzer",
            dataset_id="MARSPATH_EVIDENCE_HAZARD_CATALOG",
            instrument="Digital Elevation Analysis Engine",
            measurement_type="terrain_traversal_hazard",
            measurement_value=values,
            units="deg / roughness factor",
            geometry=geometry,
            bbox=bbox,
            crs="IAU2000:49900",
            provenance_kind=ProvenanceKind.DERIVED,
            quality_tier=QualityTier.GOLD,
            quality_flags=["DERIVED_FROM_NUMERICAL_DEM", severity],
            uncertainty_info={"grid_cell_resolution_m": 1.0 if "HiRISE" in source_dem_name else 200.0},
            doi=source_doi,
            title=f"Terrain Traversal Hazard: {hazard_type} ({severity})",
            description=f"Steep or rough localized surface anomaly identified from {source_dem_name}.",
            metadata={"severity": severity, "source_dem": source_dem_name},
        )
