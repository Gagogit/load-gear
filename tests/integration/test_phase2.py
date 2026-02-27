"""End-to-end integration test for Phase 2: Ingest Pipeline.

Scenario:
1. POST /jobs → pending
2. POST /files/upload (sample_lastgang.csv) → file_id
3. POST /ingest {job_id, file_id} → 202
4. GET /jobs/{job_id} → verify status progressed past ingesting
5. GET /files/{file_id}/reader-profile → verify detected rules
6. GET /ingest/{job_id}/normalized → verify v1 rows
7. Verify meter_reads: correct ts_utc, values, unit, version=1, quality_flag=0
"""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from load_gear.api.app import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_full_ingest_pipeline(client: AsyncClient) -> None:
    """Full P2 pipeline: create job → upload → ingest → verify profile + rows."""

    # Step 1: Create job (unique meter_id per run)
    meter_id = f"DE_P2_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Statistik"],
    })
    assert job_resp.status_code == 201
    job_id = job_resp.json()["id"]
    assert job_resp.json()["status"] == "pending"

    # Step 2: Generate unique CSV data (same format as sample_lastgang.csv but unique values)
    import random
    base = random.randint(100, 9999)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    values = [12.5, 13.2, 11.8, 12.1, 10.9, 11.4, 10.2, 9.8,
              9.5, 9.1, 8.7, 8.9, 8.5, 8.2, 8.0, 8.3,
              8.6, 9.0, 9.4, 10.1, 11.3, 12.8, 14.5, 16.2]
    for i, v in enumerate(values):
        h, m = divmod(i * 15, 60)
        val_str = f"{v + base}".replace(".", ",")
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("sample_lastgang.csv", csv_data, "text/csv")},
    )
    assert upload_resp.status_code == 201
    file_id = upload_resp.json()["id"]

    # Step 3: Run ingest
    ingest_resp = await client.post("/api/v1/ingest", json={
        "job_id": job_id,
        "file_id": file_id,
    })
    assert ingest_resp.status_code == 202
    ingest_data = ingest_resp.json()
    assert ingest_data["status"] == "completed"
    assert ingest_data["valid_rows"] == 24  # sample has 24 data rows

    # Step 4: Verify job status advanced
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.status_code == 200
    job_status = job_check.json()["status"]
    assert job_status in ("qa_running", "done"), f"Unexpected status: {job_status}"

    # Step 5: Verify reader profile
    profile_resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert profile_resp.status_code == 200
    profile = profile_resp.json()
    assert profile["is_override"] is False
    rules = profile["rules"]
    assert rules["encoding"] in ("utf-8", "ascii")
    assert rules["delimiter"] == ";"
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M"
    assert rules["decimal_separator"] == ","
    assert rules["unit"] == "kWh"
    assert rules["series_type"] == "interval"
    assert "Datum" in rules["timestamp_columns"]
    assert "Uhrzeit" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"

    # Verify technical quality stats
    tq = profile["technical_quality"]
    assert tq["total_rows"] == 24
    assert tq["valid_rows"] == 24
    assert tq["invalid_rows"] == 0

    # Step 6: Verify normalized v1 rows
    norm_resp = await client.get(f"/api/v1/ingest/{job_id}/normalized?limit=100")
    assert norm_resp.status_code == 200
    norm_data = norm_resp.json()
    assert norm_data["total"] == 24
    assert len(norm_data["items"]) == 24

    # Step 7: Verify individual meter reads
    for item in norm_data["items"]:
        assert item["meter_id"] == meter_id
        assert item["version"] == 1
        assert item["quality_flag"] == 0
        assert item["unit"] == "kWh"
        assert item["value"] > 0

    # Verify UTC timestamps (Jan 1 CET = UTC+1)
    # 00:00 CET → 23:00 UTC Dec 31
    first_ts = norm_data["items"][0]["ts_utc"]
    assert "23:00" in first_ts  # UTC conversion of 00:00 CET

    # Step 6b: Verify ingest status endpoint
    status_resp = await client.get(f"/api/v1/ingest/{job_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["valid_rows"] == 24


@pytest.mark.asyncio
async def test_ingest_pipeline_cumulative(client: AsyncClient) -> None:
    """Ingest pipeline correctly handles cumulative meter data."""

    # Create job
    cum_meter_id = f"CUM_INT_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": cum_meter_id,
        "tasks": ["Statistik"],
    })
    job_id = job_resp.json()["id"]

    # Upload cumulative CSV (unique content to avoid SHA-256 dedup)
    import random
    base = random.randint(10000, 99999)
    cum_lines = ["Datum;Uhrzeit;Zaehlerstand (kWh)"]
    cum_val = float(base)
    for i in range(8):
        h, m = divmod(i * 15, 60)
        val_str = f"{cum_val:.1f}".replace(".", ",")
        cum_lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
        cum_val += random.uniform(8.0, 15.0)
    csv_data = ("\n".join(cum_lines) + "\n").encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("cumulative.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest
    ingest_resp = await client.post("/api/v1/ingest", json={
        "job_id": job_id,
        "file_id": file_id,
    })
    assert ingest_resp.status_code == 202, f"Ingest failed: {ingest_resp.json()}"

    # Verify profile detects cumulative
    profile_resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert profile_resp.json()["rules"]["series_type"] == "cumulative"

    # Verify normalized rows are interval deltas (8 rows → 7 deltas)
    norm_resp = await client.get(f"/api/v1/ingest/{job_id}/normalized")
    assert norm_resp.json()["total"] == 7

    # All deltas should be positive (monotonically increasing input)
    for item in norm_resp.json()["items"]:
        assert item["value"] > 0
