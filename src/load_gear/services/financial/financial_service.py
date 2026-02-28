"""Financial calculation orchestrator: forecast × HPFC = cost series."""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.control import JobStatus
from load_gear.models.data import FinancialRun
from load_gear.repositories import (
    job_repo,
    forecast_run_repo,
    forecast_series_repo,
    hpfc_snapshot_repo,
    hpfc_series_repo,
    financial_run_repo,
)

logger = logging.getLogger(__name__)


class FinancialError(Exception):
    """Raised when financial calculation fails."""
    pass


async def run_financial(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    snapshot_id: uuid.UUID | None = None,
) -> dict:
    """Run cost calculation: forecast × HPFC = cost time series.

    Steps:
    1. Validate job is in financial_running state
    2. Fetch forecast series (v3)
    3. Find matching HPFC snapshot
    4. Align timestamps and vector multiply
    5. Aggregate monthly summaries
    6. Store FinancialRun record
    7. Advance job state
    """
    # 1. Validate job
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise FinancialError(f"Job {job_id} not found")

    if job.status != JobStatus.FINANCIAL_RUNNING:
        raise FinancialError(
            f"Job {job_id} is in status '{job.status.value}', expected 'financial_running'"
        )

    job.current_phase = "P6"
    await session.flush()

    try:
        meter_id = job.meter_id or str(job_id)

        # 2. Fetch forecast run + series
        forecast_run = await forecast_run_repo.get_by_job_id(session, job_id)
        if forecast_run is None:
            raise FinancialError(f"No forecast run found for job {job_id}")

        fc_rows, fc_total = await forecast_series_repo.get_by_forecast_id(
            session, forecast_run.id, limit=200_000, offset=0
        )
        if fc_total == 0:
            raise FinancialError(f"No forecast series found for job {job_id}")

        # 3. Find HPFC snapshot
        if snapshot_id is not None:
            snapshot = await hpfc_snapshot_repo.get_by_id(session, snapshot_id)
            if snapshot is None:
                raise FinancialError(f"HPFC snapshot {snapshot_id} not found")
        else:
            # Auto-find: latest snapshot covering the forecast horizon
            snapshot = await hpfc_snapshot_repo.get_latest_covering(
                session, forecast_run.horizon_start, forecast_run.horizon_end
            )
            if snapshot is None:
                raise FinancialError(
                    f"No HPFC snapshot covers forecast horizon "
                    f"{forecast_run.horizon_start} – {forecast_run.horizon_end}"
                )

        # 4. Load HPFC series
        hpfc_rows = await hpfc_series_repo.get_all_by_snapshot_id(session, snapshot.id)
        if not hpfc_rows:
            raise FinancialError(f"HPFC snapshot {snapshot.id} has no series data")

        # Build price lookup: ts_utc → price_mwh (hourly)
        price_map: dict[datetime, float] = {
            r.ts_utc.replace(tzinfo=None) if r.ts_utc.tzinfo else r.ts_utc: r.price_mwh
            for r in hpfc_rows
        }

        # 5. Create FinancialRun record
        fin_run = FinancialRun(
            id=uuid.uuid4(),
            job_id=job_id,
            forecast_run_id=forecast_run.id,
            hpfc_snapshot_id=snapshot.id,
            meter_id=meter_id,
            status="running",
        )
        await financial_run_repo.create(session, fin_run)

        # 6. Detect interval and compute costs
        if len(fc_rows) >= 2:
            delta = (fc_rows[1].ts_utc - fc_rows[0].ts_utc).total_seconds()
            interval_minutes = max(int(delta / 60), 15)
        else:
            interval_minutes = 15

        hours_per_interval = interval_minutes / 60.0
        cost_rows: list[dict] = []

        for fr in fc_rows:
            ts = fr.ts_utc
            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts

            # Look up HPFC price — try exact match, then truncate to hour
            price = price_map.get(ts_naive)
            if price is None:
                ts_hour = ts_naive.replace(minute=0, second=0, microsecond=0)
                price = price_map.get(ts_hour)

            if price is None:
                continue  # Skip intervals without price data

            # y_hat is in kW → convert to kWh for the interval
            consumption_kwh = fr.y_hat * hours_per_interval
            # Cost = (consumption_kwh / 1000) * price_mwh
            cost_eur = (consumption_kwh / 1000.0) * price

            cost_rows.append({
                "ts_utc": ts,
                "consumption_kwh": consumption_kwh,
                "price_mwh": price,
                "cost_eur": cost_eur,
            })

        if not cost_rows:
            raise FinancialError("No overlapping timestamps between forecast and HPFC")

        # 7. Aggregate totals and monthly summaries
        total_cost = sum(r["cost_eur"] for r in cost_rows)

        monthly: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "kwh": 0.0, "prices": []})
        for r in cost_rows:
            ts = r["ts_utc"]
            month_key = ts.strftime("%Y-%m") if hasattr(ts, "strftime") else str(ts)[:7]
            monthly[month_key]["cost"] += r["cost_eur"]
            monthly[month_key]["kwh"] += r["consumption_kwh"]
            monthly[month_key]["prices"].append(r["price_mwh"])

        monthly_summary = [
            {
                "month": k,
                "total_cost_eur": round(v["cost"], 4),
                "total_kwh": round(v["kwh"], 4),
                "avg_price_mwh": round(float(np.mean(v["prices"])), 4),
            }
            for k, v in sorted(monthly.items())
        ]

        # 8. Update FinancialRun
        fin_run.status = "ok"
        fin_run.total_cost_eur = round(total_cost, 4)
        fin_run.monthly_summary = monthly_summary
        fin_run.completed_at = datetime.now(timezone.utc)
        await session.flush()

        # 9. Advance job to done
        job.status = JobStatus.DONE
        job.current_phase = None
        await session.flush()

        return {
            "calc_id": str(fin_run.id),
            "job_id": str(job_id),
            "total_cost_eur": fin_run.total_cost_eur,
            "monthly_summary": monthly_summary,
            "cost_rows": cost_rows,
            "matched_intervals": len(cost_rows),
            "total_forecast_rows": fc_total,
        }

    except FinancialError:
        raise
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = f"Financial error: {exc}"
        job.current_phase = None
        await session.flush()
        try:
            if fin_run:
                fin_run.status = "failed"
                fin_run.completed_at = datetime.now(timezone.utc)
                await session.flush()
        except Exception:
            pass
        raise FinancialError(f"Financial calculation failed: {exc}") from exc


