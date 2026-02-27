"""Async repository for control.jobs CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import Job, JobStatus


async def create_job(session: AsyncSession, job: Job) -> Job:
    """Insert a new job and return it."""
    session.add(job)
    await session.flush()
    return job


async def get_job_by_id(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Fetch a single job by ID."""
    return await session.get(Job, job_id)


async def list_jobs(
    session: AsyncSession,
    *,
    status: JobStatus | None = None,
    company_id: str | None = None,
    meter_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    """List jobs with optional filters. Returns (jobs, total_count)."""
    query = select(Job)
    count_query = select(func.count()).select_from(Job)

    if status is not None:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)
    if company_id is not None:
        query = query.where(Job.company_id == company_id)
        count_query = count_query.where(Job.company_id == company_id)
    if meter_id is not None:
        query = query.where(Job.meter_id == meter_id)
        count_query = count_query.where(Job.meter_id == meter_id)

    query = query.order_by(Job.created_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    jobs = list(result.scalars().all())
    total = await session.execute(count_query)

    return jobs, total.scalar_one()


async def update_job_status(
    session: AsyncSession, job: Job, new_status: JobStatus, *, error_message: str | None = None
) -> Job:
    """Update a job's status."""
    job.status = new_status
    if error_message is not None:
        job.error_message = error_message
    await session.flush()
    return job


async def delete_job(session: AsyncSession, job: Job) -> None:
    """Delete a job."""
    await session.delete(job)
    await session.flush()
