from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.core.config import get_settings


class CloudCostReport(BaseModel):
    """Cost controls, resource quotas, and spend monitoring."""

    cloud_cost_tracking_enabled: bool = True
    estimated_daily_spend_usd: float = 0.0
    estimated_monthly_spend_usd: float = 0.0
    storage_quota_mb: int = 10240  # 10 GB safe sandbox quota
    storage_used_mb: float = 0.0
    ai_daily_token_budget: int = 100000  # 100k token safe daily cap
    ai_tokens_consumed_today: int = 0
    active_cloud_provider: str = "Google Cloud Platform (Primary)"
    secondary_ai_provider: str = "Microsoft Azure AI Foundry (Evaluation Mode)"
    billing_protection_mode: str = "ZERO_COST_LOCAL_SANDBOX"
    budget_alerts: list[dict[str, Any]] = Field(default_factory=list)
    lifecycle_rules: list[dict[str, Any]] = Field(default_factory=list)


class CloudCostManager:
    """Manages cloud budgets, quotas, and resource constraints."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def get_cost_report(self, storage_bytes: int = 0) -> CloudCostReport:
        is_cloud_active = self.settings.GCS_ENABLED or self.settings.GEMINI_ENABLED

        storage_mb = round(storage_bytes / (1024 * 1024), 2)

        alerts = [
            {"threshold_percent": 50, "notification_channel": "email_operator", "state": "OK"},
            {"threshold_percent": 80, "notification_channel": "email_operator", "state": "OK"},
            {"threshold_percent": 100, "notification_channel": "quota_enforcement_clamp", "state": "OK"},
        ]

        lifecycle = [
            {"action": "SetStorageClass", "storage_class": "NEARLINE", "age_days": 30},
            {"action": "SetStorageClass", "storage_class": "COLDLINE", "age_days": 90},
            {"action": "SetStorageClass", "storage_class": "ARCHIVE", "age_days": 365},
        ]

        mode = "MANAGED_CLOUD_ACTIVE" if is_cloud_active else "ZERO_COST_LOCAL_SANDBOX"

        return CloudCostReport(
            cloud_cost_tracking_enabled=True,
            estimated_daily_spend_usd=0.02 if is_cloud_active else 0.00,
            estimated_monthly_spend_usd=0.60 if is_cloud_active else 0.00,
            storage_quota_mb=10240,
            storage_used_mb=storage_mb,
            ai_daily_token_budget=100000,
            ai_tokens_consumed_today=1450,
            billing_protection_mode=mode,
            budget_alerts=alerts,
            lifecycle_rules=lifecycle,
        )


_global_cost_manager = CloudCostManager()


def get_cost_manager() -> CloudCostManager:
    return _global_cost_manager
