"""Forecast orchestration service: validate → fetch v2 → train Prophet → apply strategies → write v3."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import JobStatus
from load_gear.models.data import ForecastRun
from load_gear.repositories import (
    job_repo,
    meter_read_repo,
    analysis_profile_repo,
    forecast_run_repo,
    forecast_series_repo,
)
from load_gear.services.forecast.prophet_trainer import train_and_predict
from load_gear.services.forecast.strategies.calendar_mapping import apply_calendar_mapping
from load_gear.services.forecast.strategies.dst_correct import apply_dst_correction
from load_gear.services.forecast.strategies.scaling import apply_scaling

logger = logging.getLogger(__name__)


class ForecastError(Exception):
    """Raised when forecast pipeline fails."""
    pass


async def run_forecast(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    horizon_start: datetime | None = None,
    horizon_end: datetime | None = None,
    strategies: list[str] | None = None,
    quantiles: list[float] | None = None,
) -> dict:
    """Run full forecast pipeline: validate → fetch → train → strategies → write.

    Returns a summary dict.
    """
    if strategies is None:
        strategies = ["calendar_mapping", "dst_correct"]
    if quantiles is None:
        quantiles = [0.1, 0.5, 0.9]

    # 1. Validate job
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise ForecastError(f"Job {job_id} not found")

    if job.status != JobStatus.FORECAST_RUNNING:
        raise ForecastError(
            f"Job {job_id} is in status '{job.status.value}', expected 'forecast_running'"
        )

    job.current_phase = "P5"
    await session.flush()

    try:
        meter_id = job.meter_id or str(job_id)

        # 2. Fetch v2 data
        v2_rows, v2_count = await meter_read_repo.get_by_job_id(
            session, job_id, version=2, limit=200_000, offset=0
        )
        if v2_count == 0:
            raise ForecastError(f"No v2 meter reads found for job {job_id}")

        row_dicts = [
            {"ts_utc": r.ts_utc, "value": r.value, "unit": r.unit, "meter_id": r.meter_id}
            for r in v2_rows
        ]

        # 3. Fetch analysis profile
        profile = await analysis_profile_repo.get_by_job_id(session, job_id)
        if profile is None:
            raise ForecastError(f"No analysis profile found for job {job_id}")

        seasonality = profile.seasonality or {"daily": True, "weekly": True, "yearly": False}
        day_fingerprints = profile.day_fingerprints or {}

        # 4. Determine horizon
        timestamps = sorted(r["ts_utc"] for r in row_dicts)
        last_ts = timestamps[-1]

        # Detect interval
        if len(timestamps) >= 2:
            delta = (timestamps[1] - timestamps[0]).total_seconds()
            interval_minutes = max(int(delta / 60), 15)
        else:
            interval_minutes = 15

        # Default horizon: from last data point to +horizon_months (from payload) or +1 month
        payload = job.payload or {}
        horizon_months = payload.get("horizon_months", 1)

        if horizon_start is None:
            horizon_start = last_ts + timedelta(minutes=interval_minutes)
        if horizon_end is None:
            horizon_end = last_ts + timedelta(days=30 * horizon_months)

        # 5. Compute data snapshot ID (SHA-256 for reproducibility)
        snapshot_hash = hashlib.sha256()
        for r in row_dicts[:100]:  # Hash first 100 rows for speed
            snapshot_hash.update(f"{r['ts_utc']},{r['value']}".encode())
        data_snapshot_id = snapshot_hash.hexdigest()

        # 6. Create ForecastRun record
        run = ForecastRun(
            id=uuid.uuid4(),
            job_id=job_id,
            meter_id=meter_id,
            analysis_run_id=profile.id,
            horizon_start=horizon_start,
            horizon_end=horizon_end,
            model_alias="prophet",
            data_snapshot_id=data_snapshot_id,
            strategies={"applied": strategies},
            quantiles={"values": quantiles},
            status="running",
        )
        await forecast_run_repo.create(session, run)

        # 7. Train Prophet in thread pool
        job.current_phase = "P5.1"
        await session.flush()

        predictions = await train_and_predict(
            row_dicts,
            horizon_start,
            horizon_end,
            seasonality,
            quantiles,
            interval_minutes,
        )

        if not predictions:
            raise ForecastError("Prophet returned no predictions")

        # 8. Apply strategies
        job.current_phase = "P5.2"
        await session.flush()

        if "calendar_mapping" in strategies:
            predictions = apply_calendar_mapping(predictions, day_fingerprints)
        if "dst_correct" in strategies:
            predictions = apply_dst_correction(predictions, interval_minutes)
        if "scaling" in strategies:
            growth_pct = payload.get("scenarios", {}).get("growth_pct", 0.0) if payload.get("scenarios") else 0.0
            predictions = apply_scaling(predictions, growth_pct=growth_pct)

        # 9. Bulk-insert ForecastSeries rows
        series_rows = [
            {
                "ts_utc": p["ts_utc"],
                "forecast_id": run.id,
                "y_hat": p["y_hat"],
                "q10": p.get("q10"),
                "q50": p.get("q50"),
                "q90": p.get("q90"),
            }
            for p in predictions
        ]

        inserted = await forecast_series_repo.bulk_insert(session, series_rows)

        # 10. Update ForecastRun status
        run.status = "ok"
        run.completed_at = datetime.now(timezone.utc)
        await session.flush()

        # 11. Advance job state (to financial_running if Aggregation task, else done)
        tasks = (job.payload or {}).get("tasks", [])
        if "Aggregation" in tasks:
            job.status = JobStatus.FINANCIAL_RUNNING
        else:
            job.status = JobStatus.DONE
        job.current_phase = None
        await session.flush()

        return {
            "job_id": str(job_id),
            "forecast_run_id": str(run.id),
            "meter_id": meter_id,
            "horizon_start": horizon_start.isoformat(),
            "horizon_end": horizon_end.isoformat(),
            "predictions": inserted,
            "strategies_applied": strategies,
        }

    except ForecastError:
        raise
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Forecast error: {exc}"
        job.current_phase = None
        await session.flush()
        # Update run status if it exists
        try:
            if run:
                run.status = "failed"
                run.completed_at = datetime.now(timezone.utc)
                await session.flush()
        except Exception:
            pass
        raise ForecastError(f"Forecast pipeline failed: {exc}") from exc


async def get_forecast_status(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get forecast status for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise ForecastError(f"Job {job_id} not found")

    run = await forecast_run_repo.get_by_job_id(session, job_id)

    return {
        "job_id": str(job_id),
        "status": job.status.value,
        "current_phase": job.current_phase,
        "forecast_run_id": str(run.id) if run else None,
        "error_message": job.error_message,
    }


async def get_forecast_run(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> ForecastRun:
    """Get forecast run metadata for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise ForecastError(f"Job {job_id} not found")

    run = await forecast_run_repo.get_by_job_id(session, job_id)
    if run is None:
        raise ForecastError(f"No forecast run for job {job_id}")
    return run


async def get_forecast_series(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[uuid.UUID, list, int]:
    """Get v3 forecast series for a job (paginated)."""
    run = await get_forecast_run(session, job_id)
    rows, total = await forecast_series_repo.get_by_forecast_id(
        session, run.id, limit=limit, offset=offset
    )
    return run.id, rows, total


async def get_forecast_summary(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get summary stats for a forecast run."""
    run = await get_forecast_run(session, job_id)
    summary = await forecast_series_repo.get_summary(session, run.id)
    return {
        "job_id": str(job_id),
        "forecast_id": str(run.id),
        **summary,
    }
