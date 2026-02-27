"""Integration tests for Forecast API endpoints (P5)."""

import uuid
import random

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


async def _prepare_for_forecast(client: AsyncClient) -> str:
    """Helper: create job → upload → ingest → QA → analysis → return job_id in forecast_running."""
    meter_id = f"FC_API_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Prognose"],
        "horizon_months": 1,
    })
    job_id = job_resp.json()["id"]

    # Generate 7-day CSV (672 rows = 7×96) with realistic load pattern
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for day in range(7):
        d = 1 + day  # 01.01.2025 .. 07.01.2025
        for i in range(96):
            h, m = divmod(i * 15, 60)
            hour = h + m / 60.0
            if hour < 6:
                val = 5.0 + random.uniform(0, 2)
            elif hour < 18:
                val = 12.0 + random.uniform(0, 5)
            else:
                val = 7.0 + random.uniform(0, 3)
            val += offset
            val_str = f"{val:.1f}".replace(".", ",")
            lines.append(f"{d:02d}.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("forecast_test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest
    ingest_resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert ingest_resp.status_code == 202

    # QA
    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202

    # Analysis (tasks=Prognose includes Imputation)
    ana_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert ana_resp.status_code == 202

    # Verify job is now in forecast_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    status = job_check.json()["status"]
    assert status == "forecast_running", f"Expected forecast_running, got {status}"

    return job_id


@pytest.mark.asyncio
async def test_post_forecast_returns_202(client: AsyncClient) -> None:
    """POST /forecasts with valid job in forecast_running returns 202."""
    job_id = await _prepare_for_forecast(client)

    resp = await client.post("/api/v1/forecasts", json={"job_id": job_id})
    assert resp.status_code == 202
    data = resp.json()
    assert data["predictions"] > 0
    assert "forecast_run_id" in data


@pytest.mark.asyncio
async def test_post_forecast_invalid_job_returns_404(client: AsyncClient) -> None:
    """POST /forecasts with nonexistent job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.post("/api/v1/forecasts", json={"job_id": fake})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_forecast_wrong_status_returns_409(client: AsyncClient) -> None:
    """POST /forecasts on pending job returns 409."""
    meter_id = f"FC_PEND_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={"meter_id": meter_id})
    job_id = job_resp.json()["id"]

    resp = await client.post("/api/v1/forecasts", json={"job_id": job_id})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_forecast_status(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/status returns status after forecast."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/forecasts/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["forecast_run_id"] is not None


@pytest.mark.asyncio
async def test_get_forecast_run(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/run returns run metadata."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_alias"] == "prophet"
    assert data["status"] == "ok"
    assert data["data_snapshot_id"] is not None


@pytest.mark.asyncio
async def test_get_forecast_run_404(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/run without forecast returns 404."""
    job_id = await _prepare_for_forecast(client)
    resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_forecast_series(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/series returns v3 rows."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/forecasts/{job_id}/series")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert len(data["rows"]) > 0
    for row in data["rows"]:
        assert "y_hat" in row
        assert "q10" in row
        assert "q50" in row
        assert "q90" in row


@pytest.mark.asyncio
async def test_get_forecast_series_pagination(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/series supports pagination."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/forecasts/{job_id}/series?limit=5&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) <= 5
    assert data["total"] > 5  # Should have more than 5 total rows


@pytest.mark.asyncio
async def test_get_forecast_summary(client: AsyncClient) -> None:
    """GET /forecasts/{job_id}/summary returns min/max/mean per quantile."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/forecasts/{job_id}/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert "y_hat" in data
    assert data["y_hat"]["min"] <= data["y_hat"]["max"]
    assert data["q10"] is not None
    assert data["q90"] is not None


@pytest.mark.asyncio
async def test_forecast_advances_job_to_done(client: AsyncClient) -> None:
    """After forecast, Prognose job advances to done."""
    job_id = await _prepare_for_forecast(client)
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.json()["status"] == "done"
