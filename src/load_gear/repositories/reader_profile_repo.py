"""Async repository for control.reader_profiles CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import ReaderProfile


async def create_reader_profile(session: AsyncSession, profile: ReaderProfile) -> ReaderProfile:
    """Insert a new reader profile and return it."""
    session.add(profile)
    await session.flush()
    return profile


async def get_by_file_id(session: AsyncSession, file_id: uuid.UUID) -> ReaderProfile | None:
    """Fetch a reader profile by its file_id."""
    result = await session.execute(
        select(ReaderProfile).where(ReaderProfile.file_id == file_id).limit(1)
    )
    return result.scalar_one_or_none()


async def update_reader_profile(
    session: AsyncSession,
    profile: ReaderProfile,
    *,
    rules: dict | None = None,
    technical_quality: dict | None = None,
    is_override: bool | None = None,
) -> ReaderProfile:
    """Update fields on an existing reader profile."""
    if rules is not None:
        profile.rules = rules
    if technical_quality is not None:
        profile.technical_quality = technical_quality
    if is_override is not None:
        profile.is_override = is_override
    await session.flush()
    return profile
