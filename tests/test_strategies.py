"""Unit tests for forecast post-processing strategies (P5.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.forecast.strategies.calendar_mapping import (
    _classify_date,
    _get_fingerprint,
    apply_calendar_mapping,
)
from load_gear.services.forecast.strategies.dst_correct import (
    _get_dst_transitions,
    apply_dst_correction,
)
from load_gear.services.forecast.strategies.scaling import (
    apply_scaling,
    apply_weather_conditioned,
    apply_asset_scenarios,
)


def _make_forecast_rows(
    start: datetime,
    hours: int = 24,
    interval_minutes: int = 15,
    base_value: float = 10.0,
) -> list[dict]:
    """Generate synthetic forecast rows."""
    rows: list[dict] = []
    intervals = hours * 60 // interval_minutes
    for i in range(intervals):
        ts = start + timedelta(minutes=i * interval_minutes)
        rows.append({
            "ts_utc": ts,
            "y_hat": base_value + i * 0.01,
            "q10": base_value - 1.0,
            "q50": base_value,
            "q90": base_value + 1.0,
        })
    return rows


# --- Calendar Mapping ---

def test_classify_date_weekday() -> None:
    """Classify a normal Monday in January → Werktag-Winter."""
    from datetime import date
    result = _classify_date(date(2025, 1, 6), set())  # Monday
    assert result == "Werktag-Winter"


def test_classify_date_summer_weekday() -> None:
    """Classify a Monday in July → Werktag-Sommer."""
    from datetime import date
    result = _classify_date(date(2025, 7, 7), set())  # Monday
    assert result == "Werktag-Sommer"


def test_classify_date_saturday() -> None:
    """Classify a Saturday → Samstag."""
    from datetime import date
    result = _classify_date(date(2025, 1, 4), set())  # Saturday
    assert result == "Samstag"


def test_classify_date_holiday() -> None:
    """Classify a known holiday → Feiertag."""
    from datetime import date
    holidays = {date(2025, 1, 1)}
    result = _classify_date(date(2025, 1, 1), holidays)
    assert result == "Feiertag"


def test_get_fingerprint_direct_match() -> None:
    """Direct match returns the fingerprint."""
    fps = {"Werktag-Winter": {"avg_kw": [5.0] * 24, "count": 10}}
    result = _get_fingerprint("Werktag-Winter", fps)
    assert result == [5.0] * 24


def test_get_fingerprint_fallback() -> None:
    """Missing type falls back to nearest neighbor."""
    fps = {"Werktag-Winter": {"avg_kw": [5.0] * 24, "count": 10}}
    result = _get_fingerprint("Werktag-Sommer", fps)
    assert result == [5.0] * 24  # Falls back to Werktag-Winter


def test_apply_calendar_mapping_blends() -> None:
    """Calendar mapping blends Prophet forecast with fingerprint."""
    start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)  # Monday
    rows = _make_forecast_rows(start, hours=1, interval_minutes=60, base_value=10.0)
    fingerprints = {"Werktag-Winter": {"avg_kw": [20.0] * 24, "count": 10}}

    result = apply_calendar_mapping(rows, fingerprints, blend_weight=0.5)
    # Should be blended: 0.5 * 10.0 + 0.5 * 20.0 = 15.0
    assert abs(result[0]["y_hat"] - 15.0) < 0.1


def test_apply_calendar_mapping_empty_fingerprints() -> None:
    """Empty fingerprints returns rows unchanged."""
    start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)
    rows = _make_forecast_rows(start, hours=1)
    original_yhat = rows[0]["y_hat"]
    result = apply_calendar_mapping(rows, {})
    assert result[0]["y_hat"] == original_yhat


# --- DST Correction ---

def test_get_dst_transitions_2025() -> None:
    """2025 should have exactly 2 DST transitions for Europe/Berlin."""
    transitions = _get_dst_transitions(2025)
    assert len(transitions) == 2
    types = set(transitions.values())
    assert "spring_forward" in types
    assert "fall_back" in types


def test_apply_dst_correction_normal_day() -> None:
    """Non-DST day should pass through unchanged."""
    start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)  # Normal Monday
    rows = _make_forecast_rows(start, hours=24, interval_minutes=15)
    result = apply_dst_correction(rows, interval_minutes=15)
    assert len(result) == 96  # 24h * 4 intervals


def test_apply_dst_correction_empty() -> None:
    """Empty input returns empty."""
    result = apply_dst_correction([], interval_minutes=15)
    assert result == []


# --- Scaling ---

def test_apply_scaling_growth() -> None:
    """Positive growth should increase values."""
    rows = _make_forecast_rows(
        datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc),
        hours=1, interval_minutes=60, base_value=100.0,
    )
    original = rows[0]["y_hat"]
    result = apply_scaling(rows, growth_pct=10.0)
    assert result[0]["y_hat"] == pytest.approx(original * 1.1)


def test_apply_scaling_load_shift() -> None:
    """Load shift adds constant offset."""
    rows = _make_forecast_rows(
        datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc),
        hours=1, interval_minutes=60, base_value=100.0,
    )
    result = apply_scaling(rows, load_shift_kw=-5.0)
    assert result[0]["y_hat"] == pytest.approx(95.0)


def test_apply_scaling_no_change() -> None:
    """Zero growth and zero shift returns unchanged."""
    rows = _make_forecast_rows(
        datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc),
        hours=1, interval_minutes=60, base_value=100.0,
    )
    original = rows[0]["y_hat"]
    result = apply_scaling(rows, growth_pct=0.0, load_shift_kw=0.0)
    assert result[0]["y_hat"] == original


def test_weather_conditioned_stub() -> None:
    """Weather stub returns rows unchanged."""
    rows = [{"y_hat": 10.0}]
    result = apply_weather_conditioned(rows)
    assert result[0]["y_hat"] == 10.0


def test_asset_scenarios_stub() -> None:
    """Asset scenarios stub returns rows unchanged."""
    rows = [{"y_hat": 10.0}]
    result = apply_asset_scenarios(rows)
    assert result[0]["y_hat"] == 10.0
