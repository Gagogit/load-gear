"""Admin endpoints: health check, config, queue status."""

from __future__ import annotations

from fastapi import APIRouter

from load_gear.core.database import check_db_connection

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/health")
async def health_check():
    db_ok = await check_db_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "unreachable",
    }
