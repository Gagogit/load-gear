"""Check 2: Completeness percentage — ratio of present to expected slots."""

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
    """Calculate completeness percentage and list missing slots."""
    if not rows:
        return _finding(job_id, 0.0, config.min_completeness_pct, [], "error")

    timestamps = sorted(r["ts_utc"] for r in rows)
    ts_min = timestamps[0]
    ts_max = timestamps[-1]

    # Build expected set of timestamps
    delta = timedelta(minutes=interval_minutes)
    expected_set: set[datetime] = set()
    current = ts_min
    while current <= ts_max:
        expected_set.add(current)
        current += delta

    observed_set = set(timestamps)
    missing = sorted(expected_set - observed_set)
    expected_count = len(expected_set)
    completeness_pct = (len(observed_set) / expected_count * 100) if expected_count > 0 else 0.0

    if completeness_pct >= config.min_completeness_pct:
        status = "ok"
    elif completeness_pct >= config.min_completeness_pct - 5.0:
        status = "warn"
    else:
        status = "error"

    return _finding(
        job_id, completeness_pct, config.min_completeness_pct,
        [ts.isoformat() for ts in missing[:50]],  # cap at 50 for JSON size
        status,
    )


def _finding(
    job_id: uuid.UUID,
    completeness_pct: float,
    threshold: float,
    missing_slots: list[str],
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 2,
        "check_name": "completeness_pct",
        "status": status,
        "metric_key": "completeness_pct",
        "metric_value": round(completeness_pct, 2),
        "threshold": threshold,
        "affected_slots": {"missing_count": len(missing_slots), "missing_slots": missing_slots},
        "recommendation": (
            f"Completeness {completeness_pct:.1f}% below threshold {threshold}%"
            if status != "ok" else None
        ),
    }
