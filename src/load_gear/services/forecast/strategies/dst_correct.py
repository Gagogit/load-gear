"""DST correction strategy — adjust interval count on DST transition days.

Standard day: 96 intervals (15-min) or 24 intervals (60-min)
Spring forward: -4 intervals (15-min) or -1 interval (60-min)
Fall back: +4 intervals (15-min) or +1 interval (60-min)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
_BERLIN = ZoneInfo("Europe/Berlin")


def _get_dst_transitions(year: int) -> dict[date, str]:
    """Find DST transition dates for Europe/Berlin in a given year.

    Returns: {date: 'spring_forward' | 'fall_back'}
    """
    transitions: dict[date, str] = {}
    # Check each day for UTC offset change
    d = date(year, 1, 1)
    end = date(year, 12, 31)
    prev_offset = datetime(d.year, d.month, d.day, 12, tzinfo=_BERLIN).utcoffset()

    while d <= end:
        d += timedelta(days=1)
        if d > end:
            break
        curr_offset = datetime(d.year, d.month, d.day, 12, tzinfo=_BERLIN).utcoffset()
        if curr_offset != prev_offset:
            if curr_offset > prev_offset:
                transitions[d] = "spring_forward"  # clocks jump ahead, shorter day
            else:
                transitions[d] = "fall_back"  # clocks fall back, longer day
        prev_offset = curr_offset

    return transitions


def apply_dst_correction(
    forecast_rows: list[dict],
    interval_minutes: int = 15,
) -> list[dict]:
    """Adjust forecast values on DST transition days.

    On spring-forward days: remove duplicate intervals in the skipped hour.
    On fall-back days: ensure extra hour intervals have reasonable values.

    In practice, Prophet already handles this via its timestamp-based approach.
    This strategy acts as a guard to ensure interval counts are correct.
    """
    if not forecast_rows:
        return forecast_rows

    # Collect years
    years: set[int] = set()
    for row in forecast_rows:
        ts = row["ts_utc"]
        local = ts.astimezone(_BERLIN) if ts.tzinfo else ts
        years.add(local.year)

    # Get DST transitions for all years
    transitions: dict[date, str] = {}
    for year in years:
        transitions.update(_get_dst_transitions(year))

    if not transitions:
        return forecast_rows

    # Group rows by local date
    from collections import defaultdict
    daily_rows: dict[date, list[dict]] = defaultdict(list)
    for row in forecast_rows:
        ts = row["ts_utc"]
        local = ts.astimezone(_BERLIN) if ts.tzinfo else ts
        daily_rows[local.date()].append(row)

    intervals_per_hour = 60 // interval_minutes
    normal_count = 24 * intervals_per_hour

    for d, transition_type in transitions.items():
        if d not in daily_rows:
            continue

        day_rows = daily_rows[d]
        actual = len(day_rows)

        if transition_type == "spring_forward":
            expected = normal_count - intervals_per_hour
            if actual > expected:
                logger.debug("DST spring: trimming %d → %d intervals on %s", actual, expected, d)
                # Keep only 'expected' intervals (remove extras)
                daily_rows[d] = day_rows[:expected]
        elif transition_type == "fall_back":
            expected = normal_count + intervals_per_hour
            if actual < expected:
                logger.debug("DST fall: %d intervals on %s (expected %d), padding", actual, d, expected)
                # Pad with last known values if needed
                while len(daily_rows[d]) < expected and daily_rows[d]:
                    last = daily_rows[d][-1].copy()
                    last["ts_utc"] = last["ts_utc"] + timedelta(minutes=interval_minutes)
                    daily_rows[d].append(last)

    # Rebuild flat list preserving order
    result: list[dict] = []
    seen_dates = set()
    for row in forecast_rows:
        ts = row["ts_utc"]
        local = ts.astimezone(_BERLIN) if ts.tzinfo else ts
        d = local.date()
        if d in transitions and d not in seen_dates:
            result.extend(daily_rows[d])
            seen_dates.add(d)
        elif d not in transitions:
            result.append(row)

    return result
