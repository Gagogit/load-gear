"""Calendar mapping strategy — map day-class fingerprints onto forecast dates.

Uses nearest-neighbor matching when a day type has no fingerprint data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

import numpy as np
from zoneinfo import ZoneInfo

from load_gear.services.analysis.day_classifier import (
    _get_federal_holidays,
    _is_bridge_day,
    _is_non_workday,
    _SUMMER_MONTHS,
)

logger = logging.getLogger(__name__)
_BERLIN = ZoneInfo("Europe/Berlin")

# Day type similarity for nearest-neighbor fallback
_SIMILAR_TYPES: dict[str, list[str]] = {
    "Werktag-Sommer": ["Werktag-Winter", "Werktag-nach-Frei", "Werktag-vor-Frei", "Samstag", "Sonntag"],
    "Werktag-Winter": ["Werktag-Sommer", "Werktag-nach-Frei", "Werktag-vor-Frei", "Samstag", "Sonntag"],
    "Werktag-nach-Frei": ["Werktag-Winter", "Werktag-Sommer", "Werktag-vor-Frei", "Samstag"],
    "Werktag-vor-Frei": ["Werktag-Winter", "Werktag-Sommer", "Werktag-nach-Frei", "Samstag"],
    "Samstag": ["Sonntag", "Feiertag", "Werktag-Sommer", "Werktag-Winter"],
    "Sonntag": ["Samstag", "Feiertag", "Werktag-Sommer", "Werktag-Winter"],
    "Feiertag": ["Sonntag", "Samstag", "Brückentag"],
    "Brückentag": ["Feiertag", "Samstag", "Sonntag"],
    "Störung": ["Sonntag", "Feiertag", "Samstag"],
}


def _classify_date(d: date, holidays: set[date]) -> str:
    """Classify a single date into a day type."""
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


def _get_fingerprint(day_type: str, fingerprints: dict[str, dict]) -> list[float] | None:
    """Get hourly profile for a day type, with nearest-neighbor fallback."""
    if day_type in fingerprints:
        return fingerprints[day_type]["avg_kw"]
    # Nearest neighbor
    for alt in _SIMILAR_TYPES.get(day_type, []):
        if alt in fingerprints:
            logger.debug("Calendar mapping: fallback %s → %s", day_type, alt)
            return fingerprints[alt]["avg_kw"]
    return None


def apply_calendar_mapping(
    forecast_rows: list[dict],
    day_fingerprints: dict[str, dict],
    *,
    blend_weight: float = 0.3,
) -> list[dict]:
    """Blend Prophet forecast with day-class fingerprint profiles.

    For each forecast timestamp, look up the day-class fingerprint for that date
    and blend: result = (1 - blend_weight) * prophet + blend_weight * fingerprint.

    Args:
        forecast_rows: [{ts_utc, y_hat, q10, q50, q90}]
        day_fingerprints: {day_type: {avg_kw: [24 floats], count: int}}
        blend_weight: how much to weight the fingerprint (0=pure Prophet, 1=pure fingerprint)

    Returns:
        Modified forecast rows (in place).
    """
    if not forecast_rows or not day_fingerprints:
        return forecast_rows

    # Collect years
    years: set[int] = set()
    for row in forecast_rows:
        ts = row["ts_utc"]
        local = ts.astimezone(_BERLIN) if ts.tzinfo else ts
        years.add(local.year)

    # Build holiday set
    all_holidays: set[date] = set()
    for year in years:
        all_holidays.update(_get_federal_holidays(year))

    for row in forecast_rows:
        ts = row["ts_utc"]
        local = ts.astimezone(_BERLIN) if ts.tzinfo else ts
        d = local.date()
        hour = local.hour

        day_type = _classify_date(d, all_holidays)
        fp = _get_fingerprint(day_type, day_fingerprints)
        if fp is None:
            continue

        fp_val = fp[hour]
        for key in ("y_hat", "q10", "q50", "q90"):
            if row.get(key) is not None:
                row[key] = (1 - blend_weight) * row[key] + blend_weight * fp_val

    return forecast_rows
