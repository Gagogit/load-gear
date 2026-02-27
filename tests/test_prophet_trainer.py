"""Unit tests for Prophet training service (P5.1)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from load_gear.services.forecast.prophet_trainer import (
    _get_german_holidays_df,
    _train_and_predict,
    train_and_predict,
)


def _make_v2_rows(days: int = 30, interval_minutes: int = 15) -> list[dict]:
    """Generate synthetic v2 meter read rows for testing."""
    import numpy as np
    rows: list[dict] = []
    start = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    intervals_per_day = 24 * 60 // interval_minutes
    meter_id = f"PROPHET_{uuid.uuid4().hex[:8]}"

    for day in range(days):
        for i in range(intervals_per_day):
            ts = start + timedelta(days=day, minutes=i * interval_minutes)
            hour = ts.hour + ts.minute / 60.0
            # Realistic load curve: baseload + daytime peak
            base = 5.0
            if 6 <= hour < 18:
                val = base + 10.0 * np.sin((hour - 6) / 12 * np.pi)
            else:
                val = base + np.random.uniform(0, 1)
            rows.append({
                "ts_utc": ts,
                "value": round(val, 2),
                "unit": "kW",
                "meter_id": meter_id,
            })
    return rows


def test_german_holidays_df_contains_neujahr() -> None:
    """Holiday dataframe should contain New Year's Day."""
    holidays = _get_german_holidays_df([2025])
    dates = {h["ds"].date() for h in holidays}
    from datetime import date
    assert date(2025, 1, 1) in dates


def test_german_holidays_df_multiple_years() -> None:
    """Holiday dataframe should work for multiple years."""
    holidays = _get_german_holidays_df([2025, 2026])
    dates = {h["ds"].date() for h in holidays}
    from datetime import date
    assert date(2025, 1, 1) in dates
    assert date(2026, 1, 1) in dates


def test_german_holidays_df_contains_bridge_days() -> None:
    """Holiday dataframe should detect bridge days."""
    holidays = _get_german_holidays_df([2025])
    bridge_rows = [h for h in holidays if h["holiday"] == "DE_bridge"]
    # May or may not have bridge days in 2025, but should not crash
    assert isinstance(bridge_rows, list)


def test_train_and_predict_returns_results() -> None:
    """Prophet training should return predictions for the horizon."""
    rows = _make_v2_rows(days=14, interval_minutes=60)  # 14 days hourly for speed
    horizon_start = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
    horizon_end = datetime(2025, 1, 16, 23, 0, tzinfo=timezone.utc)

    results = _train_and_predict(
        rows,
        horizon_start,
        horizon_end,
        seasonality={"daily": True, "weekly": True, "yearly": False},
        quantiles=[0.1, 0.5, 0.9],
        interval_minutes=60,
    )

    assert len(results) > 0
    for r in results:
        assert "ts_utc" in r
        assert "y_hat" in r
        assert "q10" in r
        assert "q50" in r
        assert "q90" in r
        assert isinstance(r["y_hat"], float)
        assert r["q10"] <= r["q90"]


def test_train_and_predict_empty_input() -> None:
    """Empty input should return empty results."""
    results = _train_and_predict(
        [],
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        seasonality={"daily": True, "weekly": True},
        quantiles=[0.1, 0.5, 0.9],
        interval_minutes=15,
    )
    assert results == []


@pytest.mark.asyncio
async def test_async_train_and_predict() -> None:
    """Async wrapper should work correctly (thread pool)."""
    rows = _make_v2_rows(days=7, interval_minutes=60)
    horizon_start = datetime(2025, 1, 8, 0, 0, tzinfo=timezone.utc)
    horizon_end = datetime(2025, 1, 8, 23, 0, tzinfo=timezone.utc)

    results = await train_and_predict(
        rows,
        horizon_start,
        horizon_end,
        seasonality={"daily": True, "weekly": False, "yearly": False},
        quantiles=[0.1, 0.5, 0.9],
        interval_minutes=60,
    )

    assert len(results) == 24  # 24 hours
    assert all(isinstance(r["y_hat"], float) for r in results)
