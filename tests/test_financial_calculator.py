"""Unit tests for financial cost calculation logic."""

from datetime import datetime, timezone

import numpy as np
import pytest


class TestCostCalculation:
    """Test vector multiplication and aggregation logic."""

    def test_basic_cost_formula(self) -> None:
        """cost_eur = (consumption_kwh / 1000) * price_mwh."""
        consumption_kwh = 10.0  # 10 kWh
        price_mwh = 50.0  # EUR/MWh
        cost = (consumption_kwh / 1000.0) * price_mwh
        assert abs(cost - 0.50) < 0.001

    def test_15min_kw_to_kwh(self) -> None:
        """15-min interval: value_kw * 0.25 = kWh."""
        value_kw = 40.0  # 40 kW
        interval_minutes = 15
        hours = interval_minutes / 60.0
        consumption_kwh = value_kw * hours
        assert abs(consumption_kwh - 10.0) < 0.001

    def test_60min_kw_to_kwh(self) -> None:
        """60-min interval: value_kw * 1.0 = kWh."""
        value_kw = 40.0
        interval_minutes = 60
        hours = interval_minutes / 60.0
        consumption_kwh = value_kw * hours
        assert abs(consumption_kwh - 40.0) < 0.001

    def test_vector_multiply_numpy(self) -> None:
        """Vectorized: costs = (consumption / 1000) * prices."""
        consumption_kwh = np.array([10.0, 20.0, 15.0])
        prices_mwh = np.array([50.0, 45.0, 55.0])
        costs = (consumption_kwh / 1000.0) * prices_mwh
        expected = np.array([0.50, 0.90, 0.825])
        np.testing.assert_allclose(costs, expected, rtol=1e-6)

    def test_monthly_aggregation(self) -> None:
        """Monthly summary groups costs by YYYY-MM."""
        from collections import defaultdict

        rows = [
            {"ts_utc": datetime(2025, 1, 15, tzinfo=timezone.utc), "cost_eur": 1.5, "consumption_kwh": 30.0, "price_mwh": 50.0},
            {"ts_utc": datetime(2025, 1, 20, tzinfo=timezone.utc), "cost_eur": 2.0, "consumption_kwh": 40.0, "price_mwh": 50.0},
            {"ts_utc": datetime(2025, 2, 5, tzinfo=timezone.utc), "cost_eur": 1.0, "consumption_kwh": 25.0, "price_mwh": 40.0},
        ]

        monthly: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "kwh": 0.0, "prices": []})
        for r in rows:
            key = r["ts_utc"].strftime("%Y-%m")
            monthly[key]["cost"] += r["cost_eur"]
            monthly[key]["kwh"] += r["consumption_kwh"]
            monthly[key]["prices"].append(r["price_mwh"])

        assert abs(monthly["2025-01"]["cost"] - 3.5) < 0.001
        assert abs(monthly["2025-02"]["cost"] - 1.0) < 0.001
        assert abs(monthly["2025-01"]["kwh"] - 70.0) < 0.001
        assert abs(float(np.mean(monthly["2025-01"]["prices"])) - 50.0) < 0.001

    def test_zero_consumption(self) -> None:
        """Zero consumption yields zero cost."""
        consumption_kwh = 0.0
        price_mwh = 50.0
        cost = (consumption_kwh / 1000.0) * price_mwh
        assert cost == 0.0

    def test_negative_price_allowed(self) -> None:
        """Negative prices (spot market) yield negative costs."""
        consumption_kwh = 10.0
        price_mwh = -5.0
        cost = (consumption_kwh / 1000.0) * price_mwh
        assert cost < 0.0
        assert abs(cost - (-0.05)) < 0.001

    def test_price_alignment_hourly_to_15min(self) -> None:
        """Hourly prices are reused for all 4 intervals within the hour."""
        hourly_price = {0: 50.0, 1: 45.0}  # hour → price

        intervals_15min = [
            (0, 0), (0, 15), (0, 30), (0, 45),
            (1, 0), (1, 15), (1, 30), (1, 45),
        ]

        prices = []
        for h, m in intervals_15min:
            prices.append(hourly_price[h])

        assert prices == [50.0, 50.0, 50.0, 50.0, 45.0, 45.0, 45.0, 45.0]
