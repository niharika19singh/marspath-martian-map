from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.integrations.google_cloud.jobs.base_job import BaseCloudRunJob, JobExecutionResult
from backend.app.integrations.google_cloud.jobs.crism_processor import CrismProcessorJob
from backend.app.integrations.google_cloud.jobs.dem_processor import DemProcessorJob
from backend.app.integrations.google_cloud.jobs.imagery_tile_generator import ImageryTileGeneratorJob
from backend.app.integrations.google_cloud.jobs.meda_processor import MedaProcessorJob
from backend.app.integrations.google_cloud.jobs.nasa_catalog_sync import NasaCatalogSyncJob
from backend.app.integrations.google_cloud.jobs.planetary_imagery_processor import PlanetaryImageryProcessorJob
from backend.app.integrations.google_cloud.jobs.provenance_validator import ProvenanceValidatorJob
from backend.app.integrations.google_cloud.jobs.themis_processor import ThemisProcessorJob


class JobInfo(BaseModel):
    name: str
    description: str
    timeout_seconds: int
    memory_limit_mb: int
    cpu_limit: str
    last_status: str | None = None
    last_duration_seconds: float | None = None
    last_run_utc: str | None = None
    execution_history_count: int = 0


class CloudRunJobsStatus(BaseModel):
    cloud_run_enabled: bool = False
    total_registered_jobs: int = 8
    active_environment: str = "Cloud Run Jobs (Batch Execution Engine)"
    jobs: list[JobInfo] = Field(default_factory=list)
    recent_executions: list[JobExecutionResult] = Field(default_factory=list)


class CloudRunJobRegistry:
    """Central registry and dispatcher for all containerized Cloud Run processing jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, BaseCloudRunJob] = {
            "nasa_catalog_sync": NasaCatalogSyncJob(),
            "planetary_imagery_processor": PlanetaryImageryProcessorJob(),
            "dem_processor": DemProcessorJob(),
            "meda_processor": MedaProcessorJob(),
            "themis_processor": ThemisProcessorJob(),
            "crism_processor": CrismProcessorJob(),
            "provenance_validator": ProvenanceValidatorJob(),
            "imagery_tile_generator": ImageryTileGeneratorJob(),
        }
        self._history: list[JobExecutionResult] = []

    def list_jobs(self) -> list[JobInfo]:
        results: list[JobInfo] = []
        for name, job in self._jobs.items():
            last = job.last_result
            hist_count = sum(1 for h in self._history if h.job_name == name)
            results.append(
                JobInfo(
                    name=name,
                    description=job.description,
                    timeout_seconds=job.timeout_seconds,
                    memory_limit_mb=job.memory_limit_mb,
                    cpu_limit=job.cpu_limit,
                    last_status=last.status if last else None,
                    last_duration_seconds=last.duration_seconds if last else None,
                    last_run_utc=last.completed_at.isoformat() if last else None,
                    execution_history_count=hist_count,
                )
            )
        return results

    def get_job(self, name: str) -> BaseCloudRunJob | None:
        return self._jobs.get(name)

    def get_history(self) -> list[JobExecutionResult]:
        """Returns recorded execution history for all batch jobs."""
        return list(self._history)

    async def run_job(self, name: str, params: dict[str, Any] | None = None) -> JobExecutionResult:
        job = self.get_job(name)
        if not job:
            raise KeyError(f"Cloud Run Job '{name}' not found in registry.")

        result = await job.run(params)
        self._history.insert(0, result)
        if len(self._history) > 50:
            self._history.pop()
        return result

    def get_status(self, is_enabled: bool = False) -> CloudRunJobsStatus:
        return CloudRunJobsStatus(
            cloud_run_enabled=is_enabled,
            total_registered_jobs=len(self._jobs),
            jobs=self.list_jobs(),
            recent_executions=self._history[:10],
        )


_global_job_registry = CloudRunJobRegistry()


def get_job_registry() -> CloudRunJobRegistry:
    return _global_job_registry
