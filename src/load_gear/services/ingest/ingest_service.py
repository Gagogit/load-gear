"""Ingest orchestration service: detect profile → normalize → update job state."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select as sa_select

from load_gear.models.control import File, Job, JobStatus, ReaderProfile
from load_gear.models.schemas import ReaderProfileRules
from load_gear.repositories import file_repo, job_repo
from load_gear.repositories import reader_profile_repo, meter_read_repo
from load_gear.services.ingest.format_detector import detect_format, ParseError
from load_gear.services.ingest.normalizer import normalize, NormalizationError
from load_gear.services.job_service import validate_transition
from load_gear.core.storage import get_storage

logger = logging.getLogger(__name__)


class IngestError(Exception):
    """Raised when ingest pipeline fails."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message)
        self.context = context or {}


async def run_ingest(
    session: AsyncSession,
    job_id: uuid.UUID,
    file_id: uuid.UUID,
) -> dict:
    """Run the full P2 ingest pipeline: detect → normalize → store.

    Returns quality stats dict.
    """
    # 1. Validate job exists and is in pending state
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise IngestError(f"Job {job_id} not found")

    if job.status != JobStatus.PENDING:
        raise IngestError(
            f"Job {job_id} is in status '{job.status.value}', expected 'pending'"
        )

    # 2. Validate file exists
    file_record = await file_repo.get_file_by_id(session, file_id)
    if file_record is None:
        raise IngestError(f"File {file_id} not found")

    # 3. Advance job → ingesting
    if not validate_transition(job.status, JobStatus.INGESTING):
        raise IngestError(f"Cannot transition job from {job.status.value} to ingesting")

    job.status = JobStatus.INGESTING
    job.current_phase = "P2"
    await session.flush()

    try:
        # 4. Load raw file bytes
        storage = get_storage()
        storage_path = file_record.storage_uri
        if storage_path.startswith("local://"):
            storage_path = storage_path[len("local://"):]
        raw_bytes = await storage.get(storage_path)

        # 5. Check for existing reader profile (manual override)
        existing_profile = await reader_profile_repo.get_by_file_id(session, file_id)

        if existing_profile and existing_profile.is_override:
            rules_dict = existing_profile.rules
            logger.info(f"Using manually overridden reader profile for file {file_id}")
        else:
            # 6. Run format detection (P2a)
            rules_dict = detect_format(raw_bytes)

            # Save reader profile
            if existing_profile:
                await reader_profile_repo.update_reader_profile(
                    session, existing_profile, rules=rules_dict
                )
            else:
                profile = ReaderProfile(
                    id=uuid.uuid4(),
                    file_id=file_id,
                    rules=rules_dict,
                    is_override=False,
                )
                await reader_profile_repo.create_reader_profile(session, profile)

        # 7. Run normalization (P2b)
        meter_id = job.meter_id or str(job_id)
        rows, quality_stats = normalize(
            raw_bytes,
            rules_dict,
            meter_id=meter_id,
            job_id=job_id,
            source_file_id=file_id,
        )

        # 8. Delete old v1 data for this meter (allows re-upload)
        old_count = await meter_read_repo.delete_by_meter_version(
            session, meter_id, version=1
        )
        if old_count > 0:
            logger.info(
                "Deleted %d old v1 rows for meter %s before re-ingest",
                old_count, meter_id,
            )
            quality_stats.setdefault("warnings", []).append(
                f"{old_count} old v1 rows replaced by new upload"
            )

        # 9. Bulk insert into meter_reads
        inserted = await meter_read_repo.bulk_insert(session, rows)
        quality_stats["inserted_rows"] = inserted

        # 9. Update reader profile with quality stats
        profile = await reader_profile_repo.get_by_file_id(session, file_id)
        if profile:
            await reader_profile_repo.update_reader_profile(
                session, profile, technical_quality=quality_stats
            )

        # 10. Advance job state
        tasks = (job.payload or {}).get("tasks", ["Statistik"])
        next_status = _determine_next_status(tasks)
        job.status = next_status
        job.current_phase = None
        await session.flush()

        return quality_stats

    except (ParseError, NormalizationError) as exc:
        # Pipeline failure — set job to failed
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
        job.current_phase = None
        await session.flush()
        ctx = getattr(exc, "context", None) or {}
        raise IngestError(str(exc), context=ctx) from exc
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Unexpected ingest error: {exc}"
        job.current_phase = None
        await session.flush()
        raise IngestError(f"Unexpected ingest error: {exc}") from exc


def _determine_next_status(tasks: list[str]) -> JobStatus:
    """Determine the next job status after successful ingest based on configured tasks."""
    # If any task requires QA/analysis/forecast, advance to qa_running
    task_set = set(tasks)
    if task_set & {"Statistik", "Fehleranalyse", "Imputation", "Prognose", "Aggregation"}:
        return JobStatus.QA_RUNNING
    return JobStatus.DONE


async def get_ingest_status(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get ingest status for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise IngestError(f"Job {job_id} not found")

    # Count meter reads
    total = await meter_read_repo.count_by_job_id(session, job_id, version=1)

    # Find reader profile quality stats via file query
    quality_stats: dict = {}
    files_result = await session.execute(
        sa_select(File).where(File.job_id == job_id)
    )
    files = list(files_result.scalars().all())
    for f in files:
        profile = await reader_profile_repo.get_by_file_id(session, f.id)
        if profile and profile.technical_quality:
            quality_stats = profile.technical_quality
            break

    return {
        "job_id": str(job_id),
        "status": job.status.value,
        "current_phase": job.current_phase,
        "total_rows": quality_stats.get("total_rows", total),
        "valid_rows": quality_stats.get("valid_rows", total),
        "invalid_rows": quality_stats.get("invalid_rows", 0),
        "warnings": quality_stats.get("warnings", []),
        "error_message": job.error_message,
    }
