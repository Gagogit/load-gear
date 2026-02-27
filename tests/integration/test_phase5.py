"""End-to-end integration test for Phase 5: Prophet Forecast.

Scenario:
1. POST /jobs (tasks=["Prognose"]) → pending
2. POST /files/upload (7-day CSV) → file_id
3. POST /ingest → qa_running
4. POST /qa → analysis_running
5. POST /analysis → forecast_running
6. POST /forecasts → 202, P5.1-P5.2 execute
7. GET /forecasts/{job_id}/status → done
8. GET /forecasts/{job_id}/run → verify run metadata
9. GET /forecasts/{job_id}/series → verify v3 rows with quantiles
10. GET /forecasts/{job_id}/summary → verify stats
11. GET /jobs/{job_id} → verify status is done
"""

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


@pytest.mark.asyncio
async def test_full_forecast_pipeline(client: AsyncClient) -> None:
    """Full P5 pipeline: ingest → QA → analysis → forecast → verify v3."""

    # Step 1: Create job with Prognose task
    meter_id = f"DE_P5_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Prognose"],
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
        files={"file": ("forecast_e2e.csv", csv_data, "text/csv")},
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

    # Verify job transitions to analysis_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "analysis_running"

    # Step 5: Analysis
    analysis_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert analysis_resp.status_code == 202

    # Verify job transitions to forecast_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "forecast_running"

    # Step 6: Forecast
    forecast_resp = await client.post("/api/v1/forecasts", json={"job_id": job_id})
    assert forecast_resp.status_code == 202
    fc_data = forecast_resp.json()
    assert fc_data["predictions"] > 0
    forecast_run_id = fc_data["forecast_run_id"]

    # Step 7: Verify forecast status
    status_resp = await client.get(f"/api/v1/forecasts/{job_id}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "done"
    assert status_resp.json()["forecast_run_id"] == forecast_run_id

    # Step 8: Verify run metadata
    run_resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["model_alias"] == "prophet"
    assert run_data["status"] == "ok"
    assert run_data["data_snapshot_id"] is not None
    assert run_data["strategies"] == {"applied": ["calendar_mapping", "dst_correct"]}

    # Step 9: Verify v3 series
    series_resp = await client.get(f"/api/v1/forecasts/{job_id}/series?limit=100")
    assert series_resp.status_code == 200
    series_data = series_resp.json()
    assert series_data["total"] > 0
    assert len(series_data["rows"]) > 0
    for row in series_data["rows"]:
        assert row["y_hat"] is not None
        assert row["q10"] is not None
        assert row["q50"] is not None
        assert row["q90"] is not None

    # Step 10: Verify summary
    summary_resp = await client.get(f"/api/v1/forecasts/{job_id}/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["total"] > 0
    assert summary["y_hat"]["min"] <= summary["y_hat"]["max"]
    assert summary["y_hat"]["mean"] is not None

    # Step 11: Verify job is done
    final_job = await client.get(f"/api/v1/jobs/{job_id}")
    assert final_job.json()["status"] == "done"


@pytest.mark.asyncio
async def test_forecast_without_prognose_task_stays_done(client: AsyncClient) -> None:
    """Job with tasks=["Imputation"] should go to done after analysis, skip forecast."""
    meter_id = f"DE_P5_SKIP_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Imputation"],
    })
    job_id = job_resp.json()["id"]

    # Generate simple 96-row CSV
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for i in range(96):
        h, m = divmod(i * 15, 60)
        val = 10.0 + random.uniform(0, 5) + offset
        val_str = f"{val:.1f}".replace(".", ",")
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("no_forecast.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    await client.post("/api/v1/qa", json={"job_id": job_id})
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    # Should be done, not forecast_running
    final_job = await client.get(f"/api/v1/jobs/{job_id}")
    assert final_job.json()["status"] == "done"
