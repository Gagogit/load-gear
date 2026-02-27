"""P4.2 — Weather Enrichment (Spatial-Temporal Join + Correlation Engine).

Performs a PostGIS KNN join to find the nearest weather station, matches
meter reads to weather observations by hour, and computes correlation
coefficients with lag analysis.

Falls back to API sources (BrightSky / Open-Meteo) when no bulk DWD data
is available within the search radius.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.repositories import weather_observation_repo
from load_gear.services.weather.api_fallback import ensure_weather_data

logger = logging.getLogger(__name__)

# Default search radius for nearest station (meters)
DEFAULT_RADIUS_M = 50_000
# Minimum matched data points for meaningful correlation
MIN_MATCHED_POINTS = 10
# Lag range to test (hours)
LAG_RANGE = range(-3, 4)  # -3h to +3h


def _empty_correlations() -> dict[str, Any]:
    """Return empty weather correlation dict."""
    return {
        "temp_sensitivity": None,
        "ghi_sensitivity": None,
        "lags": {},
        "confidence_threshold": 0.5,
        "data_available": False,
    }


async def enrich_weather_async(
    session: AsyncSession,
    rows: list[dict],
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Compute weather correlations using real DB weather data.

    Steps:
    1. Determine time range from meter reads
    2. Ensure weather data exists (cache check + fallback fetch)
    3. Load nearest station observations from DB
    4. Match by hour + compute correlations with lag analysis

    Args:
        session: async DB session
        rows: v1 meter reads (ts_utc, value, unit)
        lat: location latitude (from PLZ geocoding or job config)
        lon: location longitude

    Returns:
        weather_correlations dict for analysis_profiles.weather_correlations
    """
    if not rows or lat is None or lon is None:
        logger.info("No location or rows — returning empty correlations")
        return _empty_correlations()

    # Determine time range from meter reads
    timestamps = [r["ts_utc"] for r in rows]
    start = min(timestamps)
    end = max(timestamps)

    # Try to load weather data; gracefully degrade on any failure
    try:
        # Ensure weather data is available (cache check + API fallback)
        ensure_result = await ensure_weather_data(session, lat, lon, start, end)
        logger.info("Weather data status: %s", ensure_result)
    except Exception as exc:
        logger.warning("Weather data ensure failed: %s — continuing without", exc)
        return _empty_correlations()

    # Load observations from nearest station via PostGIS KNN
    try:
        obs, total = await weather_observation_repo.get_nearest_observations(
            session, lat, lon,
            start=start, end=end,
            max_distance_m=DEFAULT_RADIUS_M,
            limit=100_000,
        )
    except Exception as exc:
        logger.warning("PostGIS weather query failed: %s — continuing without", exc)
        return _empty_correlations()

    if total < MIN_MATCHED_POINTS:
        logger.info("Only %d weather observations found — insufficient", total)
        return _empty_correlations()

    # Convert observations to dicts for matching
    weather_data = [
        {
            "ts_utc": o.ts_utc,
            "temp_c": o.temp_c,
            "ghi_wm2": o.ghi_wm2,
            "wind_ms": o.wind_ms,
            "cloud_pct": o.cloud_pct,
            "confidence": o.confidence,
        }
        for o in obs
    ]

    # Compute correlations
    return _compute_correlations(rows, weather_data)


def enrich_weather(
    rows: list[dict],
    weather_data: list[dict] | None = None,
) -> dict[str, Any]:
    """Compute weather correlations (sync version, backward compatible).

    Used when weather_data is pre-loaded or for testing.
    For production use with DB access, prefer enrich_weather_async().
    """
    if not weather_data or not rows:
        logger.info("No weather data available — returning empty correlations")
        return _empty_correlations()

    return _compute_correlations(rows, weather_data)


def _compute_correlations(
    rows: list[dict],
    weather_data: list[dict],
) -> dict[str, Any]:
    """Core correlation engine: match by hour, compute with lag analysis.

    Tests lags from -3h to +3h and picks the lag with highest |correlation|.
    """
    # Index weather data by hour
    weather_by_hour: dict[datetime, dict] = {}
    for w in weather_data:
        ts = w["ts_utc"]
        if hasattr(ts, "replace"):
            ts_hour = ts.replace(minute=0, second=0, microsecond=0)
        else:
            continue
        weather_by_hour[ts_hour] = w

    # Build aligned arrays for lag=0
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

    if len(matched_values) < MIN_MATCHED_POINTS:
        return _empty_correlations()

    # Compute base correlation (lag=0)
    values_arr = np.array(matched_values)
    temps_arr = np.array(matched_temps)
    temp_corr = float(np.corrcoef(values_arr, temps_arr)[0, 1])

    ghi_corr: float | None = None
    if len(matched_ghi) >= MIN_MATCHED_POINTS:
        ghi_arr = np.array(matched_ghi[:len(matched_values)])
        vals_for_ghi = values_arr[:len(ghi_arr)]
        ghi_corr = float(np.corrcoef(vals_for_ghi, ghi_arr)[0, 1])

    # Lag analysis — find optimal lag for temperature
    best_lags = _compute_lag_analysis(rows, weather_by_hour)

    # Compute wind correlation if available
    wind_corr = _compute_wind_correlation(rows, weather_by_hour)

    result: dict[str, Any] = {
        "temp_sensitivity": _safe_round(temp_corr),
        "ghi_sensitivity": _safe_round(ghi_corr),
        "wind_sensitivity": _safe_round(wind_corr),
        "lags": best_lags,
        "confidence_threshold": 0.5,
        "data_available": True,
        "matched_hours": len(matched_values),
        "total_weather_hours": len(weather_data),
    }

    return result


def _compute_lag_analysis(
    rows: list[dict],
    weather_by_hour: dict[datetime, dict],
) -> dict[str, int]:
    """Test lags -3h to +3h, return best lag per parameter."""
    from datetime import timedelta

    best_lags: dict[str, int] = {}

    for param, key in [("temp", "temp_c"), ("ghi", "ghi_wm2")]:
        best_abs_corr = 0.0
        best_lag = 0

        for lag_h in LAG_RANGE:
            shift = timedelta(hours=lag_h)
            vals: list[float] = []
            params: list[float] = []

            for r in rows:
                ts_hour = r["ts_utc"].replace(minute=0, second=0, microsecond=0)
                w = weather_by_hour.get(ts_hour + shift)
                if w and w.get(key) is not None:
                    vals.append(r["value"])
                    params.append(w[key])

            if len(vals) >= MIN_MATCHED_POINTS:
                corr = abs(float(np.corrcoef(vals, params)[0, 1]))
                if not np.isnan(corr) and corr > best_abs_corr:
                    best_abs_corr = corr
                    best_lag = lag_h

        best_lags[param] = best_lag

    return best_lags


def _compute_wind_correlation(
    rows: list[dict],
    weather_by_hour: dict[datetime, dict],
) -> float | None:
    """Compute correlation between load and wind speed."""
    vals: list[float] = []
    winds: list[float] = []

    for r in rows:
        ts_hour = r["ts_utc"].replace(minute=0, second=0, microsecond=0)
        w = weather_by_hour.get(ts_hour)
        if w and w.get("wind_ms") is not None:
            vals.append(r["value"])
            winds.append(w["wind_ms"])

    if len(vals) < MIN_MATCHED_POINTS:
        return None

    corr = float(np.corrcoef(vals, winds)[0, 1])
    return corr if not np.isnan(corr) else None


def _safe_round(val: float | None, decimals: int = 4) -> float | None:
    """Round a value, returning None if NaN or None."""
    if val is None:
        return None
    if np.isnan(val):
        return None
    return round(val, decimals)
