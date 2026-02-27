"""Scaling strategy — apply growth %, load shifting from job parameters.

Also includes stubs for weather-conditioned and asset scenario strategies.
"""

from __future__ import annotations

import logging

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


def apply_weather_conditioned(forecast_rows: list[dict], **kwargs: object) -> list[dict]:
    """Weather-conditioned strategy — STUB (deferred: no weather data yet)."""
    logger.warning("Weather-conditioned strategy not yet implemented, returning forecast unchanged")
    return forecast_rows


def apply_asset_scenarios(forecast_rows: list[dict], **kwargs: object) -> list[dict]:
    """Asset scenario strategy — STUB (deferred: P4.3 stub)."""
    logger.warning("Asset scenario strategy not yet implemented, returning forecast unchanged")
    return forecast_rows
