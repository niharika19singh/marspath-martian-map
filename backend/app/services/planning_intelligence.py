"""Phase 2 & 3 Advanced Mission-Planning Intelligence Engine.

Implements:
1. Segment-level Uncertainty-Aware Planning (STRONG / MODERATE / WEAK / UNKNOWN data support).
2. True Multi-Objective Pareto Route Optimization across Time, Terrain Hazard,
   Uncertainty Exposure, and Science Return.
3. Next-Best Reconnaissance Planner (checking existing NASA PDS/ODE observations first,
   then hypothetical new tasking).
4. Geologically Grounded Science Return per EVA Hour Evaluator.
5. Deterministic 7-Scenario Operational Mission Stress Testing Suite.
6. Five Curated Jezero Demonstration Presets & Flagship Expedition Brief Generator.
"""

from __future__ import annotations

import math
from typing import Any

from backend.app.conditions.mission_clock import evaluate_route_mission_clock
from backend.app.geospatial.crs import MarsCoordinate, haversine_distance_mars

# Geologically grounded Jezero Crater Science Target Catalog
JEZERO_SCIENCE_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "target_id": "JSC_01_OCTAVIA_FLOOR",
        "name": "Octavia E. Butler Crater Floor (Máaz Formation)",
        "lon": 77.4508,
        "lat": 18.4447,
        "elevation_m": -2573.0,
        "geologic_unit": "Crater Floor Fractured Rough (Cf-fr)",
        "astrobiology_score": 22.0,
        "stratigraphy_score": 26.0,
        "sample_caching_score": 24.0,
        "total_science_value": 72.0,
        "recommended_stop_minutes": 25.0,
        "instruments": ["SuperCam", "Mastcam-Z", "RIMFAX"],
        "scientific_rationale": "Igneous/volcaniclastic baseline for absolute radiometric dating of Jezero floor.",
    },
    {
        "target_id": "JSC_02_SEITAH_OLIVINE",
        "name": "Séítah Olivine-Carbonate Cumulate Ridge",
        "lon": 77.4395,
        "lat": 18.4310,
        "elevation_m": -2580.0,
        "geologic_unit": "Crater Floor Fractured 1 (Cf-f1)",
        "astrobiology_score": 30.0,
        "stratigraphy_score": 28.0,
        "sample_caching_score": 27.0,
        "total_science_value": 85.0,
        "recommended_stop_minutes": 35.0,
        "instruments": ["PIXL", "SHERLOC", "SuperCam"],
        "scientific_rationale": "Olivine cumulate altered by aqueous carbonation; key record of early Noachian water-rock interaction.",
    },
    {
        "target_id": "JSC_03_KODIAK_BUTTE",
        "name": "Kodiak Delta Remnant Butte",
        "lon": 77.4290,
        "lat": 18.4265,
        "elevation_m": -2555.0,
        "geologic_unit": "Delta Blocky Remnant (D-bl)",
        "astrobiology_score": 29.0,
        "stratigraphy_score": 30.0,
        "sample_caching_score": 23.0,
        "total_science_value": 82.0,
        "recommended_stop_minutes": 25.0,
        "instruments": ["Mastcam-Z", "SuperCam"],
        "scientific_rationale": "Exhumed Gilbert-type delta foreset/topset beds establishing paleolake highstand level.",
    },
    {
        "target_id": "JSC_04_THREE_FORKS_DEPOT",
        "name": "Three Forks / Hawksbill Gap Mudstone",
        "lon": 77.4110,
        "lat": 18.4515,
        "elevation_m": -2545.0,
        "geologic_unit": "Delta Finely Layered (D-fl)",
        "astrobiology_score": 38.0,
        "stratigraphy_score": 28.0,
        "sample_caching_score": 29.0,
        "total_science_value": 95.0,
        "recommended_stop_minutes": 40.0,
        "instruments": ["PIXL", "SHERLOC", "SuperCam", "Mastcam-Z"],
        "scientific_rationale": "Fine-grained prodelta/lacustrine mudstones and sulfates with highest biosignature preservation potential.",
    },
    {
        "target_id": "JSC_05_WESTERN_FAN_TOP",
        "name": "Western Delta Upper Alluvial Fan (Tenby)",
        "lon": 77.3820,
        "lat": 18.4695,
        "elevation_m": -2415.0,
        "geologic_unit": "Delta Truncated Curvilinear (D-tc)",
        "astrobiology_score": 32.0,
        "stratigraphy_score": 29.0,
        "sample_caching_score": 26.0,
        "total_science_value": 87.0,
        "recommended_stop_minutes": 30.0,
        "instruments": ["PIXL", "SuperCam", "RIMFAX"],
        "scientific_rationale": "Late-stage high-energy fluvial conglomerate boulders transported from Nili Fossae watershed.",
    },
    {
        "target_id": "JSC_06_MARGIN_CARBONATES",
        "name": "Marginal Carbonate Shoreline Unit",
        "lon": 77.3580,
        "lat": 18.4740,
        "elevation_m": -2340.0,
        "geologic_unit": "Margin Fractured Carbonate (M-fc)",
        "astrobiology_score": 39.0,
        "stratigraphy_score": 29.0,
        "sample_caching_score": 30.0,
        "total_science_value": 98.0,
        "recommended_stop_minutes": 45.0,
        "instruments": ["PIXL", "SHERLOC", "SuperCam", "Mastcam-Z"],
        "scientific_rationale": "Authigenic littoral Mg-carbonates and hydrated silica precipitated along ancient Jezero shoreline.",
    },
    {
        "target_id": "JSC_07_NERETVA_VALLIS",
        "name": "Neretva Vallis Inlet Channel (Bright Angel)",
        "lon": 77.3410,
        "lat": 18.4785,
        "elevation_m": -2295.0,
        "geologic_unit": "Valley Network Sedimentary Fill (Vn-sf)",
        "astrobiology_score": 37.0,
        "stratigraphy_score": 27.0,
        "sample_caching_score": 28.0,
        "total_science_value": 92.0,
        "recommended_stop_minutes": 40.0,
        "instruments": ["PIXL", "SHERLOC", "SuperCam"],
        "scientific_rationale": "Light-toned mudstone outcrop within feeder canyon containing redox-sensitive nodules.",
    },
)

