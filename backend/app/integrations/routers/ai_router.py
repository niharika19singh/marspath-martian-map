from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.app.integrations.ai.schemas.models import (
    AIProviderInfo,
    ImageryInterpretationRequest,
    ImageryInterpretationResponse,
    MarsScienceChatRequest,
    MarsScienceChatResponse,
    ModelComparisonRequest,
    ModelComparisonResponse,
    RouteExplanationRequest,
    RouteExplanationResponse,
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
