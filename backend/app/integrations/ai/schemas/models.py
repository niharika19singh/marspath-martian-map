from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AIProviderInfo(BaseModel):
    """Metadata describing an AI model provider and its capability tier."""

    provider_id: str = Field(description="'gemini' or 'azure_foundry'")
    name: str
    is_configured: bool
    model_name: str
    capabilities: list[str] = Field(default_factory=list)
    status_message: str


class MarsScienceChatRequest(BaseModel):
    """User prompt for scientific interpretation or mission assistance."""

    message: str = Field(min_length=1, max_length=2000, description="Natural language scientific question")
    provider: str = Field(default="gemini", description="AI provider to query ('gemini' or 'azure_foundry')")
    observation_id: str | None = Field(
        default=None, description="Optional catalog observation context (e.g. 'ESP_069176_1985')"
    )
    route_id: str | None = Field(default=None, description="Optional active route context")
    conversation_history: list[dict[str, str]] = Field(default_factory=list, description="Previous message turns")


class MarsScienceChatResponse(BaseModel):
    """Structured response from the Mars Science Copilot."""

    reply: str
    provider_used: str
    model_used: str
    scientific_citations: list[dict[str, Any]] = Field(default_factory=list)
    products_referenced: list[str] = Field(default_factory=list)
    uncertainty_notice: str = Field(
        default="AI interpretation represents an explanatory hypothesis based on available orbital and in-situ data; not a definitive physical discovery."
    )
    latency_ms: float = 0.0
    token_count_estimated: int = 0


class RouteExplanationRequest(BaseModel):
    """Request for AI analysis of deterministic route calculation metrics."""

    route_id: str = Field(description="Identifier of computed route (or 'primary')")
    provider: str = Field(default="gemini")
    question: str = Field(
        default="Why was this route corridor selected and what terrain risk trade-offs were made?",
        description="Specific question regarding route optimality or cost penalties",
    )
    include_algorithm_comparison: bool = Field(default=True)
    route_metrics: dict[str, Any] | None = Field(
        default=None,
        description="Optional actual computed route summary and cost breakdown from the routing engine",
    )


class RouteExplanationResponse(BaseModel):
    """Explanatory breakdown of route costs and trade-offs."""

    explanation: str
    route_id: str
    total_distance_km: float
    total_cost: float
    max_slope_deg: float
    risk_category: str
    algorithm_comparison_summary: str | None = None
    provider_used: str
    model_used: str
    latency_ms: float = 0.0


class ImageryInterpretationRequest(BaseModel):
    """Request for geological and morphological visual analysis of a catalog image."""

    product_id: str = Field(description="Catalog product ID, e.g. 'ESP_069176_1985_RDR'")
    provider: str = Field(default="gemini")
    user_prompt: str | None = Field(
        default=None,
        description="Specific focus area, e.g. 'Analyze inverted delta channels and layering'",
    )


class ImageryInterpretationResponse(BaseModel):
    """Grounded visual interpretation of Martian orbital imagery."""

    product_id: str
    instrument: str
    target_name: str
    spatial_resolution_m_per_px: float
    interpretation_summary: str
    visible_morphology: list[str] = Field(default_factory=list)
    candidate_hypotheses: list[str] = Field(default_factory=list)
    scientific_caveats: str = Field(
        default="Visual morphological interpretation is non-unique and must be verified against targeted spectral (CRISM) and in-situ rover ground truth."
    )
    official_archive_url: str
    provider_used: str
    model_used: str
    latency_ms: float = 0.0


class ModelComparisonRequest(BaseModel):
    """Side-by-side prompt submission for comparing Gemini and Azure AI Foundry."""

    question: str = Field(min_length=1, max_length=2000)
    observation_id: str | None = None
    route_id: str | None = None


class ModelComparisonResponse(BaseModel):
    """Side-by-side comparative evaluation results."""

    question: str
    gemini_response: MarsScienceChatResponse
    azure_response: MarsScienceChatResponse | None
    comparison_summary: str
    latency_delta_ms: float | None = None
    citation_alignment_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Agreement between provider citations"
    )


# -------------------------------------------------------------
# AI Mission Intelligence Layer Models
# -------------------------------------------------------------


class NaturalLanguageMissionPlanRequest(BaseModel):
    """User instruction describing a planetary mission in plain language."""

    user_prompt: str = Field(
        min_length=3,
        max_length=1500,
        description="Natural language mission prompt (e.g. 'Find a safe route from the current rover position to Séítah, prioritizing low slope and sufficient return EVA margin.')",
    )
    current_coords: dict[str, float] | None = Field(
        default=None,
        description="Optional current rover position {'lon': float, 'lat': float} if known by frontend",
    )
    provider: str = Field(default="gemini", description="AI provider ('gemini' or 'azure_foundry')")