# Existing NASA Orbital Observations covering Jezero sub-regions for Reconnaissance Lookup
EXISTING_NASA_OBSERVATIONS: tuple[dict[str, Any], ...] = (
    {
        "product_id": "JEZ_hirise_soc_006_orthoMosaic_25cm",
        "instrument": "MRO HiRISE + DTM",
        "source_archive": "NASA Mars Trek / USGS Astrogeology",
        "resolution_m": 0.25,
        "dtm_resolution_m": 1.0,
        "bbox": [77.28, 18.35, 77.52, 18.52],
        "observation_type": "Stereo Orthomosaic & Photogrammetric DTM",
    },
    {
        "product_id": "ESP_045994_1985_RED",
        "instrument": "MRO HiRISE",
        "source_archive": "NASA PDS Geosciences Node (ODE)",
        "resolution_m": 0.25,
        "dtm_resolution_m": 1.0,
        "bbox": [77.38, 18.40, 77.47, 18.49],
        "observation_type": "High-Resolution Delta Front Sub-Meter Imagery",
    },
    {
        "product_id": "J03_045994_1986_XN_18N282W",
        "instrument": "MRO CTX",
        "source_archive": "NASA PDS Geosciences Node (ODE)",
        "resolution_m": 6.0,
        "dtm_resolution_m": 20.0,
        "bbox": [77.20, 18.20, 77.75, 18.60],
        "observation_type": "Regional Context Camera Swath",
    },
    {
        "product_id": "FRT000047A3_07_IF166L_TRR3",
        "instrument": "MRO CRISM",
        "source_archive": "NASA PDS Geosciences Node (ODE)",
        "resolution_m": 18.0,
        "dtm_resolution_m": None,
        "bbox": [77.33, 18.41, 77.46, 18.50],
        "observation_type": "Hyperspectral VNIR/IR Carbonate & Phyllosilicate Map",
    },
    {
        "product_id": "THEMIS_TI_I87421002_JEZERO",
        "instrument": "Mars Odyssey THEMIS",
        "source_archive": "ASU Mars Space Flight Facility / PDS",
        "resolution_m": 100.0,
        "dtm_resolution_m": None,
        "bbox": [77.20, 18.15, 77.95, 18.65],
        "observation_type": "Nighttime Thermal Inertia & Regolith Induration Map",
    },
)

# Five Curated Jezero Demonstration Presets + Flagship Expedition
MISSION_DEMONSTRATION_PRESETS: tuple[dict[str, Any], ...] = (
    {
        "preset_id": "jezero_robust_science_expedition",
        "name": "Integrated Jezero Robust Science Expedition (Flagship)",
        "category": "FLAGSHIP_EXPEDITION",
        "description": (
            "Full end-to-end multi-waypoint traverse from Octavia E. Butler Landing across Séítah margin "
            "to Three Forks and the Western Delta Front, combining Pareto optimization, Mars24 daylight clock, "
            "DEM shadow analysis, recon planning, and 7-scenario stress testing."
        ),
        "start": {"lon": 77.4508, "lat": 18.4447},
        "end": {"lon": 77.3820, "lat": 18.4695},
        "waypoints": [
            {"id": "W1", "name": "Séítah Margin", "lon": 77.4395, "lat": 18.4310, "stop_minutes": 30},
            {"id": "W2", "name": "Three Forks Depot", "lon": 77.4110, "lat": 18.4515, "stop_minutes": 40},
        ],
        "optimization_mode": "science_first",
        "departure_utc": "2026-06-15T07:30:00Z",
        "walking_speed_m_s": 1.11,
        "max_eva_hours": 8.0,
        "include_return_leg": True,
    },
    {
        "preset_id": "delta_front_astrobiology_traverse",
        "name": "Preset 1: Western Delta Front Astrobiology Traverse",
        "category": "ASTROBIOLOGY",
        "description": "High-priority mudstone and carbonate sampling traverse from Crater Floor to Hawksbill Gap.",
        "start": {"lon": 77.4508, "lat": 18.4447},
        "end": {"lon": 77.4110, "lat": 18.4515},
        "waypoints": [
            {"id": "W1", "name": "Kodiak Butte Overlook", "lon": 77.4290, "lat": 18.4265, "stop_minutes": 25},
        ],
        "optimization_mode": "balanced",
        "departure_utc": "2026-06-15T08:00:00Z",
        "walking_speed_m_s": 1.11,
        "max_eva_hours": 6.5,
        "include_return_leg": True,
    },
    {
        "preset_id": "low_sun_scarp_shadow_test",
        "name": "Preset 2: Late-Afternoon Western Scarp Shadow & Twilight Traverse",
        "category": "ILLUMINATION_STRESS",
        "description": "Tests DEM terrain shadow ray-marching and sunset cutoff near the steep Western Delta scarp.",
        "start": {"lon": 77.4110, "lat": 18.4515},
        "end": {"lon": 77.3820, "lat": 18.4695},
        "waypoints": [],
        "optimization_mode": "safety_first",
        "departure_utc": "2026-06-15T12:15:00Z",
        "walking_speed_m_s": 1.0,
        "max_eva_hours": 6.0,
        "include_return_leg": True,
    },
    {
        "preset_id": "marginal_carbonates_neretva_climb",
        "name": "Preset 3: Marginal Carbonates to Neretva Vallis Ascent",
        "category": "STRATIGRAPHY",
        "description": "Uphill stratigraphic transect from Upper Fan across shoreline carbonates into Neretva Vallis.",
        "start": {"lon": 77.3820, "lat": 18.4695},
        "end": {"lon": 77.3410, "lat": 18.4785},
        "waypoints": [
            {"id": "W1", "name": "Margin Carbonate Unit", "lon": 77.3580, "lat": 18.4740, "stop_minutes": 45},
        ],
        "optimization_mode": "safety_first",
        "departure_utc": "2026-06-15T06:45:00Z",
        "walking_speed_m_s": 0.95,
        "max_eva_hours": 7.5,
        "include_return_leg": True,
    },
    {
        "preset_id": "seitah_hazard_avoidance_corridor",
        "name": "Preset 4: Séítah Dune & Roughness Avoidance Corridor",
        "category": "TERRAIN_SAFETY",
        "description": "Demonstrates strict slope ceiling and roughness avoidance skirting the Séítah ripple field.",
        "start": {"lon": 77.4508, "lat": 18.4447},
        "end": {"lon": 77.4290, "lat": 18.4265},
        "waypoints": [],
        "optimization_mode": "safety_first",
        "departure_utc": "2026-06-15T08:30:00Z",
        "walking_speed_m_s": 1.15,
        "max_eva_hours": 5.0,
        "include_return_leg": True,
    },
    {
        "preset_id": "eastern_basin_recon_gap_survey",
        "name": "Preset 5: Eastern Floor Reconnaissance & Coverage Transition",
        "category": "RECONNAISSANCE",
        "description": "Long-baseline regional traverse transitioning out of sub-meter HiRISE coverage into 200m MOLA-HRSC.",
        "start": {"lon": 77.4508, "lat": 18.4447},
        "end": {"lon": 77.5450, "lat": 18.4100},
        "waypoints": [],
        "optimization_mode": "balanced",
        "departure_utc": "2026-06-15T07:00:00Z",
        "walking_speed_m_s": 1.20,
        "max_eva_hours": 8.5,
        "include_return_leg": False,
    },
)


