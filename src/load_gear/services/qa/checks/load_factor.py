"""Check 7: Load factor — average/peak ratio and standard deviation."""

from __future__ import annotations

import uuid

import numpy as np

from load_gear.services.qa.config import QAConfig


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Calculate load factor = kw_avg / kw_peak and standard deviation."""
    if not rows:
        return _finding(job_id, 0.0, 0.0, 0.0, 0.0, "error")

    hours_per_interval = interval_minutes / 60.0
    kw_values = np.array([r["value"] / hours_per_interval for r in rows])

    kw_avg = float(np.mean(kw_values))
    kw_peak = float(np.max(kw_values))
    kw_stddev = float(np.std(kw_values))
    load_factor = kw_avg / kw_peak if kw_peak > 0 else 0.0

    # Load factor: informational, but very low factor can indicate issues
    if load_factor >= 0.1:
        status = "ok"
    else:
        status = "warn"

    return _finding(job_id, load_factor, kw_avg, kw_peak, kw_stddev, status)


def _finding(
    job_id: uuid.UUID,
    load_factor: float,
    kw_avg: float,
    kw_peak: float,
    kw_stddev: float,
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 7,
        "check_name": "load_factor",
        "status": status,
        "metric_key": "load_factor",
        "metric_value": round(load_factor, 4),
        "threshold": None,
        "affected_slots": {
            "kw_avg": round(kw_avg, 3),
            "kw_peak": round(kw_peak, 3),
            "stddev_kw": round(kw_stddev, 3),
        },
        "recommendation": (
            f"Very low load factor ({load_factor:.3f}) — may indicate data quality issues"
            if status == "warn" else None
        ),
    }
