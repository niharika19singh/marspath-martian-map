"""
Scenario & What-If Analysis Engine for MARSPath Mission Intelligence.
Simulates environmental and operational stress-testing against baseline routes:
- Atmospheric dust storm opacity (tau increase)
- Solar power budget degradation
- Instrument/mobility degradation (wheel wear, drive constraints)
- Slope tolerance reduction
- Thermal inertia sinkage hazard penalties
- Direct-to-Earth / Orbiter pass communication constraints
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from backend.app.intelligence.fusion.evidence_model import NormalizedObservation
from backend.app.intelligence.risk_propagation.propagation_engine import (
    RiskPropagationEngine,
    RouteRiskPropagationResult,
)


class ScenarioModifiers(BaseModel):
    """Environmental, rover subsystem, and operational constraint adjustments."""

    tau_atmospheric_increase: float = Field(
        0.0, ge=0.0, le=5.0, description="Additional optical depth tau from dust storm"
    )
    power_budget_factor: float = Field(1.0, ge=0.2, le=1.0, description="Solar/RTG available energy fraction")
    max_slope_ceiling_deg: float = Field(14.0, ge=5.0, le=30.0, description="Rover maximum traversing slope limit")
    max_roughness_limit: float = Field(0.85, ge=0.1, le=1.0, description="Rover rock/roughness tolerance")
    thermal_sinkage_penalty_mult: float = Field(
        1.0, ge=1.0, le=5.0, description="Weighting penalty for low thermal inertia soft regolith"
    )
    wheel_degradation_factor: float = Field(
        1.0, ge=0.3, le=1.0, description="Drive efficiency multiplier (lower = degraded motor/wheel)"
    )
    comm_window_constrained: bool = Field(
        False, description="Enforce strict line-of-sight orbiter communication window"
    )
    spe_radiation_active: bool = Field(False, description="Simulate acute Solar Particle Event (SPE) solar proton flux")
    require_topographic_shelter: bool = Field(
        False, description="Require corridor within reach of designated topographic shelter"
    )


class MissionScenario(BaseModel):
    """Configuration record for a what-if mission scenario."""

    scenario_id: str
    name: str
    description: str
    created_at_utc: str
    baseline_route_id: str
    modifiers: ScenarioModifiers
    tags: list[str] = Field(default_factory=list)


class ScenarioCreateRequest(BaseModel):
    """Request payload to create a new what-if scenario."""

    name: str
    description: str = ""
    baseline_route_id: str = "primary"
    modifiers: ScenarioModifiers = Field(default_factory=ScenarioModifiers)
    tags: list[str] = Field(default_factory=list)


class ScenarioAnalysisResult(BaseModel):
    """Outcome of risk propagation under specific scenario conditions."""

    scenario_id: str
    scenario_name: str
    evaluated_at_utc: str
    baseline_route_id: str
    modifiers: ScenarioModifiers
    risk_propagation: RouteRiskPropagationResult
    total_distance_m: float
    estimated_relative_effort: float
    constrained_segments_count: int
    impassable_segments_count: int
    hazard_exposure_distance_m: float
    return_margin_feasibility: str  # FEASIBLE, MARGINAL, UNFEASIBLE
    recommendations: list[str]
    disclaimer: str = (
        "Scenario evaluations are deterministic sensitivity analyses based on DEM models and "
        "atmospheric telemetry; they do not represent statistical failure probabilities."
    )


class ScenarioComparisonReport(BaseModel):
    """Side-by-side comparison of a what-if scenario versus nominal baseline."""

    scenario_id: str
    scenario_name: str
    baseline_route_id: str
    baseline_distance_m: float
    scenario_distance_m: float
    delta_distance_m: float
    baseline_relative_effort: float
    scenario_relative_effort: float
    delta_relative_effort: float
    baseline_hazard_exposure_m: float
    scenario_hazard_exposure_m: float
    delta_hazard_exposure_distance_m: float
    baseline_constrained_count: int
    scenario_constrained_count: int
    delta_constrained_segments: int
    baseline_impassable_count: int
    scenario_impassable_count: int
    delta_impassable_segments: int
    baseline_traversability: str
    scenario_traversability: str
    return_feasibility: str
    operational_summary: str
    key_tradeoffs: list[str]
    disclaimer: str = (
        "Relative route scores and estimated relative effort are planning indicators. "
        "No-data cells are never assumed safe."
    )


class ScenarioManager:
    """Manages creation, execution, and comparison of mission scenarios."""

    def __init__(self) -> None:
        self._scenarios: dict[str, MissionScenario] = {}
        self._results: dict[str, ScenarioAnalysisResult] = {}
        self._seed_default_scenarios()

    def _seed_default_scenarios(self) -> None:
        """Seed pre-configured standard Mars mission operational contingencies."""
        defaults = [
            MissionScenario(
                scenario_id="scenario-dust-storm-tau-1-5",
                name="Severe Regional Dust Storm (Δτ +1.5)",
                description="Simulates Jezero atmospheric dust storm opacity surge, degrading optical navigation and solar insolation.",
                created_at_utc=datetime.now(UTC).isoformat(),
                baseline_route_id="primary",
                modifiers=ScenarioModifiers(
                    tau_atmospheric_increase=1.5,
                    power_budget_factor=0.55,
                    max_slope_ceiling_deg=11.0,
                    wheel_degradation_factor=0.85,
                ),
                tags=["dust_storm", "environmental", "high_contingency"],
            ),
            MissionScenario(
                scenario_id="scenario-wheel-tread-wear",
                name="Degraded Wheel Drive & Low Regolith Caution",
                description="Elevated wheel wear requiring strict avoidance of soft regolith ripples and steep bedrock outcrops.",
                created_at_utc=datetime.now(UTC).isoformat(),
                baseline_route_id="primary",
                modifiers=ScenarioModifiers(
                    max_slope_ceiling_deg=10.0,
                    thermal_sinkage_penalty_mult=2.5,
                    wheel_degradation_factor=0.6,
                ),
                tags=["subsystem_wear", "mobility", "thermal_inertia"],
            ),
            MissionScenario(
                scenario_id="scenario-strict-science-return",
                name="Strict Return Margin & Orbiter Pass Window",
                description="Constrains traverse duration to guaranteed MRO/TGO UHF relay windows and maximum slope limit 12°.",
                created_at_utc=datetime.now(UTC).isoformat(),
                baseline_route_id="primary",
                modifiers=ScenarioModifiers(
                    max_slope_ceiling_deg=12.0,
                    comm_window_constrained=True,
                    power_budget_factor=0.85,
                ),
                tags=["telecom", "relay", "science_priority"],
            ),
            MissionScenario(
                scenario_id="scenario-spe-radiation-storm",
                name="Solar Particle Event (SPE) Class X2.5 Flare",
                description="Simulates acute coronal mass ejection (CME) solar proton flux (~48.5 mSv/h) requiring immediate topographic shelter diversion or habitat abort.",
                created_at_utc=datetime.now(UTC).isoformat(),
                baseline_route_id="primary",
                modifiers=ScenarioModifiers(
                    max_slope_ceiling_deg=11.0,
                    spe_radiation_active=True,
                    require_topographic_shelter=True,
                    power_budget_factor=0.75,
                ),
                tags=["radiation", "solar_particle_event", "astronaut_survival", "contingency"],
            ),
        ]
        for s in defaults:
            self._scenarios[s.scenario_id] = s

    def create_scenario(self, req: ScenarioCreateRequest) -> MissionScenario:
        sc_id = f"scenario-{uuid.uuid4().hex[:8]}"
        scenario = MissionScenario(
            scenario_id=sc_id,
            name=req.name,
            description=req.description,
            created_at_utc=datetime.now(UTC).isoformat(),
            baseline_route_id=req.baseline_route_id,
            modifiers=req.modifiers,
            tags=req.tags,
        )
        self._scenarios[sc_id] = scenario
        return scenario

    def get_scenario(self, scenario_id: str) -> MissionScenario | None:
        return self._scenarios.get(scenario_id)

    def list_scenarios(self) -> list[MissionScenario]:
        return list(self._scenarios.values())

    def analyze_scenario(
        self,
        scenario_id: str,
        route_data: dict[str, Any],
        observations: list[NormalizedObservation],
    ) -> ScenarioAnalysisResult:
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise KeyError(f"Scenario {scenario_id} not found")

        mods = scenario.modifiers
        # Run risk propagation engine with scenario modified parameters
        risk_res = RiskPropagationEngine.evaluate_route(
            route_data=route_data,
            observations=observations,
            max_slope_ceiling_deg=mods.max_slope_ceiling_deg,
            max_roughness_limit=mods.max_roughness_limit,
        )

        # Apply scenario modifiers to effort and feasibility
        # Atmospheric dust & wheel degradation increase effort multiplier
        effort_mult = (1.0 / max(0.2, mods.wheel_degradation_factor)) * (1.0 + mods.tau_atmospheric_increase * 0.25)
        adjusted_effort = round(risk_res.relative_route_effort_index * effort_mult, 2)

        # Count constrained and impassable segments
        impassable_count = sum(1 for s in risk_res.segment_evaluations if s.operational_status == "IMPASSABLE")
        constrained_count = sum(1 for s in risk_res.segment_evaluations if s.operational_status == "CONSTRAINED")

        # Total distance
        total_dist_m = sum(s.distance_m for s in risk_res.segment_evaluations)

        # Return margin feasibility
        if impassable_count > 0 or adjusted_effort > 3.0:
            return_feasibility = "UNFEASIBLE"
        elif constrained_count > (len(risk_res.segment_evaluations) * 0.4) or adjusted_effort > 1.8:
            return_feasibility = "MARGINAL"
        else:
            return_feasibility = "FEASIBLE"

        # Actionable recommendations
        recs: list[str] = []
        if mods.tau_atmospheric_increase > 1.0:
            recs.append(
                "Restrict single-sol drive distance to <60 m due to low contrast auto-navigation hazard camera range."
            )
        if mods.power_budget_factor < 0.7:
            recs.append(
                "Park rover in northern slope attitude during overnight sleep to optimize solar array angle at dawn."
            )
        if impassable_count > 0:
            recs.append(
                f"Route contains {impassable_count} segments exceeding {mods.max_slope_ceiling_deg}° slope ceiling; plan detour via crater delta bench."
            )
        if mods.comm_window_constrained:
            recs.append("Traverse must halt 45 minutes prior to MRO UHF overflight pass for mast pointing calibration.")
        if not recs:
            recs.append("Nominal traverse conditions under current scenario parameter tolerances.")

        res = ScenarioAnalysisResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            evaluated_at_utc=datetime.now(UTC).isoformat(),
            baseline_route_id=scenario.baseline_route_id,
            modifiers=mods,
            risk_propagation=risk_res,
            total_distance_m=round(total_dist_m, 1),
            estimated_relative_effort=adjusted_effort,
            constrained_segments_count=constrained_count,
            impassable_segments_count=impassable_count,
            hazard_exposure_distance_m=risk_res.hazard_exposure_distance_m,
            return_margin_feasibility=return_feasibility,
            recommendations=recs,
        )
        self._results[scenario_id] = res
        return res

    def compare_scenario(
        self,
        scenario_id: str,
        baseline_route_data: dict[str, Any],
        observations: list[NormalizedObservation],
    ) -> ScenarioComparisonReport:
        scenario = self.get_scenario(scenario_id)
        if not scenario:
            raise KeyError(f"Scenario {scenario_id} not found")

        # Nominal baseline evaluation (default 14 deg slope ceiling, no modifier penalties)
        baseline_risk = RiskPropagationEngine.evaluate_route(
            route_data=baseline_route_data,
            observations=observations,
            max_slope_ceiling_deg=14.0,
            max_roughness_limit=0.85,
        )
        baseline_dist = sum(s.distance_m for s in baseline_risk.segment_evaluations)
        baseline_constrained = sum(
            1 for s in baseline_risk.segment_evaluations if s.operational_status == "CONSTRAINED"
        )
        baseline_impassable = sum(1 for s in baseline_risk.segment_evaluations if s.operational_status == "IMPASSABLE")

        # Scenario evaluation
        sc_res = self.analyze_scenario(scenario_id, baseline_route_data, observations)

        delta_dist = round(sc_res.total_distance_m - baseline_dist, 1)
        delta_effort = round(sc_res.estimated_relative_effort - baseline_risk.relative_route_effort_index, 2)
        delta_haz_exp = round(sc_res.hazard_exposure_distance_m - baseline_risk.hazard_exposure_distance_m, 1)
        delta_constrained = sc_res.constrained_segments_count - baseline_constrained
        delta_impassable = sc_res.impassable_segments_count - baseline_impassable

        tradeoffs: list[str] = [
            f"Estimated relative effort shifts from {baseline_risk.relative_route_effort_index:.2f} to {sc_res.estimated_relative_effort:.2f} (Δ {delta_effort:+.2f}).",
            f"Hazard exposure changes by {delta_haz_exp:+.1f} m.",
            f"Constrained segments change by {delta_constrained:+d}, impassable segments by {delta_impassable:+d}.",
            f"Return feasibility evaluated as {sc_res.return_margin_feasibility}.",
        ]

        summary = (
            f"Comparison of scenario '{scenario.name}' against baseline route '{scenario.baseline_route_id}'. "
            f"Operational state shifts to {sc_res.risk_propagation.overall_traversability_state}. "
            f"Return feasibility is {sc_res.return_margin_feasibility}."
        )

        return ScenarioComparisonReport(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.name,
            baseline_route_id=scenario.baseline_route_id,
            baseline_distance_m=round(baseline_dist, 1),
            scenario_distance_m=round(sc_res.total_distance_m, 1),
            delta_distance_m=delta_dist,
            baseline_relative_effort=round(baseline_risk.relative_route_effort_index, 2),
            scenario_relative_effort=round(sc_res.estimated_relative_effort, 2),
            delta_relative_effort=delta_effort,
            baseline_hazard_exposure_m=baseline_risk.hazard_exposure_distance_m,
            scenario_hazard_exposure_m=sc_res.hazard_exposure_distance_m,
            delta_hazard_exposure_distance_m=delta_haz_exp,
            baseline_constrained_count=baseline_constrained,
            scenario_constrained_count=sc_res.constrained_segments_count,
            delta_constrained_segments=delta_constrained,
            baseline_impassable_count=baseline_impassable,
            scenario_impassable_count=sc_res.impassable_segments_count,
            delta_impassable_segments=delta_impassable,
            baseline_traversability=baseline_risk.overall_traversability_state,
            scenario_traversability=sc_res.risk_propagation.overall_traversability_state,
            return_feasibility=sc_res.return_margin_feasibility,
            operational_summary=summary,
            key_tradeoffs=tradeoffs,
        )


# Global singleton scenario manager instance
scenario_manager = ScenarioManager()
