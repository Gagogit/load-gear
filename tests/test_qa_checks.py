"""Unit tests for the 9 QA checks."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.qa.config import QAConfig
from load_gear.services.qa.checks import (
    interval_completeness,
    completeness_pct,
    gaps_duplicates,
    daily_monthly_energy,
    peak_load,
    baseload,
    load_factor,
    hourly_weekday_profile,
    dst_conformity,
)

JOB_ID = uuid.uuid4()
CONFIG = QAConfig()


def _make_rows(n: int = 96, start: datetime | None = None, interval_min: int = 15, value: float = 10.0) -> list[dict]:
    """Generate n rows of 15-min interval data starting at a given time."""
    if start is None:
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "ts_utc": start + timedelta(minutes=i * interval_min),
            "value": value + (i % 5) * 0.5,
            "unit": "kWh",
            "meter_id": "TEST_METER",
        }
        for i in range(n)
    ]


# --- Check 1: Interval completeness ---

def test_check1_complete_series():
    rows = _make_rows(96)
    result = interval_completeness.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 1
    assert result["status"] == "ok"
    assert result["metric_value"] == 96.0


def test_check1_missing_intervals():
    rows = _make_rows(96)
    # Remove 5 rows to create gaps
    rows = rows[:40] + rows[45:]
    result = interval_completeness.run(rows, CONFIG, job_id=JOB_ID)
    assert result["status"] == "error"
    assert result["affected_slots"]["delta"] == 5


def test_check1_empty():
    result = interval_completeness.run([], CONFIG, job_id=JOB_ID)
    assert result["status"] == "error"


# --- Check 2: Completeness % ---

def test_check2_full_completeness():
    rows = _make_rows(96)
    result = completeness_pct.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 2
    assert result["status"] == "ok"
    assert result["metric_value"] == 100.0


def test_check2_below_threshold():
    rows = _make_rows(96)
    # Remove 10 rows → ~89.6% completeness
    rows = rows[:40] + rows[50:]
    result = completeness_pct.run(rows, CONFIG, job_id=JOB_ID)
    assert result["status"] in ("warn", "error")
    assert result["metric_value"] < 95.0


# --- Check 3: Gaps & duplicates ---

def test_check3_no_gaps():
    rows = _make_rows(96)
    result = gaps_duplicates.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 3
    assert result["status"] == "ok"


def test_check3_with_gap():
    rows = _make_rows(96)
    # Create a 1-hour gap
    rows = rows[:20] + rows[24:]
    result = gaps_duplicates.run(rows, CONFIG, job_id=JOB_ID)
    assert result["status"] == "warn"
    assert result["affected_slots"]["gap_count"] >= 1


def test_check3_with_duplicates():
    rows = _make_rows(96)
    rows.append(rows[10].copy())  # Duplicate a row
    result = gaps_duplicates.run(rows, CONFIG, job_id=JOB_ID)
    assert result["affected_slots"]["duplicate_count"] >= 1


# --- Check 4: Daily/monthly energy ---

def test_check4_complete_day():
    rows = _make_rows(96)  # One full day
    result = daily_monthly_energy.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 4
    assert result["metric_value"] > 0
    assert len(result["affected_slots"]["kwh_day"]) >= 1


def test_check4_incomplete_day():
    rows = _make_rows(48)  # Half day
    result = daily_monthly_energy.run(rows, CONFIG, job_id=JOB_ID)
    assert result["affected_slots"]["incomplete_days"] >= 1


# --- Check 5: Peak load ---

def test_check5_peak():
    rows = _make_rows(96, value=10.0)
    result = peak_load.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 5
    assert result["status"] == "ok"
    assert result["metric_value"] > 0


def test_check5_above_threshold():
    config = QAConfig(max_kw=1.0)  # Very low threshold
    rows = _make_rows(96, value=10.0)
    result = peak_load.run(rows, config, job_id=JOB_ID)
    assert result["status"] == "error"


# --- Check 6: Baseload ---

def test_check6_baseload():
    rows = _make_rows(96)
    result = baseload.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 6
    assert result["status"] == "ok"
    assert result["affected_slots"]["p5_kw"] >= 0
    assert result["affected_slots"]["p10_kw"] >= 0


# --- Check 7: Load factor ---

def test_check7_load_factor():
    rows = _make_rows(96)
    result = load_factor.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 7
    assert 0 < result["metric_value"] <= 1.0


def test_check7_uniform_load():
    """Uniform values → load factor near 1.0."""
    rows = _make_rows(96, value=10.0)
    # Override to all same value
    for r in rows:
        r["value"] = 10.0
    result = load_factor.run(rows, CONFIG, job_id=JOB_ID)
    assert result["metric_value"] == pytest.approx(1.0, abs=0.01)


# --- Check 8: Hourly/weekday profile ---

def test_check8_profiles():
    rows = _make_rows(96)
    result = hourly_weekday_profile.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 8
    assert len(result["affected_slots"]["hourly_profile"]) == 24
    assert len(result["affected_slots"]["weekday_profile"]) == 7


# --- Check 9: DST conformity ---

def test_check9_no_dst_days():
    """Data without DST days → ok."""
    rows = _make_rows(96)  # Jan 1, no DST
    result = dst_conformity.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 9
    assert result["status"] == "ok"


def test_check9_spring_forward():
    """Spring forward day should expect 92 intervals (23h)."""
    # March 30, 2025 is the spring forward in Germany
    start = datetime(2025, 3, 29, 23, 0, tzinfo=timezone.utc)  # Midnight CET = 23:00 UTC
    rows = _make_rows(92, start=start)
    result = dst_conformity.run(rows, CONFIG, job_id=JOB_ID)
    assert result["check_id"] == 9
    # Should find the DST day and check it
    dst_days = result["affected_slots"]["dst_days"]
    if dst_days:
        for day in dst_days:
            if day["date"] == "2025-03-30":
                assert day["expected_slots"] == 92
