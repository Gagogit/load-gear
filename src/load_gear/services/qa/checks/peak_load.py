"""Check 5: Peak load — maximum kW value and top-N peaks."""

from __future__ import annotations

import uuid

from load_gear.services.qa.config import QAConfig


def run(
    rows: list[dict],
    config: QAConfig,
    *,
    job_id: uuid.UUID,
    interval_minutes: int = 15,
) -> dict:
    """Find peak kW value and top-N peaks. Flag if above max_kw threshold."""
    if not rows:
        return _finding(job_id, 0.0, "", [], config, "error")

    # Convert kWh interval values to kW (power = energy / hours)
    hours_per_interval = interval_minutes / 60.0
    kw_rows = [
        {"ts": r["ts_utc"], "kw": r["value"] / hours_per_interval}
        for r in rows
    ]

    # Sort by kW descending for top-N
    kw_rows.sort(key=lambda x: x["kw"], reverse=True)

    peak = kw_rows[0]
    top_n = kw_rows[: config.top_n_peaks]

    top_n_list = [
        {"ts": r["ts"].isoformat(), "kw": round(r["kw"], 3)}
        for r in top_n
    ]

    # Check against max_kw threshold
    if peak["kw"] > config.max_kw:
        status = "error"
    elif peak["kw"] > config.max_kw * 0.9:
        status = "warn"
    else:
        status = "ok"

    return _finding(
        job_id, peak["kw"], peak["ts"].isoformat(), top_n_list, config, status,
    )


def _finding(
    job_id: uuid.UUID,
    kw_peak: float,
    peak_ts: str,
    top_n: list[dict],
    config: QAConfig,
    status: str,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "job_id": job_id,
        "check_id": 5,
        "check_name": "peak_load",
        "status": status,
        "metric_key": "kw_peak_value",
        "metric_value": round(kw_peak, 3),
        "threshold": config.max_kw,
        "affected_slots": {
            "kw_peak_timestamp": peak_ts,
            "top_n_peaks": top_n,
        },
        "recommendation": (
            f"Peak {kw_peak:.1f} kW exceeds threshold {config.max_kw} kW"
            if status == "error" else None
        ),
    }
