"""Job management endpoints: POST/GET/DELETE /api/v1/jobs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.control import JobStatus
from load_gear.models.schemas import (
    JobCreateRequest,
    JobDetailResponse,
    JobListResponse,
    JobResponse,
)
from load_gear.services import job_service

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(
    request: JobCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> JobResponse:
    """Create a new processing job."""
    job = await job_service.create_job(session, request)
    return JobResponse.model_validate(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: str | None = Query(None, description="Filter by status"),
    company_id: str | None = Query(None, description="Filter by company"),
    meter_id: str | None = Query(None, description="Filter by meter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> JobListResponse:
    """List jobs with optional filters."""
    status_enum = None
    if status is not None:
        try:
            status_enum = JobStatus(status)
        except ValueError:
            status_enum = JobStatus[status.upper()]

    jobs, total = await job_service.list_jobs(
        session, status=status_enum, company_id=company_id, meter_id=meter_id,
        limit=limit, offset=offset,
    )
    return JobListResponse(
        items=[JobResponse.model_validate(j) for j in jobs],
        total=total,
    )


@router.get("/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> JobDetailResponse:
    """Get job details by ID."""
    job = await job_service.get_job(session, job_id)
    return JobDetailResponse.model_validate(job)


@router.delete("/{job_id}", status_code=200)
async def delete_job(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Delete a pending or failed job."""
    await job_service.delete_job(session, job_id)
    return {"detail": f"Job {job_id} deleted"}
