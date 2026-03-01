"""Phase 1 end-to-end integration test.

Scenario: create job → upload file → verify state → download → delete → verify cleanup.
This is the final acceptance test for Phase 1 (Foundation).
"""

import hashlib
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from load_gear.api.app import create_app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_lastgang.csv"


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_phase1_full_scenario(client: AsyncClient) -> None:
    """End-to-end: create job → upload file → verify → download → delete."""

    # --- Step A: Create job ---
    create_resp = await client.post("/api/v1/jobs", json={
        "meter_id": "DE0009876543210000000000000000001",
        "company_id": "Stadtwerke München",
        "plz": "80331",
        "tasks": ["Prognose"],
        "horizon_months": 12,
        "unit": "kWh",
        "interval_minutes": 15,
    })
    assert create_resp.status_code == 201, f"Expected 201, got {create_resp.status_code}"
    job_data = create_resp.json()
    job_id = job_data["id"]
    assert job_data["status"] == "pending"
    assert job_data["meter_id"] == "DE0009876543210000000000000000001"

    # --- Step B: Upload sample CSV (unique per run to avoid dedup) ---
    raw = SAMPLE_CSV.read_bytes()
    csv_content = raw + f"\n# {uuid.uuid4()}\n".encode()
    expected_sha256 = hashlib.sha256(csv_content).hexdigest()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("lastgang_2025_Q1.csv", csv_content, "text/csv")},
    )
    assert upload_resp.status_code == 201, f"Expected 201, got {upload_resp.status_code}"
    file_data = upload_resp.json()
    file_id = file_data["id"]
    assert file_data["sha256"] == expected_sha256
    assert file_data["original_name"] == "lastgang_2025_Q1.csv"
    assert file_data["file_size"] == len(csv_content)
    assert file_data["duplicate"] is False

    # --- Step C: Verify job state ---
    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    job_detail = job_resp.json()
    assert job_detail["id"] == job_id
    assert job_detail["status"] == "pending"
    assert job_detail["payload"]["tasks"] == ["Prognose"]
    assert job_detail["payload"]["horizon_months"] == 12
    assert job_detail["payload"]["unit"] == "kWh"
    assert job_detail["payload"]["interval_minutes"] == 15

    # --- Step D: Verify file metadata ---
    file_resp = await client.get(f"/api/v1/files/{file_id}")
    assert file_resp.status_code == 200
    file_meta = file_resp.json()
    assert file_meta["id"] == file_id
    assert file_meta["job_id"] == job_id
    assert file_meta["original_name"] == "lastgang_2025_Q1.csv"
    assert file_meta["sha256"] == expected_sha256
    assert file_meta["file_size"] == len(csv_content)
    assert file_meta["mime_type"] == "text/csv"
    assert file_meta["storage_uri"].startswith("local://raw/")

    # --- Step E: Download and verify content ---
    download_resp = await client.get(f"/api/v1/files/{file_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.content == csv_content
    assert "lastgang_2025_Q1.csv" in download_resp.headers["content-disposition"]

    # --- Step F: Verify job appears in list ---
    list_resp = await client.get("/api/v1/jobs?company_id=Stadtwerke+München")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    found = any(j["id"] == job_id for j in list_data["items"])
    assert found, "Job not found in filtered list"

    # --- Step G: Delete job ---
    delete_resp = await client.delete(f"/api/v1/jobs/{job_id}")
    assert delete_resp.status_code == 200

    # --- Step H: Verify job is gone ---
    gone_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert gone_resp.status_code == 404

    # --- Step I: Verify file is also gone (CASCADE) ---
    file_gone_resp = await client.get(f"/api/v1/files/{file_id}")
    assert file_gone_resp.status_code == 404, (
        f"File should be cascade-deleted with job, got {file_gone_resp.status_code}"
    )


@pytest.mark.asyncio
async def test_phase1_sample_csv_is_realistic(client: AsyncClient) -> None:
    """Verify the sample CSV fixture has realistic German meter reading format."""
    csv_content = SAMPLE_CSV.read_text(encoding="utf-8")
    lines = csv_content.strip().split("\n")

    # Header
    assert lines[0] == "Datum;Uhrzeit;Wert (kWh)", "Expected German-format header"

    # At least 24 data rows (6 hours at 15-min intervals)
    data_lines = lines[1:]
    assert len(data_lines) == 24, f"Expected 24 rows, got {len(data_lines)}"

    # Check format of first data row
    parts = data_lines[0].split(";")
    assert len(parts) == 3, "Expected 3 semicolon-separated columns"
    assert parts[0] == "01.01.2025", "Expected DD.MM.YYYY date format"
    assert parts[1] == "00:00", "Expected HH:MM time format"
    assert "," in parts[2], "Expected German decimal separator (comma)"
