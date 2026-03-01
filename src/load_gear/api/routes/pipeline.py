"""Pipeline endpoints: /api/v1/pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import PipelineStatusResponse
from load_gear.services.pipeline_service import (
    PipelineError,
    get_led_status,
    run_pipeline,
)
from load_gear.services.financial.financial_service import (
    FinancialError,
    export_financial,
)
from load_gear.services.forecast.forecast_service import (
    ForecastError,
    get_forecast_series,
)
from load_gear.repositories import job_repo

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/run", status_code=202)
async def pipeline_run(
    project_name: str = Form(...),
    malo_id: str = Form(...),
    plz: str = Form(""),
    user_id: str = Form(""),
    prognosis_from: str = Form(""),
    prognosis_to: str = Form(""),
    growth_pct: float = Form(100.0),
    provider_ids: str = Form(""),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Run the full pipeline: upload → ingest → QA → analysis → forecast → financial."""
    # Parse optional dates
    p_from: datetime | None = None
    p_to: datetime | None = None
    if prognosis_from:
        try:
            p_from = datetime.fromisoformat(prognosis_from)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid prognosis_from: {prognosis_from}")
    if prognosis_to:
        try:
            p_to = datetime.fromisoformat(prognosis_to)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid prognosis_to: {prognosis_to}")

    file_content = await file.read()
    file_name = file.filename or "upload.csv"

    # Parse provider_ids from comma-separated string
    parsed_provider_ids: list[str] | None = None
    if provider_ids.strip():
        parsed_provider_ids = [p.strip() for p in provider_ids.split(",") if p.strip()]

    result = await run_pipeline(
        session,
        project_name=project_name,
        malo_id=malo_id,
        plz=plz,
        user_id=user_id,
        prognosis_from=p_from,
        prognosis_to=p_to,
        growth_pct=growth_pct,
        provider_ids=parsed_provider_ids,
        file_content=file_content,
        file_name=file_name,
    )
    return result


@router.get("/{job_id}/status", response_model=PipelineStatusResponse)
async def pipeline_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PipelineStatusResponse:
    """Get 10 LED status booleans for a pipeline job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    leds = await get_led_status(session, job_id)
    return PipelineStatusResponse(
        job_id=job_id,
        status=job.status.value,
        error_message=job.error_message,
        error_context=job.error_context,
        leds=leds,
    )


@router.get("/{job_id}/download")
async def pipeline_download(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download pipeline results: financial CSV if available, else forecast series CSV."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Try financial export first
    try:
        content, content_type, filename = await export_financial(session, job_id, fmt="csv")
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FinancialError:
        pass

    # Fallback to forecast series CSV (German format: semicolon + decimal comma)
    try:
        forecast_id, rows, total = await get_forecast_series(session, job_id, limit=100_000, offset=0)

        def _fmt(v: float | None) -> str:
            if v is None:
                return ""
            return f"{v:.4f}".replace(".", ",")

        lines = ["ts_utc;y_hat;q10;q50;q90"]
        for r in rows:
            lines.append(
                f"{r.ts_utc.isoformat()};{_fmt(r.y_hat)};{_fmt(r.q10)};{_fmt(r.q50)};{_fmt(r.q90)}"
            )
        csv_content = "\n".join(lines).encode("utf-8-sig")
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="forecast_{job_id}.csv"'},
        )
    except ForecastError:
        raise HTTPException(status_code=404, detail="No results available for download")
