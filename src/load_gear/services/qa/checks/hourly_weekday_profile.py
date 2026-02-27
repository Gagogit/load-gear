"""Check 8: Hourly/weekday profile — 24-value hour profile, 7-value weekday profile."""

from __future__ import annotations

import uuid
from collections import defaultdict

import numpy as np
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
    """Build average kW profiles by hour-of-day and day-of-week."""
    if not rows:
        return _finding(job_id, [0.0] * 24, [0.0] * 7, "error")

    hours_per_interval = interval_minutes / 60.0

    hourly_values: dict[int, list[float]] = defaultdict(list)
    weekday_values: dict[int, list[float]] = defaultdict(list)

    for r in rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        kw = r["value"] / hours_per_interval
        hourly_values[ts_local.hour].append(kw)
        weekday_values[ts_local.weekday()].append(kw)  # Mon=0, Sun=6

    hourly_profile = [
        round(float(np.mean(hourly_values.get(h, [0.0]))), 3)
        for h in range(24)
    ]
    weekday_profile = [
        round(float(np.mean(weekday_values.get(d, [0.0]))), 3)
        for d in range(7)
    ]

    # Informational check — always ok
    status = "ok"

    return _finding(job_id, hourly_profile, weekday_profile, status)


def _finding(
    job_id: uuid.UUID,
    hourly_profile: list[float],
    weekday_profile: list[float],
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 8,
        "check_name": "hourly_weekday_profile",
        "status": status,
        "metric_key": "hourly_profile_peak",
        "metric_value": max(hourly_profile) if hourly_profile else 0.0,
        "threshold": None,
        "affected_slots": {
            "hourly_profile": hourly_profile,
            "weekday_profile": weekday_profile,
        },
        "recommendation": None,
    }
