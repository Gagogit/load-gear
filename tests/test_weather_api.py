"""Unit tests for weather API fallback service (T-036)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from load_gear.services.weather.api_fallback import (
    fetch_brightsky,
    fetch_openmeteo,
)


def _mock_client(response_data: dict) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns response_data from .json()."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()

    client = AsyncMock()
    client.get.return_value = mock_resp
    return client


@pytest.fixture
def mock_brightsky_response() -> dict[str, Any]:
    """Minimal BrightSky-style API response."""
    return {
        "weather": [
            {
                "timestamp": "2025-01-01T00:00:00+00:00",
                "source_id": 12345,
                "temperature": 3.5,
                "solar": 0.0,
                "wind_speed": 2.1,
                "cloud_cover": 80.0,
            },
            {
                "timestamp": "2025-01-01T01:00:00+00:00",
                "source_id": 12345,
                "temperature": 3.2,
                "solar": 0.0,
                "wind_speed": 1.8,
                "cloud_cover": 75.0,
            },
        ]
    }


@pytest.fixture
def mock_openmeteo_response() -> dict[str, Any]:
    """Minimal Open-Meteo-style API response."""
    return {
        "hourly": {
            "time": [
                "2025-01-01T00:00",
                "2025-01-01T01:00",
            ],
            "temperature_2m": [3.5, 3.2],
            "shortwave_radiation": [0.0, 0.0],
            "wind_speed_10m": [7.56, 6.48],  # km/h
            "cloud_cover": [80.0, 75.0],
        }
    }


@pytest.mark.asyncio
async def test_fetch_brightsky_parses_response(
    mock_brightsky_response: dict,
) -> None:
    """BrightSky response is correctly parsed into observation dicts."""
    client = _mock_client(mock_brightsky_response)

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)

    rows = await fetch_brightsky(client, 48.13, 11.58, start, end)

    assert len(rows) == 2
    assert rows[0]["source"] == "brightsky"
    assert rows[0]["temp_c"] == 3.5
    assert rows[0]["confidence"] == 0.8
    assert rows[0]["station_id"].startswith("bs_")


@pytest.mark.asyncio
async def test_fetch_openmeteo_parses_response(
    mock_openmeteo_response: dict,
) -> None:
    """Open-Meteo response is correctly parsed with km/h→m/s wind conversion."""
    client = _mock_client(mock_openmeteo_response)

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)

    rows = await fetch_openmeteo(client, 48.13, 11.58, start, end)

    assert len(rows) == 2
    assert rows[0]["source"] == "open_meteo"
    assert rows[0]["temp_c"] == 3.5
    assert rows[0]["confidence"] == 0.6
    # Wind: 7.56 km/h → 2.1 m/s
    assert rows[0]["wind_ms"] == pytest.approx(2.1, abs=0.01)
    assert rows[0]["station_id"].startswith("om_")


@pytest.mark.asyncio
async def test_fetch_brightsky_empty_weather() -> None:
    """BrightSky with empty weather list returns empty."""
    client = _mock_client({"weather": []})

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)

    rows = await fetch_brightsky(client, 48.13, 11.58, start, end)
    assert rows == []


@pytest.mark.asyncio
async def test_fetch_openmeteo_empty_times() -> None:
    """Open-Meteo with no times returns empty."""
    client = _mock_client({"hourly": {"time": []}})

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 2, tzinfo=timezone.utc)

    rows = await fetch_openmeteo(client, 48.13, 11.58, start, end)
    assert rows == []
