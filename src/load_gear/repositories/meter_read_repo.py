"""Async repository for data.meter_reads bulk operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import MeterRead


async def bulk_insert(
    session: AsyncSession,
    rows: list[dict],
) -> int:
    """Bulk insert meter read rows using ORM session.add().

    Uses individual adds to work correctly with the SQLAlchemy session
    transaction lifecycle across all database backends.

    For duplicate handling, caller should ensure unique (ts_utc, meter_id, version)
    or clean up before inserting.

    Returns the number of rows added to the session.
    """
    if not rows:
        return 0

    for row_data in rows:
        mr = MeterRead(**row_data)
        session.add(mr)

    await session.flush()
    return len(rows)


async def get_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    version: int = 1,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[MeterRead], int]:
    """Fetch meter reads for a job+version. Returns (rows, total_count)."""
    base = select(MeterRead).where(
        MeterRead.job_id == job_id,
        MeterRead.version == version,
    )
    count_q = select(func.count()).select_from(
        base.subquery()
    )

    query = base.order_by(MeterRead.ts_utc).limit(limit).offset(offset)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    return rows, total


async def count_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    version: int = 1,
) -> int:
    """Count meter reads for a job+version."""
    result = await session.execute(
        select(func.count()).select_from(MeterRead).where(
            MeterRead.job_id == job_id,
            MeterRead.version == version,
        )
    )
    return result.scalar_one()
