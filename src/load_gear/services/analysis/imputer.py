"""P4.4 — Imputation Engine.

Replace missing/flagged intervals using priority chain:
1. Day-type profile (from P4.1) — use average for this hour + day label
2. Weather-sensitive value (from P4.2) — adjust by temperature/GHI regression
3. Asset-adjusted (from P4.3) — SKIPPED (stub returns null)
4. Fallback — linear interpolation between nearest valid neighbors

Quality flags: 0=original, 1=interpolated, 2=profile-based, 3=weather-based
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
from zoneinfo import ZoneInfo

_BERLIN = ZoneInfo("Europe/Berlin")


def impute(
    v1_rows: list[dict],
    day_fingerprints: dict[str, dict],
    day_labels: list[dict],
    weather_correlations: dict | None = None,
    asset_hints: dict | None = None,
    *,
    interval_minutes: int = 15,
    meter_id: str,
    job_id: uuid.UUID,
    source_file_id: uuid.UUID | None = None,
    max_gap_min: int = 1440,
) -> tuple[list[dict], dict]:
    """Run imputation chain on v1 rows and produce v2 rows.

    Args:
        v1_rows: sorted list of v1 meter read dicts
        day_fingerprints: from P4.1 day classifier
        day_labels: from P4.1 day classifier
        weather_correlations: from P4.2 (unused if None/no data)
        asset_hints: from P4.3 (None in v0.1)
        interval_minutes: data interval
        meter_id: meter identifier
        job_id: parent job
        source_file_id: original file
        max_gap_min: don't impute gaps longer than this

    Returns:
        (v2_rows, method_summary)
        - v2_rows: list of dicts ready for meter_reads insertion (version=2)
        - method_summary: {"profile": n, "interpolation": n, "original": n}
    """
    if not v1_rows:
        return [], {"profile": 0, "interpolation": 0, "original": 0}

    delta = timedelta(minutes=interval_minutes)
    hours_per_interval = interval_minutes / 60.0

    # Build label lookup by date
    label_by_date: dict[str, str] = {
        dl["date"]: dl["label"] for dl in day_labels
    }

    # Build existing timestamp → value map
    existing: dict[datetime, dict] = {r["ts_utc"]: r for r in v1_rows}

    # Determine full expected range
    sorted_ts = sorted(existing.keys())
    ts_min = sorted_ts[0]
    ts_max = sorted_ts[-1]

    # Build complete timestamp grid
    all_timestamps: list[datetime] = []
    current = ts_min
    while current <= ts_max:
        all_timestamps.append(current)
        current += delta

    # Find missing slots
    missing_slots = [ts for ts in all_timestamps if ts not in existing]

    # Group missing into contiguous gaps for max_gap check
    gaps: list[list[datetime]] = []
    if missing_slots:
        current_gap = [missing_slots[0]]
        for i in range(1, len(missing_slots)):
            if missing_slots[i] - missing_slots[i - 1] == delta:
                current_gap.append(missing_slots[i])
            else:
                gaps.append(current_gap)
                current_gap = [missing_slots[i]]
        gaps.append(current_gap)

    # Determine which missing slots to impute (skip gaps > max_gap_min)
    imputable: set[datetime] = set()
    for gap in gaps:
        gap_duration = len(gap) * interval_minutes
        if gap_duration <= max_gap_min:
            imputable.update(gap)

    # Build v2 rows
    v2_rows: list[dict] = []
    method_counts = defaultdict(int)

    for ts in all_timestamps:
        if ts in existing:
            # Original value → copy to v2 with quality_flag=0
            orig = existing[ts]
            v2_rows.append({
                "ts_utc": ts,
                "meter_id": meter_id,
                "version": 2,
                "job_id": job_id,
                "value": orig["value"],
                "unit": orig.get("unit", "kWh"),
                "quality_flag": 0,
                "source_file_id": source_file_id,
            })
            method_counts["original"] += 1
        elif ts in imputable:
            # Try imputation chain
            value, flag = _impute_slot(
                ts, existing, day_fingerprints, label_by_date,
                weather_correlations, asset_hints,
                hours_per_interval=hours_per_interval,
            )
            v2_rows.append({
                "ts_utc": ts,
                "meter_id": meter_id,
                "version": 2,
                "job_id": job_id,
                "value": value,
                "unit": "kWh",
                "quality_flag": flag,
                "source_file_id": source_file_id,
            })
            if flag == 2:
                method_counts["profile"] += 1
            elif flag == 1:
                method_counts["interpolation"] += 1
            elif flag == 3:
                method_counts["weather"] += 1
        # else: gap too long, skip

    method_summary = {
        "original": method_counts["original"],
        "profile": method_counts["profile"],
        "interpolation": method_counts["interpolation"],
        "weather": method_counts.get("weather", 0),
    }

    return v2_rows, method_summary


def _impute_slot(
    ts: datetime,
    existing: dict[datetime, dict],
    day_fingerprints: dict[str, dict],
    label_by_date: dict[str, str],
    weather_correlations: dict | None,
    asset_hints: dict | None,
    *,
    hours_per_interval: float,
) -> tuple[float, int]:
    """Impute a single missing slot using the priority chain.

    Returns (value_kwh, quality_flag).
    """
    ts_local = ts.astimezone(_BERLIN)
    date_str = ts_local.date().isoformat()
    hour = ts_local.hour

    # Priority 1: Day-type profile
    label = label_by_date.get(date_str)
    if label and label in day_fingerprints:
        fp = day_fingerprints[label]
        avg_kw = fp.get("avg_kw", [])
        if avg_kw and hour < len(avg_kw) and avg_kw[hour] > 0:
            # Convert avg kW back to kWh for the interval
            value = avg_kw[hour] * hours_per_interval
            return round(value, 4), 2  # profile-based

    # Priority 2: Weather-sensitive — skip if no data (v0.1)
    # Future: adjust profile value by weather regression

    # Priority 3: Asset-adjusted — skip (stub, ADR-005)

    # Priority 4: Linear interpolation
    value = _linear_interpolate(ts, existing)
    if value is not None:
        return round(value, 4), 1  # interpolated

    # Last resort: use overall mean
    all_values = [r["value"] for r in existing.values()]
    return round(float(np.mean(all_values)), 4), 1


def _linear_interpolate(
    ts: datetime,
    existing: dict[datetime, dict],
) -> float | None:
    """Linear interpolation between nearest valid neighbors."""
    # Find nearest before and after
    before_ts = None
    after_ts = None

    sorted_existing = sorted(existing.keys())

    for t in sorted_existing:
        if t < ts:
            before_ts = t
        elif t > ts:
            after_ts = t
            break

    if before_ts is not None and after_ts is not None:
        before_val = existing[before_ts]["value"]
        after_val = existing[after_ts]["value"]
        total_span = (after_ts - before_ts).total_seconds()
        elapsed = (ts - before_ts).total_seconds()
        if total_span > 0:
            ratio = elapsed / total_span
            return before_val + (after_val - before_val) * ratio

    # One-sided: use the available neighbor
    if before_ts is not None:
        return existing[before_ts]["value"]
    if after_ts is not None:
        return existing[after_ts]["value"]

    return None
