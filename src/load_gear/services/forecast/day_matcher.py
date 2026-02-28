"""Day-type matching forecast: find matching historical day-types and scale by percentage."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from load_gear.services.analysis.day_classifier import (
    _get_federal_holidays,
    _is_bridge_day,
    _is_non_workday,
    _SUMMER_MONTHS,
)

_BERLIN = ZoneInfo("Europe/Berlin")

# Fallback chain for day types when no exact match is found
_SIMILAR_TYPES: dict[str, list[str]] = {
    "Werktag-Sommer": ["Werktag-Winter", "Werktag-nach-Frei", "Werktag-vor-Frei"],
    "Werktag-Winter": ["Werktag-Sommer", "Werktag-nach-Frei", "Werktag-vor-Frei"],
    "Werktag-nach-Frei": ["Werktag-Winter", "Werktag-Sommer", "Werktag-vor-Frei"],
    "Werktag-vor-Frei": ["Werktag-Winter", "Werktag-Sommer", "Werktag-nach-Frei"],
    "Samstag": ["Sonntag", "Feiertag", "Brückentag"],
    "Sonntag": ["Samstag", "Feiertag", "Brückentag"],
    "Feiertag": ["Sonntag", "Samstag", "Brückentag"],
    "Brückentag": ["Feiertag", "Samstag", "Sonntag"],
}


def _classify_date(d, holidays: set) -> str:
    """Classify a single date into one of 9 day types (excluding Störung)."""
    from datetime import date as date_type

    if isinstance(d, datetime):
        d = d.date() if not hasattr(d, 'date') or callable(d.date) else d
        if isinstance(d, datetime):
            d = d.date()

    if d in holidays:
        return "Feiertag"
    if _is_bridge_day(d, holidays):
        return "Brückentag"
    if d.weekday() == 6:
        return "Sonntag"
    if d.weekday() == 5:
        return "Samstag"

    prev_day = d - timedelta(days=1)
    next_day = d + timedelta(days=1)
    if _is_non_workday(prev_day, holidays):
        return "Werktag-nach-Frei"
    if _is_non_workday(next_day, holidays):
        return "Werktag-vor-Frei"

    return "Werktag-Sommer" if d.month in _SUMMER_MONTHS else "Werktag-Winter"


def match_days(
    v2_rows: list[dict],
    *,
    horizon_start: datetime,
    horizon_end: datetime,
    interval_minutes: int = 15,
    percentage: float = 100.0,
) -> list[dict]:
    """Produce forecast by matching historical day-type averages.

    Args:
        v2_rows: [{ts_utc, value, unit, meter_id}]
        horizon_start: first forecast timestamp (inclusive)
        horizon_end: last forecast timestamp (exclusive-ish)
        interval_minutes: interval size (default 15)
        percentage: scaling factor (100 = unchanged, 110 = +10%)

    Returns:
        [{ts_utc, y_hat, q10, q50, q90}]
    """
    if not v2_rows:
        return []

    intervals_per_day = 24 * 60 // interval_minutes
    scale = percentage / 100.0

    # Collect years from historical data
    years: set[int] = set()
    for r in v2_rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        years.add(ts_local.year)

    # Also add forecast years
    h_start_local = horizon_start.astimezone(_BERLIN)
    h_end_local = horizon_end.astimezone(_BERLIN)
    for y in range(h_start_local.year, h_end_local.year + 1):
        years.add(y)

    # Build holiday set
    all_holidays = set()
    for year in years:
        all_holidays.update(_get_federal_holidays(year))

    # Classify historical data and group by (day_type, interval_index)
    # Skip Störung days from the matching pool
    type_interval_values: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    global_interval_values: dict[int, list[float]] = defaultdict(list)

    for r in v2_rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        d = ts_local.date()
        day_type = _classify_date(d, all_holidays)

        # Compute interval index within the day
        minutes_in_day = ts_local.hour * 60 + ts_local.minute
        interval_idx = minutes_in_day // interval_minutes

        val = r["value"]

        if day_type != "Störung":
            type_interval_values[day_type][interval_idx].append(val)
        global_interval_values[interval_idx].append(val)

    # Generate forecast timestamps
    predictions: list[dict] = []
    current = horizon_start
    delta = timedelta(minutes=interval_minutes)

    while current <= horizon_end:
        local = current.astimezone(_BERLIN)
        d = local.date()
        day_type = _classify_date(d, all_holidays)

        minutes_in_day = local.hour * 60 + local.minute
        interval_idx = minutes_in_day // interval_minutes

        # Lookup: exact type → similar type → global average → 0.0
        val = _lookup_value(day_type, interval_idx, type_interval_values, global_interval_values)
        val *= scale

        predictions.append({
            "ts_utc": current,
            "y_hat": round(val, 4),
            "q10": round(val, 4),
            "q50": round(val, 4),
            "q90": round(val, 4),
        })

        current += delta

    return predictions


def _lookup_value(
    day_type: str,
    interval_idx: int,
    type_interval_values: dict[str, dict[int, list[float]]],
    global_interval_values: dict[int, list[float]],
) -> float:
    """Look up average value with fallback chain."""
    # Exact match
    if day_type in type_interval_values and interval_idx in type_interval_values[day_type]:
        vals = type_interval_values[day_type][interval_idx]
        if vals:
            return sum(vals) / len(vals)

    # Similar types
    for alt in _SIMILAR_TYPES.get(day_type, []):
        if alt in type_interval_values and interval_idx in type_interval_values[alt]:
            vals = type_interval_values[alt][interval_idx]
            if vals:
                return sum(vals) / len(vals)

    # Global average
    if interval_idx in global_interval_values:
        vals = global_interval_values[interval_idx]
        if vals:
            return sum(vals) / len(vals)

    return 0.0
