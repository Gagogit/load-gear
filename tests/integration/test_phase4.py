"""End-to-end integration test for Phase 4: Analysis & Imputation.

Scenario:
1. POST /jobs (tasks=["Imputation"]) → pending
2. POST /files/upload (96-row CSV with 4-slot gap) → file_id
3. POST /ingest → qa_running
4. POST /qa → analysis_running
5. POST /analysis → 202, P4.1-P4.4 execute
6. GET /analysis/{job_id}/profile → verify day fingerprints
7. GET /analysis/{job_id}/day-labels → verify classification
8. GET /analysis/{job_id}/weather → verify weather stub
9. GET /analysis/{job_id}/imputation → verify slots_replaced > 0
10. GET /analysis/{job_id}/normalized-v2 → verify v2 rows with quality flags
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
async def test_full_analysis_pipeline(client: AsyncClient) -> None:
    """Full P4 pipeline: ingest → QA → analysis → verify v2 + profile."""

    # Step 1: Create job with Imputation task
    meter_id = f"DE_P4_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Imputation"],
    })
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    # Step 2: Generate 96-row CSV with a 4-slot gap (1 hour missing)
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for i in range(96):
        if 40 <= i < 44:
            continue  # Create 1-hour gap at ~10:00
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
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("gapped_analysis.csv", csv_data, "text/csv")},
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

    # Verify job is in analysis_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "analysis_running"

    # Step 5: Analysis
    analysis_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert analysis_resp.status_code == 202
    ana_data = analysis_resp.json()
    assert ana_data["v2_rows"] >= 92  # At least the original rows
    assert ana_data["day_types"] >= 1
    assert ana_data["slots_replaced"] >= 1  # Gap should be imputed

    # Step 6: Verify profile
    profile_resp = await client.get(f"/api/v1/analysis/{job_id}/profile")
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["day_fingerprints"] is not None
    for label, fp in profile["day_fingerprints"].items():
        assert len(fp["avg_kw"]) == 24
    assert profile["impute_policy"]["method"] == "chain"
    assert profile["seasonality"] is not None

    # Step 7: Verify day labels
    labels_resp = await client.get(f"/api/v1/analysis/{job_id}/day-labels")
    assert labels_resp.status_code == 200
    assert labels_resp.json()["total"] >= 1

    # Step 8: Verify weather (stub)
    weather_resp = await client.get(f"/api/v1/analysis/{job_id}/weather")
    assert weather_resp.status_code == 200
    assert weather_resp.json()["correlations"]["data_available"] is False

    # Step 9: Verify imputation report
    imp_resp = await client.get(f"/api/v1/analysis/{job_id}/imputation")
    assert imp_resp.status_code == 200
    imp_data = imp_resp.json()
    assert imp_data["slots_replaced"] >= 1
    assert imp_data["total_v2_rows"] >= 92

    # Step 10: Verify v2 rows
    v2_resp = await client.get(f"/api/v1/analysis/{job_id}/normalized-v2?limit=200")
    assert v2_resp.status_code == 200
    v2_data = v2_resp.json()
    assert v2_data["total"] >= 92

    # Check quality flags
    flags = {item["quality_flag"] for item in v2_data["items"]}
    assert 0 in flags  # Original values
    # Should have some imputed values (flag 1 or 2)
    assert flags & {1, 2}, f"Expected imputed flags, got {flags}"

    # All items should be version=2
    for item in v2_data["items"]:
        assert item["version"] == 2

    # Step 11: Verify job is done
    final_job = await client.get(f"/api/v1/jobs/{job_id}")
    assert final_job.json()["status"] == "done"


@pytest.mark.asyncio
async def test_analysis_complete_data_no_imputation(client: AsyncClient) -> None:
    """Analysis with complete data → v2 rows all quality_flag=0."""
    meter_id = f"ANA_FULL_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Imputation"],
    })
    job_id = job_resp.json()["id"]

    # Complete 96-row CSV (no gaps)
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
        files={"file": ("complete.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Pipeline: ingest → QA → analysis
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    await client.post("/api/v1/qa", json={"job_id": job_id})
    ana_resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert ana_resp.status_code == 202
    assert ana_resp.json()["slots_replaced"] == 0

    # All v2 rows should have quality_flag=0
    v2_resp = await client.get(f"/api/v1/analysis/{job_id}/normalized-v2?limit=200")
    for item in v2_resp.json()["items"]:
        assert item["quality_flag"] == 0
