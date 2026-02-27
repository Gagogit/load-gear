"""Async repository for analysis.analysis_profiles CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.analysis import AnalysisProfile


async def create_profile(
    session: AsyncSession,
    profile: AnalysisProfile,
) -> AnalysisProfile:
    """Insert a new analysis profile."""
    session.add(profile)
    await session.flush()
    return profile


async def get_by_job_id(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> AnalysisProfile | None:
    """Get analysis profile for a job."""
    result = await session.execute(
        select(AnalysisProfile).where(AnalysisProfile.job_id == job_id)
    )
    return result.scalar_one_or_none()


async def update_profile(
    session: AsyncSession,
    profile: AnalysisProfile,
    **kwargs: dict,
) -> AnalysisProfile:
    """Update analysis profile fields."""
    for key, value in kwargs.items():
        if hasattr(profile, key) and value is not None:
            setattr(profile, key, value)
    await session.flush()
    return profile
