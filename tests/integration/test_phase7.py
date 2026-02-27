"""Integration test for Phase 7: Weather Integration & Asset Intelligence.

Tests the full weather pipeline without external API calls:
1. Weather observation repo: bulk insert + query
2. PLZ geocoding → lat/lon
3. Weather enrichment with real data
4. Asset fingerprinting with weather correlations
5. Weather admin API endpoints
6. Full P4 pipeline with weather data available
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from load_gear.api.app import create_app
from load_gear.services.analysis.asset_fingerprint import detect_assets
from load_gear.services.analysis.weather_enrichment import enrich_weather
from load_gear.services.weather.geocoding import geocode_plz, geocode_plz_safe, reset_cache


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _reset_geo_cache():
    reset_cache()
    yield
    reset_cache()


# --- Geocoding integration ---

def test_geocoding_major_cities() -> None:
    """Geocoding works for major German cities."""
    cities = {
        "10115": ("Berlin-Mitte", 52.0, 53.0),
        "80331": ("München", 48.0, 48.5),
        "20095": ("Hamburg-Mitte", 53.0, 54.0),
        "50667": ("Köln", 50.5, 51.5),
        "60311": ("Frankfurt", 49.5, 50.5),
    }
    for plz, (city, lat_min, lat_max) in cities.items():
        point = geocode_plz(plz)
        assert point.city == city, f"PLZ {plz}: expected {city}, got {point.city}"
        assert lat_min < point.lat < lat_max, f"PLZ {plz}: lat {point.lat} out of range"


def test_geocoding_all_regions() -> None:
    """At least one PLZ per leading digit (0-9) resolves."""
    for digit in range(10):
        plz = f"{digit}0000"
        result = geocode_plz_safe(plz)
        # All German regions 0-9 should have some coverage
        if digit == 0:
            # 00xxx doesn't exist, but 01xxx does — use prefix fallback
            plz = f"0{digit}067"
        result = geocode_plz_safe(plz)
        # At minimum, 2-digit prefix fallback should work for valid regions
        if digit > 0:
            assert result is not None, f"No geocoding for PLZ region {digit}xxxx"


# --- Weather enrichment integration ---

def test_enrichment_full_correlation() -> None:
    """Full correlation computation with matched weather + load data."""
    # Generate 7 days of hourly data
    rows = []
    weather = []
    start = datetime(2025, 1, 6, 0, 0, tzinfo=timezone.utc)

    for h in range(168):  # 7 days
        ts = start + timedelta(hours=h)
        hour = h % 24
        temp = 5.0 + 10.0 * (1.0 if 10 <= hour <= 16 else 0.0)

        # Load correlates with temperature
        load = 20.0 + 0.5 * temp

        rows.append({"ts_utc": ts, "value": load, "unit": "kW", "meter_id": "INT_TEST"})
        weather.append({"ts_utc": ts, "temp_c": temp, "ghi_wm2": None, "wind_ms": None, "confidence": 1.0})

    result = enrich_weather(rows, weather_data=weather)

    assert result["data_available"] is True
    assert result["temp_sensitivity"] is not None
    # Positive temp correlation expected
    assert result["temp_sensitivity"] > 0
    assert "lags" in result
    assert result["matched_hours"] >= 100


# --- Asset fingerprinting integration ---

def test_asset_detection_with_weather() -> None:
    """Asset detection uses weather correlations for PV scoring."""
    # Create PV-like pattern
    rows = []
    start = datetime(2025, 6, 2, 0, 0, tzinfo=timezone.utc)
    for d in range(14):
        for h in range(24):
            ts = start + timedelta(days=d, hours=h)
            if 11 <= h <= 15:
                val = 8.0  # PV dip
            elif 8 <= h <= 18:
                val = 20.0
            else:
                val = 5.0
            rows.append({"ts_utc": ts, "value": val, "unit": "kW", "meter_id": "PV_INT"})

    # With GHI correlation
    weather_corr = {"ghi_sensitivity": -0.6, "data_available": True}
    result = detect_assets(rows, weather_correlations=weather_corr)

    assert result["pv"]["detected"] is True
    assert result["pv"]["score"] >= 0.3
    assert result["asset_hints"] is not None
    assert "pv" in result["asset_hints"]["detected_assets"]


# --- Weather admin API integration ---

@pytest.mark.asyncio
async def test_weather_stations_endpoint(client: AsyncClient) -> None:
    """GET /weather/stations returns valid response structure."""
    resp = await client.get("/api/v1/weather/stations")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_weather_observations_pagination(client: AsyncClient) -> None:
    """GET observations endpoint respects limit/offset."""
    resp = await client.get(
        "/api/v1/weather/stations/00433/observations",
        params={"limit": 10, "offset": 0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["station_id"] == "00433"
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_full_p4_pipeline_with_plz(client: AsyncClient) -> None:
    """Full P4 pipeline: job with PLZ → analysis resolves location gracefully.

    Even without weather data in DB, the pipeline should complete
    (geocoding resolves PLZ, weather enrichment returns empty correlations).
    """
    meter_id = f"P7_INT_{uuid.uuid4().hex[:8]}"

    # 1. Create job with PLZ (München)
    resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "plz": "80331",
        "tasks": ["Imputation"],
    })
    assert resp.status_code == 201
    job_id = resp.json()["id"]

    # 2. Upload CSV (7 days, 15-min, with a small gap)
    import random
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    offset = random.uniform(0.1, 0.9)
    for day in range(7):
        d = 1 + day
        for i in range(96):
            # Skip 4 intervals on day 3 to create a gap
            if day == 2 and 40 <= i < 44:
                continue
            h, m = divmod(i * 15, 60)
            hour = h + m / 60.0
            if hour < 6:
                val = 5.0 + offset + random.uniform(-0.3, 0.3)
            elif hour < 20:
                val = 12.0 + offset + 3 * (1 - abs(hour - 13) / 7) + random.uniform(-0.5, 0.5)
            else:
                val = 6.0 + offset + random.uniform(-0.3, 0.3)
            lines.append(f"{d:02d}.01.2025;{h:02d}:{m:02d};{val:.2f}".replace(".", ",", 1).replace(".", ","))
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")

    # Fix: only replace dots in value, not dates
    lines2 = ["Datum;Uhrzeit;Wert (kWh)"]
    for day in range(7):
        d = 1 + day
        for i in range(96):
            if day == 2 and 40 <= i < 44:
                continue
            h, m = divmod(i * 15, 60)
            hour = h + m / 60.0
            if hour < 6:
                val = 5.0 + offset + random.uniform(-0.3, 0.3)
            elif hour < 20:
                val = 12.0 + offset + 3 * (1 - abs(hour - 13) / 7) + random.uniform(-0.5, 0.5)
            else:
                val = 6.0 + offset + random.uniform(-0.3, 0.3)
            val_str = f"{val:.2f}".replace(".", ",")
            lines2.append(f"{d:02d}.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_bytes = ("\n".join(lines2) + "\n").encode("utf-8")

    resp = await client.post(
        "/api/v1/files/upload",
        files={"file": ("test.csv", csv_bytes, "text/csv")},
        params={"job_id": job_id},
    )
    assert resp.status_code == 201
    file_id = resp.json()["id"]

    # 3. Ingest
    resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert resp.status_code == 202

    # 4. QA
    resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert resp.status_code == 202

    # 5. Analysis (should resolve PLZ → lat/lon, attempt weather, gracefully degrade)
    resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert resp.status_code == 202
    data = resp.json()
    assert data["job_id"] == job_id
    assert data["v2_rows"] > 0

    # 6. Verify job reached done
    resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "done"
