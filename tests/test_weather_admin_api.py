"""Tests for weather admin API endpoints (T-040)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from load_gear.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_stations_empty(client: AsyncClient) -> None:
    """GET /weather/stations on empty DB returns empty list."""
    resp = await client.get("/api/v1/weather/stations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 0
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_observations_empty(client: AsyncClient) -> None:
    """GET /weather/stations/{id}/observations for unknown station returns empty."""
    resp = await client.get("/api/v1/weather/stations/99999/observations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["station_id"] == "99999"


@pytest.mark.asyncio
async def test_delete_station_not_found(client: AsyncClient) -> None:
    """DELETE /weather/stations/{id} for unknown station returns 404."""
    resp = await client.delete("/api/v1/weather/stations/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_import_weather_validation(client: AsyncClient) -> None:
    """POST /weather/import with invalid lat returns 422."""
    resp = await client.post("/api/v1/weather/import", json={
        "station_id": "00433",
        "lat": 999.0,  # Invalid latitude
        "lon": 11.0,
    })
    assert resp.status_code == 422
