"""P4.2 — Weather Enrichment.

Spatial-temporal join of meter reads with weather observations.
In v0.1, this returns empty correlations when no weather data is available.
The interface is designed for future PostGIS KNN joins.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


def enrich_weather(
    rows: list[dict],
    weather_data: list[dict] | None = None,
) -> dict:
    """Compute weather correlations for the time series.

    Args:
        rows: v1 meter reads (ts_utc, value, unit)
        weather_data: optional weather observations (ts_utc, temp_c, ghi_wm2, confidence)

    Returns:
        weather_correlations dict for analysis_profiles.weather_correlations
    """
    if not weather_data or not rows:
        logger.info("No weather data available — returning empty correlations")
        return {
            "temp_sensitivity": None,
            "ghi_sensitivity": None,
            "lags": {},
            "confidence_threshold": 0.5,
            "data_available": False,
        }

    # Match rows to weather by nearest hour
    weather_by_hour: dict = {}
    for w in weather_data:
        ts_hour = w["ts_utc"].replace(minute=0, second=0, microsecond=0)
        weather_by_hour[ts_hour] = w

    matched_values: list[float] = []
    matched_temps: list[float] = []
    matched_ghi: list[float] = []

    for r in rows:
        ts_hour = r["ts_utc"].replace(minute=0, second=0, microsecond=0)
        w = weather_by_hour.get(ts_hour)
        if w and w.get("temp_c") is not None:
            matched_values.append(r["value"])
            matched_temps.append(w["temp_c"])
            if w.get("ghi_wm2") is not None:
                matched_ghi.append(w["ghi_wm2"])

    if len(matched_values) < 10:
        return {
            "temp_sensitivity": None,
            "ghi_sensitivity": None,
            "lags": {},
            "confidence_threshold": 0.5,
            "data_available": False,
        }

    # Compute correlation coefficients
    values_arr = np.array(matched_values)
    temps_arr = np.array(matched_temps)

    temp_corr = float(np.corrcoef(values_arr, temps_arr)[0, 1])

    ghi_corr = None
    if len(matched_ghi) >= 10:
        ghi_arr = np.array(matched_ghi[:len(matched_values)])
        ghi_corr = float(np.corrcoef(values_arr[:len(ghi_arr)], ghi_arr)[0, 1])

    return {
        "temp_sensitivity": round(temp_corr, 4),
        "ghi_sensitivity": round(ghi_corr, 4) if ghi_corr is not None else None,
        "lags": {"temp": 0},
        "confidence_threshold": 0.5,
        "data_available": True,
    }
