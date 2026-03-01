"""End-to-end integration test for Phase 6: Financial (HPFC Cost Calculation).

Scenario:
1. POST /jobs (tasks=["Aggregation"]) → pending
2. POST /files/upload (7-day CSV) → file_id
3. POST /ingest → qa_running
4. POST /qa → analysis_running
5. POST /analysis → forecast_running
6. POST /forecasts → financial_running (Aggregation task triggers P6)
7. POST /hpfc/upload → snapshot with hourly prices
8. POST /financial/calculate → 202, cost calculation
9. GET /financial/{job_id}/result → verify cost series + monthly summary
10. GET /financial/{job_id}/export?format=csv → verify CSV download
11. GET /jobs/{job_id} → verify status is done
"""

import uuid
import random
from datetime import datetime, timedelta

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
async def test_full_financial_pipeline(client: AsyncClient) -> None:
    """Full P6 pipeline: ingest → QA → analysis → forecast → HPFC upload → calculate → verify."""

    # Step 1: Create job with Aggregation task
    meter_id = f"DE_P6_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Aggregation"],
        "horizon_months": 1,
    })
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    # Step 2: Generate 7-day CSV (672 rows)
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for day in range(7):
        d = 1 + day
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
        files={"file": ("p6_e2e.csv", csv_data, "text/csv")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # Step 3: Ingest
    ingest_resp = await client.post("/api/v1/ingest", json={
        "job_id": job_id, "file_id": file_id,
    })
    assert ingest_resp.status_code == 202

    # Step 4: QA
    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202

    # Verify job is analysis_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "analysis_running"

    # Step 5: Analysis
    analysis_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert analysis_resp.status_code == 202

    # Verify job is forecast_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "forecast_running"

    # Step 6: Forecast
    forecast_resp = await client.post("/api/v1/forecasts", json={"job_id": job_id})
    assert forecast_resp.status_code == 202
    fc_data = forecast_resp.json()
    assert fc_data["predictions"] > 0

    # Verify job is financial_running (Aggregation task → P6)
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "financial_running"

    # Step 7: Upload HPFC covering forecast horizon
    run_resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    horizon_start = datetime.fromisoformat(run_data["horizon_start"].replace("Z", "+00:00"))
    horizon_end = datetime.fromisoformat(run_data["horizon_end"].replace("Z", "+00:00"))

    hpfc_lines = ["ts_utc;price_mwh"]
    current = horizon_start.replace(minute=0, second=0, microsecond=0)
    while current <= horizon_end:
        price = 40.0 + (current.hour % 12) * 2.5 + random.uniform(-1, 1)
        ts_str = current.strftime("%Y-%m-%d %H:%M:%S")
        hpfc_lines.append(f"{ts_str};{price:.2f}")
        current += timedelta(hours=1)

    hpfc_csv = ("\n".join(hpfc_lines) + "\n").encode()
    hpfc_resp = await client.post(
        "/api/v1/hpfc/upload?provider_id=epex",
        files={"file": ("hpfc_e2e.csv", hpfc_csv, "text/csv")},
    )
    assert hpfc_resp.status_code == 201
    snapshot_id = hpfc_resp.json()["snapshot_id"]
    assert hpfc_resp.json()["rows_imported"] > 0

    # Step 8: Financial calculation (multi-provider response)
    fin_resp = await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "snapshot_id": snapshot_id,
    })
    assert fin_resp.status_code == 202
    fin_data = fin_resp.json()
    assert "results" in fin_data
    baseline = fin_data["results"][0]
    assert baseline["status"] == "ok"
    assert baseline["total_cost_eur"] > 0

    # Step 9: Verify result endpoint (multi-provider)
    result_resp = await client.get(f"/api/v1/financial/{job_id}/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert len(result_data["results"]) >= 1
    assert result_data["results"][0]["total_cost_eur"] > 0

    # Verify per-provider detail endpoint
    detail_resp = await client.get(f"/api/v1/financial/{job_id}/result/baseline")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["total_cost_eur"] > 0
    assert len(detail_data["rows"]) > 0
    assert len(detail_data["monthly_summary"]) >= 1

    # Verify cost row structure
    for row in detail_data["rows"][:5]:
        assert row["consumption_kwh"] > 0
        assert row["price_mwh"] > 0
        assert row["cost_eur"] > 0

    # Step 10: CSV export
    export_resp = await client.get(f"/api/v1/financial/{job_id}/export?format=csv")
    assert export_resp.status_code == 200
    assert "text/csv" in export_resp.headers["content-type"]
    csv_content = export_resp.content.decode("utf-8-sig")
    assert "ts_utc" in csv_content
    assert "cost_eur" in csv_content
    assert "Total Cost EUR" in csv_content

    # Step 11: Verify job is done
    final_job = await client.get(f"/api/v1/jobs/{job_id}")
    assert final_job.json()["status"] == "done"


@pytest.mark.asyncio
async def test_prognose_job_skips_financial(client: AsyncClient) -> None:
    """Job with tasks=["Prognose"] should go to done after forecast, skip P6."""
    meter_id = f"DE_P6_SKIP_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Prognose"],
        "horizon_months": 1,
    })
    job_id = job_resp.json()["id"]

    # Generate simple 7-day CSV
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for day in range(7):
        d = 1 + day
        for i in range(96):
            h, m = divmod(i * 15, 60)
            hour = h + m / 60.0
            val = 10.0 + random.uniform(0, 5) + offset
            val_str = f"{val:.1f}".replace(".", ",")
            lines.append(f"{d:02d}.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("no_fin.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    await client.post("/api/v1/qa", json={"job_id": job_id})
    await client.post("/api/v1/analysis", json={"job_id": job_id})
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    # Should be done, NOT financial_running
    final_job = await client.get(f"/api/v1/jobs/{job_id}")
    assert final_job.json()["status"] == "done"
