from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.integrations.ai.schemas.models import (
    AIProviderInfo,
    CandidateRouteComparisonRequest,
    CandidateRouteComparisonResponse,
    ImageryInterpretationRequest,
    ImageryInterpretationResponse,
    MarsScienceChatRequest,
    MarsScienceChatResponse,
    MissionRiskBriefingRequest,
    MissionRiskBriefingResponse,
    ModelComparisonRequest,
    ModelComparisonResponse,
    NaturalLanguageMissionPlanRequest,
    NaturalLanguageMissionPlanResponse,
    RouteExplanationRequest,
    RouteExplanationResponse,
    ScientificTerrainInterpretationRequest,
    ScientificTerrainInterpretationResponse,
)
from backend.app.integrations.ai.services.mars_science_assistant import get_science_assistant

router = APIRouter(prefix="/ai", tags=["Mars Science Copilot & AI Integrations"])


class AICopilotStatus(BaseModel):
    """Operational status of Mars Science Copilot and configured providers."""

    active_provider: str = "Google Gemini (Primary)"
    secondary_provider: str = "Microsoft Azure AI Foundry (Evaluation Mode)"
    gemini_configured: bool = False
    azure_configured: bool = False
    available_providers: list[AIProviderInfo] = Field(default_factory=list)
    system_caveat: str = (
        "AI interpretations represent explanatory scientific hypotheses based on available NASA archives; "
        "they do not override deterministic route safety constraints."
    )


@router.get("/providers", response_model=list[AIProviderInfo], summary="Enumerate AI model providers")
async def list_ai_providers() -> list[AIProviderInfo]:
    """Returns capabilities and configuration status for Gemini and Azure AI Foundry."""
    assistant = get_science_assistant()
    return assistant.list_providers()


@router.get("/status", response_model=AICopilotStatus, summary="Mars Science Copilot operational status")
async def get_ai_status() -> AICopilotStatus:
    """Returns active models, capability tiers, and configuration flags."""
    assistant = get_science_assistant()
    providers = assistant.list_providers()

    gemini_info = next((p for p in providers if p.provider_id == "gemini"), None)
    azure_info = next((p for p in providers if p.provider_id == "azure_foundry"), None)

    return AICopilotStatus(
        active_provider="Google Gemini (Primary)",
        secondary_provider="Microsoft Azure AI Foundry (Evaluation Mode)",
        gemini_configured=gemini_info.is_configured if gemini_info else False,
        azure_configured=azure_info.is_configured if azure_info else False,
        available_providers=providers,
    )


@router.post("/mars-science/chat", response_model=MarsScienceChatResponse, summary="Query Mars Science Copilot")
async def chat_mars_science(request: MarsScienceChatRequest) -> MarsScienceChatResponse:
    """Answers planetary questions grounded in catalog observations, rover telemetry, and DOIs."""
    assistant = get_science_assistant()
    return await assistant.chat(request)


@router.post("/route/explain", response_model=RouteExplanationResponse, summary="Explain route optimization decisions")
async def explain_route_decision(request: RouteExplanationRequest) -> RouteExplanationResponse:
    """Provides grounded explanation of route costs, terrain penalties, slope bounds, and algorithm optimality."""
    assistant = get_science_assistant()
    return await assistant.explain_route(request)


@router.post("/imagery/analyze", response_model=ImageryInterpretationResponse, summary="Interpret orbital imagery")
async def analyze_imagery_geology(request: ImageryInterpretationRequest) -> ImageryInterpretationResponse:
    """Performs visual morphological analysis on a specified HiRISE or CTX observation with scientific caveats."""
    assistant = get_science_assistant()
    return await assistant.interpret_imagery(request)


@router.post("/models/compare", response_model=ModelComparisonResponse, summary="Compare Gemini vs Azure AI Foundry")
async def compare_ai_models(request: ModelComparisonRequest) -> ModelComparisonResponse:
    """Executes side-by-side prompt against both Gemini and Azure AI Foundry for comparative evaluation."""
    assistant = get_science_assistant()
    return await assistant.compare_models(request)


# ---------------------------------------------------------------------
# AI Mission Intelligence Layer Endpoints
# ---------------------------------------------------------------------


@router.post(
    "/mission/plan-from-prompt",
    response_model=NaturalLanguageMissionPlanResponse,
    summary="Natural-language mission planning and intent extraction",
)
async def plan_mission_from_natural_language(
    request: NaturalLanguageMissionPlanRequest,
) -> NaturalLanguageMissionPlanResponse:
    """Translates user mission objectives into validated, schema-compliant routing parameters.
    Resolves Jezero landmarks, detects out-of-bounds requests, and produces executable route requests.
    """
    assistant = get_science_assistant()
    return await assistant.plan_mission_from_prompt(request)


@router.post(
    "/routes/compare-candidates",
    response_model=CandidateRouteComparisonResponse,
    summary="AI multi-criteria comparison of candidate routes",
)
async def compare_route_candidates(
    request: CandidateRouteComparisonRequest,
) -> CandidateRouteComparisonResponse:
    """Grounded evaluation comparing candidate corridors across distance, slope, roughness,
    EVA turnaround feasibility, and Monte Carlo robustness with exact numeric grounding.
    """
    assistant = get_science_assistant()
    return await assistant.compare_route_candidates(request)


@router.post(
    "/terrain/interpret",
    response_model=ScientificTerrainInterpretationResponse,
    summary="Scientific terrain, geological, and thermal interpretation",
)
async def interpret_scientific_terrain(
    request: ScientificTerrainInterpretationRequest,
) -> ScientificTerrainInterpretationResponse:
    """Explains geological formations, mineralogy, and thermal inertia along traversal corridor,
    explicitly distinguishing measured data, derived metrics, and proxy indicators.
    """
    assistant = get_science_assistant()
    return await assistant.interpret_scientific_terrain(request)


@router.post(
    "/mission/risk-briefing",
    response_model=MissionRiskBriefingResponse,
    summary="Executive mission risk briefing and contingency corridors",
)
async def generate_mission_risk_briefing(
    request: MissionRiskBriefingRequest,
) -> MissionRiskBriefingResponse:
    """Synthesizes deterministic stress-test results (7 scenarios), Monte Carlo simulations (50 runs),
    and return feasibility into an executive risk briefing. Enforces deterministic safety override prohibition.
    """
    assistant = get_science_assistant()
    return await assistant.generate_mission_risk_briefing(request)
