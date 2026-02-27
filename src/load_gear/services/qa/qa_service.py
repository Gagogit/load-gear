"""QA orchestration service: run 9 checks, save findings, advance job state."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import Job, JobStatus
from load_gear.repositories import job_repo, meter_read_repo, quality_finding_repo
from load_gear.services.job_service import validate_transition
from load_gear.services.qa.config import get_qa_config
from load_gear.services.qa.checks import (
    interval_completeness,
    completeness_pct,
    gaps_duplicates,
    daily_monthly_energy,
    peak_load,
    baseload,
    load_factor,
    hourly_weekday_profile,
    dst_conformity,
)

logger = logging.getLogger(__name__)


# Ordered list of all 9 QA checks
ALL_CHECKS = [
    interval_completeness,
    completeness_pct,
    gaps_duplicates,
    daily_monthly_energy,
    peak_load,
    baseload,
    load_factor,
    hourly_weekday_profile,
    dst_conformity,
]


class QAError(Exception):
    """Raised when QA pipeline fails."""
    pass


async def run_qa(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Run all 9 QA checks on v1 meter reads for a job.

    Returns a summary dict with overall_status and check count.
    """
    # 1. Validate job exists and is in qa_running state
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise QAError(f"Job {job_id} not found")

    if job.status != JobStatus.QA_RUNNING:
        raise QAError(
            f"Job {job_id} is in status '{job.status.value}', expected 'qa_running'"
        )

    # 2. Set current_phase
    job.current_phase = "P3"
    await session.flush()

    try:
        # 3. Fetch all v1 meter reads
        rows, total = await meter_read_repo.get_by_job_id(
            session, job_id, version=1, limit=100_000, offset=0
        )

        if total == 0:
            raise QAError(f"No v1 meter reads found for job {job_id}")

        # Convert ORM rows to dicts for check functions
        row_dicts = [
            {
                "ts_utc": r.ts_utc,
                "value": r.value,
                "unit": r.unit,
                "meter_id": r.meter_id,
            }
            for r in rows
        ]

        # Determine interval from job payload or detect from data
        interval_minutes = _detect_interval(row_dicts)

        # 4. Delete any previous findings (for re-runs)
        await quality_finding_repo.delete_by_job_id(session, job_id)

        # 5. Run all 9 checks
        config = get_qa_config()
        findings: list[dict] = []

        for check_module in ALL_CHECKS:
            finding = check_module.run(
                row_dicts, config,
                job_id=job_id,
                interval_minutes=interval_minutes,
            )
            findings.append(finding)

        # 6. Bulk insert findings
        await quality_finding_repo.bulk_insert(session, findings)

        # 7. Determine overall status
        statuses = [f["status"] for f in findings]
        if "error" in statuses:
            overall_status = "error"
        elif "warn" in statuses:
            overall_status = "warn"
        else:
            overall_status = "ok"

        # 8. Advance job state
        next_status = _determine_next_status(job, overall_status)
        job.status = next_status
        job.current_phase = None
        await session.flush()

        return {
            "job_id": str(job_id),
            "overall_status": overall_status,
            "checks_completed": len(findings),
            "checks_total": 9,
            "statuses": {f["check_name"]: f["status"] for f in findings},
        }

    except QAError:
        raise
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"QA error: {exc}"
        job.current_phase = None
        await session.flush()
        raise QAError(f"QA pipeline failed: {exc}") from exc


def _detect_interval(rows: list[dict]) -> int:
    """Detect interval minutes from the data (most common delta)."""
    if len(rows) < 2:
        return 15

    timestamps = sorted(r["ts_utc"] for r in rows)
    deltas = [
        int((timestamps[i] - timestamps[i - 1]).total_seconds() / 60)
        for i in range(1, min(len(timestamps), 20))
    ]
    # Most common positive delta
    positive_deltas = [d for d in deltas if d > 0]
    if not positive_deltas:
        return 15
    from collections import Counter
    most_common = Counter(positive_deltas).most_common(1)[0][0]
    return most_common


def _determine_next_status(job: Job, overall_status: str) -> JobStatus:
    """Determine next job status after QA based on tasks and results."""
    tasks = (job.payload or {}).get("tasks", ["Statistik"])
    task_set = set(tasks)

    # If job only has Statistik/Fehleranalyse → terminal after QA
    needs_analysis = task_set & {"Imputation", "Prognose", "Aggregation"}

    if overall_status == "error" and not needs_analysis:
        # Stats-only job with errors → WARN (completed but with issues)
        return JobStatus.WARN

    if needs_analysis:
        # Needs further processing
        return JobStatus.ANALYSIS_RUNNING

    # Stats-only job, all ok or warn → DONE
    if overall_status == "warn":
        return JobStatus.WARN
    return JobStatus.DONE


async def get_qa_status(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get QA run status for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise QAError(f"Job {job_id} not found")

    count = await quality_finding_repo.count_by_job_id(session, job_id)
    findings = await quality_finding_repo.get_by_job_id(session, job_id)

    overall_status = None
    if findings:
        statuses = [f.status for f in findings]
        if "error" in statuses:
            overall_status = "error"
        elif "warn" in statuses:
            overall_status = "warn"
        else:
            overall_status = "ok"

    return {
        "job_id": str(job_id),
        "status": job.status.value,
        "checks_completed": count,
        "checks_total": 9,
        "overall_status": overall_status,
        "error_message": job.error_message,
    }


async def get_qa_report(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get full QA report with all findings."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise QAError(f"Job {job_id} not found")

    findings = await quality_finding_repo.get_by_job_id(session, job_id)
    if not findings:
        raise QAError(f"No QA findings for job {job_id}")

    statuses = [f.status for f in findings]
    if "error" in statuses:
        overall_status = "error"
    elif "warn" in statuses:
        overall_status = "warn"
    else:
        overall_status = "ok"

    return {
        "job_id": str(job_id),
        "findings": findings,
        "overall_status": overall_status,
        "created_at": findings[0].created_at if findings else datetime.now(timezone.utc),
    }


async def get_qa_profile(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get hourly/weekday profile arrays from check 8 finding."""
    finding = await quality_finding_repo.get_by_job_and_check(session, job_id, 8)
    if finding is None:
        raise QAError(f"No profile data for job {job_id} (check 8 not found)")

    slots = finding.affected_slots or {}
    return {
        "job_id": str(job_id),
        "hourly_profile": slots.get("hourly_profile", [0.0] * 24),
        "weekday_profile": slots.get("weekday_profile", [0.0] * 7),
    }