async def get_financial_result(
    session: AsyncSession,
    job_id: uuid.UUID,
) -> dict:
    """Get the financial calculation result for a job."""
    job = await job_repo.get_job_by_id(session, job_id)
    if job is None:
        raise FinancialError(f"Job {job_id} not found")

    fin_run = await financial_run_repo.get_by_job_id(session, job_id)
    if fin_run is None:
        raise FinancialError(f"No financial result for job {job_id}")

    # Re-compute cost rows from forecast + HPFC for the response
    forecast_run = await forecast_run_repo.get_by_job_id(session, job_id)
    if forecast_run is None:
        raise FinancialError(f"No forecast run for job {job_id}")

    fc_rows, _ = await forecast_series_repo.get_by_forecast_id(
        session, forecast_run.id, limit=200_000, offset=0
    )

    hpfc_rows = await hpfc_series_repo.get_all_by_snapshot_id(session, fin_run.hpfc_snapshot_id)
    price_map: dict[datetime, float] = {
        r.ts_utc.replace(tzinfo=None) if r.ts_utc.tzinfo else r.ts_utc: r.price_mwh
        for r in hpfc_rows
    }

    if len(fc_rows) >= 2:
        delta = (fc_rows[1].ts_utc - fc_rows[0].ts_utc).total_seconds()
        interval_minutes = max(int(delta / 60), 15)
    else:
        interval_minutes = 15

    hours_per_interval = interval_minutes / 60.0
    cost_rows: list[dict] = []

    for fr in fc_rows:
        ts = fr.ts_utc
        ts_naive = ts.replace(tzinfo=None) if ts.tzinfo else ts

        price = price_map.get(ts_naive)
        if price is None:
            ts_hour = ts_naive.replace(minute=0, second=0, microsecond=0)
            price = price_map.get(ts_hour)

        if price is None:
            continue

        consumption_kwh = fr.y_hat * hours_per_interval
        cost_eur = (consumption_kwh / 1000.0) * price

        cost_rows.append({
            "ts_utc": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "consumption_kwh": round(consumption_kwh, 6),
            "price_mwh": round(price, 4),
            "cost_eur": round(cost_eur, 6),
        })

    return {
        "calc_id": str(fin_run.id),
        "job_id": str(job_id),
        "total_cost_eur": fin_run.total_cost_eur,
        "monthly_summary": fin_run.monthly_summary or [],
        "rows": cost_rows,
    }