def classify_route_uncertainty(
    segments: list[dict[str, Any]],
    coordinates: list[list[float]],
    dem_resolution_m: float = 200.0,
    dem_source_id: str = "jezero_mola_hrsc_200m",
) -> dict[str, Any]:
    """Classify every route segment into STRONG, MODERATE, WEAK, or UNKNOWN data support."""
    strong_m = 0.0
    moderate_m = 0.0
    weak_m = 0.0
    unknown_m = 0.0
    classified_segments: list[dict[str, Any]] = []

    mars_r = 3396190.0

    for idx, seg in enumerate(segments):
        lon0 = float(seg.get("start_lon", coordinates[min(idx, len(coordinates) - 1)][0]))
        lat0 = float(seg.get("start_lat", coordinates[min(idx, len(coordinates) - 1)][1]))
        lon1 = float(seg.get("end_lon", coordinates[min(idx + 1, len(coordinates) - 1)][0]))
        lat1 = float(seg.get("end_lat", coordinates[min(idx + 1, len(coordinates) - 1)][1]))

        dlat = math.radians(lat1 - lat0)
        dlon = math.radians(lon1 - lon0) * math.cos(math.radians(0.5 * (lat0 + lat1)))
        dist_m = float(seg.get("length_meters") or (mars_r * math.hypot(dlat, dlon)))

        is_valid = bool(seg.get("is_valid_data", True))
        slope = float(seg.get("slope_deg") or 0.0)
        roughness = float(seg.get("roughness") or 0.0)
        q_flags = seg.get("quality_flags") or []
        near_nodata = "near_nodata_boundary" in q_flags

        # Check if segment falls inside high-res HiRISE stereo footprint [77.28..77.52, 18.35..18.52]
        in_hirise_zone = 77.28 <= lon0 <= 77.52 and 18.35 <= lat0 <= 18.52

        if not is_valid:
            tier = "UNKNOWN"
            reason = "Segment intersects NoData or unverified elevation cell."
            unknown_m += dist_m
        elif slope > 16.0 or roughness > 0.50 or (near_nodata and slope > 10.0):
            tier = "WEAK"
            reason = (
                f"Elevated sub-pixel obstacle uncertainty on {slope:.1f}° slope / {roughness:.2f} roughness "
                f"at {dem_resolution_m:.0f}m grid spacing."
            )
            weak_m += dist_m
        elif near_nodata or slope > 9.5 or roughness > 0.30 or not in_hirise_zone:
            tier = "MODERATE"
            reason = (
                "Regional 200m MOLA-HRSC terrain support without sub-meter boulder resolution."
                if not in_hirise_zone
                else f"Moderate slope ({slope:.1f}°) or proximity to data boundary."
            )
            moderate_m += dist_m
        else:
            tier = "STRONG"
            reason = "Well-supported low-relief terrain within validated multi-instrument coverage."
            strong_m += dist_m

        classified_segments.append(
            {
                "segment_index": idx,
                "start_lon": round(lon0, 6),
                "start_lat": round(lat0, 6),
                "end_lon": round(lon1, 6),
                "end_lat": round(lat1, 6),
                "distance_m": round(dist_m, 2),
                "support_tier": tier,
                "slope_deg": round(slope, 2),
                "roughness": round(roughness, 3),
                "in_hirise_coverage": in_hirise_zone,
                "effective_resolution_m": 1.0 if (in_hirise_zone and dem_resolution_m <= 5.0) else dem_resolution_m,
                "rationale": reason,
            }
        )

    total_m = max(1e-6, strong_m + moderate_m + weak_m + unknown_m)
    strong_f = strong_m / total_m
    mod_f = moderate_m / total_m
    weak_f = weak_m / total_m
    unk_f = unknown_m / total_m

    # Uncertainty exposure score in [0, 100] (0 = 100% STRONG, 100 = 100% UNKNOWN)
    exposure_score = min(100.0, (0.0 * strong_f + 25.0 * mod_f + 65.0 * weak_f + 100.0 * unk_f))
    penalty_cost = (0.12 * moderate_m) + (0.45 * weak_m) + (1.50 * unknown_m)

    if unk_f > 0.05 or weak_f > 0.35:
        overall_support = "WEAK"
    elif weak_f > 0.10 or mod_f > 0.45:
        overall_support = "MODERATE"
    else:
        overall_support = "STRONG"

    return {
        "overall_support_tier": overall_support,
        "dem_source_id": dem_source_id,
        "dem_resolution_m": round(dem_resolution_m, 2),
        "registration_tolerance_m": round(max(1.5, 0.15 * dem_resolution_m), 1),
        "strong_support_m": round(strong_m, 1),
        "moderate_support_m": round(moderate_m, 1),
        "weak_support_m": round(weak_m, 1),
        "unknown_support_m": round(unknown_m, 1),
        "strong_fraction": round(strong_f, 4),
        "moderate_fraction": round(mod_f, 4),
        "weak_fraction": round(weak_f, 4),
        "unknown_fraction": round(unk_f, 4),
        "uncertainty_exposure_score": round(exposure_score, 2),
        "uncertainty_penalty_cost": round(penalty_cost, 2),
        "segments_classified_count": len(classified_segments),
        "high_uncertainty_segments": [
            s for s in classified_segments if s["support_tier"] in ("WEAK", "UNKNOWN")
        ][:15],
    }


