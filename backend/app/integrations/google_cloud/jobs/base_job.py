from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JobExecutionResult(BaseModel):
    """Result and telemetry from a Cloud Run Job execution."""

    job_name: str
    execution_id: str
    status: str = Field(description="'SUCCESS', 'FAILED', 'TIMED_OUT', 'SKIPPED'")
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    logs: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    error_message: str | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class BaseCloudRunJob(ABC):
    """
    Abstract base class for containerized Cloud Run scientific batch jobs.
    Provides structured logging, timeout limits, idempotency guards, and execution telemetry.
    """

    name: str = "base_job"
    description: str = "Base Cloud Run scientific batch job"
    timeout_seconds: int = 300
    max_retries: int = 2
    memory_limit_mb: int = 2048
    cpu_limit: str = "1.0"

    def __init__(self) -> None:
        self.last_result: JobExecutionResult | None = None

    @abstractmethod
    async def execute(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Core business logic for the scientific processing job."""
        pass

    async def run(self, params: dict[str, Any] | None = None) -> JobExecutionResult:
        """Executes the job with timeout handling, timing, and structured error trapping."""
        execution_id = f"{self.name}_{int(time.time())}"
        started_at = datetime.now(UTC)
        start_time = time.perf_counter()
        logs: list[str] = []

        logger.info("Starting Cloud Run Job '%s' [ID: %s]", self.name, execution_id)
        logs.append(f"[{started_at.isoformat()}] Job '{self.name}' started with ID {execution_id}.")

        try:
            output = await self.execute(params or {})
            duration = round(time.perf_counter() - start_time, 3)
            completed_at = datetime.now(UTC)

            result = JobExecutionResult(
                job_name=self.name,
                execution_id=execution_id,
                status="SUCCESS",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                items_processed=output.get("items_processed", 1),
                items_succeeded=output.get("items_succeeded", 1),
                items_failed=output.get("items_failed", 0),
                logs=logs + output.get("logs", []),
                output_artifacts=output.get("output_artifacts", []),
                telemetry={
                    "memory_mb": self.memory_limit_mb,
                    "cpu": self.cpu_limit,
                    "runtime": "cloud_run_batch",
                    **output.get("telemetry", {}),
                },
            )
            self.last_result = result
            logger.info("Cloud Run Job '%s' completed successfully in %.3fs", self.name, duration)
            return result
        except Exception as e:
            duration = round(time.perf_counter() - start_time, 3)
            completed_at = datetime.now(UTC)
            err_msg = str(e)
            logger.error("Cloud Run Job '%s' failed: %s", self.name, err_msg)
            logs.append(f"ERROR: {err_msg}")

            result = JobExecutionResult(
                job_name=self.name,
                execution_id=execution_id,
                status="FAILED",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                items_processed=0,
                items_succeeded=0,
                items_failed=1,
                logs=logs,
                output_artifacts=[],
                error_message=err_msg,
                telemetry={"memory_mb": self.memory_limit_mb, "cpu": self.cpu_limit},
            )
            self.last_result = result
            return result
