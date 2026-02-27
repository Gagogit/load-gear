"""Check 4: Daily/monthly energy — kWh aggregation per day and month."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta

from zoneinfo import ZoneInfo

from load_gear.services.qa.config import QAConfig

_BERLIN = ZoneInfo("Europe/Berlin")


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Aggregate kWh per day and per month. Flag incomplete days."""
    if not rows:
        return _finding(job_id, [], [], "error")

    intervals_per_day = 24 * 60 // interval_minutes  # 96 for 15-min

    # Group by local date (Europe/Berlin)
    daily: dict[str, float] = defaultdict(float)
    daily_counts: dict[str, int] = defaultdict(int)
    monthly: dict[str, float] = defaultdict(float)

    for r in rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        day_key = ts_local.strftime("%Y-%m-%d")
        month_key = ts_local.strftime("%Y-%m")

        value_kwh = r["value"]
        daily[day_key] += value_kwh
        daily_counts[day_key] += 1
        monthly[month_key] += value_kwh

    # Build daily array with completeness info
    kwh_day = []
    incomplete_days = 0
    for day_key in sorted(daily):
        count = daily_counts[day_key]
        coverage = count / intervals_per_day * 100
        is_complete = count >= intervals_per_day * 0.95
        if not is_complete:
            incomplete_days += 1
        kwh_day.append({
            "date": day_key,
            "kwh": round(daily[day_key], 3),
            "coverage_pct": round(coverage, 1),
            "complete": is_complete,
        })

    kwh_month = [
        {"month": k, "kwh": round(v, 3)}
        for k, v in sorted(monthly.items())
    ]

    total_kwh = sum(daily.values())
    status = "ok" if incomplete_days == 0 else "warn"

    return _finding(job_id, kwh_day, kwh_month, status, total_kwh, incomplete_days)


def _finding(
    job_id: uuid.UUID,
    kwh_day: list[dict],
    kwh_month: list[dict],
    status: str,
    total_kwh: float = 0.0,
    incomplete_days: int = 0,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 4,
        "check_name": "daily_monthly_energy",
        "status": status,
        "metric_key": "total_kwh",
        "metric_value": round(total_kwh, 3),
        "threshold": None,
        "affected_slots": {
            "kwh_day": kwh_day[:366],  # cap at 1 year
            "kwh_month": kwh_month,
            "incomplete_days": incomplete_days,
        },
        "recommendation": (
            f"{incomplete_days} incomplete days found"
            if incomplete_days > 0 else None
        ),
    }