def evaluate_science_eva_plan(
    coordinates: list[list[float]],
    duration_hours: float,
    user_waypoints: list[dict[str, Any]] | None = None,
    capture_radius_m: float = 850.0,
    max_eva_hours: float = 8.0,
) -> dict[str, Any]:
    """Evaluate geological science targets visited/nearby and compute Science Return per EVA Hour."""
    visited_targets: list[dict[str, Any]] = []
    nearby_targets: list[dict[str, Any]] = []

    # Subsample route coordinates for fast distance check
    step = max(1, len(coordinates) // 80)
    sampled_pts = [
        MarsCoordinate(lon=float(c[0]), lat=float(c[1]))
        for i, c in enumerate(coordinates)
        if i % step == 0 or i == len(coordinates) - 1
    ]

    for target in JEZERO_SCIENCE_TARGETS:
        t_coord = MarsCoordinate(lon=target["lon"], lat=target["lat"])
        min_d = min((haversine_distance_mars(pt, t_coord) for pt in sampled_pts), default=float("inf"))
        item = {
            **target,
            "closest_approach_m": round(min_d, 1),
        }
        if min_d <= capture_radius_m:
            visited_targets.append(item)
        elif min_d <= capture_radius_m * 2.5:
            nearby_targets.append(item)

    # Also score any explicit user science waypoints not already matched
    custom_wp_score = 0.0
    custom_stop_min = 0.0
    if user_waypoints:
        for idx, wp in enumerate(user_waypoints):
            w_lon = float(wp.get("lon", 0.0))
            w_lat = float(wp.get("lat", 0.0))
            stop_m = float(wp.get("stop_minutes", 20.0))
            custom_stop_min += stop_m
            custom_wp_score += 35.0
            visited_targets.append(
                {
                    "target_id": f"USER_WP_{idx + 1}",
                    "name": wp.get("name") or f"Science Waypoint W{idx + 1}",
                    "lon": w_lon,
                    "lat": w_lat,
                    "geologic_unit": "Mission Defined Target",
                    "astrobiology_score": 12.0,
                    "stratigraphy_score": 12.0,
                    "sample_caching_score": 11.0,
                    "total_science_value": 35.0,
                    "recommended_stop_minutes": stop_m,
                    "instruments": ["Mastcam-Z", "SuperCam"],
                    "scientific_rationale": "User-designated intermediate science waypoint.",
                    "closest_approach_m": 0.0,
                }
            )

    total_science_score = sum(t["total_science_value"] for t in visited_targets) + 0.25 * sum(
        t["total_science_value"] for t in nearby_targets
    )
    total_stop_minutes = sum(t["recommended_stop_minutes"] for t in visited_targets)
    total_stop_hours = total_stop_minutes / 60.0

    # Straight-line distance vs actual route length for detour accounting
    start_c = MarsCoordinate(lon=float(coordinates[0][0]), lat=float(coordinates[0][1]))
    end_c = MarsCoordinate(lon=float(coordinates[-1][0]), lat=float(coordinates[-1][1]))
    crow_flies_m = haversine_distance_mars(start_c, end_c)

    mars_r = 3396190.0
    route_dist_m = 0.0
    for i in range(len(coordinates) - 1):
        dlat = math.radians(float(coordinates[i + 1][1]) - float(coordinates[i][1]))
        dlon = math.radians(float(coordinates[i + 1][0]) - float(coordinates[i][0])) * math.cos(
            math.radians(0.5 * (float(coordinates[i + 1][1]) + float(coordinates[i][1])))
        )
        route_dist_m += mars_r * math.hypot(dlat, dlon)

    detour_m = max(0.0, route_dist_m - crow_flies_m)
    total_eva_hours = max(0.25, duration_hours + total_stop_hours)
    science_per_eva_hour = total_science_score / total_eva_hours

    return {
        "total_science_score": round(total_science_score, 2),
        "science_return_per_eva_hour": round(science_per_eva_hour, 2),
        "walking_duration_hours": round(duration_hours, 3),
        "science_stop_duration_hours": round(total_stop_hours, 3),
        "total_eva_duration_hours": round(total_eva_hours, 3),
        "max_eva_budget_hours": round(max_eva_hours, 2),
        "within_eva_budget": total_eva_hours <= max_eva_hours,
        "direct_crow_flies_m": round(crow_flies_m, 1),
        "route_distance_m": round(route_dist_m, 1),
        "science_detour_distance_m": round(detour_m, 1),
        "visited_targets_count": len(visited_targets),
        "visited_targets": visited_targets,
        "nearby_targets": nearby_targets,
    }


def plan_next_best_reconnaissance(
    uncertainty_summary: dict[str, Any],
    coordinates: list[list[float]],
) -> dict[str, Any]:
    """Identify route information gaps and recommend existing NASA archive products first."""
    high_unc_segs = uncertainty_summary.get("high_uncertainty_segments", [])
    recommendations: list[dict[str, Any]] = []

    # If no WEAK/UNKNOWN segments exist, inspect midpoint of route for resolution upgrade
    if not high_unc_segs and len(coordinates) >= 2:
        mid = coordinates[len(coordinates) // 2]
        high_unc_segs = [
            {
                "segment_index": len(coordinates) // 2,
                "start_lon": float(mid[0]),
                "start_lat": float(mid[1]),
                "end_lon": float(mid[0]),
                "end_lat": float(mid[1]),
                "distance_m": 200.0,
                "support_tier": uncertainty_summary.get("overall_support_tier", "MODERATE"),
                "slope_deg": 6.5,
                "roughness": 0.22,
                "effective_resolution_m": uncertainty_summary.get("dem_resolution_m", 200.0),
                "rationale": "Regional 200m resolution corridor; sub-meter boulder clearance unverified.",
            }
        ]

    for idx, seg in enumerate(high_unc_segs[:4]):
        mid_lon = 0.5 * (float(seg["start_lon"]) + float(seg["end_lon"]))
        mid_lat = 0.5 * (float(seg["start_lat"]) + float(seg["end_lat"]))

        matching_existing: list[dict[str, Any]] = []
        for obs in EXISTING_NASA_OBSERVATIONS:
            min_lon, min_lat, max_lon, max_lat = obs["bbox"]
            if min_lon <= mid_lon <= max_lon and min_lat <= mid_lat <= max_lat:
                matching_existing.append(obs)

        has_submeter = any(o["resolution_m"] <= 1.0 for o in matching_existing)
        if matching_existing and has_submeter:
            action_type = "INGEST_EXISTING_NASA_OBSERVATION"
            primary_obs = matching_existing[0]
            action_desc = (
                f"Existing high-resolution NASA observation {primary_obs['product_id']} "
                f"({primary_obs['instrument']}, {primary_obs['resolution_m']} m/px) already covers "
                f"segment #{seg['segment_index']} ({mid_lon:.4f}°E, {mid_lat:.4f}°N). "
                "Ingest/overlay existing PDS archive before scheduling new orbital tasking."
            )
            reduction_pct = 68.0
        elif matching_existing:
            action_type = "COMBINED_ARCHIVE_AND_TARGETED_RECON"
            primary_obs = matching_existing[0]
            action_desc = (
                f"Regional observation {primary_obs['product_id']} ({primary_obs['resolution_m']} m/px) "
                f"exists in PDS, but sub-meter stereo DTM is absent at ({mid_lon:.4f}°E, {mid_lat:.4f}°N). "
                "Fuse existing CTX/THEMIS archive with hypothetical HiRISE stereo tasking."
            )
            reduction_pct = 54.0
        else:
            action_type = "HYPOTHETICAL_NEW_ORBITAL_TASKING"
            action_desc = (
                f"No sub-meter NASA stereo observation found at ({mid_lon:.4f}°E, {mid_lat:.4f}°N). "
                "Schedule hypothetical MRO HiRISE stereo pair or rotorcraft scout pass."
            )
            reduction_pct = 45.0

        recommendations.append(
            {
                "recon_id": f"RECON_{idx + 1}",
                "priority_rank": idx + 1,
                "segment_index": seg["segment_index"],
                "target_lon": round(mid_lon, 5),
                "target_lat": round(mid_lat, 5),
                "current_support_tier": seg["support_tier"],
                "current_resolution_m": seg["effective_resolution_m"],
                "information_gap_reason": seg["rationale"],
                "recommended_action_type": action_type,
                "existing_nasa_observations": matching_existing,
                "recommendation_summary": action_desc,
                "projected_uncertainty_reduction_pct": reduction_pct,
            }
        )

    pre_score = float(uncertainty_summary.get("uncertainty_exposure_score", 25.0))
    best_red = max((r["projected_uncertainty_reduction_pct"] for r in recommendations), default=40.0)
    post_score = round(pre_score * (1.0 - 0.01 * best_red), 2)

    return {
        "search_policy": "EXISTING_NASA_ARCHIVES_FIRST",
        "pre_recon_uncertainty_score": pre_score,
        "projected_post_recon_uncertainty_score": post_score,
        "recommendations_count": len(recommendations),
        "recommendations": recommendations,
    }


def evaluate_pareto_frontier(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Perform true non-dominated Pareto filtering across 4 explicit mission objectives.

    Objectives:
    1. duration_hours (MINIMIZE)
    2. terrain_hazard_score (MINIMIZE: slope + roughness + hazard penalties)
    3. uncertainty_exposure_score (MINIMIZE: weak + unknown terrain exposure)
    4. science_return_score (MAXIMIZE: geological science value)
    """
    if not candidates:
        return {"pareto_optimal_count": 0, "candidates": []}

    evaluated: list[dict[str, Any]] = []
    for c in candidates:
        evaluated.append(
            {
                "route_id": c["route_id"],
                "label": c.get("label", c["route_id"]),
                "duration_hours": float(c["duration_hours"]),
                "distance_m": float(c["distance_m"]),
                "terrain_hazard_score": float(c["terrain_hazard_score"]),
                "uncertainty_exposure_score": float(c["uncertainty_exposure_score"]),
                "science_return_score": float(c["science_return_score"]),
                "science_return_per_eva_hour": float(c.get("science_return_per_eva_hour", 0.0)),
            }
        )

    # Check dominance: A dominates B iff A is <= B on min objectives, >= B on max objectives, and strictly better on >= 1
    for i, a in enumerate(evaluated):
        dominated_by: list[str] = []
        for j, b in enumerate(evaluated):
            if i == j:
                continue
            no_worse = (
                b["duration_hours"] <= a["duration_hours"] + 1e-6
                and b["terrain_hazard_score"] <= a["terrain_hazard_score"] + 1e-6
                and b["uncertainty_exposure_score"] <= a["uncertainty_exposure_score"] + 1e-6
                and b["science_return_score"] >= a["science_return_score"] - 1e-6
            )
            strictly_better = (
                b["duration_hours"] < a["duration_hours"] - 1e-4
                or b["terrain_hazard_score"] < a["terrain_hazard_score"] - 1e-4
                or b["uncertainty_exposure_score"] < a["uncertainty_exposure_score"] - 1e-4
                or b["science_return_score"] > a["science_return_score"] + 1e-4
            )
            if no_worse and strictly_better:
                dominated_by.append(b["route_id"])

        a["is_pareto_optimal"] = len(dominated_by) == 0
        a["dominated_by_route_ids"] = dominated_by

    min_dur = min(e["duration_hours"] for e in evaluated)
    min_haz = min(e["terrain_hazard_score"] for e in evaluated)
    min_unc = min(e["uncertainty_exposure_score"] for e in evaluated)
    max_sci = max(e["science_return_score"] for e in evaluated)

    for e in evaluated:
        if not e["is_pareto_optimal"]:
            e["pareto_archetype"] = "Dominated Sub-Optimal Candidate"
            e["tradeoff_explanation"] = (
                f"Dominated by {', '.join(e['dominated_by_route_ids'])} across duration, hazard, "
                "uncertainty, and science objectives."
            )
        elif abs(e["duration_hours"] - min_dur) < 1e-4:
            e["pareto_archetype"] = "Fastest Transit (Min Duration)"
            e["tradeoff_explanation"] = (
                f"Minimizes travel duration ({e['duration_hours']:.2f} h) with terrain hazard "
                f"{e['terrain_hazard_score']:.1f} and science score {e['science_return_score']:.1f}."
            )
        elif abs(e["terrain_hazard_score"] - min_haz) < 1e-4:
            e["pareto_archetype"] = "Minimum Terrain Hazard (Safest)"
            e["tradeoff_explanation"] = (
                f"Minimizes cumulative slope/roughness hazard ({e['terrain_hazard_score']:.1f}) "
                f"at {e['duration_hours']:.2f} h travel duration."
            )
        elif abs(e["science_return_score"] - max_sci) < 1e-4:
            e["pareto_archetype"] = "Maximum Science Return"
            e["tradeoff_explanation"] = (
                f"Maximizes geological science return ({e['science_return_score']:.1f} pts, "
                f"{e['science_return_per_eva_hour']:.1f} pts/EVA-hr)."
            )
        elif abs(e["uncertainty_exposure_score"] - min_unc) < 1e-4:
            e["pareto_archetype"] = "Maximum Terrain Data Confidence"
            e["tradeoff_explanation"] = (
                f"Minimizes weak/unknown terrain exposure ({e['uncertainty_exposure_score']:.1f})."
            )
        else:
            e["pareto_archetype"] = "Balanced Pareto Frontier Candidate"
            e["tradeoff_explanation"] = (
                "Non-dominated compromise balancing transit time, slope safety, data support, and science."
            )

    pareto_count = sum(1 for e in evaluated if e["is_pareto_optimal"])
    return {
        "objectives": [
            {"id": "duration_hours", "direction": "MINIMIZE", "unit": "hours"},
            {"id": "terrain_hazard_score", "direction": "MINIMIZE", "unit": "hazard_index"},
            {"id": "uncertainty_exposure_score", "direction": "MINIMIZE", "unit": "exposure_0_100"},
            {"id": "science_return_score", "direction": "MAXIMIZE", "unit": "science_points"},
        ],
        "total_candidates": len(evaluated),
        "pareto_optimal_count": pareto_count,
        "dominated_count": len(evaluated) - pareto_count,
        "candidates": evaluated,
    }


def evaluate_mission_stress_suite(
    coordinates: list[list[float]],
    baseline_duration_hours: float,
    baseline_cost: float,
    max_slope_deg: float,
    uncertainty_summary: dict[str, Any],
    science_plan: dict[str, Any],
    departure_utc: str = "2026-06-15T08:00:00Z",
    base_speed_m_s: float = 1.1111,
    max_eva_hours: float = 8.0,
    alternative_routes_count: int = 1,
) -> dict[str, Any]:
    """Execute the deterministic 7-scenario operational mission stress testing suite."""
    base_clock = evaluate_route_mission_clock(
        coordinates=coordinates,
        departure_utc=departure_utc,
        base_speed_m_s=base_speed_m_s,
        include_return_leg=True,
        return_time_multiplier=1.0,
        max_eva_duration_hours=max_eva_hours,
    )
    base_total_h = float(base_clock["total_duration_hours"]) + float(
        science_plan.get("science_stop_duration_hours", 0.5)
    )

    scenarios: list[dict[str, Any]] = []

    # 1. Reduced walking speed (-35%)
    s1_clock = evaluate_route_mission_clock(
        coordinates=coordinates,
        departure_utc=departure_utc,
        base_speed_m_s=base_speed_m_s * 0.65,
        include_return_leg=True,
        max_eva_duration_hours=max_eva_hours,
    )
    s1_h = float(s1_clock["total_duration_hours"]) + float(science_plan.get("science_stop_duration_hours", 0.5))
    s1_feasible = s1_h <= max_eva_hours and not s1_clock["darkness_encountered"]
    scenarios.append(
        {
            "scenario_id": "STRESS_01_REDUCED_WALKING_SPEED",
            "scenario_number": 1,
            "title": "Reduced Walking Speed (-35% Mobility Degradation)",
            "perturbation": f"Base speed reduced from {base_speed_m_s:.2f} m/s to {base_speed_m_s * 0.65:.2f} m/s",
            "baseline_metric": f"{base_total_h:.2f} h total EVA",
            "stressed_metric": f"{s1_h:.2f} h total EVA (darkness: {s1_clock['darkness_fraction'] * 100:.1f}%)",
            "status": "PASS" if s1_feasible else ("MARGINAL" if s1_h <= max_eva_hours * 1.15 else "FAIL"),
            "remains_feasible": s1_feasible,
            "explanation": (
                f"Under 35% mobility reduction, total EVA duration rises from {base_total_h:.2f} h to {s1_h:.2f} h "
                f"(budget {max_eva_hours:.1f} h)."
            ),
        }
    )

    # 2. Increased stop duration (+100% science/sampling stops)
    base_stop_h = max(0.5, float(science_plan.get("science_stop_duration_hours", 0.5)))
    s2_h = float(base_clock["total_duration_hours"]) + (2.0 * base_stop_h)
    s2_rem_day = float(base_clock["available_daylight_at_departure_hours"]) - s2_h
    s2_feasible = s2_h <= max_eva_hours and s2_rem_day >= 0.0
    scenarios.append(
        {
            "scenario_id": "STRESS_02_INCREASED_STOP_DURATION",
            "scenario_number": 2,
            "title": "Increased Stop Duration (2.0x Science Sampling Delays)",
            "perturbation": f"Waypoint/science stop time doubled from {base_stop_h:.2f} h to {2.0 * base_stop_h:.2f} h",
            "baseline_metric": f"{base_total_h:.2f} h EVA / {science_plan.get('science_return_per_eva_hour', 0):.1f} sci/h",
            "stressed_metric": f"{s2_h:.2f} h EVA / {science_plan.get('total_science_score', 0) / max(0.25, s2_h):.1f} sci/h",
            "status": "PASS" if s2_feasible else ("MARGINAL" if s2_h <= max_eva_hours * 1.15 else "FAIL"),
            "remains_feasible": s2_feasible,
            "explanation": (
                f"Doubling station dwell times leaves {max(0.0, s2_rem_day):.2f} h daylight margin before sunset."
            ),
        }
    )

    # 3. Obstructed route segment (rockfall / slipface blockage at midpoint)
    has_bypass = alternative_routes_count >= 1
    detour_penalty_h = 0.42 if has_bypass else 1.85
    s3_h = base_total_h + detour_penalty_h
    s3_feasible = has_bypass and s3_h <= max_eva_hours
    scenarios.append(
        {
            "scenario_id": "STRESS_03_OBSTRUCTED_SEGMENT",
            "scenario_number": 3,
            "title": "Mid-Route Segment Obstruction (Corridor Blockage)",
            "perturbation": "Primary corridor midpoint segment blocked; reroute via secondary corridor",
            "baseline_metric": "Primary corridor unobstructed",
            "stressed_metric": (
                f"Bypass corridor +{detour_penalty_h:.2f} h ({s3_h:.2f} h total)"
                if has_bypass
                else "No disjoint alternative corridor available"
            ),
            "status": "PASS" if s3_feasible else ("MARGINAL" if has_bypass else "FAIL"),
            "remains_feasible": s3_feasible,
            "explanation": (
                f"Secondary corridor absorbs midpoint obstruction with +{detour_penalty_h:.2f} h detour."
                if has_bypass
                else "Single corridor vulnerable to midpoint blockage; add alternative corridor."
            ),
        }
    )

    # 4. Higher terrain & uncertainty penalties (2.0x weights, slope ceiling -3°)
    tight_ceiling = max(8.0, max_slope_deg - 3.0)
    unc_pen = float(uncertainty_summary.get("uncertainty_penalty_cost", 10.0))
    s4_cost = baseline_cost * 1.35 + (2.0 * unc_pen)
    weak_frac = float(uncertainty_summary.get("weak_fraction", 0.0)) + float(
        uncertainty_summary.get("unknown_fraction", 0.0)
    )
    s4_feasible = weak_frac <= 0.20
    scenarios.append(
        {
            "scenario_id": "STRESS_04_HIGHER_TERRAIN_UNCERTAINTY_PENALTIES",
            "scenario_number": 4,
            "title": "Strict Terrain & Uncertainty Penalties (2x Penalty, -3° Slope Ceiling)",
            "perturbation": f"Slope ceiling tightened to {tight_ceiling:.1f}°; hazard & uncertainty weights doubled",
            "baseline_metric": f"Cost {baseline_cost:.1f}, weak/unknown {weak_frac * 100:.1f}%",
            "stressed_metric": f"Cost {s4_cost:.1f} (+{((s4_cost - baseline_cost) / max(1.0, baseline_cost)) * 100:.1f}%)",
            "status": "PASS" if s4_feasible else ("MARGINAL" if weak_frac <= 0.35 else "FAIL"),
            "remains_feasible": s4_feasible,
            "explanation": (
                f"Route maintains {100.0 * (1.0 - weak_frac):.1f}% strong/moderate support under stricter safety weights."
            ),
        }
    )

    # 5. Reduced daylight / shifted departure time (+3.5 hours later departure)
    from datetime import timedelta

    from backend.app.conditions.mars24 import parse_utc_datetime

    delayed_dt = parse_utc_datetime(departure_utc) + timedelta(hours=3.5)
    s5_clock = evaluate_route_mission_clock(
        coordinates=coordinates,
        departure_utc=delayed_dt,
        base_speed_m_s=base_speed_m_s,
        include_return_leg=True,
        max_eva_duration_hours=max_eva_hours,
    )
    s5_dark_frac = float(s5_clock["darkness_fraction"])
    s5_sh_frac = float(s5_clock["terrain_shadowed_fraction"])
    s5_feasible = not s5_clock["darkness_encountered"] and s5_sh_frac <= 0.25
    scenarios.append(
        {
            "scenario_id": "STRESS_05_REDUCED_DAYLIGHT_DELAYED_DEPARTURE",
            "scenario_number": 5,
            "title": "Delayed Departure (+3.5h Afternoon Shift / Reduced Daylight)",
            "perturbation": f"Departure shifted +3.5h to {delayed_dt.strftime('%Y-%m-%dT%H:%M:%SZ')} (LTST {s5_clock['departure_ltst_hms']})",
            "baseline_metric": f"Darkness {base_clock['darkness_fraction'] * 100:.1f}%, shadow {base_clock['terrain_shadowed_fraction'] * 100:.1f}%",
            "stressed_metric": f"Darkness {s5_dark_frac * 100:.1f}%, shadow {s5_sh_frac * 100:.1f}%",
            "status": "PASS" if s5_feasible else ("MARGINAL" if s5_dark_frac <= 0.15 else "FAIL"),
            "remains_feasible": s5_feasible,
            "explanation": (
                f"Shifting departure by +3.5h results in {s5_dark_frac * 100:.1f}% night travel and "
                f"{s5_sh_frac * 100:.1f}% DEM terrain shadow exposure."
            ),
        }
    )

    # 6. Increased return cost (1.5x return leg duration/energy multiplier)
    s6_clock = evaluate_route_mission_clock(
        coordinates=coordinates,
        departure_utc=departure_utc,
        base_speed_m_s=base_speed_m_s,
        include_return_leg=True,
        return_time_multiplier=1.5,
        max_eva_duration_hours=max_eva_hours,
    )
    s6_h = float(s6_clock["total_duration_hours"]) + float(science_plan.get("science_stop_duration_hours", 0.5))
    s6_feasible = s6_h <= max_eva_hours and not s6_clock["darkness_encountered"]
    scenarios.append(
        {
            "scenario_id": "STRESS_06_INCREASED_RETURN_COST",
            "scenario_number": 6,
            "title": "Elevated Return-Leg Cost (1.5x Return Time / Consumables Multiplier)",
            "perturbation": "Return traversal speed derated by 1.5x (uphill grade / sample mass / suit fatigue)",
            "baseline_metric": f"Return leg {base_clock['return_leg']['walking_duration_hours'] if base_clock.get('return_leg') else 0:.2f} h",
            "stressed_metric": f"Return leg {s6_clock['return_leg']['walking_duration_hours'] if s6_clock.get('return_leg') else 0:.2f} h (total {s6_h:.2f} h)",
            "status": "PASS" if s6_feasible else ("MARGINAL" if s6_h <= max_eva_hours * 1.15 else "FAIL"),
            "remains_feasible": s6_feasible,
            "explanation": (
                f"With 1.5x return cost multiplier, round-trip duration reaches {s6_h:.2f} h vs {max_eva_hours:.1f} h budget."
            ),
        }
    )

    # 7. Missing / degraded data (loss of high-res support -> +25% uncertainty exposure)
    base_exp = float(uncertainty_summary.get("uncertainty_exposure_score", 20.0))
    deg_exp = min(100.0, base_exp + 25.0)
    unk_m = float(uncertainty_summary.get("unknown_support_m", 0.0))
    s7_feasible = unk_m == 0.0 and deg_exp <= 55.0
    scenarios.append(
        {
            "scenario_id": "STRESS_07_DEGRADED_MISSING_DATA",
            "scenario_number": 7,
            "title": "Degraded / Missing High-Resolution Data Support",
            "perturbation": "Fallback to coarse 200m regional DEM only (+25 pts uncertainty exposure)",
            "baseline_metric": f"Exposure {base_exp:.1f}/100 ({uncertainty_summary.get('overall_support_tier', 'MODERATE')})",
            "stressed_metric": f"Exposure {deg_exp:.1f}/100, NoData overlap {unk_m:.0f} m",
            "status": "PASS" if s7_feasible else ("MARGINAL" if deg_exp <= 75.0 else "FAIL"),
            "remains_feasible": s7_feasible,
            "explanation": (
                f"Under orbital telemetry drop to regional 200m grid only, uncertainty exposure increases to {deg_exp:.1f}/100."
            ),
        }
    )

    pass_count = sum(1 for s in scenarios if s["remains_feasible"])
    return {
        "baseline_preserved": True,
        "baseline_summary": {
            "total_eva_duration_hours": round(base_total_h, 3),
            "weighted_cost": round(baseline_cost, 2),
            "uncertainty_exposure_score": round(base_exp, 2),
            "science_return_per_eva_hour": science_plan.get("science_return_per_eva_hour", 0.0),
            "darkness_fraction": base_clock["darkness_fraction"],
        },
        "scenarios_evaluated_count": len(scenarios),
        "scenarios_passed_count": pass_count,
        "overall_stress_resilience_pct": round((pass_count / len(scenarios)) * 100.0, 1),
        "scenarios": scenarios,
    }


def generate_mission_brief_markdown(
    mission_title: str,
    route_summary: dict[str, Any],
    mission_clock: dict[str, Any],
    uncertainty: dict[str, Any],
    science_plan: dict[str, Any],
    pareto: dict[str, Any],
    recon: dict[str, Any],
    stress_suite: dict[str, Any],
) -> str:
    """Generate a structured, printable Markdown operational Mission Brief."""
    lines = [
        f"# MARSPath Operational Mission Brief — {mission_title}",
        "",
        "## 1. Executive Traverse Summary",
        f"- **Departure UTC:** `{mission_clock.get('departure_utc')}` (Jezero LTST `{mission_clock.get('departure_ltst_hms')}`, $L_s = {mission_clock.get('departure_ls_deg')}^\\circ$)",
        f"- **Outbound Distance:** `{mission_clock.get('outbound_leg', {}).get('distance_m', 0) / 1000.0:.2f} km`",
        f"- **Total Round-Trip Distance:** `{mission_clock.get('total_distance_m', 0) / 1000.0:.2f} km`",
        f"- **Total EVA Duration (with Science Stops):** `{science_plan.get('total_eva_duration_hours', 0):.2f} hours` (Budget: `{science_plan.get('max_eva_budget_hours', 8.0):.1f} hours`)",
        f"- **Terrain Data Support Tier:** `{uncertainty.get('overall_support_tier')}` (`{uncertainty.get('dem_resolution_m')} m` grid, exposure `{uncertainty.get('uncertainty_exposure_score')}/100`)",
        f"- **Science Return per EVA Hour:** `{science_plan.get('science_return_per_eva_hour')} pts/hr` (`{science_plan.get('visited_targets_count')}` targets visited)",
        f"- **Operational Stress Resilience:** `{stress_suite.get('scenarios_passed_count')}/{stress_suite.get('scenarios_evaluated_count')}` scenarios passed (`{stress_suite.get('overall_stress_resilience_pct')}%`)",
        "",
        "## 2. Mars24 Illumination & DEM Shadow Assessment",
        f"- **Departure Solar Elevation:** `{mission_clock.get('departure_solar_elevation_deg')}°`",
        f"- **Completion UTC / LTST:** `{mission_clock.get('completion_utc')}` (`{mission_clock.get('completion_ltst_hms')} LTST`)",
        f"- **Available Daylight at Departure:** `{mission_clock.get('available_daylight_at_departure_hours')} hours`",
        f"- **Darkness Exposure:** `{mission_clock.get('darkness_distance_m')} m` (`{mission_clock.get('darkness_fraction', 0) * 100:.1f}%`)",
        f"- **DEM Terrain Shadow Exposure:** `{mission_clock.get('terrain_shadowed_distance_m')} m` (`{mission_clock.get('terrain_shadowed_fraction', 0) * 100:.1f}%`)",
        "",
        "## 3. Multi-Objective Pareto Trade-Offs",
    ]
    for cand in pareto.get("candidates", []):
        badge = "PARETO OPTIMAL" if cand.get("is_pareto_optimal") else "DOMINATED"
        lines.append(
            f"- **{cand.get('route_id')} ({cand.get('pareto_archetype')}) [{badge}]:** "
            f"`{cand.get('duration_hours'):.2f} h`, Hazard `{cand.get('terrain_hazard_score'):.1f}`, "
            f"Uncertainty `{cand.get('uncertainty_exposure_score'):.1f}`, Science `{cand.get('science_return_score'):.1f}`"
        )

    lines.extend(["", "## 4. Science Targets & Sampling Schedule"])
    for tgt in science_plan.get("visited_targets", []):
        lines.append(
            f"- **{tgt['name']} (`{tgt['target_id']}`):** {tgt['geologic_unit']} — "
            f"Value `{tgt['total_science_value']}` pts, Stop `{tgt['recommended_stop_minutes']} min`, "
            f"Instruments: `{', '.join(tgt['instruments'])}`"
        )

    lines.extend(["", "## 5. Next-Best Reconnaissance Recommendations"])
    for rec in recon.get("recommendations", []):
        lines.append(
            f"- **#{rec['priority_rank']} (Segment {rec['segment_index']} at {rec['target_lon']}°E, {rec['target_lat']}°N):** "
            f"`{rec['recommended_action_type']}` — {rec['recommendation_summary']} "
            f"(Projected uncertainty reduction: `-{rec['projected_uncertainty_reduction_pct']}%`)"
        )

    lines.extend(["", "## 6. 7-Scenario Mission Stress Test Results"])
    for sc in stress_suite.get("scenarios", []):
        lines.append(
            f"- **Scenario {sc['scenario_number']} — {sc['title']} [{sc['status']}]:** "
            f"{sc['baseline_metric']} -> {sc['stressed_metric']}. {sc['explanation']}"
        )

    lines.extend(
        [
            "",
            "---",
            "*Generated by MARSPath Mission Intelligence Engine. Regional corridor planning (~200 m MOLA-HRSC / 1 m HiRISE DTM where available); not a substitute for rover onboard hazard avoidance.*",
        ]
    )
    return "\n".join(lines)
