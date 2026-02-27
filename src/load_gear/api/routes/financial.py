"""Financial endpoints: /api/v1/financial."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import FinancialCalcRequest, FinancialResultResponse
from load_gear.services.financial.financial_service import (
    FinancialError,
    export_financial,
    get_financial_result,
    run_financial,
)

router = APIRouter(prefix="/api/v1/financial", tags=["financial"])


@router.post("/calculate", status_code=202)
async def calculate_financial(
    body: FinancialCalcRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Trigger financial calculation for a job in financial_running state."""
    try:
        result = await run_financial(
            session,
            body.job_id,
            snapshot_id=body.snapshot_id,
        )
        # Return summary (without full cost_rows for brevity)
        return {
            "calc_id": result["calc_id"],
            "job_id": result["job_id"],
            "total_cost_eur": result["total_cost_eur"],
            "matched_intervals": result["matched_intervals"],
            "total_forecast_rows": result["total_forecast_rows"],
            "monthly_summary": result["monthly_summary"],
        }
    except FinancialError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        if "expected 'financial_running'" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/result")
async def financial_result(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get financial calculation result with cost time series and monthly summaries."""
    try:
        result = await get_financial_result(session, job_id)
        return result
    except FinancialError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No financial" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/export")
async def financial_export(
    job_id: uuid.UUID,
    format: str = Query("csv", description="Export format: csv or xlsx"),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Export financial results as CSV or XLSX file."""
    try:
        content, content_type, filename = await export_financial(
            session, job_id, fmt=format
        )
        return Response(
            content=content,
            media_type=content_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except FinancialError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No financial" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc
