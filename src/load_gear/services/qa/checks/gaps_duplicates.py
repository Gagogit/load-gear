"""Check 3: Gaps & duplicates — detect time gaps and duplicate timestamps."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import timedelta

from load_gear.services.qa.config import QAConfig


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Detect gaps (missing intervals) and duplicate timestamps."""
    if not rows:
        return _finding(job_id, 0, 0, 0, [], [], "error")

    timestamps = [r["ts_utc"] for r in rows]
    sorted_ts = sorted(timestamps)
    expected_delta = timedelta(minutes=interval_minutes)

    # Detect gaps
    gap_count = 0
    gap_max_duration_min = 0
    gap_details: list[dict] = []
    for i in range(1, len(sorted_ts)):
        diff = sorted_ts[i] - sorted_ts[i - 1]
        if diff > expected_delta:
            gap_minutes = int(diff.total_seconds() / 60)
            gap_count += 1
            gap_max_duration_min = max(gap_max_duration_min, gap_minutes)
            if len(gap_details) < 20:  # cap details
                gap_details.append({
                    "start": sorted_ts[i - 1].isoformat(),
                    "end": sorted_ts[i].isoformat(),
                    "duration_min": gap_minutes,
                })

    # Detect duplicates
    ts_counts = Counter(timestamps)
    duplicates = [
        {"ts": ts.isoformat(), "count": cnt}
        for ts, cnt in ts_counts.items() if cnt > 1
    ]

    # Status
    has_long_gap = gap_max_duration_min > config.max_gap_duration_min
    has_duplicates = len(duplicates) > 0

    if not has_long_gap and not has_duplicates and gap_count == 0:
        status = "ok"
    elif has_long_gap:
        status = "error"
    else:
        status = "warn"

    return _finding(
        job_id, gap_count, gap_max_duration_min,
        len(duplicates), gap_details, duplicates, status,
    )


def _finding(
    job_id: uuid.UUID,
    gap_count: int,
    gap_max_duration_min: int,
    duplicate_count: int,
    gap_details: list[dict],
    duplicates: list[dict],
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 3,
        "check_name": "gaps_duplicates",
        "status": status,
        "metric_key": "gap_count",
        "metric_value": float(gap_count),
        "threshold": float(gap_max_duration_min),
        "affected_slots": {
            "gap_count": gap_count,
            "gap_max_duration_min": gap_max_duration_min,
            "duplicate_count": duplicate_count,
            "gaps": gap_details[:10],
            "duplicates": duplicates[:10],
        },
        "recommendation": (
            f"{gap_count} gaps found (max {gap_max_duration_min}min), "
            f"{duplicate_count} duplicate timestamps"
            if status != "ok" else None
        ),
    }
