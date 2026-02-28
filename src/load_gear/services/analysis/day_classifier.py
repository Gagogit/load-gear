"""P4.1 — Day Classification & Calendar Matching.

Classifies each day in the v1 time series into one of:
- Werktag-Sommer, Werktag-Winter, Werktag-nach-Frei, Werktag-vor-Frei,
  Samstag, Sonntag, Feiertag, Brückentag, Störung

Produces day_fingerprints (24-hour avg kW profiles per day type) and day_labels.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta

import numpy as np
from zoneinfo import ZoneInfo

_BERLIN = ZoneInfo("Europe/Berlin")

# Summer months: April–September, Winter: October–March
_SUMMER_MONTHS = {4, 5, 6, 7, 8, 9}

# German federal holidays (fixed dates + Easter-dependent)
# We compute Easter dynamically and derive movable holidays from it.


def _easter(year: int) -> date:
    """Compute Easter Sunday for a given year (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = ((h + ll - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _get_federal_holidays(year: int) -> set[date]:
    """Return German federal holidays for a year."""
    easter_sun = _easter(year)
    holidays = {
        date(year, 1, 1),      # Neujahr
        date(year, 5, 1),      # Tag der Arbeit
        date(year, 10, 3),     # Tag der Deutschen Einheit
        date(year, 12, 25),    # 1. Weihnachtstag
        date(year, 12, 26),    # 2. Weihnachtstag
        easter_sun - timedelta(days=2),   # Karfreitag
        easter_sun + timedelta(days=1),   # Ostermontag
        easter_sun + timedelta(days=39),  # Christi Himmelfahrt
        easter_sun + timedelta(days=50),  # Pfingstmontag
    }
    return holidays


def _is_non_workday(d: date, holidays: set[date]) -> bool:
    """True if Sat/Sun/Feiertag/Brückentag."""
    if d.weekday() >= 5:
        return True
    if d in holidays:
        return True
    if _is_bridge_day(d, holidays):
        return True
    return False


def _is_bridge_day(d: date, holidays: set[date]) -> bool:
    """Check if a date is a potential bridge day (weekday between holiday and weekend)."""
    if d.weekday() >= 5:  # Sat/Sun not bridge days
        return False
    if d in holidays:
        return False

    # Monday after holiday Thursday, or Friday before holiday Monday
    prev_day = d - timedelta(days=1)
    next_day = d + timedelta(days=1)

    # Friday where Thursday is a holiday
    if d.weekday() == 4 and prev_day in holidays:
        return True
    # Monday where Tuesday is a holiday
    if d.weekday() == 0 and next_day in holidays:
        return True
    return False


def classify_days(
    rows: list[dict],
    *,
    interval_minutes: int = 15,
    holiday_dates: set[date] | None = None,
) -> tuple[dict[str, dict], list[dict]]:
    """Classify each day and build fingerprints.

    Args:
        rows: v1 meter read dicts with ts_utc, value, unit
        interval_minutes: interval size
        holiday_dates: optional set of known holiday dates (from control.holidays)

    Returns:
        (day_fingerprints, day_labels)
        - day_fingerprints: {label: {avg_kw: [24 floats], count: int}}
        - day_labels: [{date: str, label: str, confidence: float}]
    """
    if not rows:
        return {}, []

    hours_per_interval = interval_minutes / 60.0

    # Collect all years in data to compute holidays
    years: set[int] = set()
    daily_hourly: dict[date, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    for r in rows:
        ts_local = r["ts_utc"].astimezone(_BERLIN)
        d = ts_local.date()
        years.add(d.year)
        kw = r["value"] / hours_per_interval
        daily_hourly[d][ts_local.hour].append(kw)

    # Build holiday set
    all_holidays = set()
    for year in years:
        all_holidays.update(_get_federal_holidays(year))
    if holiday_dates:
        all_holidays.update(holiday_dates)

    # Classify each day
    day_labels: list[dict] = []
    label_hourly: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))

    intervals_per_day = 24 * 60 // interval_minutes
    daily_totals: dict[date, float] = {}
    for d, hourly_data in daily_hourly.items():
        total_kw = sum(sum(vals) for vals in hourly_data.values())
        daily_totals[d] = total_kw

    # Compute reference weekday load for bridge day detection
    weekday_loads: list[float] = []
    for d, total in daily_totals.items():
        if d.weekday() < 5 and d not in all_holidays:
            weekday_loads.append(total)
    avg_weekday_load = float(np.mean(weekday_loads)) if weekday_loads else 0.0

    for d in sorted(daily_hourly.keys()):
        hourly_data = daily_hourly[d]
        total_intervals = sum(len(vals) for vals in hourly_data.values())
        confidence = min(total_intervals / intervals_per_day, 1.0)

        # Check for Störung (very low load — less than 10% of average weekday)
        day_total = daily_totals.get(d, 0.0)
        if avg_weekday_load > 0 and day_total < avg_weekday_load * 0.1:
            label = "Störung"
        elif d in all_holidays:
            label = "Feiertag"
        elif _is_bridge_day(d, all_holidays):
            # Bridge day verification: compare load to reference
            if avg_weekday_load > 0 and day_total < avg_weekday_load * 0.8:
                label = "Brückentag"
            else:
                # Load didn't drop — treat as normal weekday
                is_summer = d.month in _SUMMER_MONTHS
                label = "Werktag-Sommer" if is_summer else "Werktag-Winter"
        elif d.weekday() == 6:  # Sunday
            label = "Sonntag"
        elif d.weekday() == 5:  # Saturday
            label = "Samstag"
        else:
            # Check for Werktag-nach-Frei / Werktag-vor-Frei
            prev_day = d - timedelta(days=1)
            next_day = d + timedelta(days=1)
            if _is_non_workday(prev_day, all_holidays):
                label = "Werktag-nach-Frei"
            elif _is_non_workday(next_day, all_holidays):
                label = "Werktag-vor-Frei"
            else:
                is_summer = d.month in _SUMMER_MONTHS
                label = "Werktag-Sommer" if is_summer else "Werktag-Winter"

        day_labels.append({
            "date": d.isoformat(),
            "label": label,
            "confidence": round(confidence, 3),
        })

        # Aggregate hourly values for fingerprints
        for hour, vals in hourly_data.items():
            label_hourly[label][hour].extend(vals)

    # Build fingerprints (24-hour avg kW per label)
    day_fingerprints: dict[str, dict] = {}
    for label, hourly_data in label_hourly.items():
        avg_kw = [
            round(float(np.mean(hourly_data.get(h, [0.0]))), 3)
            for h in range(24)
        ]
        count = sum(1 for dl in day_labels if dl["label"] == label)
        day_fingerprints[label] = {
            "avg_kw": avg_kw,
            "count": count,
        }

    return day_fingerprints, day_labels
