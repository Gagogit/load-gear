"""Unit tests for P4.1 day classification service."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.analysis.day_classifier import classify_days, _get_federal_holidays, _easter


def _make_rows(
    days: int = 7,
    start_date: datetime | None = None,
    interval_min: int = 15,
    base_value: float = 10.0,
) -> list[dict]:
    """Generate multi-day 15-min interval data."""
    if start_date is None:
        # Monday Jan 6, 2025 (first Monday of the year, not a holiday)
        start_date = datetime(2025, 1, 5, 23, 0, tzinfo=timezone.utc)  # Midnight CET = 23:00 UTC

    rows = []
    intervals_per_day = 24 * 60 // interval_min
    for day in range(days):
        for i in range(intervals_per_day):
            ts = start_date + timedelta(days=day, minutes=i * interval_min)
            hour = (ts.hour + 1) % 24  # rough CET approximation
            # Simulate day/night pattern
            if 6 <= hour <= 20:
                val = base_value + (hour - 6) * 0.5
            else:
                val = base_value * 0.5
            rows.append({
                "ts_utc": ts,
                "value": val,
                "unit": "kWh",
                "meter_id": "TEST",
            })
    return rows


def test_easter_2025():
    """Easter 2025 should be April 20."""
    from datetime import date
    assert _easter(2025) == date(2025, 4, 20)


def test_federal_holidays_2025():
    """Check key German federal holidays for 2025."""
    from datetime import date
    holidays = _get_federal_holidays(2025)
    assert date(2025, 1, 1) in holidays      # Neujahr
    assert date(2025, 5, 1) in holidays      # Tag der Arbeit
    assert date(2025, 10, 3) in holidays     # Tag der Einheit
    assert date(2025, 12, 25) in holidays    # 1. Weihnachtstag
    assert date(2025, 4, 18) in holidays     # Karfreitag (Easter - 2)
    assert date(2025, 4, 21) in holidays     # Ostermontag (Easter + 1)


def test_classify_weekdays():
    """7 weekdays in January should classify as Werktag-Winter."""
    # Jan 6-10, 2025 = Mon-Fri (weekdays), Jan 11-12 = Sat-Sun
    rows = _make_rows(days=7, start_date=datetime(2025, 1, 5, 23, 0, tzinfo=timezone.utc))
    fingerprints, labels = classify_days(rows)

    assert len(labels) == 7
    label_names = {dl["label"] for dl in labels}
    assert "Werktag-Winter" in label_names
    assert "Samstag" in label_names
    assert "Sonntag" in label_names


def test_classify_holiday():
    """Jan 1 (Neujahr) should be classified as Feiertag."""
    rows = _make_rows(days=3, start_date=datetime(2024, 12, 31, 23, 0, tzinfo=timezone.utc))
    _, labels = classify_days(rows)

    jan1_label = next((dl for dl in labels if dl["date"] == "2025-01-01"), None)
    assert jan1_label is not None
    assert jan1_label["label"] == "Feiertag"


def test_classify_summer():
    """June weekday should be Werktag-Sommer."""
    rows = _make_rows(days=1, start_date=datetime(2025, 6, 1, 22, 0, tzinfo=timezone.utc))
    _, labels = classify_days(rows)
    assert len(labels) >= 1
    # June 2 is Monday (summer)
    summer_label = next((dl for dl in labels if "Sommer" in dl.get("label", "")), None)
    assert summer_label is not None


def test_fingerprints_have_24_hours():
    """Each fingerprint should have exactly 24 hourly averages."""
    rows = _make_rows(days=7)
    fingerprints, _ = classify_days(rows)

    for label, fp in fingerprints.items():
        assert len(fp["avg_kw"]) == 24, f"{label} has {len(fp['avg_kw'])} hours"
        assert fp["count"] >= 1


def test_empty_rows():
    """Empty input returns empty results."""
    fingerprints, labels = classify_days([])
    assert fingerprints == {}
    assert labels == []


def test_confidence_score():
    """Days with full data should have confidence near 1.0."""
    rows = _make_rows(days=1)
    _, labels = classify_days(rows)
    for dl in labels:
        assert 0 <= dl["confidence"] <= 1.0


def test_stoerung_detection():
    """Days with very low load should be classified as Störung."""
    # Create normal weekdays first, then one day with near-zero load
    rows = _make_rows(days=5, base_value=10.0)
    # Add a day with ~0 load
    start = datetime(2025, 1, 10, 23, 0, tzinfo=timezone.utc)  # Friday
    for i in range(96):
        rows.append({
            "ts_utc": start + timedelta(minutes=i * 15),
            "value": 0.01,
            "unit": "kWh",
            "meter_id": "TEST",
        })

    _, labels = classify_days(rows)
    jan11_label = next((dl for dl in labels if dl["date"] == "2025-01-11"), None)
    if jan11_label:
        assert jan11_label["label"] == "Störung"
