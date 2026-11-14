from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.integrations.ai.schemas.models import (
    AIProviderInfo,
    ImageryInterpretationResponse,
    MarsScienceChatResponse,
    RouteExplanationResponse,
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
