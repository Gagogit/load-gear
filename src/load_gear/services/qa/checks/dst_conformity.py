"""Check 9: DST conformity — verify correct interval counts on DST transition days."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date

from zoneinfo import ZoneInfo

from load_gear.services.qa.config import QAConfig

_BERLIN = ZoneInfo("Europe/Berlin")

# Known DST transition dates (Germany) — spring forward, fall back
# Spring: last Sunday of March (23h day → 92 intervals at 15-min)
# Fall: last Sunday of October (25h day → 100 intervals at 15-min)
# Normal day: 24h → 96 intervals at 15-min


def _get_dst_dates(year: int) -> dict[date, int]:
    """Return DST transition dates and expected intervals for a given year."""
    import calendar

    # Last Sunday of March
    march_last = max(
        d for d in range(25, 32) if d <= calendar.monthrange(year, 3)[1]
        and date(year, 3, d).weekday() == 6
    )
    spring = date(year, 3, march_last)

    # Last Sunday of October
    october_last = max(
        d for d in range(25, 32) if d <= calendar.monthrange(year, 10)[1]
        and date(year, 10, d).weekday() == 6
    )
    fall = date(year, 10, october_last)

    return {spring: 92, fall: 100}  # 15-min intervals


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Check interval counts on DST transition days."""
    if not rows:
        return _finding(job_id, [], "error")

    intervals_per_normal_day = 24 * 60 // interval_minutes

    # Group rows by local date
    daily_counts: dict[date, int] = defaultdict(int)
    years: set[int] = set()
    for r in rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        d = ts_local.date()
        daily_counts[d] += 1
        years.add(d.year)

    # Get all DST dates in the data range
    dst_dates: dict[date, int] = {}
    for year in years:
        dst_dates.update(_get_dst_dates(year))

    # Scale expected intervals by actual interval size
    scale = 15 / interval_minutes
    dst_results = []
    all_ok = True

    for dst_date, expected_15min in sorted(dst_dates.items()):
        if dst_date not in daily_counts:
            continue

        expected = int(expected_15min * scale)
        observed = daily_counts[dst_date]
        ok = observed == expected

        if not ok:
            all_ok = False

        dst_results.append({
            "date": dst_date.isoformat(),
            "expected_slots": expected,
            "observed_slots": observed,
            "ok": ok,
        })

    if not dst_results:
        status = "ok"  # No DST days in data range
    elif all_ok:
        status = "ok"
    else:
        status = "warn"

    return _finding(job_id, dst_results, status)


def _finding(
    job_id: uuid.UUID,
    dst_results: list[dict],
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 9,
        "check_name": "dst_conformity",
        "status": status,
        "metric_key": "dst_days_checked",
        "metric_value": float(len(dst_results)),
        "threshold": None,
        "affected_slots": {"dst_days": dst_results},
        "recommendation": (
            "DST transition days have unexpected interval counts"
            if status != "ok" else None
        ),
    }
