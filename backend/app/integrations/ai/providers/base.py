from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.integrations.ai.schemas.models import (
    AIProviderInfo,
    CandidateRouteComparisonResponse,
    ImageryInterpretationResponse,
    MarsScienceChatResponse,
    MissionRiskBriefingResponse,
    NaturalLanguageMissionPlanResponse,
    RouteExplanationResponse,
    ScientificTerrainInterpretationResponse,
)


class BaseAIProvider(ABC):
    """Abstract interface defining required capabilities for planetary AI assistants."""

    provider_id: str = "base"
    name: str = "Base Provider"

    @abstractmethod
    def get_info(self) -> AIProviderInfo:
        """Returns provider status, active model, and capability set."""
        pass

    @abstractmethod
    async def chat(
        self,
        message: str,
        context_data: dict[str, Any] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> MarsScienceChatResponse:
        """Answers scientific questions grounded in genuine Martian catalog context."""
        pass

    @abstractmethod
    async def explain_route(
        self,
        route_data: dict[str, Any],
        user_question: str,
        algorithm_comparison: dict[str, Any] | None = None,
    ) -> RouteExplanationResponse:
        """Explains deterministic route optimization decisions, costs, and safety constraints."""
        pass

    @abstractmethod
    async def interpret_imagery(
        self,
        product_meta: dict[str, Any],
        user_prompt: str | None = None,
        image_bytes: bytes | None = None,
    ) -> ImageryInterpretationResponse:
        """Performs visual morphological analysis with mandatory scientific caveats."""
        pass

    @abstractmethod
    async def plan_mission_from_prompt(
        self,
        user_prompt: str,
        current_coords: dict[str, float] | None = None,
    ) -> NaturalLanguageMissionPlanResponse:
        """Parses natural-language mission objective into structured, validated routing parameters."""
        pass

    @abstractmethod
    async def compare_route_candidates(
        self,
        routes: list[dict[str, Any]],
        mission_objective: str | None = None,
    ) -> CandidateRouteComparisonResponse:
        """Compares route candidates with strict grounding on computed engineering metrics."""
        pass

    @abstractmethod
    async def interpret_scientific_terrain(
        self,
        route_summary: dict[str, Any] | None = None,
        corridor_bounds: list[float] | None = None,
        geological_focus: str | None = None,
    ) -> ScientificTerrainInterpretationResponse:
        """Interprets terrain morphology and mineralogy with clear evidence provenance."""
        pass

    @abstractmethod
    async def generate_mission_risk_briefing(
        self,
        selected_route: dict[str, Any],
        operational_stress_suite: dict[str, Any] | None = None,
        robustness_assessment: dict[str, Any] | None = None,
        turnaround: dict[str, Any] | None = None,
    ) -> MissionRiskBriefingResponse:
        """Synthesizes risk, stress testing, and return feasibility into an executive risk briefing."""
        pass
