"""File upload and download endpoints: /api/v1/files."""

from __future__ import annotations

import mimetypes
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.core.storage import compute_sha256, get_storage
from load_gear.models.control import File
from load_gear.models.schemas import (
    FileResponse,
    FileUploadResponse,
    ReaderProfileOverrideRequest,
    ReaderProfileResponse,
)
from load_gear.repositories import file_repo, reader_profile_repo

router = APIRouter(prefix="/api/v1/files", tags=["files"])


@router.post("/upload", response_model=FileUploadResponse, status_code=201)
async def upload_file(
    file: UploadFile,
    job_id: uuid.UUID = Query(..., description="Job to attach the file to"),
    session: AsyncSession = Depends(get_session),
) -> FileUploadResponse:
    """Upload a source file (CSV/Excel). Deduplicates by SHA-256."""
    data = await file.read()
    sha256 = compute_sha256(data)

    # Check for duplicate
    existing = await file_repo.get_file_by_sha256(session, sha256)
    if existing is not None:
        return FileUploadResponse(
            id=existing.id,
            sha256=existing.sha256,
            original_name=existing.original_name,
            file_size=existing.file_size,
            duplicate=True,
        )

    # Determine file extension and mime type
    original_name = file.filename or "upload"
    mime_type = file.content_type or mimetypes.guess_type(original_name)[0]
    ext = original_name.rsplit(".", 1)[-1] if "." in original_name else "bin"

    # Store file
    file_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    storage_path = f"raw/{now.year}/{file_id}.{ext}"
    storage = get_storage()
    storage_uri = await storage.save(storage_path, data)

    # Create DB record
    file_record = File(
        id=file_id,
        job_id=job_id,
        storage_uri=storage_uri,
        original_name=original_name,
        sha256=sha256,
        file_size=len(data),
        mime_type=mime_type,
    )
    await file_repo.create_file(session, file_record)

    return FileUploadResponse(
        id=file_id,
        sha256=sha256,
        original_name=original_name,
        file_size=len(data),
        duplicate=False,
    )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file_metadata(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    """Get file metadata by ID."""
    file_record = await file_repo.get_file_by_id(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")
    return FileResponse.model_validate(file_record)


@router.get("/{file_id}/download")
async def download_file(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download the original file content."""
    file_record = await file_repo.get_file_by_id(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    storage = get_storage()
    # Extract storage path from URI (strip local:// prefix)
    storage_path = file_record.storage_uri
    if storage_path.startswith("local://"):
        storage_path = storage_path[len("local://"):]

    data = await storage.get(storage_path)

    return Response(
        content=data,
        media_type=file_record.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file_record.original_name}"'},
    )


# --- Reader Profile endpoints (P2a) ---


@router.get("/{file_id}/reader-profile", response_model=ReaderProfileResponse)
async def get_reader_profile(
    file_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ReaderProfileResponse:
    """Get the reader profile (detected or overridden parsing rules) for a file."""
    file_record = await file_repo.get_file_by_id(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    profile = await reader_profile_repo.get_by_file_id(session, file_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"No reader profile for file {file_id}"
        )

    return ReaderProfileResponse.model_validate(profile)


@router.put("/{file_id}/reader-profile", response_model=ReaderProfileResponse)
async def override_reader_profile(
    file_id: uuid.UUID,
    body: ReaderProfileOverrideRequest,
    session: AsyncSession = Depends(get_session),
) -> ReaderProfileResponse:
    """Override the reader profile rules for a file (sets is_override=True)."""
    file_record = await file_repo.get_file_by_id(session, file_id)
    if file_record is None:
        raise HTTPException(status_code=404, detail=f"File {file_id} not found")

    profile = await reader_profile_repo.get_by_file_id(session, file_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail=f"No reader profile for file {file_id}"
        )

    await reader_profile_repo.update_reader_profile(
        session,
        profile,
        rules=body.rules.model_dump(),
        is_override=True,
    )

    return ReaderProfileResponse.model_validate(profile)
