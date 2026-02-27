"""P4.3 — Asset Fingerprinting.

Detects behind-the-meter assets from load profile shape analysis:
- **PV**: midday dip (11-15h), negative correlation with GHI, pv_score > 0.3
- **Battery**: night charge ramp (22-06h), night-to-day variance ratio
- **KWK/CHP**: flat baseload + heat-correlated winter spikes, seasonal consistency

Each detector returns a score (0-1) and supporting metrics.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# PV detection thresholds
PV_MIDDAY_HOURS = range(11, 16)  # 11:00 - 15:00
PV_SHOULDER_HOURS = [8, 9, 10, 16, 17, 18]
PV_SCORE_THRESHOLD = 0.3

# Battery detection thresholds
BATTERY_CHARGE_HOURS = range(22, 24)  # 22:00 - 23:00
BATTERY_CHARGE_HOURS_EARLY = range(0, 6)  # 00:00 - 05:00
BATTERY_VARIANCE_RATIO_THRESHOLD = 0.4

# KWK detection thresholds
KWK_WINTER_MONTHS = {1, 2, 3, 10, 11, 12}
KWK_SUMMER_MONTHS = {5, 6, 7, 8}
KWK_BASELOAD_CV_THRESHOLD = 0.3  # coefficient of variation for flat baseload


def detect_assets(
    rows: list[dict],
    weather_correlations: dict | None = None,
) -> dict[str, Any]:
    """Detect asset patterns in the time series.

    Args:
        rows: v1 meter reads (ts_utc, value, unit, meter_id)
        weather_correlations: optional P4.2 output with temp/ghi sensitivity

    Returns:
        dict with keys: asset_hints (summary), pv, battery, kwk
    """
    if len(rows) < 48:
        logger.debug("Too few rows (%d) for asset detection", len(rows))
        return {"asset_hints": None, "pv": None, "battery": None, "kwk": None}

    # Build hourly profile arrays
    hourly_values = _build_hourly_profile(rows)
    monthly_values = _build_monthly_profile(rows)

    # Run detectors
    pv_result = _detect_pv(hourly_values, weather_correlations)
    battery_result = _detect_battery(hourly_values, rows)
    kwk_result = _detect_kwk(hourly_values, monthly_values)

    # Build summary
    detected: list[str] = []
    if pv_result["detected"]:
        detected.append("pv")
    if battery_result["detected"]:
        detected.append("battery")
    if kwk_result["detected"]:
        detected.append("kwk")

    asset_hints: dict[str, Any] | None = None
    if detected:
        asset_hints = {
            "detected_assets": detected,
            "pv_score": pv_result["score"],
            "battery_score": battery_result["score"],
            "kwk_score": kwk_result["score"],
        }

    return {
        "asset_hints": asset_hints,
        "pv": pv_result,
        "battery": battery_result,
        "kwk": kwk_result,
    }


def _build_hourly_profile(rows: list[dict]) -> dict[int, list[float]]:
    """Group values by hour-of-day (0-23)."""
    hourly: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        h = r["ts_utc"].hour
        hourly[h].append(r["value"])
    return dict(hourly)


def _build_monthly_profile(rows: list[dict]) -> dict[int, list[float]]:
    """Group values by month (1-12)."""
    monthly: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        m = r["ts_utc"].month
        monthly[m].append(r["value"])
    return dict(monthly)


def _detect_pv(
    hourly_values: dict[int, list[float]],
    weather_correlations: dict | None = None,
) -> dict[str, Any]:
    """Detect PV generation behind the meter.

    Indicators:
    1. Midday dip: average load at 11-15h is lower than shoulder hours (8-10, 16-18)
    2. Negative GHI correlation from weather enrichment
    3. Combined PV score
    """
    # Compute hourly averages
    hourly_avg = {h: np.mean(vals) for h, vals in hourly_values.items() if vals}

    if not hourly_avg or len(hourly_avg) < 12:
        return {"detected": False, "score": 0.0, "metrics": {}}

    # Midday average
    midday_vals = [hourly_avg[h] for h in PV_MIDDAY_HOURS if h in hourly_avg]
    shoulder_vals = [hourly_avg[h] for h in PV_SHOULDER_HOURS if h in hourly_avg]

    if not midday_vals or not shoulder_vals:
        return {"detected": False, "score": 0.0, "metrics": {}}

    midday_avg = float(np.mean(midday_vals))
    shoulder_avg = float(np.mean(shoulder_vals))

    # Dip ratio: how much lower is midday vs shoulders
    # Positive dip_ratio = midday is lower (PV signature)
    if shoulder_avg > 0:
        dip_ratio = (shoulder_avg - midday_avg) / shoulder_avg
    else:
        dip_ratio = 0.0

    # GHI correlation component
    ghi_sensitivity = 0.0
    if weather_correlations and weather_correlations.get("ghi_sensitivity") is not None:
        ghi_sensitivity = weather_correlations["ghi_sensitivity"]

    # PV score: weighted combination
    # - dip_ratio > 0.1 suggests PV (midday load is lower)
    # - negative GHI correlation suggests PV (more sun = less net load)
    dip_score = max(0.0, min(1.0, dip_ratio * 3))  # scale 0.33 dip → 1.0
    ghi_score = max(0.0, min(1.0, -ghi_sensitivity)) if ghi_sensitivity < 0 else 0.0

    score = 0.6 * dip_score + 0.4 * ghi_score

    return {
        "detected": score >= PV_SCORE_THRESHOLD,
        "score": round(score, 4),
        "metrics": {
            "midday_avg_kw": round(midday_avg, 2),
            "shoulder_avg_kw": round(shoulder_avg, 2),
            "dip_ratio": round(dip_ratio, 4),
            "ghi_sensitivity": round(ghi_sensitivity, 4) if ghi_sensitivity else None,
        },
    }


def _detect_battery(
    hourly_values: dict[int, list[float]],
    rows: list[dict],
) -> dict[str, Any]:
    """Detect battery storage behind the meter.

    Indicators:
    1. Night charge ramp: elevated load at 22-06h compared to overall average
    2. Night-to-day variance ratio: battery smooths daytime peaks
    """
    hourly_avg = {h: np.mean(vals) for h, vals in hourly_values.items() if vals}

    if not hourly_avg or len(hourly_avg) < 12:
        return {"detected": False, "score": 0.0, "metrics": {}}

    # Night charge hours (22-05)
    night_hours = list(BATTERY_CHARGE_HOURS) + list(BATTERY_CHARGE_HOURS_EARLY)
    day_hours = list(range(6, 22))

    night_avg_vals = [hourly_avg[h] for h in night_hours if h in hourly_avg]
    day_avg_vals = [hourly_avg[h] for h in day_hours if h in hourly_avg]

    if not night_avg_vals or not day_avg_vals:
        return {"detected": False, "score": 0.0, "metrics": {}}

    night_avg = float(np.mean(night_avg_vals))
    day_avg = float(np.mean(day_avg_vals))
    overall_avg = float(np.mean(list(hourly_avg.values())))

    # Night charge ratio: elevated night load suggests charging
    if overall_avg > 0:
        night_ratio = night_avg / overall_avg
    else:
        night_ratio = 1.0

    # Variance ratio: battery smooths peaks → lower daytime variance
    night_all = [r["value"] for r in rows if r["ts_utc"].hour in night_hours]
    day_all = [r["value"] for r in rows if r["ts_utc"].hour in day_hours]

    if len(night_all) > 1 and len(day_all) > 1:
        night_var = float(np.var(night_all))
        day_var = float(np.var(day_all))
        variance_ratio = night_var / day_var if day_var > 0 else 0.0
    else:
        variance_ratio = 1.0

    # Battery score
    # Higher night_ratio (>1.1) suggests charging; only consider smoothing if charging present
    charge_score = max(0.0, min(1.0, (night_ratio - 1.0) * 5))  # 1.2 ratio → 1.0
    smooth_score = max(0.0, min(1.0, 1.0 - variance_ratio / BATTERY_VARIANCE_RATIO_THRESHOLD))

    # Require evidence of night charging — smoothing alone is not enough
    if night_ratio < 1.05:
        score = charge_score * 0.3  # Heavily penalize without charging evidence
    else:
        score = 0.5 * charge_score + 0.5 * smooth_score

    return {
        "detected": score >= 0.3,
        "score": round(score, 4),
        "metrics": {
            "night_avg_kw": round(night_avg, 2),
            "day_avg_kw": round(day_avg, 2),
            "night_charge_ratio": round(night_ratio, 4),
            "variance_ratio": round(variance_ratio, 4),
        },
    }


def _detect_kwk(
    hourly_values: dict[int, list[float]],
    monthly_values: dict[int, list[float]],
) -> dict[str, Any]:
    """Detect KWK/CHP (combined heat and power) behind the meter.

    Indicators:
    1. Flat baseload: low coefficient of variation in night hours
    2. Seasonal pattern: higher load in winter (heat-driven) vs summer
    """
    hourly_avg = {h: np.mean(vals) for h, vals in hourly_values.items() if vals}

    if not hourly_avg or len(hourly_avg) < 12:
        return {"detected": False, "score": 0.0, "metrics": {}}

    # Baseload analysis (0-5h): flat load suggests CHP running continuously
    night_values_flat: list[float] = []
    for h in range(0, 6):
        if h in hourly_values:
            night_values_flat.extend(hourly_values[h])

    if len(night_values_flat) < 10:
        return {"detected": False, "score": 0.0, "metrics": {}}

    baseload_mean = float(np.mean(night_values_flat))
    baseload_std = float(np.std(night_values_flat))
    baseload_cv = baseload_std / baseload_mean if baseload_mean > 0 else float("inf")

    # Seasonal analysis
    winter_vals = [v for m in KWK_WINTER_MONTHS if m in monthly_values for v in monthly_values[m]]
    summer_vals = [v for m in KWK_SUMMER_MONTHS if m in monthly_values for v in monthly_values[m]]

    seasonal_ratio = 1.0
    if winter_vals and summer_vals:
        winter_avg = float(np.mean(winter_vals))
        summer_avg = float(np.mean(summer_vals))
        if summer_avg > 0:
            seasonal_ratio = winter_avg / summer_avg

    # KWK score
    # Low CV (<0.3) in baseload + high seasonal ratio (>1.2) suggest CHP
    flatness_score = max(0.0, min(1.0, 1.0 - baseload_cv / KWK_BASELOAD_CV_THRESHOLD))
    seasonal_score = max(0.0, min(1.0, (seasonal_ratio - 1.0) * 3))  # 1.33 ratio → 1.0

    score = 0.5 * flatness_score + 0.5 * seasonal_score

    return {
        "detected": score >= 0.3,
        "score": round(score, 4),
        "metrics": {
            "baseload_kw": round(baseload_mean, 2),
            "baseload_cv": round(baseload_cv, 4),
            "seasonal_ratio": round(seasonal_ratio, 4),
        },
    }
