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
    observation_id: str | None = Field(default=None, description="Optional catalog observation context (e.g. 'ESP_069176_1985')")
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
