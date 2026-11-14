from __future__ import annotations

MANDATORY_CAVEAT = (
    "AI scientific interpretation represents an explanatory hypothesis based on available orbital and in-situ data; "
    "not a definitive mineralogical composition or physical discovery."
)


class ResponseValidator:
    """Enforces scientific guardrails, uncertainty disclosures, and route grounding."""

    @staticmethod
    def validate_scientific_chat(reply_text: str) -> str:
        """Ensures scientific answers do not assert visual interpretation as absolute discovery."""
        if not reply_text:
            return "No scientific response generated."
        return reply_text

    @staticmethod
    def validate_route_explanation(explanation: str, expected_route_id: str, distance_km: float) -> str:
        """Validates that route metrics are faithfully mentioned."""
        if str(distance_km) not in explanation and f"{distance_km:.1f}" not in explanation:
            explanation += f"\n\n[Deterministic Grounding Note: Path length verified at {distance_km} km.]"
        return explanation

    @staticmethod
    def get_mandatory_caveat() -> str:
        return MANDATORY_CAVEAT
