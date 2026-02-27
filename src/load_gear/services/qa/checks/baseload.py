"""Check 6: Baseload — P5/P10 percentile of kW values, optional night window."""

from __future__ import annotations

import uuid

import numpy as np
from zoneinfo import ZoneInfo

from load_gear.services.qa.config import QAConfig

_BERLIN = ZoneInfo("Europe/Berlin")


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Calculate baseload as P5 and P10 of kW values. Also compute night baseload (00-04h)."""
    if not rows:
        return _finding(job_id, 0.0, 0.0, 0.0, 0.0, "error")

    hours_per_interval = interval_minutes / 60.0

    all_kw = np.array([r["value"] / hours_per_interval for r in rows])
    night_kw = np.array([
        r["value"] / hours_per_interval
        for r in rows
        if 0 <= r["ts_utc"].astimezone(_BERLIN).hour < 4
    ])

    p5 = float(np.percentile(all_kw, 5))
    p10 = float(np.percentile(all_kw, 10))

    night_p5 = float(np.percentile(night_kw, 5)) if len(night_kw) > 0 else 0.0
    night_p10 = float(np.percentile(night_kw, 10)) if len(night_kw) > 0 else 0.0

    # Baseload is always ok — purely informational
    status = "ok"

    return _finding(job_id, p5, p10, night_p5, night_p10, status)


def _finding(
    job_id: uuid.UUID,
    p5: float,
    p10: float,
    night_p5: float,
    night_p10: float,
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 6,
        "check_name": "baseload",
        "status": status,
        "metric_key": "kw_baseload",
        "metric_value": round(p10, 3),
        "threshold": None,
        "affected_slots": {
            "p5_kw": round(p5, 3),
            "p10_kw": round(p10, 3),
            "night_p5_kw": round(night_p5, 3),
            "night_p10_kw": round(night_p10, 3),
        },
        "recommendation": None,
    }
