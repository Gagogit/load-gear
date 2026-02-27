"""Check 1: Interval completeness — observed vs expected interval count."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from load_gear.services.qa.config import QAConfig


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Compare observed interval count against expected for the date range.

    Returns a quality_finding dict ready for DB insertion.
    """
    if not rows:
        return _finding(job_id, 0, 0, 0, "error", "No data rows")

    timestamps = sorted(r["ts_utc"] for r in rows)
    ts_min = timestamps[0]
    ts_max = timestamps[-1]

    # Expected intervals: from first to last timestamp
    span = ts_max - ts_min
    expected = int(span / timedelta(minutes=interval_minutes)) + 1
    observed = len(timestamps)
    delta = expected - observed

    if delta == 0:
        status = "ok"
    elif delta <= 2:
        status = "warn"
    else:
        status = "error"

    return _finding(job_id, observed, expected, delta, status)


def _finding(
    job_id: uuid.UUID,
    observed: int,
    expected: int,
    delta: int,
    status: str,
    recommendation: str | None = None,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 1,
        "check_name": "interval_completeness",
        "status": status,
        "metric_key": "interval_count_observed",
        "metric_value": float(observed),
        "threshold": float(expected),
        "affected_slots": {"expected": expected, "observed": observed, "delta": delta},
        "recommendation": recommendation or (
            f"Missing {delta} intervals" if delta > 0 else None
        ),
    }
