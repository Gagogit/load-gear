"""Unit tests for P4.3 asset fingerprinting (T-038)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.analysis.asset_fingerprint import (
    detect_assets,
    _detect_pv,
    _detect_battery,
    _detect_kwk,
    _build_hourly_profile,
    _build_monthly_profile,
)


def _make_rows(
    days: int = 7,
    start: datetime | None = None,
    interval_min: int = 60,
) -> list[dict]:
    """Generate hourly rows with a standard office load pattern."""
    if start is None:
        start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)  # Monday
    rows = []
    for d in range(days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            # Office pattern: low at night, high during day
            if 8 <= h <= 18:
                val = 15.0 + (h - 8) * 0.5
            else:
                val = 5.0 + h * 0.1
            rows.append({"ts_utc": ts, "value": val, "unit": "kW", "meter_id": "TEST"})
    return rows


def _make_pv_rows(days: int = 7) -> list[dict]:
    """Generate rows with a PV midday dip signature."""
    start = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc)  # Summer Monday
    rows = []
    for d in range(days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            # Base office load
            if 8 <= h <= 18:
                val = 20.0
            else:
                val = 5.0
            # PV dip at midday (11-15h): net load drops significantly
            if 11 <= h <= 15:
                val = 8.0  # Much lower than shoulder hours
            rows.append({"ts_utc": ts, "value": val, "unit": "kW", "meter_id": "TEST"})
    return rows


def _make_battery_rows(days: int = 7) -> list[dict]:
    """Generate rows with battery charge/discharge signature."""
    start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)
    rows = []
    for d in range(days):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            if 22 <= h or h < 6:
                val = 18.0  # High night load (charging)
            elif 10 <= h < 18:
                val = 8.0  # Low day load (discharging)
            else:
                val = 12.0
            rows.append({"ts_utc": ts, "value": val, "unit": "kW", "meter_id": "TEST"})
    return rows


def _make_kwk_rows(months: int = 12) -> list[dict]:
    """Generate monthly rows with KWK/CHP pattern: flat baseload + winter spike."""
    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = []
    for m in range(months):
        month = m + 1
        for d in range(28):  # Simplified
            for h in range(24):
                ts = start + timedelta(days=m * 30 + d, hours=h)
                # Flat baseload at night
                if h < 6:
                    val = 10.0 + 0.1  # Very consistent
                else:
                    val = 15.0
                # Winter spike
                if month in (1, 2, 3, 10, 11, 12):
                    val *= 1.4
                rows.append({"ts_utc": ts, "value": val, "unit": "kW", "meter_id": "TEST"})
    return rows


# --- detect_assets interface ---

def test_detect_assets_too_few_rows() -> None:
    """Less than 48 rows returns null hints."""
    rows = [{"ts_utc": datetime(2025, 1, 1, h, tzinfo=timezone.utc), "value": 10.0, "unit": "kW", "meter_id": "T"} for h in range(10)]
    result = detect_assets(rows)
    assert result["asset_hints"] is None
    assert result["pv"] is None


def test_detect_assets_returns_dict_structure() -> None:
    """Result always has asset_hints, pv, battery, kwk keys."""
    rows = _make_rows()
    result = detect_assets(rows)
    assert "asset_hints" in result
    assert "pv" in result
    assert "battery" in result
    assert "kwk" in result


def test_detect_assets_normal_office_no_assets() -> None:
    """Normal office pattern should not detect PV or battery."""
    rows = _make_rows(days=14)
    result = detect_assets(rows)
    pv = result["pv"]
    battery = result["battery"]
    assert pv["detected"] is False
    assert battery["detected"] is False


# --- PV detection ---

def test_detect_pv_with_midday_dip() -> None:
    """PV midday dip pattern should be detected."""
    rows = _make_pv_rows(days=14)
    hourly = _build_hourly_profile(rows)
    result = _detect_pv(hourly)
    assert result["detected"] is True
    assert result["score"] >= 0.3
    assert result["metrics"]["dip_ratio"] > 0.1


def test_detect_pv_with_ghi_correlation() -> None:
    """Negative GHI sensitivity boosts PV score."""
    rows = _make_pv_rows()
    hourly = _build_hourly_profile(rows)
    weather_corr = {"ghi_sensitivity": -0.7, "data_available": True}
    result = _detect_pv(hourly, weather_correlations=weather_corr)
    assert result["detected"] is True
    assert result["score"] > 0.3


def test_detect_pv_no_dip() -> None:
    """Standard office load without dip → not detected."""
    rows = _make_rows()
    hourly = _build_hourly_profile(rows)
    result = _detect_pv(hourly)
    assert result["score"] < 0.3


# --- Battery detection ---

def test_detect_battery_charge_pattern() -> None:
    """Battery night charge + day discharge pattern should be detected."""
    rows = _make_battery_rows(days=14)
    hourly = _build_hourly_profile(rows)
    result = _detect_battery(hourly, rows)
    assert result["detected"] is True
    assert result["metrics"]["night_charge_ratio"] > 1.0


def test_detect_battery_normal_load() -> None:
    """Normal office load without battery signature."""
    rows = _make_rows(days=14)
    hourly = _build_hourly_profile(rows)
    result = _detect_battery(hourly, rows)
    assert result["detected"] is False


# --- KWK detection ---

def test_detect_kwk_flat_baseload_and_seasonal() -> None:
    """KWK pattern: flat night baseload + winter/summer ratio > 1.2."""
    rows = _make_kwk_rows(months=12)
    hourly = _build_hourly_profile(rows)
    monthly = _build_monthly_profile(rows)
    result = _detect_kwk(hourly, monthly)
    assert result["detected"] is True
    assert result["metrics"]["baseload_cv"] < 0.3
    assert result["metrics"]["seasonal_ratio"] > 1.0


def test_detect_kwk_no_seasonal() -> None:
    """No seasonal variation → KWK not detected."""
    rows = _make_rows(days=14)
    hourly = _build_hourly_profile(rows)
    monthly = _build_monthly_profile(rows)
    result = _detect_kwk(hourly, monthly)
    # Single month data → seasonal_ratio = 1.0 → low score
    assert result["score"] < 0.5
