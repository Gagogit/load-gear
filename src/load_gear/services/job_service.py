"""Job lifecycle service: creation, state machine transitions, deletion."""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import Job, JobStatus
from load_gear.models.schemas import JobCreateRequest
from load_gear.repositories import job_repo

# Valid state transitions per ADR-003 + ADR-004
VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.PENDING: {JobStatus.INGESTING, JobStatus.FAILED},
    JobStatus.INGESTING: {JobStatus.QA_RUNNING, JobStatus.FAILED},
    JobStatus.QA_RUNNING: {JobStatus.ANALYSIS_RUNNING, JobStatus.DONE, JobStatus.WARN, JobStatus.FAILED},
    JobStatus.ANALYSIS_RUNNING: {JobStatus.FORECAST_RUNNING, JobStatus.DONE, JobStatus.WARN, JobStatus.FAILED},
    JobStatus.FORECAST_RUNNING: {JobStatus.DONE, JobStatus.WARN, JobStatus.FAILED},
    # Terminal states — no transitions out
    JobStatus.DONE: set(),
    JobStatus.WARN: set(),
    JobStatus.FAILED: set(),
}

# Map task level to terminal phase (ADR-004)
TASK_TERMINAL_PHASE: dict[str, JobStatus] = {
    "Statistik": JobStatus.QA_RUNNING,
    "Fehleranalyse": JobStatus.QA_RUNNING,
    "Imputation": JobStatus.ANALYSIS_RUNNING,
    "Prognose": JobStatus.FORECAST_RUNNING,
    "Aggregation": JobStatus.FORECAST_RUNNING,  # P6 runs after forecast
}


def validate_transition(current: JobStatus, target: JobStatus) -> bool:
    """Check if a state transition is valid per ADR-003."""
    return target in VALID_TRANSITIONS.get(current, set())


async def create_job(session: AsyncSession, request: JobCreateRequest) -> Job:
    """Create a new job from an API request."""
    payload = {
        "tasks": request.tasks,
        "horizon_months": request.horizon_months,
        "unit": request.unit,
        "interval_minutes": request.interval_minutes,
        "scenarios": request.scenarios,
    }
    # Remove None values from payload
    payload = {k: v for k, v in payload.items() if v is not None}

    job = Job(
        id=uuid.uuid4(),
        status=JobStatus.PENDING,
        company_id=request.company_id,
        meter_id=request.meter_id,
        plz=request.plz,
        payload=payload,
    )
    return await job_repo.create_job(session, job)


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    """Get a job by ID, raising 404 if not found."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return job


async def list_jobs(
    session: AsyncSession,
    *,
    status: JobStatus | None = None,
    company_id: str | None = None,
    meter_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """List jobs with optional filters."""
    return await job_repo.list_jobs(
        session, status=status, company_id=company_id, meter_id=meter_id,
        limit=limit, offset=offset,
    )


async def advance_job(session: AsyncSession, job_id: uuid.UUID, new_status: JobStatus) -> Job:
    """Advance a job to a new state, validating the transition."""
    job = await get_job(session, job_id)

    if not validate_transition(job.status, new_status):
        raise HTTPException(
            status_code=409,
            detail=f"Invalid transition: {job.status.value} → {new_status.value}",
        )

    return await job_repo.update_job_status(session, job, new_status)


async def delete_job(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Delete a job. Only pending or failed jobs can be deleted."""
    job = await get_job(session, job_id)

    if job.status not in (JobStatus.PENDING, JobStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete job in status '{job.status.value}'. Only pending or failed jobs can be deleted.",
        )

    await job_repo.delete_job(session, job)
