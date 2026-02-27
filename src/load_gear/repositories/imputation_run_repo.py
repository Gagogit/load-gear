"""Async repository for analysis.imputation_runs CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.analysis import ImputationRun


async def create_run(
    session: AsyncSession,
    run: ImputationRun,
) -> ImputationRun:
    """Insert a new imputation run record."""
    session.add(run)
    await session.flush()
    return run


async def get_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> list[ImputationRun]:
    """Get all imputation runs for a job, ordered by created_at."""
    result = await session.execute(
        select(ImputationRun)
        .where(ImputationRun.job_id == job_id)
        .order_by(ImputationRun.created_at)
    )
    return list(result.scalars().all())


async def get_latest_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> ImputationRun | None:
    """Get the most recent imputation run for a job."""
    result = await session.execute(
        select(ImputationRun)
        .where(ImputationRun.job_id == job_id)
        .order_by(ImputationRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
