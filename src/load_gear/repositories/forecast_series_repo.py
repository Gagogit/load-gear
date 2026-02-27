"""Async repository for data.forecast_series bulk operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import ForecastSeries


async def bulk_insert(session: AsyncSession, rows: list[dict]) -> int:
    """Bulk insert forecast series rows using ORM session.add()."""
    if not rows:
        return 0
    for row_data in rows:
        fs = ForecastSeries(**row_data)
        session.add(fs)
    await session.flush()
    return len(rows)


async def get_by_forecast_id(
    session: AsyncSession,
    forecast_id: uuid.UUID,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[ForecastSeries], int]:
    """Fetch forecast series for a run. Returns (rows, total_count)."""
    base = select(ForecastSeries).where(ForecastSeries.forecast_id == forecast_id)
    count_q = select(func.count()).select_from(base.subquery())

    query = base.order_by(ForecastSeries.ts_utc).limit(limit).offset(offset)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    return rows, total


async def get_summary(
    session: AsyncSession,
    forecast_id: uuid.UUID,
) -> dict:
    """Get summary statistics for a forecast run."""
    result = await session.execute(
        select(
            func.count().label("total"),
            func.min(ForecastSeries.y_hat).label("y_hat_min"),
            func.max(ForecastSeries.y_hat).label("y_hat_max"),
            func.avg(ForecastSeries.y_hat).label("y_hat_mean"),
            func.min(ForecastSeries.q10).label("q10_min"),
            func.max(ForecastSeries.q10).label("q10_max"),
            func.avg(ForecastSeries.q10).label("q10_mean"),
            func.min(ForecastSeries.q50).label("q50_min"),
            func.max(ForecastSeries.q50).label("q50_max"),
            func.avg(ForecastSeries.q50).label("q50_mean"),
            func.min(ForecastSeries.q90).label("q90_min"),
            func.max(ForecastSeries.q90).label("q90_max"),
            func.avg(ForecastSeries.q90).label("q90_mean"),
        ).where(ForecastSeries.forecast_id == forecast_id)
    )
    row = result.one()
    return {
        "total": row.total,
        "y_hat": {"min": row.y_hat_min, "max": row.y_hat_max, "mean": float(row.y_hat_mean) if row.y_hat_mean else None},
        "q10": {"min": row.q10_min, "max": row.q10_max, "mean": float(row.q10_mean) if row.q10_mean else None},
        "q50": {"min": row.q50_min, "max": row.q50_max, "mean": float(row.q50_mean) if row.q50_mean else None},
        "q90": {"min": row.q90_min, "max": row.q90_max, "mean": float(row.q90_mean) if row.q90_mean else None},
    }
