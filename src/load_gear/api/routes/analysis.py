"""Analysis & Imputation endpoints: /api/v1/analysis."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    AnalysisProfileResponse,
    AnalysisRunRequest,
    AnalysisStatusResponse,
    DayFingerprintEntry,
    DayLabelEntry,
    DayLabelsResponse,
    ImputationReportResponse,
    NormalizedRowResponse,
    NormalizedV2Response,
    WeatherResponse,
)
from load_gear.repositories import meter_read_repo
from load_gear.services.analysis.analysis_service import (
    AnalysisError,
    get_analysis_profile,
    get_analysis_status,
    get_day_labels,
    get_imputation_report,
    run_analysis,
)

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post("", status_code=202)
async def start_analysis(
    body: AnalysisRunRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Start analysis run (P4.1→P4.4) for a job."""
    try:
        result = await run_analysis(session, body.job_id)
        return result
    except AnalysisError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        if "expected 'analysis_running'" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/status", response_model=AnalysisStatusResponse)
async def analysis_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AnalysisStatusResponse:
    """Get analysis status for a job."""
    try:
        status = await get_analysis_status(session, job_id)
        return AnalysisStatusResponse(**status)
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/profile")
async def analysis_profile(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get analysis profile (day fingerprints, seasonality, weather, etc.)."""
    try:
        profile = await get_analysis_profile(session, job_id)
        # Serialize manually to handle JSONB fields
        return {
            "job_id": str(profile.job_id),
            "meter_id": profile.meter_id,
            "day_fingerprints": profile.day_fingerprints,
            "seasonality": profile.seasonality,
            "weather_correlations": profile.weather_correlations,
            "asset_hints": profile.asset_hints,
            "impute_policy": profile.impute_policy,
            "created_at": profile.created_at.isoformat(),
        }
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/day-labels")
async def analysis_day_labels(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get day classification labels and scores."""
    try:
        labels = await get_day_labels(session, job_id)
        return {
            "job_id": str(job_id),
            "labels": labels,
            "total": len(labels),
        }
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/weather")
async def analysis_weather(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get weather features and correlations."""
    try:
        profile = await get_analysis_profile(session, job_id)
        return {
            "job_id": str(job_id),
            "features": [],  # No weather observations in v0.1
            "correlations": profile.weather_correlations,
        }
    except AnalysisError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/imputation")
async def analysis_imputation(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get imputation report (replaced slots, methods, fallback flags)."""
    try:
        report = await get_imputation_report(session, job_id)
        return report
    except AnalysisError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No imputation" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/normalized-v2", response_model=NormalizedV2Response)
async def analysis_normalized_v2(
    job_id: uuid.UUID,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> NormalizedV2Response:
    """Get cleaned v2 time series (paginated)."""
    rows, total = await meter_read_repo.get_by_job_id(
        session, job_id, version=2, limit=limit, offset=offset
    )

    items = [
        NormalizedRowResponse(
            ts_utc=r.ts_utc,
            meter_id=r.meter_id,
            value=r.value,
            unit=r.unit,
            version=r.version,
            quality_flag=r.quality_flag,
        )
        for r in rows
    ]

    return NormalizedV2Response(items=items, total=total)
