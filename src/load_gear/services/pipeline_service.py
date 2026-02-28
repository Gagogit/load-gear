"""Pipeline orchestration service: chain all phases into a single run."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import File, Job, JobStatus, ReaderProfile
from load_gear.repositories import (
    analysis_profile_repo,
    file_repo,
    forecast_run_repo,
    forecast_series_repo,
    job_repo,
    meter_read_repo,
    reader_profile_repo,
)
from load_gear.services.ingest.ingest_service import IngestError, run_ingest
from load_gear.services.qa.qa_service import QAError, run_qa
from load_gear.services.analysis.analysis_service import AnalysisError, run_analysis
from load_gear.services.forecast.forecast_service import ForecastError, run_forecast
from load_gear.services.financial.financial_service import FinancialError, run_financial
from load_gear.services.job_service import validate_transition

logger = logging.getLogger(__name__)


class PipelineError(Exception):
    """Raised when the pipeline fails at any stage."""
    pass


async def run_pipeline(
    session: AsyncSession,
    *,
    project_name: str,
    malo_id: str,
    plz: str,
    user_id: str,
    prognosis_from: datetime | None,
    prognosis_to: datetime | None,
    file_content: bytes,
    file_name: str,
) -> dict:
    """Run the full pipeline: create job → upload → ingest → QA → analysis → forecast → [financial] → done.

    Returns dict with job_id, status, and LED states.
    """
    from load_gear.core.storage import compute_sha256, get_storage
    from load_gear.models.schemas import JobCreateRequest
    from load_gear.services.job_service import create_job

    # 1. Create job
    request = JobCreateRequest(
        project_name=project_name,
        meter_id=malo_id,
        plz=plz,
        user_id=user_id,
        tasks=["Aggregation"],
        horizon_months=None,
    )
    job = await create_job(session, request)
    job_id = job.id

    # Store prognosis dates in payload
    payload = job.payload or {}
    if prognosis_from:
        payload["prognosis_from"] = prognosis_from.isoformat()
    if prognosis_to:
        payload["prognosis_to"] = prognosis_to.isoformat()
    job.payload = payload
    await session.flush()

    try:
        # 2. Upload file
        sha256 = compute_sha256(file_content)
        file_id = uuid.uuid4()
        ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "csv"
        storage_path = f"raw/{datetime.now(timezone.utc).year}/{file_id}.{ext}"
        storage = get_storage()
        storage_uri = await storage.save(storage_path, file_content)

        file_record = File(
            id=file_id,
            job_id=job_id,
            storage_uri=storage_uri,
            original_name=file_name,
            sha256=sha256,
            file_size=len(file_content),
            mime_type="text/csv",
        )
        await file_repo.create_file(session, file_record)

        # 3. Ingest (pending → ingesting → qa_running)
        await run_ingest(session, job_id, file_id)

        # Refresh job
        job = await job_repo.get_job_by_id(session, job_id)

        # 4. QA (already in qa_running after ingest with Aggregation task)
        if job.status == JobStatus.QA_RUNNING:
            await run_qa(session, job_id)
            job = await job_repo.get_job_by_id(session, job_id)

        # 5. Analysis (qa_running → analysis_running → forecast_running)
        if job.status == JobStatus.ANALYSIS_RUNNING:
            await run_analysis(session, job_id)
            job = await job_repo.get_job_by_id(session, job_id)

        # 6. Forecast with prognosis dates as horizon
        if job.status == JobStatus.FORECAST_RUNNING:
            await run_forecast(
                session,
                job_id,
                horizon_start=prognosis_from,
                horizon_end=prognosis_to,
            )
            job = await job_repo.get_job_by_id(session, job_id)

        # 7. Financial (if Aggregation task pushes to financial_running)
        if job.status == JobStatus.FINANCIAL_RUNNING:
            try:
                await run_financial(session, job_id)
            except FinancialError as exc:
                # Financial may fail if no HPFC snapshot — still advance to done
                logger.warning(f"Financial step skipped: {exc}")
                job = await job_repo.get_job_by_id(session, job_id)
                if job.status == JobStatus.FINANCIAL_RUNNING:
                    job.status = JobStatus.DONE
                    job.current_phase = None
                    await session.flush()
            job = await job_repo.get_job_by_id(session, job_id)

        leds = await get_led_status(session, job_id)
        return {
            "job_id": str(job_id),
            "status": job.status.value,
            "leds": leds,
        }

    except (IngestError, QAError, AnalysisError, ForecastError) as exc:
        # Job already marked as FAILED by the service
        leds = await get_led_status(session, job_id)
        result: dict = {
            "job_id": str(job_id),
            "status": "failed",
            "error_message": str(exc),
            "leds": leds,
        }
        error_ctx = getattr(exc, "context", None)
        if not error_ctx and exc.__cause__:
            error_ctx = getattr(exc.__cause__, "context", None)
        if error_ctx:
            result["error_context"] = error_ctx
        return result
    except Exception as exc:
        logger.exception(f"Pipeline failed for job {job_id}")
        try:
            job = await job_repo.get_job_by_id(session, job_id)
            if job and job.status not in (JobStatus.DONE, JobStatus.WARN, JobStatus.FAILED):
                job.status = JobStatus.FAILED
                job.error_message = f"Pipeline error: {exc}"
                job.current_phase = None
                await session.flush()
            leds = await get_led_status(session, job_id)
        except Exception:
            logger.exception("Failed to update job status after pipeline error")
            leds = {str(i): False for i in range(1, 11)}
        return {
            "job_id": str(job_id),
            "status": "failed",
            "error_message": str(exc),
            "leds": leds,
        }


async def get_led_status(session: AsyncSession, job_id: uuid.UUID) -> dict[str, bool]:
    """Compute 10 LED booleans for a job.

    Returns dict with keys "1".."10" → bool.
    """
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        return {str(i): False for i in range(1, 11)}

    status_order = [
        JobStatus.PENDING, JobStatus.INGESTING, JobStatus.QA_RUNNING,
        JobStatus.ANALYSIS_RUNNING, JobStatus.FORECAST_RUNNING,
        JobStatus.FINANCIAL_RUNNING, JobStatus.DONE, JobStatus.WARN,
    ]

    def status_ge(threshold: JobStatus) -> bool:
        """Check if job status is >= threshold in the pipeline order."""
        if job.status == JobStatus.FAILED:
            # For failed jobs, check what phase was reached
            return False
        try:
            return status_order.index(job.status) >= status_order.index(threshold)
        except ValueError:
            return False

    # LED 1: Upload erfolgreich — file exists for this job
    files_result = await session.execute(
        select(File.id).where(File.job_id == job_id).limit(1)
    )
    file_row = files_result.first()
    led_1 = file_row is not None

    # LED 2: Format erkannt — reader profile exists with rules
    led_2 = False
    if file_row:
        profile = await reader_profile_repo.get_by_file_id(session, file_row[0])
        led_2 = profile is not None and profile.rules is not None

    # LED 3: Original gespeichert — v1 meter reads exist
    v1_count = await meter_read_repo.count_by_job_id(session, job_id, version=1)
    led_3 = v1_count > 0

    # LED 4: Header extrahiert — reader profile has header_row + columns
    led_4 = False
    if file_row:
        profile = await reader_profile_repo.get_by_file_id(session, file_row[0])
        if profile and profile.rules:
            rules = profile.rules
            led_4 = "header_row" in rules and "timestamp_columns" in rules

    # LED 5: Zeitreihen erkannt — job status >= qa_running
    led_5 = status_ge(JobStatus.QA_RUNNING)

    # LED 6: Zeitreihen verbessert — v2 imputed reads exist
    v2_count = await meter_read_repo.count_by_job_id(session, job_id, version=2)
    led_6 = v2_count > 0

    # LED 7: Statistik erstellt — analysis profile exists
    analysis_profile = await analysis_profile_repo.get_by_job_id(session, job_id)
    led_7 = analysis_profile is not None

    # LED 8: Mit Wetterdaten angereichert — weather_correlations in analysis profile
    led_8 = False
    if analysis_profile and analysis_profile.weather_correlations:
        led_8 = True

    # LED 9: Auf Zeitraum prognostiziert — forecast series exist
    forecast_run = await forecast_run_repo.get_by_job_id(session, job_id)
    led_9 = False
    if forecast_run:
        fs_rows, fs_total = await forecast_series_repo.get_by_forecast_id(
            session, forecast_run.id, limit=1
        )
        led_9 = fs_total > 0

    # LED 10: Fertig zu Output — job status is done or warn
    led_10 = job.status in (JobStatus.DONE, JobStatus.WARN)

    return {
        "1": led_1,
        "2": led_2,
        "3": led_3,
        "4": led_4,
        "5": led_5,
        "6": led_6,
        "7": led_7,
        "8": led_8,
        "9": led_9,
        "10": led_10,
    }
