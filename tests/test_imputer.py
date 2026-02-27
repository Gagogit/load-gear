"""Unit tests for P4.4 imputation engine."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.analysis.imputer import impute


JOB_ID = uuid.uuid4()
METER_ID = "TEST_IMPUTE"


def _make_rows(n: int = 96, start: datetime | None = None, gap_start: int = -1, gap_end: int = -1) -> list[dict]:
    """Generate n rows of 15-min data, optionally with a gap."""
    if start is None:
        start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)

    rows = []
    for i in range(n):
        if gap_start <= i < gap_end:
            continue  # Skip to create gap
        rows.append({
            "ts_utc": start + timedelta(minutes=i * 15),
            "value": 10.0 + (i % 8) * 0.5,
            "unit": "kWh",
            "meter_id": METER_ID,
        })
    return rows


def _make_fingerprints() -> dict:
    """Create simple day fingerprints for testing."""
    avg_kw = [30.0 + h * 1.0 for h in range(24)]  # Increasing by hour
    return {
        "Werktag-Winter": {"avg_kw": avg_kw, "count": 5},
    }


def _make_labels(dates: list[str]) -> list[dict]:
    """Create day labels for given dates."""
    return [{"date": d, "label": "Werktag-Winter", "confidence": 1.0} for d in dates]


def test_impute_no_gaps():
    """Complete data → v2 has same rows, all quality_flag=0."""
    rows = _make_rows(96)
    fingerprints = _make_fingerprints()
    labels = _make_labels(["2025-01-01"])

    v2_rows, summary = impute(
        rows, fingerprints, labels,
        meter_id=METER_ID, job_id=JOB_ID,
    )

    assert len(v2_rows) == 96
    assert summary["original"] == 96
    assert summary["profile"] == 0
    assert summary["interpolation"] == 0

    # All should be version=2 with quality_flag=0
    for r in v2_rows:
        assert r["version"] == 2
        assert r["quality_flag"] == 0


def test_impute_fills_gap_with_profile():
    """Gap in data → imputed using day-type profile (quality_flag=2)."""
    rows = _make_rows(96, gap_start=20, gap_end=24)  # 4 missing slots (1 hour)
    fingerprints = _make_fingerprints()
    labels = _make_labels(["2025-01-01"])

    v2_rows, summary = impute(
        rows, fingerprints, labels,
        meter_id=METER_ID, job_id=JOB_ID,
    )

    assert len(v2_rows) == 96  # All slots filled
    assert summary["profile"] >= 1  # Some profile-imputed

    # Check the imputed rows have quality_flag=2
    imputed = [r for r in v2_rows if r["quality_flag"] == 2]
    assert len(imputed) >= 1


def test_impute_fills_gap_with_interpolation():
    """Gap without matching profile → falls back to linear interpolation."""
    rows = _make_rows(96, gap_start=20, gap_end=24)
    # Empty fingerprints → no profile match
    fingerprints = {}
    labels = []

    v2_rows, summary = impute(
        rows, fingerprints, labels,
        meter_id=METER_ID, job_id=JOB_ID,
    )

    assert len(v2_rows) == 96
    assert summary["interpolation"] >= 1

    interpolated = [r for r in v2_rows if r["quality_flag"] == 1]
    assert len(interpolated) >= 1


def test_impute_skips_large_gaps():
    """Gaps larger than max_gap_min are not imputed."""
    # Create 2-day gap (2880 min > default 1440)
    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    # Day 1: 96 intervals
    for i in range(96):
        rows.append({
            "ts_utc": start + timedelta(minutes=i * 15),
            "value": 10.0,
            "unit": "kWh",
            "meter_id": METER_ID,
        })
    # Day 4: 96 intervals (skip days 2-3)
    for i in range(96):
        rows.append({
            "ts_utc": start + timedelta(days=3, minutes=i * 15),
            "value": 10.0,
            "unit": "kWh",
            "meter_id": METER_ID,
        })

    v2_rows, summary = impute(
        rows, {}, [],
        meter_id=METER_ID, job_id=JOB_ID,
        max_gap_min=1440,
    )

    # v2 should NOT include the gap days (too large)
    assert len(v2_rows) < 96 * 4  # Less than full 4 days


def test_impute_empty_input():
    """Empty input returns empty output."""
    v2_rows, summary = impute(
        [], {}, [],
        meter_id=METER_ID, job_id=JOB_ID,
    )
    assert v2_rows == []
    assert summary["original"] == 0


def test_impute_v2_metadata():
    """v2 rows have correct version, job_id, meter_id."""
    rows = _make_rows(24, gap_start=10, gap_end=12)
    v2_rows, _ = impute(
        rows, _make_fingerprints(), _make_labels(["2025-01-01"]),
        meter_id=METER_ID, job_id=JOB_ID,
    )

    for r in v2_rows:
        assert r["meter_id"] == METER_ID
        assert r["version"] == 2
        assert r["job_id"] == JOB_ID
