"""Async repository for data.forecast_runs CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import ForecastRun


async def create(session: AsyncSession, run: ForecastRun) -> ForecastRun:
    """Insert a new forecast run."""
    session.add(run)
    await session.flush()
    return run


async def get_by_id(session: AsyncSession, run_id: uuid.UUID) -> ForecastRun | None:
    """Fetch a single forecast run by ID."""
    return await session.get(ForecastRun, run_id)


async def get_by_job_id(session: AsyncSession, job_id: uuid.UUID) -> ForecastRun | None:
    """Get the most recent forecast run for a job."""
    result = await session.execute(
        select(ForecastRun)
        .where(ForecastRun.job_id == job_id)
        .order_by(ForecastRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    run: ForecastRun,
    status: str,
    *,
    completed_at: object = None,
) -> ForecastRun:
    """Update forecast run status."""
    run.status = status
    if completed_at is not None:
        run.completed_at = completed_at
    await session.flush()
    return run
