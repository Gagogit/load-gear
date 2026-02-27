"""Async repository for analysis.quality_findings CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.analysis import QualityFinding


async def bulk_insert(
    session: AsyncSession,
    findings: list[dict],
) -> int:
    """Insert multiple QA findings. Returns count inserted."""
    if not findings:
        return 0

    for finding_data in findings:
        qf = QualityFinding(**finding_data)
        session.add(qf)

    await session.flush()
    return len(findings)


async def get_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> list[QualityFinding]:
    """Get all QA findings for a job, ordered by check_id."""
    result = await session.execute(
        select(QualityFinding)
        .where(QualityFinding.job_id == job_id)
        .order_by(QualityFinding.check_id)
    )
    return list(result.scalars().all())


async def get_by_job_and_check(
    session: AsyncSession,
    job_id: uuid.UUID,
    check_id: int,
) -> QualityFinding | None:
    """Get a specific check finding for a job."""
    result = await session.execute(
        select(QualityFinding).where(
            QualityFinding.job_id == job_id,
            QualityFinding.check_id == check_id,
        )
    )
    return result.scalar_one_or_none()


async def count_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> int:
    """Count findings for a job."""
    result = await session.execute(
        select(func.count()).select_from(QualityFinding).where(
            QualityFinding.job_id == job_id,
        )
    )
    return result.scalar_one()


async def delete_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> int:
    """Delete all findings for a job (for re-runs). Returns count deleted."""
    result = await session.execute(
        delete(QualityFinding).where(QualityFinding.job_id == job_id)
    )
    await session.flush()
    return result.rowcount