async def export_financial(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    fmt: str = "csv",
) -> tuple[bytes, str, str]:
    """Export financial results as CSV or XLSX.

    Returns (file_bytes, content_type, filename).
    """
    result = await get_financial_result(session, job_id)

    if fmt == "xlsx":
        return _export_xlsx(result, job_id)
    return _export_csv(result, job_id)


def _fmt_de(v: float | int | None) -> str:
    """Format a number with German decimal comma."""
    if v is None:
        return ""
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")
    return str(v)


def _export_csv(result: dict, job_id: uuid.UUID) -> tuple[bytes, str, str]:
    """Generate CSV export (German format: semicolon delimiter, decimal comma)."""
    import io

    lines: list[str] = []

    # Header
    lines.append("ts_utc;consumption_kwh;price_mwh;cost_eur")

    for row in result["rows"]:
        lines.append(
            f"{row['ts_utc']};{_fmt_de(row['consumption_kwh'])};{_fmt_de(row['price_mwh'])};{_fmt_de(row['cost_eur'])}"
        )

    # Blank line + monthly summary
    lines.append("")
    lines.append("Month;Total Cost EUR;Total kWh;Avg Price EUR/MWh")
    for ms in result["monthly_summary"]:
        lines.append(
            f"{ms['month']};{_fmt_de(ms['total_cost_eur'])};{_fmt_de(ms['total_kwh'])};{_fmt_de(ms['avg_price_mwh'])}"
        )

    lines.append("")
    lines.append(f"Total Cost EUR;{_fmt_de(result['total_cost_eur'])}")

    content = "\n".join(lines).encode("utf-8-sig")
    return content, "text/csv; charset=utf-8", f"financial_{job_id}.csv"


def _export_xlsx(result: dict, job_id: uuid.UUID) -> tuple[bytes, str, str]:
    """Generate XLSX export using openpyxl."""
    try:
        import openpyxl
    except ImportError:
        raise FinancialError("openpyxl is required for XLSX export. Install with: pip install openpyxl")

    import io

    wb = openpyxl.Workbook()

    # Cost rows sheet
    ws = wb.active
    ws.title = "Cost Series"
    ws.append(["ts_utc", "consumption_kwh", "price_mwh", "cost_eur"])
    for row in result["rows"]:
        ws.append([row["ts_utc"], row["consumption_kwh"], row["price_mwh"], row["cost_eur"]])

    # Monthly summary sheet
    ws2 = wb.create_sheet("Monthly Summary")
    ws2.append(["Month", "Total Cost EUR", "Total kWh", "Avg Price EUR/MWh"])
    for ms in result["monthly_summary"]:
        ws2.append([ms["month"], ms["total_cost_eur"], ms["total_kwh"], ms["avg_price_mwh"]])
    ws2.append([])
    ws2.append(["Total Cost EUR", result["total_cost_eur"]])

    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    return content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"financial_{job_id}.xlsx"
