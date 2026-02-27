"""Prophet training wrapper — prepares data, fits model, returns predictions.

Prophet requires pandas internally; we convert at the boundary only.
All public inputs/outputs use plain dicts/lists (no pandas in public API).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from functools import partial

import numpy as np

logger = logging.getLogger(__name__)


def _get_german_holidays_df(years: list[int]) -> list[dict]:
    """Build Prophet-compatible holiday rows for German federal holidays + bridge days."""
    from load_gear.services.analysis.day_classifier import _easter, _get_federal_holidays, _is_bridge_day

    rows: list[dict] = []
    for year in years:
        holidays = _get_federal_holidays(year)
        for h in sorted(holidays):
            rows.append({"holiday": "DE_federal", "ds": datetime(h.year, h.month, h.day)})
        # Bridge days
        for day_offset in range(-1, 366):
            d = date(year, 1, 1) + timedelta(days=day_offset)
            if d.year != year:
                continue
            if _is_bridge_day(d, holidays):
                rows.append({"holiday": "DE_bridge", "ds": datetime(d.year, d.month, d.day)})
    return rows


def _train_and_predict(
    rows: list[dict],
    horizon_start: datetime,
    horizon_end: datetime,
    seasonality: dict,
    quantiles: list[float],
    interval_minutes: int,
) -> list[dict]:
    """Synchronous Prophet fit + predict. Run in thread pool executor.

    Args:
        rows: v2 meter reads [{ts_utc, value, ...}]
        horizon_start: forecast start (inclusive)
        horizon_end: forecast end (inclusive)
        seasonality: {daily: bool, weekly: bool, yearly: bool}
        quantiles: e.g. [0.1, 0.5, 0.9]
        interval_minutes: 15 or 60

    Returns:
        List of dicts with keys: ts_utc, y_hat, q10, q50, q90
    """
    import pandas as pd
    from prophet import Prophet

    # Convert to Prophet DataFrame (ds, y)
    df = pd.DataFrame([{"ds": r["ts_utc"], "y": r["value"]} for r in rows])
    if df.empty:
        return []

    # Ensure ds is datetime and tz-naive (Prophet requirement)
    df["ds"] = pd.to_datetime(df["ds"], utc=True).dt.tz_localize(None)
    df = df.sort_values("ds").reset_index(drop=True)

    # Collect years for holidays
    years_in_data = sorted(df["ds"].dt.year.unique().tolist())
    horizon_years = list(range(horizon_start.year, horizon_end.year + 1))
    all_years = sorted(set(years_in_data + horizon_years))

    # Build holidays DataFrame
    holiday_rows = _get_german_holidays_df(all_years)
    holidays_df = pd.DataFrame(holiday_rows) if holiday_rows else None

    # Configure Prophet
    model = Prophet(
        daily_seasonality=seasonality.get("daily", True),
        weekly_seasonality=seasonality.get("weekly", True),
        yearly_seasonality=seasonality.get("yearly", False),
        holidays=holidays_df,
        uncertainty_samples=300,
        interval_width=0.8,  # 80% interval = ~q10/q90
    )

    # Fit
    logger.info("Prophet fit: %d rows, horizon %s → %s", len(df), horizon_start, horizon_end)
    model.fit(df)

    # Build future DataFrame
    freq = f"{interval_minutes}min"
    hs = horizon_start.replace(tzinfo=None) if horizon_start.tzinfo else horizon_start
    he = horizon_end.replace(tzinfo=None) if horizon_end.tzinfo else horizon_end
    future_dates = pd.date_range(start=hs, end=he, freq=freq)
    future = pd.DataFrame({"ds": future_dates})

    # Predict
    forecast = model.predict(future)

    # Extract quantile columns
    results: list[dict] = []
    for _, row in forecast.iterrows():
        ts = row["ds"]
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        results.append({
            "ts_utc": ts.to_pydatetime(),
            "y_hat": float(row["yhat"]),
            "q10": float(row["yhat_lower"]),
            "q50": float(row["yhat"]),  # median ≈ yhat for Prophet
            "q90": float(row["yhat_upper"]),
        })

    return results


async def train_and_predict(
    rows: list[dict],
    horizon_start: datetime,
    horizon_end: datetime,
    seasonality: dict,
    quantiles: list[float],
    interval_minutes: int = 15,
) -> list[dict]:
    """Async wrapper — runs Prophet in thread pool executor (CPU-bound)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(
            _train_and_predict,
            rows,
            horizon_start,
            horizon_end,
            seasonality,
            quantiles,
            interval_minutes,
        ),
    )
