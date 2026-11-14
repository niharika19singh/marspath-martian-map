from __future__ import annotations

from pydantic import BaseModel


class ScheduledTaskConfig(BaseModel):
    name: str
    cron_expression: str
    description: str
    target_job: str
    target_endpoint: str
    http_method: str = "POST"
    auth_type: str = "OIDC"
    service_account: str = "marspath-scheduler-invoker@PROJECT_ID.iam.gserviceaccount.com"
    retry_count: int = 3
    is_active: bool = True


DEFAULT_SCHEDULES: list[ScheduledTaskConfig] = [
  ScheduledTaskConfig(
    name="marspath-pds-release-monitor",
    cron_expression="0 2 1 * *",  # Monthly on the 1st at 02:00 UTC
    description="Polls NASA PDS quarterly release notices and syncs newly published mission products.",
    target_job="nasa_catalog_sync",
    target_endpoint="/api/v1/cloud/jobs/run/nasa_catalog_sync",
    retry_count=3,
  ),
  ScheduledTaskConfig(
    name="marspath-daily-catalog-sync",
    cron_expression="0 4 * * *",  # Daily at 04:00 UTC
    description="Synchronizes planetary observations, rover traverse waypoints, and MEDA telemetry.",
    target_job="nasa_catalog_sync",
    target_endpoint="/api/v1/cloud/jobs/run/nasa_catalog_sync",
    retry_count=2,
  ),
  ScheduledTaskConfig(
    name="marspath-provenance-audit-weekly",
    cron_expression="0 3 * * 0",  # Every Sunday at 03:00 UTC
    description="Validates cryptographic checksums and persistent DOIs against upstream registries.",
    target_job="provenance_validator",
    target_endpoint="/api/v1/cloud/jobs/run/provenance_validator",
    retry_count=2,
  ),
  ScheduledTaskConfig(
    name="marspath-meda-telemetry-ingestion",
    cron_expression="0 6 * * *",  # Daily at 06:00 UTC
    description="Ingests latest Perseverance in-situ surface weather tables into processed storage.",
    target_job="meda_processor",
    target_endpoint="/api/v1/cloud/jobs/run/meda_processor",
    retry_count=3,
  ),
]


class CloudSchedulerService:
  """Manages scheduled synchronization workflows and provides status to the dashboard."""

  def __init__(
    self, schedules: list[ScheduledTaskConfig] | None = None
  ) -> None:
    self._schedules = schedules or DEFAULT_SCHEDULES

  def list_schedules(self) -> list[ScheduledTaskConfig]:
    return self._schedules

  def get_schedule(self, name: str) -> ScheduledTaskConfig | None:
    for s in self._schedules:
      if s.name == name:
        return s
    return None


_scheduler_instance: CloudSchedulerService | None = None


def get_scheduler_service() -> CloudSchedulerService:
  global _scheduler_instance
  if _scheduler_instance is None:
    _scheduler_instance = CloudSchedulerService()
  return _scheduler_instance

