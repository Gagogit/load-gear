"""Unit tests for day-type matching forecast."""

from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.forecast.day_matcher import match_days


def _make_v2_rows(
    days: int = 14,
    start_date: datetime | None = None,
    interval_min: int = 15,
    base_value: float = 10.0,
    weekend_factor: float = 0.5,
) -> list[dict]:
    """Generate multi-day v2 data with weekday/weekend pattern."""
    if start_date is None:
        # Monday Jan 6, 2025
        start_date = datetime(2025, 1, 5, 23, 0, tzinfo=timezone.utc)

    rows = []
    intervals_per_day = 24 * 60 // interval_min
    for day in range(days):
        for i in range(intervals_per_day):
            ts = start_date + timedelta(days=day, minutes=i * interval_min)
            hour = (ts.hour + 1) % 24  # rough CET
            weekday = ts.weekday()
            factor = weekend_factor if weekday >= 5 else 1.0
            if 6 <= hour <= 20:
                val = base_value * factor + (hour - 6) * 0.3 * factor
            else:
                val = base_value * 0.4 * factor
            rows.append({
                "ts_utc": ts,
                "value": val,
                "unit": "kWh",
                "meter_id": "TEST_MATCH",
            })
    return rows


def test_correct_interval_count():
    """1 day at 15-min intervals should produce 96+1 predictions (inclusive end)."""
    v2 = _make_v2_rows(days=14)
    start = datetime(2025, 2, 3, 0, 0, tzinfo=timezone.utc)  # Monday
    end = datetime(2025, 2, 3, 23, 45, tzinfo=timezone.utc)

    result = match_days(v2, horizon_start=start, horizon_end=end)
    assert len(result) == 96


def test_output_format():
    """Output dicts have all required keys, q10=q50=q90=y_hat."""
    v2 = _make_v2_rows(days=14)
    start = datetime(2025, 2, 3, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 2, 3, 3, 45, tzinfo=timezone.utc)

    result = match_days(v2, horizon_start=start, horizon_end=end)
    assert len(result) > 0
    for row in result:
        assert "ts_utc" in row
        assert "y_hat" in row
        assert "q10" in row
        assert "q50" in row
        assert "q90" in row
        assert row["q10"] == row["y_hat"]
        assert row["q50"] == row["y_hat"]
        assert row["q90"] == row["y_hat"]


def test_percentage_doubles_values():
    """Percentage 200% should double the forecast values."""
    v2 = _make_v2_rows(days=14)
    start = datetime(2025, 2, 3, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 2, 3, 3, 45, tzinfo=timezone.utc)

    result_100 = match_days(v2, horizon_start=start, horizon_end=end, percentage=100.0)
    result_200 = match_days(v2, horizon_start=start, horizon_end=end, percentage=200.0)

    assert len(result_100) == len(result_200)
    for r100, r200 in zip(result_100, result_200):
        assert abs(r200["y_hat"] - 2.0 * r100["y_hat"]) < 0.01


def test_empty_v2_returns_empty():
    """Empty v2 input should return empty result."""
    start = datetime(2025, 2, 3, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 2, 3, 23, 45, tzinfo=timezone.utc)
    result = match_days([], horizon_start=start, horizon_end=end)
    assert result == []


def test_weekend_vs_weekday_values_differ():
    """Weekend and weekday forecast values should differ when historical data has different patterns."""
    v2 = _make_v2_rows(days=14, weekend_factor=0.3)

    # Weekday forecast (Monday)
    start_wd = datetime(2025, 2, 3, 10, 0, tzinfo=timezone.utc)
    end_wd = datetime(2025, 2, 3, 10, 0, tzinfo=timezone.utc)
    result_wd = match_days(v2, horizon_start=start_wd, horizon_end=end_wd)

    # Weekend forecast (Saturday)
    start_we = datetime(2025, 2, 8, 10, 0, tzinfo=timezone.utc)
    end_we = datetime(2025, 2, 8, 10, 0, tzinfo=timezone.utc)
    result_we = match_days(v2, horizon_start=start_we, horizon_end=end_we)

    assert len(result_wd) == 1
    assert len(result_we) == 1
    # Weekend values should be notably lower than weekday
    assert result_we[0]["y_hat"] < result_wd[0]["y_hat"]
