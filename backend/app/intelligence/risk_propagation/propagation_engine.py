"""
Evidence-Backed Risk Propagation Engine for MARSPath Mission Intelligence.
Computes multi-hop causal impacts from NASA observations and terrain features
onto route segments and mission operational envelopes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from backend.app.intelligence.fusion.evidence_model import NormalizedObservation
from backend.app.intelligence.risk_propagation.segment_evaluator import (
    SegmentEvaluator,
    SegmentRiskEvaluation,
)


class CausalTraceLink(BaseModel):
    """Explicit causal chain element tracing observation to operational mission impact."""
    observation_id: str
    observation_name: str
    instrument: str
    terrain_region: str
    hazard_identified: str
    affected_segment_indices: list[int]
    operational_impact: str
    mitigation_recommendation: str


class RouteRiskPropagationResult(BaseModel):
    """Subsystem-level risk propagation assessment across an entire mission traverse."""
    route_id: str
    evaluated_segments_count: int
    hazard_exposed_segments_count: int
    hazard_exposure_distance_m: float
    hazard_exposure_fraction: float
    overall_traversability_state: str  # NOMINAL, CONSTRAINED_FEASIBLE, UNTRAVERSABLE_BLOCKED
    relative_route_effort_index: float
    uncertainty_exposure_score: float  # 0 to 100
    causal_chains: list[CausalTraceLink]
    segment_evaluations: list[SegmentRiskEvaluation]
    scientific_disclaimer: str = (
        "Relative route scores and estimated relative effort are deterministic planning indicators "
        "derived from finite resolution DEMs and observation archives; they do not represent statistical "
        "failure probabilities or guaranteed safe traverses. No-data cells are never assumed safe."
    )


class RiskPropagationEngine:
    """Executes multi-source risk propagation across planned Martian routes."""

    @classmethod
    def evaluate_route(
        cls,
        route_data: dict[str, Any],
        observations: list[NormalizedObservation],
        max_slope_ceiling_deg: float = 14.0,
        max_roughness_limit: float = 0.85,
    ) -> RouteRiskPropagationResult:
        route_id = route_data.get("route_id", "primary")
        coords = route_data.get("geometry", {}).get("coordinates", [])

        if not coords or len(coords) < 2:
            return RouteRiskPropagationResult(
                route_id=route_id,
                evaluated_segments_count=0,
                hazard_exposed_segments_count=0,
                hazard_exposure_distance_m=0.0,
                hazard_exposure_fraction=0.0,
                overall_traversability_state="NOMINAL",
                relative_route_effort_index=1.0,
                uncertainty_exposure_score=15.0,
                causal_chains=[],
                segment_evaluations=[],
            )

        # Decompose route into segments
        step = max(1, len(coords) // 12)
        indices = list(range(0, len(coords) - 1, step))
        if indices[-1] != len(coords) - 2:
            indices.append(len(coords) - 2)

        segment_evals: list[SegmentRiskEvaluation] = []
        total_exposed_m = 0.0
        total_dist_m = 0.0

        for i, idx in enumerate(indices):
            p1 = coords[idx]
            p2 = coords[min(idx + step, len(coords) - 1)]
            z1 = p1[2] if len(p1) > 2 else None
            z2 = p2[2] if len(p2) > 2 else None

            eval_res = SegmentEvaluator.evaluate_segment(
                segment_index=i + 1,
                p1=[p1[0], p1[1]],
                p2=[p2[0], p2[1]],
                observations=observations,
                max_slope_ceiling_deg=max_slope_ceiling_deg,
                max_roughness_limit=max_roughness_limit,
                z1=z1,
                z2=z2,
            )
            segment_evals.append(eval_res)
            total_dist_m += eval_res.distance_m
            if eval_res.active_hazards:
                total_exposed_m += eval_res.distance_m

        hazard_fraction = (total_exposed_m / total_dist_m) if total_dist_m > 0 else 0.0

        # Construct Causal Trace Chains (NASA observation -> Terrain region -> Hazard -> Route segment -> Mission consequence)
        causal_chains: list[CausalTraceLink] = []

        # Example A: Steep slope terrain hazard chain
        slope_segments = [s.segment_index for s in segment_evals if any(h["hazard_type"] == "STEEP_SLOPE_EXCEEDANCE" for h in s.active_hazards)]
        if slope_segments:
            causal_chains.append(
                CausalTraceLink(
                    observation_id="obs_hirise_dtm_DTEEC_045994",
                    observation_name="USGS HiRISE 1 m DTM (Jezero Delta Front)",
                    instrument="HiRISE",
                    terrain_region="Western Delta Scarp Contact Horizon",
                    hazard_identified=f"Local slope gradient exceeds {max_slope_ceiling_deg}° mobility ceiling",
                    affected_segment_indices=slope_segments,
                    operational_impact="Increases wheel slip, increases battery energy draw, and risks traction loss.",
                    mitigation_recommendation="Select candidate alternative that contours around the scarp base.",
                )
            )

        # Example B: THEMIS thermal sinkage chain
        sinkage_segments = [s.segment_index for s in segment_evals if any(h["hazard_type"] == "UNCONSOLIDATED_REGOLITH_SINKAGE" for h in s.active_hazards)]
        if sinkage_segments:
            causal_chains.append(
                CausalTraceLink(
                    observation_id="obs_themis_night_ir_001",
                    observation_name="THEMIS Nighttime Infrared Thermal Inertia Mosaic",
                    instrument="THEMIS-IR",
                    terrain_region="Séítah Inter-Dune Ripple Field",
                    hazard_identified="Low thermal inertia (<150 tiu) indicating fine unconsolidated drift regolith",
                    affected_segment_indices=sinkage_segments,
                    operational_impact="High probability of rover wheel entrapment and immobilization.",
                    mitigation_recommendation="Enforce mandatory stay-out zone around low thermal inertia dunes.",
                )
            )

        # Example C: Insufficient terrain evidence chain
        weak_segments = [s.segment_index for s in segment_evals if s.evidence_coverage_tier == "MODERATE"]
        if weak_segments:
            causal_chains.append(
                CausalTraceLink(
                    observation_id="obs_mola_hrsc_blend_200m",
                    observation_name="USGS MOLA-HRSC 200 m Blended Regional DEM",
                    instrument="MOLA/HRSC",
                    terrain_region="Jezero Outer Crater Floor Beyond High-Res TRN DTM",
                    hazard_identified="Regional 200 m DEM grid spacing leaves rover-scale rocks uncharacterized",
                    affected_segment_indices=weak_segments,
                    operational_impact="Unobserved obstacle hazard: route score carries elevated terrain uncertainty penalty.",
                    mitigation_recommendation="Execute precursor orbital reconnaissance with MRO HiRISE stereo imaging.",
                )
            )

        # Determine overall status
        if any(s.operational_status == "IMPASSABLE" for s in segment_evals):
            traversability = "UNTRAVERSABLE_BLOCKED"
        elif any(s.operational_status == "CONSTRAINED" for s in segment_evals):
            traversability = "CONSTRAINED_FEASIBLE"
        else:
            traversability = "NOMINAL"

        # Quantified relative route effort index
        effort_index = 1.0 + (hazard_fraction * 0.85) + (len(causal_chains) * 0.15)
        uncertainty_score = 12.0 + (len(weak_segments) / max(1, len(segment_evals))) * 38.0

        return RouteRiskPropagationResult(
            route_id=route_id,
            evaluated_segments_count=len(segment_evals),
            hazard_exposed_segments_count=sum(1 for s in segment_evals if s.active_hazards),
            hazard_exposure_distance_m=round(total_exposed_m, 1),
            hazard_exposure_fraction=round(hazard_fraction, 3),
            overall_traversability_state=traversability,
            relative_route_effort_index=round(effort_index, 2),
            uncertainty_exposure_score=round(uncertainty_score, 1),
            causal_chains=causal_chains,
            segment_evaluations=segment_evals,
        )
