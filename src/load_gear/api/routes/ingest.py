"""Ingest pipeline endpoints: /api/v1/ingest."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    IngestRequest,
    IngestStatusResponse,
    NormalizedListResponse,
    NormalizedRowResponse,
)
from load_gear.repositories import meter_read_repo
from load_gear.services.ingest.ingest_service import IngestError, get_ingest_status, run_ingest

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.post("", status_code=202)
async def start_ingest(
    body: IngestRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Start the ingest pipeline (P2a detect + P2b normalize) for a job+file."""
    try:
        quality_stats = await run_ingest(session, body.job_id, body.file_id)
        return {
            "job_id": str(body.job_id),
            "status": "completed",
            **quality_stats,
        }
    except IngestError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        if "expected 'pending'" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/status", response_model=IngestStatusResponse)
async def ingest_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> IngestStatusResponse:
    """Get ingest progress/result for a job."""
    try:
        status = await get_ingest_status(session, job_id)
        return IngestStatusResponse(**status)
    except IngestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/normalized", response_model=NormalizedListResponse)
async def get_normalized_data(
    job_id: uuid.UUID,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> NormalizedListResponse:
    """Get normalized v1 meter reads for a job (paginated)."""
    rows, total = await meter_read_repo.get_by_job_id(
        session, job_id, version=1, limit=limit, offset=offset
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

    return NormalizedListResponse(items=items, total=total)
