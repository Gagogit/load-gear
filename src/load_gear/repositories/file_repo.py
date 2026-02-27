"""Async repository for control.files CRUD operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import File


async def create_file(session: AsyncSession, file: File) -> File:
    """Insert a new file record and return it."""
    session.add(file)
    await session.flush()
    return file


async def get_file_by_id(session: AsyncSession, file_id: uuid.UUID) -> File | None:
    """Fetch a single file by ID."""
    return await session.get(File, file_id)


async def get_file_by_sha256(session: AsyncSession, sha256: str) -> File | None:
    """Find a file by its SHA-256 hash (duplicate detection)."""
    result = await session.execute(
        select(File).where(File.sha256 == sha256).limit(1)
    )
    return result.scalar_one_or_none()
