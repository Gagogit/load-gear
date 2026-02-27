"""Async repository for data.hpfc_series bulk operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import HpfcSeries


async def bulk_insert(session: AsyncSession, rows: list[dict]) -> int:
    """Bulk insert HPFC series rows using ORM session.add()."""
    if not rows:
        return 0
    for row_data in rows:
        hs = HpfcSeries(**row_data)
        session.add(hs)
    await session.flush()
    return len(rows)


async def get_by_snapshot_id(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[HpfcSeries], int]:
    """Fetch HPFC series for a snapshot. Returns (rows, total_count)."""
    base = select(HpfcSeries).where(HpfcSeries.snapshot_id == snapshot_id)
    count_q = select(func.count()).select_from(base.subquery())

    query = base.order_by(HpfcSeries.ts_utc).limit(limit).offset(offset)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    return rows, total


async def get_all_by_snapshot_id(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
) -> list[HpfcSeries]:
    """Fetch all HPFC series rows for a snapshot (no pagination)."""
    result = await session.execute(
        select(HpfcSeries)
        .where(HpfcSeries.snapshot_id == snapshot_id)
        .order_by(HpfcSeries.ts_utc)
    )
    return list(result.scalars().all())


async def delete_by_snapshot_id(session: AsyncSession, snapshot_id: uuid.UUID) -> int:
    """Delete all series rows for a snapshot. Returns count deleted."""
    result = await session.execute(
        delete(HpfcSeries).where(HpfcSeries.snapshot_id == snapshot_id)
    )
    await session.flush()
    return result.rowcount
