"""Analysis orchestration service: P4.1→P4.2→P4.3→P4.4, advance job state."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.analysis import AnalysisProfile, ImputationRun
from load_gear.models.control import JobStatus
from load_gear.repositories import (
    job_repo,
    meter_read_repo,
    analysis_profile_repo,
    imputation_run_repo,
    quality_finding_repo,
)
from load_gear.services.analysis.day_classifier import classify_days
from load_gear.services.analysis.weather_enrichment import enrich_weather
from load_gear.services.analysis.asset_fingerprint import detect_assets
from load_gear.services.analysis.imputer import impute

logger = logging.getLogger(__name__)


class AnalysisError(Exception):
    """Raised when analysis pipeline fails."""
    pass


async def run_analysis(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Run full P4 analysis pipeline: classify → weather → assets → impute.

    Returns a summary dict.
    """
    # 1. Validate job exists and is in analysis_running state
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise AnalysisError(f"Job {job_id} not found")

    if job.status != JobStatus.ANALYSIS_RUNNING:
        raise AnalysisError(
            f"Job {job_id} is in status '{job.status.value}', expected 'analysis_running'"
        )

    # 2. Set current_phase
    job.current_phase = "P4"
    await session.flush()

    try:
        # 3. Fetch v1 meter reads
        rows, total = await meter_read_repo.get_by_job_id(
            session, job_id, version=1, limit=100_000, offset=0
        )
        if total == 0:
            raise AnalysisError(f"No v1 meter reads found for job {job_id}")

        row_dicts = [
            {
                "ts_utc": r.ts_utc,
                "value": r.value,
                "unit": r.unit,
                "meter_id": r.meter_id,
            }
            for r in rows
        ]

        meter_id = job.meter_id or str(job_id)

        # Detect interval
        interval_minutes = _detect_interval(row_dicts)

        # Get source file id from first v1 row
        source_file_id = rows[0].source_file_id if rows else None

        # --- P4.1: Day Classification ---
        job.current_phase = "P4.1"
        await session.flush()

        day_fingerprints, day_labels = classify_days(
            row_dicts, interval_minutes=interval_minutes,
        )

        # --- P4.2: Weather Enrichment ---
        job.current_phase = "P4.2"
        await session.flush()

        weather_correlations = enrich_weather(row_dicts, weather_data=None)

        # --- P4.3: Asset Fingerprinting (STUB) ---
        job.current_phase = "P4.3"
        await session.flush()

        asset_result = detect_assets(row_dicts)
        asset_hints = asset_result.get("asset_hints")

        # --- Save analysis profile ---
        profile = AnalysisProfile(
            id=uuid.uuid4(),
            job_id=job_id,
            meter_id=meter_id,
            day_fingerprints=day_fingerprints,
            seasonality={"daily": True, "weekly": True, "yearly": len(row_dicts) > 35000},
            weather_correlations=weather_correlations,
            asset_hints=asset_result if asset_hints else None,
            impute_policy={
                "method": "chain",
                "max_gap_min": 1440,
                "outlier_clip_p": 99.0,
                "fallback": "linear",
            },
        )
        await analysis_profile_repo.create_profile(session, profile)

        # --- P4.4: Imputation ---
        job.current_phase = "P4.4"
        await session.flush()

        v2_rows, method_summary = impute(
            row_dicts,
            day_fingerprints,
            day_labels,
            weather_correlations=weather_correlations,
            asset_hints=asset_hints,
            interval_minutes=interval_minutes,
            meter_id=meter_id,
            job_id=job_id,
            source_file_id=source_file_id,
        )

        # Insert v2 rows
        if v2_rows:
            inserted = await meter_read_repo.bulk_insert(session, v2_rows)
            method_summary["inserted_v2"] = inserted

        # Create imputation run record
        slots_replaced = method_summary.get("profile", 0) + method_summary.get("interpolation", 0) + method_summary.get("weather", 0)
        imp_run = ImputationRun(
            id=uuid.uuid4(),
            analysis_profile_id=profile.id,
            job_id=job_id,
            slots_replaced=slots_replaced,
            method_summary=method_summary,
        )
        await imputation_run_repo.create_run(session, imp_run)

        # 4. Advance job state
        next_status = _determine_next_status(job)
        job.status = next_status
        job.current_phase = None
        await session.flush()

        return {
            "job_id": str(job_id),
            "profile_id": str(profile.id),
            "day_types": len(day_fingerprints),
            "total_days": len(day_labels),
            "v2_rows": len(v2_rows),
            "slots_replaced": slots_replaced,
            "method_summary": method_summary,
            "weather_available": weather_correlations.get("data_available", False),
        }

    except AnalysisError:
        raise
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Analysis error: {exc}"
        job.current_phase = None
        await session.flush()
        raise AnalysisError(f"Analysis pipeline failed: {exc}") from exc


def _detect_interval(rows: list[dict]) -> int:
    """Detect interval minutes from the data."""
    if len(rows) < 2:
        return 15
    timestamps = sorted(r["ts_utc"] for r in rows)
    deltas = [
        int((timestamps[i] - timestamps[i - 1]).total_seconds() / 60)
        for i in range(1, min(len(timestamps), 20))
    ]
    positive_deltas = [d for d in deltas if d > 0]
    if not positive_deltas:
        return 15
    from collections import Counter
    return Counter(positive_deltas).most_common(1)[0][0]


def _determine_next_status(job) -> JobStatus:
    """Determine next job status after analysis based on tasks."""
    tasks = (job.payload or {}).get("tasks", ["Statistik"])
    task_set = set(tasks)
    if task_set & {"Prognose", "Aggregation"}:
        return JobStatus.FORECAST_RUNNING
    return JobStatus.DONE


async def get_analysis_status(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get analysis status for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise AnalysisError(f"Job {job_id} not found")

    profile = await analysis_profile_repo.get_by_job_id(session, job_id)
    imp_run = await imputation_run_repo.get_latest_by_job_id(session, job_id)

    return {
        "job_id": str(job_id),
        "status": job.status.value,
        "current_phase": job.current_phase,
        "sub_phase": job.current_phase,
        "has_profile": profile is not None,
        "has_imputation": imp_run is not None,
        "error_message": job.error_message,
    }


async def get_analysis_profile(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> AnalysisProfile:
    """Get analysis profile for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise AnalysisError(f"Job {job_id} not found")

    profile = await analysis_profile_repo.get_by_job_id(session, job_id)
    if profile is None:
        raise AnalysisError(f"No analysis profile for job {job_id}")
    return profile


async def get_day_labels(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> list[dict]:
    """Get day labels from the analysis profile."""
    profile = await get_analysis_profile(session, job_id)
    # Day labels are derived from fingerprints — we reconstruct from stored data
    # In a full implementation, day_labels would be stored separately
    # For now, return the fingerprint keys and their counts
    fingerprints = profile.day_fingerprints or {}
    labels: list[dict] = []
    for label, data in fingerprints.items():
        labels.append({
            "label": label,
            "count": data.get("count", 0),
        })
    return labels


async def get_imputation_report(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get imputation report for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise AnalysisError(f"Job {job_id} not found")

    imp_run = await imputation_run_repo.get_latest_by_job_id(session, job_id)
    if imp_run is None:
        raise AnalysisError(f"No imputation run for job {job_id}")

    # Count v2 rows
    v2_count = await meter_read_repo.count_by_job_id(session, job_id, version=2)

    return {
        "job_id": str(job_id),
        "slots_replaced": imp_run.slots_replaced,
        "method_summary": imp_run.method_summary or {},
        "total_v2_rows": v2_count,
    }
