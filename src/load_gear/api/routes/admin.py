"""Admin endpoints: health check, config, queue status."""

from __future__ import annotations

from fastapi import APIRouter

from load_gear.core.database import check_db_connection
from load_gear.models.schemas import AdminConfigResponse
from load_gear.services.qa.config import get_qa_config, update_qa_config

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/health")
async def health_check():
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
    }


@router.get("/config", response_model=AdminConfigResponse)
async def get_config() -> AdminConfigResponse:
    """Get current QA threshold configuration."""
    config = get_qa_config()
    return AdminConfigResponse(**config.to_dict())


@router.put("/config", response_model=AdminConfigResponse)
async def put_config(body: AdminConfigResponse) -> AdminConfigResponse:
    """Update QA threshold configuration."""
    updated = update_qa_config(body.model_dump())
    return AdminConfigResponse(**updated.to_dict())
