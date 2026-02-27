"""Integration tests for Financial API endpoints (P6)."""

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


def _make_hpfc_csv(hours: int = 744, start_date: str = "2025-02-01") -> bytes:
    """Generate HPFC CSV covering ~1 month hourly."""
    lines = ["ts_utc;price_mwh"]
    for h in range(hours):
        day_offset = h // 24
        hour = h % 24
        d = 1 + day_offset
        # Keep within valid date range
        if d > 28:
            break
        price = 40.0 + (h % 12) * 2.5 + random.uniform(-2, 2)
        lines.append(f"2025-02-{d:02d} {hour:02d}:00:00;{price:.2f}")
    return ("\n".join(lines) + "\n").encode()


async def _prepare_for_financial(client: AsyncClient) -> tuple[str, str]:
    """Helper: create job(Aggregation) → ingest → QA → analysis → forecast → return (job_id, snapshot_id).

    Job ends up in financial_running state with HPFC uploaded.
    """
    meter_id = f"FIN_API_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Aggregation"],
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
        files={"file": ("financial_test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest → QA → Analysis → Forecast
    ingest_resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert ingest_resp.status_code == 202

    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202

    ana_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert ana_resp.status_code == 202

    # Verify forecast_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "forecast_running"

    fc_resp = await client.post("/api/v1/forecasts", json={"job_id": job_id})
    assert fc_resp.status_code == 202

    # Verify financial_running
    job_check2 = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check2.json()["status"] == "financial_running"

    # Upload HPFC covering the forecast horizon
    # Get forecast run to know the horizon
    run_resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    run_data = run_resp.json()
    horizon_start = run_data["horizon_start"]
    horizon_end = run_data["horizon_end"]

    # Generate HPFC CSV covering the entire forecast horizon
    from datetime import datetime, timedelta
    start_dt = datetime.fromisoformat(horizon_start.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(horizon_end.replace("Z", "+00:00"))

    hpfc_lines = ["ts_utc;price_mwh"]
    current = start_dt.replace(minute=0, second=0, microsecond=0)
    while current <= end_dt:
        price = 40.0 + (current.hour % 12) * 2.5 + random.uniform(-1, 1)
        ts_str = current.strftime("%Y-%m-%d %H:%M:%S")
        hpfc_lines.append(f"{ts_str};{price:.2f}")
        current += timedelta(hours=1)

    hpfc_csv = ("\n".join(hpfc_lines) + "\n").encode()
    hpfc_resp = await client.post(
        "/api/v1/hpfc/upload?provider_id=test",
        files={"file": ("hpfc_test.csv", hpfc_csv, "text/csv")},
    )
    assert hpfc_resp.status_code == 201
    snapshot_id = hpfc_resp.json()["snapshot_id"]

    return job_id, snapshot_id


@pytest.mark.asyncio
async def test_calculate_financial_returns_202(client: AsyncClient) -> None:
    """POST /financial/calculate with valid job returns 202."""
    job_id, snapshot_id = await _prepare_for_financial(client)

    resp = await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "snapshot_id": snapshot_id,
    })
    assert resp.status_code == 202
    data = resp.json()
    assert "calc_id" in data
    assert data["total_cost_eur"] > 0
    assert data["matched_intervals"] > 0
    assert len(data["monthly_summary"]) >= 1


@pytest.mark.asyncio
async def test_calculate_financial_invalid_job_returns_404(client: AsyncClient) -> None:
    """POST /financial/calculate with nonexistent job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.post("/api/v1/financial/calculate", json={"job_id": fake})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_calculate_financial_wrong_status_returns_409(client: AsyncClient) -> None:
    """POST /financial/calculate on pending job returns 409."""
    meter_id = f"FIN_PEND_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={"meter_id": meter_id})
    job_id = job_resp.json()["id"]

    resp = await client.post("/api/v1/financial/calculate", json={"job_id": job_id})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_financial_result(client: AsyncClient) -> None:
    """GET /financial/{job_id}/result returns cost time series."""
    job_id, snapshot_id = await _prepare_for_financial(client)
    await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "snapshot_id": snapshot_id,
    })

    resp = await client.get(f"/api/v1/financial/{job_id}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_cost_eur"] > 0
    assert len(data["rows"]) > 0
    assert len(data["monthly_summary"]) >= 1
    for row in data["rows"]:
        assert "ts_utc" in row
        assert "consumption_kwh" in row
        assert "price_mwh" in row
        assert "cost_eur" in row


@pytest.mark.asyncio
async def test_get_financial_result_404(client: AsyncClient) -> None:
    """GET /financial/{job_id}/result without calculation returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/financial/{fake}/result")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_financial_export_csv(client: AsyncClient) -> None:
    """GET /financial/{job_id}/export?format=csv returns a CSV file."""
    job_id, snapshot_id = await _prepare_for_financial(client)
    await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "snapshot_id": snapshot_id,
    })

    resp = await client.get(f"/api/v1/financial/{job_id}/export?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.content.decode("utf-8-sig")
    assert "ts_utc" in content
    assert "cost_eur" in content


@pytest.mark.asyncio
async def test_financial_export_404(client: AsyncClient) -> None:
    """GET /financial/{job_id}/export for nonexistent job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/financial/{fake}/export?format=csv")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_financial_advances_job_to_done(client: AsyncClient) -> None:
    """After financial calculation, Aggregation job advances to done."""
    job_id, snapshot_id = await _prepare_for_financial(client)
    await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "snapshot_id": snapshot_id,
    })

    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.json()["status"] == "done"
