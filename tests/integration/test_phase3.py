"""End-to-end integration test for Phase 3: QA Engine.

Scenario:
1. POST /jobs → pending
2. POST /files/upload (sample CSV) → file_id
3. POST /ingest {job_id, file_id} → job goes to qa_running
4. POST /qa {job_id} → 202, 9 checks run
5. GET /qa/{job_id}/status → verify completed
6. GET /qa/{job_id}/report → verify 9 findings
7. GET /qa/{job_id}/findings → verify individual findings
8. GET /qa/{job_id}/profile → verify hourly/weekday arrays
9. GET /jobs/{job_id} → verify job status is done/warn
10. GET /admin/config → verify config endpoint works
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
async def test_full_qa_pipeline(client: AsyncClient) -> None:
    """Full P3 pipeline: ingest → QA → verify report + findings + profile."""

    # Step 1: Create job
    meter_id = f"DE_P3_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Statistik"],
    })
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]

    # Step 2: Generate and upload 96-row CSV (full day, 15-min intervals)
    # Use small offset for uniqueness, keep values realistic (kWh per 15-min)
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for i in range(96):
        h, m = divmod(i * 15, 60)
        # Realistic load curve: low at night, peak mid-day (kWh per 15-min interval)
        hour = h + m / 60.0
        if hour < 6:
            val = 5.0 + random.uniform(0, 2)
        elif hour < 9:
            val = 10.0 + random.uniform(0, 5)
        elif hour < 17:
            val = 15.0 + random.uniform(0, 8)
        elif hour < 21:
            val = 12.0 + random.uniform(0, 5)
        else:
            val = 6.0 + random.uniform(0, 3)
        val += offset
        val_str = f"{val:.1f}".replace(".", ",")
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("fullday.csv", csv_data, "text/csv")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # Step 3: Ingest
    ingest_resp = await client.post("/api/v1/ingest", json={
        "job_id": job_id, "file_id": file_id,
    })
    assert ingest_resp.status_code == 202
    assert ingest_resp.json()["valid_rows"] == 96

    # Step 4: Run QA
    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202
    qa_data = qa_resp.json()
    assert qa_data["checks_completed"] == 9
    assert qa_data["overall_status"] in ("ok", "warn", "error")

    # Step 5: Verify QA status
    status_resp = await client.get(f"/api/v1/qa/{job_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["checks_completed"] == 9
    assert status_data["overall_status"] is not None

    # Step 6: Verify full report
    report_resp = await client.get(f"/api/v1/qa/{job_id}/report")
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert len(report["findings"]) == 9

    # Verify all 9 check names present
    check_names = {f["check_name"] for f in report["findings"]}
    expected_checks = {
        "interval_completeness", "completeness_pct", "gaps_duplicates",
        "daily_monthly_energy", "peak_load", "baseload",
        "load_factor", "hourly_weekday_profile", "dst_conformity",
    }
    assert check_names == expected_checks

    # Step 7: Verify individual findings
    findings_resp = await client.get(f"/api/v1/qa/{job_id}/findings")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()
    assert len(findings) == 9

    # Verify completeness check (96 rows = full day = 100%)
    completeness = next(f for f in findings if f["check_name"] == "completeness_pct")
    assert completeness["metric_value"] == 100.0
    assert completeness["status"] == "ok"

    # Verify interval completeness
    interval = next(f for f in findings if f["check_name"] == "interval_completeness")
    assert interval["metric_value"] == 96.0
    assert interval["status"] == "ok"

    # Verify peak load exists and is reasonable
    peak = next(f for f in findings if f["check_name"] == "peak_load")
    assert peak["metric_value"] > 0
    assert peak["status"] == "ok"

    # Verify load factor
    lf = next(f for f in findings if f["check_name"] == "load_factor")
    assert 0 < lf["metric_value"] <= 1.0

    # Step 8: Verify profile
    profile_resp = await client.get(f"/api/v1/qa/{job_id}/profile")
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert len(profile["hourly_profile"]) == 24
    assert len(profile["weekday_profile"]) == 7
    # Night hours should be lower than day hours (our synthetic data)
    assert profile["hourly_profile"][3] < profile["hourly_profile"][12]

    # Step 9: Verify job status
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.status_code == 200
    final_status = job_check.json()["status"]
    assert final_status in ("done", "warn"), f"Unexpected: {final_status}"

    # Step 10: Verify admin config
    config_resp = await client.get("/api/v1/admin/config")
    assert config_resp.status_code == 200
    assert config_resp.json()["min_completeness_pct"] == 95.0


@pytest.mark.asyncio
async def test_qa_with_gaps(client: AsyncClient) -> None:
    """QA correctly detects gaps in data."""
    meter_id = f"QA_GAP_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Statistik"],
    })
    job_id = job_resp.json()["id"]

    # Generate CSV with a 1-hour gap (skip rows 20-23)
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for i in range(96):
        if 20 <= i < 24:
            continue  # Create 1-hour gap
        h, m = divmod(i * 15, 60)
        val = 10.0 + offset
        val_str = f"{val:.1f}".replace(".", ",")
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("gapped.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest + QA
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202

    # Check gap detection
    findings_resp = await client.get(f"/api/v1/qa/{job_id}/findings")
    findings = findings_resp.json()

    gaps = next(f for f in findings if f["check_name"] == "gaps_duplicates")
    assert gaps["affected_slots"]["gap_count"] >= 1

    completeness = next(f for f in findings if f["check_name"] == "completeness_pct")
    assert completeness["metric_value"] < 100.0
