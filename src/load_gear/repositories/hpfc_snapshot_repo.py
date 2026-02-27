"""Async repository for data.hpfc_snapshots CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import HpfcSnapshot


async def create(session: AsyncSession, snapshot: HpfcSnapshot) -> HpfcSnapshot:
    """Insert a new HPFC snapshot."""
    session.add(snapshot)
    await session.flush()
    return snapshot


async def get_by_id(session: AsyncSession, snapshot_id: uuid.UUID) -> HpfcSnapshot | None:
    """Fetch a single snapshot by ID."""
    return await session.get(HpfcSnapshot, snapshot_id)


async def list_all(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[HpfcSnapshot], int]:
    """List all HPFC snapshots (paginated). Returns (rows, total)."""
    base = select(HpfcSnapshot)
    count_q = select(func.count()).select_from(base.subquery())

    query = base.order_by(HpfcSnapshot.snapshot_at.desc()).limit(limit).offset(offset)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    return rows, total


async def get_latest_covering(
    session: AsyncSession,
    start: object,
    end: object,
) -> HpfcSnapshot | None:
    """Find the most recent snapshot whose delivery range covers [start, end]."""
    result = await session.execute(
        select(HpfcSnapshot)
        .where(HpfcSnapshot.delivery_start <= start)
        .where(HpfcSnapshot.delivery_end >= end)
        .order_by(HpfcSnapshot.snapshot_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def delete_snapshot(session: AsyncSession, snapshot: HpfcSnapshot) -> None:
    """Delete an HPFC snapshot."""
    await session.delete(snapshot)
    await session.flush()
