"""Scaling strategies — growth %, load shifting, weather conditioning, asset scenarios."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def apply_scaling(
    forecast_rows: list[dict],
    *,
    growth_pct: float = 0.0,
    load_shift_kw: float = 0.0,
) -> list[dict]:
    """Apply linear growth and load shifting to forecast values.

    Args:
        forecast_rows: [{ts_utc, y_hat, q10, q50, q90}]
        growth_pct: annual growth rate (e.g. 2.0 for +2%)
        load_shift_kw: constant kW offset (e.g. -5.0 for demand reduction)

    Returns:
        Modified forecast rows.
    """
    if not forecast_rows or (growth_pct == 0.0 and load_shift_kw == 0.0):
        return forecast_rows

    multiplier = 1.0 + (growth_pct / 100.0)

    for row in forecast_rows:
        for key in ("y_hat", "q10", "q50", "q90"):
            if row.get(key) is not None:
                row[key] = row[key] * multiplier + load_shift_kw

    return forecast_rows


def apply_weather_conditioned(
    forecast_rows: list[dict],
    *,
    weather_correlations: dict | None = None,
    weather_observations: list[dict] | None = None,
) -> list[dict]:
    """Weather-conditioned strategy: adjust forecast by temperature/GHI deviation.

    Uses temp_sensitivity and ghi_sensitivity from P4.2 weather correlations
    to shift forecast values based on expected weather conditions.

    The adjustment per hour:
        y_adjusted = y_hat * (1 + temp_sens * temp_dev + ghi_sens * ghi_dev)
    where dev = (actual - baseline) / baseline, clamped to ±20%.

    Args:
        forecast_rows: [{ts_utc, y_hat, q10, q50, q90}]
        weather_correlations: P4.2 output (temp_sensitivity, ghi_sensitivity, ...)
        weather_observations: hourly weather [{ts_utc, temp_c, ghi_wm2, ...}]

    Returns:
        Adjusted forecast rows.
    """
    if not forecast_rows:
        return forecast_rows

    if not weather_correlations or not weather_correlations.get("data_available"):
        logger.info("No weather correlations available — skipping weather conditioning")
        return forecast_rows

    if not weather_observations:
        logger.info("No weather observations for forecast period — skipping")
        return forecast_rows

    temp_sens = weather_correlations.get("temp_sensitivity") or 0.0
    ghi_sens = weather_correlations.get("ghi_sensitivity") or 0.0

    if temp_sens == 0.0 and ghi_sens == 0.0:
        return forecast_rows

    # Index weather by hour
    weather_by_hour: dict[Any, dict] = {}
    for w in weather_observations:
        ts_h = w["ts_utc"].replace(minute=0, second=0, microsecond=0)
        weather_by_hour[ts_h] = w

    # Baseline assumptions
    baseline_temp = 15.0  # °C average
    baseline_ghi = 200.0  # W/m² average

    for row in forecast_rows:
        ts_h = row["ts_utc"].replace(minute=0, second=0, microsecond=0)
        w = weather_by_hour.get(ts_h)
        if w is None:
            continue

        adjustment = 0.0

        if temp_sens != 0.0 and w.get("temp_c") is not None:
            temp_dev = (w["temp_c"] - baseline_temp) / baseline_temp
            adjustment += temp_sens * temp_dev * 0.1

        if ghi_sens != 0.0 and w.get("ghi_wm2") is not None:
            ghi_dev = (w["ghi_wm2"] - baseline_ghi) / baseline_ghi
            adjustment += ghi_sens * ghi_dev * 0.1

        # Clamp to ±20%
        adjustment = max(-0.2, min(0.2, adjustment))

        for key in ("y_hat", "q10", "q50", "q90"):
            if row.get(key) is not None:
                row[key] = max(0.0, row[key] * (1.0 + adjustment))

    return forecast_rows


def apply_asset_scenarios(
    forecast_rows: list[dict],
    *,
    asset_hints: dict | None = None,
    scenarios: dict | None = None,
) -> list[dict]:
    """Asset scenario strategy: apply PV, battery, and KWK modifiers.

    Modifiers based on detected assets and user-supplied scenarios:
    - PV: reduce midday load (11-15h) by pv_capacity_kwp * estimated yield
    - Battery: shift peak load to night (charge 22-06h, discharge 10-18h)
    - KWK: add flat baseload offset during heating season (Oct-Mar)

    Args:
        forecast_rows: [{ts_utc, y_hat, q10, q50, q90}]
        asset_hints: P4.3 output with detected_assets, scores
        scenarios: user-supplied parameters from job.payload.scenarios
            - pv_capacity_kwp: installed PV capacity
            - battery_capacity_kwh: battery storage capacity
            - kwk_output_kw: CHP electrical output

    Returns:
        Modified forecast rows.
    """
    if not forecast_rows:
        return forecast_rows

    if not scenarios:
        scenarios = {}

    detected = []
    if asset_hints:
        detected = asset_hints.get("detected_assets", [])

    pv_kwp = scenarios.get("pv_capacity_kwp", 0.0)
    battery_kwh = scenarios.get("battery_capacity_kwh", 0.0)
    kwk_kw = scenarios.get("kwk_output_kw", 0.0)

    # If no assets detected and no scenario params, skip
    if not detected and pv_kwp == 0.0 and battery_kwh == 0.0 and kwk_kw == 0.0:
        logger.info("No asset hints or scenarios — skipping asset adjustments")
        return forecast_rows

    for row in forecast_rows:
        ts = row["ts_utc"]
        hour = ts.hour
        month = ts.month

        # PV: reduce midday load
        if "pv" in detected or pv_kwp > 0:
            capacity = pv_kwp if pv_kwp > 0 else 5.0  # default 5 kWp if detected
            pv_offset = _pv_generation_factor(hour) * capacity
            for key in ("y_hat", "q10", "q50", "q90"):
                if row.get(key) is not None:
                    row[key] = max(0.0, row[key] - pv_offset)

        # Battery: shift load (charge at night, discharge during day)
        if "battery" in detected or battery_kwh > 0:
            capacity = battery_kwh if battery_kwh > 0 else 10.0  # default 10 kWh
            charge_rate = capacity / 8.0  # charge over 8 night hours
            discharge_rate = capacity / 8.0  # discharge over 8 day hours
            if hour in range(22, 24) or hour in range(0, 6):
                # Charging: load increases
                for key in ("y_hat", "q10", "q50", "q90"):
                    if row.get(key) is not None:
                        row[key] = row[key] + charge_rate
            elif hour in range(10, 18):
                # Discharging: load decreases
                for key in ("y_hat", "q10", "q50", "q90"):
                    if row.get(key) is not None:
                        row[key] = max(0.0, row[key] - discharge_rate)

        # KWK: add baseload in heating season
        if "kwk" in detected or kwk_kw > 0:
            output = kwk_kw if kwk_kw > 0 else 3.0  # default 3 kW
            if month in {1, 2, 3, 10, 11, 12}:
                # Heating season: CHP running → reduces net grid draw
                for key in ("y_hat", "q10", "q50", "q90"):
                    if row.get(key) is not None:
                        row[key] = max(0.0, row[key] - output)

    return forecast_rows


def _pv_generation_factor(hour: int) -> float:
    """Approximate PV generation factor by hour (0-1 of peak capacity).

    Bell-curve peaking at solar noon (12-13h).
    """
    # Simple piecewise approximation
    if hour < 6 or hour > 20:
        return 0.0
    if hour < 8:
        return 0.05 * (hour - 6)
    if hour < 11:
        return 0.1 + 0.2 * (hour - 8)
    if hour < 14:
        return 0.7 + 0.1 * (1 - abs(hour - 12.5) / 1.5)
    if hour < 17:
        return 0.7 - 0.2 * (hour - 14)
    if hour < 20:
        return 0.1 - 0.033 * (hour - 17)
    return 0.0
