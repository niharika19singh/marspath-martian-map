from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.app.integrations.google_cloud.cost_controls import CloudCostReport, get_cost_manager
from backend.app.integrations.google_cloud.jobs.base_job import JobExecutionResult
from backend.app.integrations.google_cloud.jobs.job_registry import CloudRunJobsStatus, get_job_registry
from backend.app.integrations.google_cloud.scheduler.scheduler_service import CloudSchedulerService, ScheduledTaskConfig
from backend.app.integrations.google_cloud.storage.metadata import ObjectMetadata, StorageStatus
from backend.app.integrations.google_cloud.storage.storage_factory import get_storage_adapter

router = APIRouter(prefix="/cloud", tags=["Google Cloud Infrastructure"])


class CloudGlobalStatus(BaseModel):
    """Unified operational status across Google Cloud services."""

    project_id: str | None = None
    location: str = "us-central1"
    gcs_status: StorageStatus
    cloud_run_status: CloudRunJobsStatus
    cost_report: CloudCostReport
    cloud_features: dict[str, bool] = Field(default_factory=dict)


@router.get("/status", response_model=CloudGlobalStatus, summary="Global Google Cloud infrastructure status")
async def get_cloud_status() -> CloudGlobalStatus:
    """Returns operational status for GCS, Cloud Run Jobs, Cloud Scheduler, and cost controls."""
    settings = get_settings()
    storage = get_storage_adapter()
    job_registry = get_job_registry()
    cost_mgr = get_cost_manager()

    st_status = await storage.get_status()
    jobs_status = job_registry.get_status(is_enabled=settings.CLOUD_JOBS_ENABLED)
    cost_status = cost_mgr.get_cost_report(storage_bytes=st_status.total_bytes)

    return CloudGlobalStatus(
        project_id=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_LOCATION,
        gcs_status=st_status,
        cloud_run_status=jobs_status,
        cost_report=cost_status,
        cloud_features={
            "gcs_enabled": settings.GCS_ENABLED,
            "cloud_jobs_enabled": settings.CLOUD_JOBS_ENABLED,
            "gemini_enabled": settings.GEMINI_ENABLED,
            "azure_ai_enabled": settings.AZURE_AI_ENABLED,
        },
    )


@router.get("/storage/status", response_model=StorageStatus, summary="GCS storage status")
async def get_storage_status() -> StorageStatus:
    """Returns active storage backend status, bucket name, total objects, and size."""
    storage = get_storage_adapter()
    return await storage.get_status()


@router.get("/storage/objects", response_model=list[ObjectMetadata], summary="List stored scientific assets")
async def list_storage_objects(
    prefix: str = Query("", description="Object prefix filter, e.g. 'raw/nasa/'"),
    limit: int = Query(50, ge=1, le=200),
) -> list[ObjectMetadata]:
    """Lists objects in storage under a given prefix."""
    storage = get_storage_adapter()
    return await storage.list_objects(prefix=prefix, limit=limit)


@router.get("/storage/download", summary="Download stored asset")
async def download_storage_object(
    object: str = Query(..., description="Object key path, e.g. 'raw/nasa/hirise/sample.json'"),
    token: str = Query(..., description="Access verification token"),
) -> Response:
    """Streams binary content for an authorized object."""
    storage = get_storage_adapter()
    if not await storage.exists(object):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Object '{object}' not found.")

    data = await storage.download_bytes(object)
    meta = await storage.get_metadata(object)
    media_type = meta.content_type if meta else "application/octet-stream"

    return Response(content=data, media_type=media_type)


@router.get("/jobs/status", response_model=CloudRunJobsStatus, summary="Cloud Run jobs execution status")
async def get_jobs_status() -> CloudRunJobsStatus:
    """Returns list of containerized scientific jobs and recent run telemetry."""
    settings = get_settings()
    registry = get_job_registry()
    return registry.get_status(is_enabled=settings.CLOUD_JOBS_ENABLED)


@router.post("/jobs/run/{job_name}", response_model=JobExecutionResult, summary="Trigger a Cloud Run Job")
async def trigger_cloud_run_job(job_name: str, params: dict[str, Any] | None = None) -> JobExecutionResult:
    """Dispatches execution for a specific Cloud Run scientific batch job."""
    registry = get_job_registry()
    job = registry.get_job(job_name)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cloud Run Job '{job_name}' is not registered.",
        )

    return await registry.run_job(job_name, params or {})


@router.get("/scheduler/schedules", response_model=list[ScheduledTaskConfig], summary="List Cloud Scheduler workflows")
async def list_scheduler_workflows() -> list[ScheduledTaskConfig]:
    """Returns automated ingestion schedules and recurrence definitions."""
    service = CloudSchedulerService()
    return service.list_schedules()


@router.get("/costs", response_model=CloudCostReport, summary="Cloud cost controls and budget limits")
async def get_cost_report() -> CloudCostReport:
    """Returns spend estimation, storage usage, and budget thresholds."""
    storage = get_storage_adapter()
    st_status = await storage.get_status()
    cost_mgr = get_cost_manager()
    return cost_mgr.get_cost_report(storage_bytes=st_status.total_bytes)
