"""Forecast endpoints: /api/v1/forecasts."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    ForecastRunRequest,
    ForecastRunResponse,
    ForecastSeriesListResponse,
    ForecastSeriesResponse,
    ForecastStatusResponse,
    ForecastSummaryResponse,
)
from load_gear.services.forecast.forecast_service import (
    ForecastError,
    get_forecast_run,
    get_forecast_series,
    get_forecast_status,
    get_forecast_summary,
    run_forecast,
)

router = APIRouter(prefix="/api/v1/forecasts", tags=["forecasts"])


@router.post("", status_code=202)
async def start_forecast(
    body: ForecastRunRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trigger forecast for a job in forecast_running state."""
    try:
        result = await run_forecast(
            session,
            body.job_id,
            horizon_start=body.horizon_start,
            horizon_end=body.horizon_end,
            strategies=body.strategies,
            quantiles=body.quantiles,
        )
        return result
    except ForecastError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        if "expected 'forecast_running'" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/status", response_model=ForecastStatusResponse)
async def forecast_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ForecastStatusResponse:
    """Get forecast status for a job."""
    try:
        status = await get_forecast_status(session, job_id)
        return ForecastStatusResponse(**status)
    except ForecastError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/run")
async def forecast_run(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get forecast run metadata."""
    try:
        run = await get_forecast_run(session, job_id)
        return {
            "id": str(run.id),
            "job_id": str(run.job_id),
            "meter_id": run.meter_id,
            "status": run.status,
            "horizon_start": run.horizon_start.isoformat(),
            "horizon_end": run.horizon_end.isoformat(),
            "model_alias": run.model_alias,
            "data_snapshot_id": run.data_snapshot_id,
            "strategies": run.strategies,
            "quantiles": run.quantiles,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
    except ForecastError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No forecast" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/series", response_model=ForecastSeriesListResponse)
async def forecast_series(
    job_id: uuid.UUID,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ForecastSeriesListResponse:
    """Get v3 forecast series (paginated)."""
    try:
        forecast_id, rows, total = await get_forecast_series(
            session, job_id, limit=limit, offset=offset
        )
        items = [
            ForecastSeriesResponse(
                ts_utc=r.ts_utc,
                y_hat=r.y_hat,
                q10=r.q10,
                q50=r.q50,
                q90=r.q90,
            )
            for r in rows
        ]
        return ForecastSeriesListResponse(
            job_id=job_id,
            forecast_id=forecast_id,
            rows=items,
            total=total,
        )
    except ForecastError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No forecast" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/summary")
async def forecast_summary(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get summary stats (min/max/mean per quantile)."""
    try:
        summary = await get_forecast_summary(session, job_id)
        return summary
    except ForecastError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No forecast" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc
