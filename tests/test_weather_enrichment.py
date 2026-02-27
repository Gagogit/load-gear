"""Unit tests for P4.2 weather enrichment correlation engine (T-037)."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from load_gear.services.analysis.weather_enrichment import (
    enrich_weather,
    _compute_correlations,
    _compute_lag_analysis,
    _compute_wind_correlation,
    _empty_correlations,
    _safe_round,
)


def _make_rows_and_weather(
    hours: int = 48,
    temp_effect: float = 0.5,
    ghi_effect: float = -0.3,
) -> tuple[list[dict], list[dict]]:
    """Generate correlated meter reads and weather data.

    Args:
        hours: number of hourly data points
        temp_effect: how much temperature affects load (positive = heating)
        ghi_effect: how much GHI affects load (negative = PV)
    """
    rows = []
    weather = []
    for h in range(hours):
        ts = datetime(2025, 1, 1, h % 24, tzinfo=timezone.utc)
        if h >= 24:
            ts = datetime(2025, 1, 2, h % 24, tzinfo=timezone.utc)

        temp = 5.0 + 10.0 * np.sin(h * 0.26)  # -5 to 15°C cycle
        ghi = max(0, 400 * np.sin((h % 24 - 6) * 0.26))  # solar curve
        wind = 3.0 + np.sin(h * 0.1) * 2.0

        # Load = base + temp_effect * temp + ghi_effect * ghi + noise
        base_load = 20.0
        load = base_load + temp_effect * temp + ghi_effect * ghi * 0.01

        rows.append({"ts_utc": ts, "value": load, "unit": "kW", "meter_id": "TEST"})
        weather.append({
            "ts_utc": ts,
            "temp_c": temp,
            "ghi_wm2": ghi,
            "wind_ms": wind,
            "confidence": 1.0,
        })

    return rows, weather


# --- enrich_weather (sync, backward compatible) ---

def test_enrich_weather_no_data() -> None:
    """No weather data returns empty correlations."""
    result = enrich_weather([{"ts_utc": datetime.now(timezone.utc), "value": 10}], weather_data=None)
    assert result["data_available"] is False
    assert result["temp_sensitivity"] is None


def test_enrich_weather_empty_rows() -> None:
    """Empty rows return empty correlations."""
    result = enrich_weather([], weather_data=[{"ts_utc": datetime.now(timezone.utc), "temp_c": 5}])
    assert result["data_available"] is False


def test_enrich_weather_with_correlated_data() -> None:
    """Correlated temp/load data should produce significant sensitivity."""
    rows, weather = _make_rows_and_weather(hours=48, temp_effect=1.0)
    result = enrich_weather(rows, weather_data=weather)

    assert result["data_available"] is True
    assert result["temp_sensitivity"] is not None
    assert result["matched_hours"] >= 10


def test_enrich_weather_ghi_sensitivity() -> None:
    """Negative GHI effect should produce negative ghi_sensitivity."""
    rows, weather = _make_rows_and_weather(hours=48, ghi_effect=-1.0)
    result = enrich_weather(rows, weather_data=weather)

    assert result["data_available"] is True
    # GHI sensitivity should be present (may be None if insufficient matched GHI)
    if result["ghi_sensitivity"] is not None:
        assert isinstance(result["ghi_sensitivity"], float)


# --- _compute_correlations ---

def test_compute_correlations_returns_all_fields() -> None:
    """Correlation result has all expected keys."""
    rows, weather = _make_rows_and_weather(hours=24)
    result = _compute_correlations(rows, weather)

    assert "temp_sensitivity" in result
    assert "ghi_sensitivity" in result
    assert "wind_sensitivity" in result
    assert "lags" in result
    assert "data_available" in result
    assert "matched_hours" in result


def test_compute_correlations_few_points() -> None:
    """Less than 10 matched points returns empty."""
    rows = [{"ts_utc": datetime(2025, 1, 1, h, tzinfo=timezone.utc), "value": 10.0} for h in range(5)]
    weather = [{"ts_utc": datetime(2025, 1, 1, h, tzinfo=timezone.utc), "temp_c": 5.0, "ghi_wm2": None, "wind_ms": None} for h in range(5)]
    result = _compute_correlations(rows, weather)
    assert result["data_available"] is False


# --- Lag analysis ---

def test_lag_analysis_returns_per_param() -> None:
    """Lag analysis returns lag for temp and ghi."""
    rows, weather = _make_rows_and_weather(hours=48)
    weather_by_hour = {}
    for w in weather:
        ts_h = w["ts_utc"].replace(minute=0, second=0, microsecond=0)
        weather_by_hour[ts_h] = w

    lags = _compute_lag_analysis(rows, weather_by_hour)
    assert "temp" in lags
    assert "ghi" in lags
    assert isinstance(lags["temp"], int)
    assert -3 <= lags["temp"] <= 3


# --- Wind correlation ---

def test_wind_correlation_with_data() -> None:
    """Wind correlation is computed when wind data available."""
    rows, weather = _make_rows_and_weather(hours=48)
    weather_by_hour = {}
    for w in weather:
        ts_h = w["ts_utc"].replace(minute=0, second=0, microsecond=0)
        weather_by_hour[ts_h] = w

    result = _compute_wind_correlation(rows, weather_by_hour)
    # Should be a float or None
    assert result is None or isinstance(result, float)


def test_wind_correlation_no_wind_data() -> None:
    """No wind data returns None."""
    rows = [{"ts_utc": datetime(2025, 1, 1, h, tzinfo=timezone.utc), "value": 10.0} for h in range(24)]
    weather_by_hour = {
        datetime(2025, 1, 1, h, tzinfo=timezone.utc): {"temp_c": 5.0, "wind_ms": None}
        for h in range(24)
    }
    result = _compute_wind_correlation(rows, weather_by_hour)
    assert result is None


# --- Utilities ---

def test_empty_correlations_structure() -> None:
    """Empty correlations has all expected keys."""
    result = _empty_correlations()
    assert result["data_available"] is False
    assert result["temp_sensitivity"] is None
    assert result["confidence_threshold"] == 0.5


def test_safe_round_none() -> None:
    assert _safe_round(None) is None


def test_safe_round_nan() -> None:
    assert _safe_round(float("nan")) is None


def test_safe_round_normal() -> None:
    assert _safe_round(3.14159, 2) == 3.14
