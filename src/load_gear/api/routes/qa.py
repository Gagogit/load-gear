"""QA Engine endpoints: /api/v1/qa."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    QAFindingResponse,
    QAProfileResponse,
    QAReportResponse,
    QARunRequest,
    QAStatusResponse,
)
from load_gear.repositories import quality_finding_repo
from load_gear.services.qa.qa_service import (
    QAError,
    get_qa_profile,
    get_qa_report,
    get_qa_status,
    run_qa,
)

router = APIRouter(prefix="/api/v1/qa", tags=["qa"])


@router.post("", status_code=202)
async def start_qa(
    body: QARunRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Start QA run (all 9 checks) for a job."""
    try:
        result = await run_qa(session, body.job_id)
        return result
    except QAError as exc:
        error_msg = str(exc)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        if "expected 'qa_running'" in error_msg:
            raise HTTPException(status_code=409, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/status", response_model=QAStatusResponse)
async def qa_status(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> QAStatusResponse:
    """Get QA run status for a job."""
    try:
        status = await get_qa_status(session, job_id)
        return QAStatusResponse(**status)
    except QAError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{job_id}/report")
async def qa_report(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get full QA report with all 9 check findings."""
    try:
        report = await get_qa_report(session, job_id)
        # Serialize findings from ORM objects
        findings = [
            QAFindingResponse.model_validate(f).model_dump(mode="json")
            for f in report["findings"]
        ]
        return {
            "job_id": str(report["job_id"]),
            "findings": findings,
            "overall_status": report["overall_status"],
            "created_at": report["created_at"].isoformat(),
        }
    except QAError as exc:
        error_msg = str(exc)
        if "not found" in error_msg or "No QA findings" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg) from exc
        raise HTTPException(status_code=422, detail=error_msg) from exc


@router.get("/{job_id}/findings", response_model=list[QAFindingResponse])
async def qa_findings(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[QAFindingResponse]:
    """Get individual QA findings for a job."""
    findings = await quality_finding_repo.get_by_job_id(session, job_id)
    if not findings:
        raise HTTPException(status_code=404, detail=f"No findings for job {job_id}")
    return [QAFindingResponse.model_validate(f) for f in findings]


@router.get("/{job_id}/profile", response_model=QAProfileResponse)
async def qa_profile(
    job_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> QAProfileResponse:
    """Get hourly/weekday profile arrays from QA check 8."""
    try:
        profile = await get_qa_profile(session, job_id)
        return QAProfileResponse(**profile)
    except QAError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
