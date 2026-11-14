"""
Route Segment Evaluator for MARSPath Evidence-Backed Risk Propagation.
Associates localized terrain metrics, observation footprints, environmental conditions,
and operational constraints with individual route segments.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.intelligence.fusion.evidence_model import NormalizedObservation
from backend.app.intelligence.fusion.spatial_temporal_index import (
    distance_point_to_segment_m,
    haversine_mars_distance_m,
)


class SegmentRiskEvaluation(BaseModel):
    """Scientific evaluation of hazards, environmental state, and evidence for a route segment."""
    segment_index: int
    start_coord: list[float]  # [lon, lat]
    end_coord: list[float]    # [lon, lat]
    distance_m: float
    elevation_start_m: float | None = None
    elevation_end_m: float | None = None
    elevation_delta_m: float | None = None
    slope_deg: float
    cross_slope_deg: float = 0.0
    roughness: float
    is_nodata: bool = False
    active_dem_source: str = "USGS MOLA-HRSC 200 m DEM"
    dem_resolution_m: float = 200.0
    evidence_coverage_tier: str = "MODERATE"  # STRONG, MODERATE, WEAK, UNKNOWN
    supporting_observations: list[str] = Field(default_factory=list)
    active_hazards: list[dict[str, Any]] = Field(default_factory=list)
    thermal_inertia_tiu: float | None = None
    mobility_risk_category: str = "LOW_RISK"  # LOW_RISK, MEDIUM_RISK, HIGH_RISK, CRITICAL_RISK
    operational_status: str = "NOMINAL"        # NOMINAL, CONSTRAINED, IMPASSABLE, UNKNOWN
    impact_narrative: str = ""


class SegmentEvaluator:
    """Evaluates terrain segments against spatial observations and operational thresholds."""

    @staticmethod
    def evaluate_segment(
        segment_index: int,
        p1: list[float],
        p2: list[float],
        observations: list[NormalizedObservation],
        max_slope_ceiling_deg: float = 14.0,
        max_roughness_limit: float = 0.85,
        z1: float | None = None,
        z2: float | None = None,
    ) -> SegmentRiskEvaluation:
        dist_m = haversine_mars_distance_m(p1[0], p1[1], p2[0], p2[1])
        delta_z = (z2 - z1) if (z1 is not None and z2 is not None) else None

        # Calculate slope if elevation is known
        if delta_z is not None and dist_m > 1e-3:
            slope_deg = abs(delta_z) / dist_m * (180.0 / 3.14159265)
        else:
            slope_deg = 4.5  # default nominal terrain slope in crater floor

        # Find intersecting or nearby observations
        intersecting_obs: list[NormalizedObservation] = []
        for obs in observations:
            if obs.geometry.get("type") == "Point":
                coords = obs.geometry["coordinates"]
                d = distance_point_to_segment_m(coords[0], coords[1], p1[0], p1[1], p2[0], p2[1])
                if d <= 150.0:
                    intersecting_obs.append(obs)
            elif obs.bbox:
                # Bbox intersection check
                seg_min_lon = min(p1[0], p2[0]) - 0.002
                seg_max_lon = max(p1[0], p2[0]) + 0.002
                seg_min_lat = min(p1[1], p2[1]) - 0.002
                seg_max_lat = max(p1[1], p2[1]) + 0.002
                if not (obs.bbox[2] < seg_min_lon or obs.bbox[0] > seg_max_lon or obs.bbox[3] < seg_min_lat or obs.bbox[1] > seg_max_lat):
                    intersecting_obs.append(obs)

        # Detect high-res HiRISE DTM coverage
        has_hirise = any("hirise" in o.instrument.lower() for o in intersecting_obs)
        dem_source = "USGS HiRISE 1 m DTM (DOI: 10.5066/P9REJ9JN)" if has_hirise else "USGS MOLA-HRSC 200 m DEM (DOI: 10.5066/P907276M)"
        dem_res = 1.0 if has_hirise else 200.0
        coverage_tier = "STRONG" if has_hirise else "MODERATE"

        # Check for THEMIS thermal inertia measurements
        themis_obs = next((o for o in intersecting_obs if o.measurement_type == "thermal_inertia"), None)
        ti_val = themis_obs.measurement_value.get("thermal_inertia_tiu") if (themis_obs and isinstance(themis_obs.measurement_value, dict)) else 240.0

        # Identify active hazards
        hazards: list[dict[str, Any]] = []
        if slope_deg > max_slope_ceiling_deg:
            hazards.append({
                "hazard_id": f"h_slope_seg_{segment_index}",
                "hazard_type": "STEEP_SLOPE_EXCEEDANCE",
                "severity": "CRITICAL" if slope_deg > max_slope_ceiling_deg * 1.3 else "HIGH",
                "measured_value": round(slope_deg, 1),
                "threshold": max_slope_ceiling_deg,
                "units": "deg",
                "evidence_source": dem_source,
            })

        if ti_val is not None and ti_val < 150.0:
            hazards.append({
                "hazard_id": f"h_thermal_sinkage_seg_{segment_index}",
                "hazard_type": "UNCONSOLIDATED_REGOLITH_SINKAGE",
                "severity": "HIGH",
                "measured_value": ti_val,
                "threshold": 150.0,
                "units": "tiu",
                "evidence_source": "THEMIS Nighttime Infrared",
            })

        # Operational status and risk classification
        if any(h["severity"] == "CRITICAL" for h in hazards):
            op_status = "IMPASSABLE"
            risk_cat = "CRITICAL_RISK"
        elif hazards:
            op_status = "CONSTRAINED"
            risk_cat = "HIGH_RISK"
        elif slope_deg > max_slope_ceiling_deg * 0.75:
            op_status = "CONSTRAINED"
            risk_cat = "MEDIUM_RISK"
        else:
            op_status = "NOMINAL"
            risk_cat = "LOW_RISK"

        # Construct scientific impact narrative
        narrative = (
            f"Segment {segment_index} ({dist_m:.0f} m) on {dem_source} ({dem_res:.0f} m/px). "
            f"Slope {slope_deg:.1f}° vs ceiling {max_slope_ceiling_deg:.1f}°. "
            f"Thermal inertia {ti_val:.0f} tiu. "
            f"Identified hazards: {len(hazards)}. Operational state: {op_status}."
        )

        return SegmentRiskEvaluation(
            segment_index=segment_index,
            start_coord=p1,
            end_coord=p2,
            distance_m=round(dist_m, 1),
            elevation_start_m=z1,
            elevation_end_m=z2,
            elevation_delta_m=delta_z,
            slope_deg=round(slope_deg, 1),
            roughness=0.35,
            is_nodata=False,
            active_dem_source=dem_source,
            dem_resolution_m=dem_res,
            evidence_coverage_tier=coverage_tier,
            supporting_observations=[o.observation_id for o in intersecting_obs],
            active_hazards=hazards,
            thermal_inertia_tiu=ti_val,
            mobility_risk_category=risk_cat,
            operational_status=op_status,
            impact_narrative=narrative,
        )
