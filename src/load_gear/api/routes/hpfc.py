"""HPFC endpoints: /api/v1/hpfc."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    HpfcSeriesListResponse,
    HpfcSeriesResponse,
    HpfcSnapshotListResponse,
    HpfcSnapshotResponse,
    HpfcUploadResponse,
)
from load_gear.services.financial.hpfc_service import (
    HpfcError,
    delete_snapshot_cascade,
    get_series,
    get_snapshot,
    list_snapshots,
    upload_hpfc,
)

router = APIRouter(prefix="/api/v1/hpfc", tags=["hpfc"])


@router.post("/upload", status_code=201, response_model=HpfcUploadResponse)
async def upload_hpfc_csv(
    file: UploadFile = File(...),
    provider_id: str = Query("manual", description="Provider identifier"),
    curve_type: str = Query("HPFC", description="Curve type: HPFC, Spot, Intraday"),
    currency: str = Query("EUR", description="Currency code"),
    session: AsyncSession = Depends(get_session),
) -> HpfcUploadResponse:
    """Upload an HPFC price curve CSV file."""
    try:
        content = await file.read()
        result = await upload_hpfc(
            session,
            content,
            file.filename or "unknown.csv",
            provider_id=provider_id,
            curve_type=curve_type,
            currency=currency,
        )
        return HpfcUploadResponse(
            snapshot_id=uuid.UUID(result["snapshot_id"]),
            provider_id=result["provider_id"],
            rows_imported=result["rows_imported"],
            delivery_start=result["delivery_start"],
            delivery_end=result["delivery_end"],
        )
    except HpfcError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=HpfcSnapshotListResponse)
async def list_hpfc_snapshots(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> HpfcSnapshotListResponse:
    """List all HPFC snapshots."""
    snapshots, total = await list_snapshots(session, limit=limit, offset=offset)
    items = [
        HpfcSnapshotResponse.model_validate(s)
        for s in snapshots
    ]
    return HpfcSnapshotListResponse(items=items, total=total)


@router.get("/{snapshot_id}", response_model=HpfcSnapshotResponse)
async def get_hpfc_snapshot(
    snapshot_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> HpfcSnapshotResponse:
    """Get HPFC snapshot metadata."""
    try:
        snapshot = await get_snapshot(session, snapshot_id)
        return HpfcSnapshotResponse.model_validate(snapshot)
    except HpfcError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{snapshot_id}/series", response_model=HpfcSeriesListResponse)
async def get_hpfc_series(
    snapshot_id: uuid.UUID,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> HpfcSeriesListResponse:
    """Get HPFC price curve series (paginated)."""
    try:
        rows, total = await get_series(
            session, snapshot_id, limit=limit, offset=offset
        )
        items = [
            HpfcSeriesResponse(ts_utc=r.ts_utc, price_mwh=r.price_mwh)
            for r in rows
        ]
        return HpfcSeriesListResponse(
            snapshot_id=snapshot_id,
            rows=items,
            total=total,
        )
    except HpfcError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{snapshot_id}", status_code=204)
async def delete_hpfc_snapshot(
    snapshot_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete an HPFC snapshot and all its series data."""
    try:
        await delete_snapshot_cascade(session, snapshot_id)
    except HpfcError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