class NaturalLanguageMissionPlanResponse(BaseModel):
    """Structured, schema-validated mission parameters derived from natural language."""

    extracted_intent: str
    resolved_start: dict[str, Any] = Field(
        description="Start coordinate {'name': str, 'lon': float, 'lat': float, 'is_rover_position': bool}"
    )
    resolved_destination: dict[str, Any] = Field(
        description="Destination coordinate {'name': str, 'lon': float, 'lat': float}"
    )
    routing_profile: str = Field(
        default="balanced",
        description="Deterministic profile: 'safety_first' | 'balanced' | 'science_first'",
    )
    objective: str
    constraints: dict[str, Any] = Field(
        default_factory=dict,
        description="Operational constraints, e.g. eva_time_budget_minutes, max_slope_limit",
    )
    resolved_waypoints: list[dict[str, Any]] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    validated_route_request: dict[str, Any] | None = Field(
        default=None,
        description="Complete JSON payload conforming to POST /api/v1/routes/plan schema",
    )
    ai_reasoning: str
    provider_used: str
    model_used: str
    latency_ms: float = 0.0


class CandidateEvaluation(BaseModel):
    """Structured evaluation of a deterministic route alternative."""

    route_id: str
    name: str
    routing_profile: str
    distance_km: float
    total_cost: float
    max_slope_deg: float
    average_slope_deg: float
    roughness_tri: float
    hazard_penalty: float
    eva_duration_hours: float
    return_feasibility: str
    turnaround_buffer_min: float
    monte_carlo_reliability_pct: float = 90.0
    cost_std_dev: float = 0.0
    mission_fit_verdict: str


class CandidateRouteComparisonRequest(BaseModel):
    """Request for AI-assisted multi-criteria comparison of computed route candidates."""

    routes: list[dict[str, Any]] = Field(
        min_length=1,
        description="List of candidate routes returned by the routing engine",
    )
    mission_objective: str | None = Field(
        default=None,
        description="User's operational objective (e.g. low slope, sample return)",
    )
    provider: str = Field(default="gemini")


class CandidateRouteComparisonResponse(BaseModel):
    """Multi-criteria comparison explaining distance, slope, hazard, and robustness trade-offs."""

    summary: str
    candidate_evaluations: list[CandidateEvaluation]
    tradeoff_analysis: str
    recommended_route_id: str
    recommendation_rationale: str
    grounding_audit: dict[str, Any] = Field(
        description="Verification that all numerical metrics match routing engine outputs"
    )
    provider_used: str
    model_used: str
    latency_ms: float = 0.0


class ScientificEvidenceItem(BaseModel):
    """Structured evidence item distinguishing data types and sensor origins."""

    data_type: str = Field(description="'measured' | 'derived' | 'proxy' | 'synthetic'")
    instrument_or_source: str
    parameter: str
    value_or_finding: str
    provenance_reference: str
    confidence_level: str = "HIGH"


class ScientificTerrainInterpretationRequest(BaseModel):
    """Request for geological, mineralogical, and thermal interpretation of a traversal corridor."""

    route_id: str | None = Field(default="primary")
    route_summary: dict[str, Any] | None = None
    corridor_bounds: list[float] | None = None
    geological_focus: str | None = None
    provider: str = Field(default="gemini")


class ScientificTerrainInterpretationResponse(BaseModel):
    """Scientific terrain assessment referencing real NASA PDS/USGS datasets."""

    geological_setting: str
    measured_data_evidence: list[ScientificEvidenceItem] = Field(default_factory=list)
    derived_metrics_evidence: list[ScientificEvidenceItem] = Field(default_factory=list)
    proxy_indicators_evidence: list[ScientificEvidenceItem] = Field(default_factory=list)
    synthetic_fallback_notice: str | None = None
    mineralogy_and_biosignature_potential: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    provider_used: str
    model_used: str
    latency_ms: float = 0.0


class MissionRiskBriefingRequest(BaseModel):
    """Request for executive risk briefing based on deterministic stress tests and Monte Carlo."""

    selected_route: dict[str, Any] = Field(description="Selected route candidate dictionary")
    operational_stress_suite: dict[str, Any] | None = None
    robustness_assessment: dict[str, Any] | None = None
    turnaround: dict[str, Any] | None = None
    provider: str = Field(default="gemini")


class MissionRiskBriefingResponse(BaseModel):
    """Structured mission risk briefing with contingency corridors and EVA limits."""

    mission_overview: str
    critical_hazards: list[str] = Field(default_factory=list)
    uncertainty_limitations: list[str] = Field(default_factory=list)
    recommended_contingency_corridor: str
    return_feasibility: dict[str, Any]
    contingency_considerations: list[dict[str, Any]] = Field(default_factory=list)
    deterministic_safety_mandate: str = (
        "AI mission guidance is advisory and can never override deterministic engineering safety ceilings."
    )
    provider_used: str
    model_used: str
    latency_ms: float = 0.0
