"""Async repository for data.financial_runs CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import FinancialRun


async def create(session: AsyncSession, run: FinancialRun) -> FinancialRun:
    """Insert a new financial run."""
    session.add(run)
    await session.flush()
    return run


async def get_by_id(session: AsyncSession, run_id: uuid.UUID) -> FinancialRun | None:
    """Fetch a single financial run by ID."""
    return await session.get(FinancialRun, run_id)


async def get_by_job_id(session: AsyncSession, job_id: uuid.UUID) -> FinancialRun | None:
    """Get the most recent financial run for a job."""
    result = await session.execute(
        select(FinancialRun)
        .where(FinancialRun.job_id == job_id)
        .order_by(FinancialRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def update_status(
    session: AsyncSession,
    run: FinancialRun,
    status: str,
    *,
    completed_at: object = None,
    total_cost_eur: float | None = None,
    monthly_summary: dict | None = None,
) -> FinancialRun:
    """Update financial run status and results."""
    run.status = status
    if completed_at is not None:
        run.completed_at = completed_at
    if total_cost_eur is not None:
        run.total_cost_eur = total_cost_eur
    if monthly_summary is not None:
        run.monthly_summary = monthly_summary
    await session.flush()
    return run
