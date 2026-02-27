"""Unit tests for reader_profile_repo CRUD operations."""

import uuid

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


async def _create_job_and_upload(client: AsyncClient) -> tuple[str, str]:
    """Helper: create job, upload CSV, return (job_id, file_id)."""
    resp = await client.post("/api/v1/jobs", json={"meter_id": f"RP_TEST_{uuid.uuid4().hex[:8]}"})
    job_id = resp.json()["id"]

    import random
    v = random.randint(1, 999)
    csv_data = f"Datum;Uhrzeit;Wert (kWh)\n01.01.2025;00:00;{v},5\n01.01.2025;00:15;{v-1},2\n".encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]
    return job_id, file_id


@pytest.mark.asyncio
async def test_reader_profile_not_found_before_ingest(client: AsyncClient) -> None:
    """GET reader-profile before ingest returns 404."""
    _, file_id = await _create_job_and_upload(client)
    resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reader_profile_created_after_ingest(client: AsyncClient) -> None:
    """After POST /ingest, reader profile is created and GET returns it."""
    job_id, file_id = await _create_job_and_upload(client)

    # Run ingest
    resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert resp.status_code == 202

    # Check profile
    profile_resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert profile_resp.status_code == 200
    data = profile_resp.json()
    assert data["file_id"] == file_id
    assert data["is_override"] is False
    assert data["rules"]["delimiter"] == ";"
    assert data["rules"]["encoding"] in ("utf-8", "ascii")
    assert data["rules"]["decimal_separator"] == ","
    assert data["rules"]["unit"] == "kWh"


@pytest.mark.asyncio
async def test_reader_profile_override(client: AsyncClient) -> None:
    """PUT reader-profile sets is_override=True and updates rules."""
    job_id, file_id = await _create_job_and_upload(client)

    # Run ingest first
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    # Override
    override_rules = {
        "encoding": "utf-8",
        "delimiter": ",",
        "header_row": 0,
        "timestamp_columns": ["Datum", "Uhrzeit"],
        "value_column": "Wert (kWh)",
        "date_format": "%d.%m.%Y",
        "time_format": "%H:%M",
        "decimal_separator": ",",
        "unit": "kWh",
        "series_type": "interval",
        "timezone": "Europe/Berlin",
    }
    put_resp = await client.put(
        f"/api/v1/files/{file_id}/reader-profile",
        json={"rules": override_rules},
    )
    assert put_resp.status_code == 200
    data = put_resp.json()
    assert data["is_override"] is True
    assert data["rules"]["delimiter"] == ","


@pytest.mark.asyncio
async def test_reader_profile_override_nonexistent_file(client: AsyncClient) -> None:
    """PUT reader-profile on nonexistent file returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.put(
        f"/api/v1/files/{fake_id}/reader-profile",
        json={"rules": {
            "encoding": "utf-8", "delimiter": ",", "header_row": 0,
            "timestamp_columns": ["ts"], "value_column": "val",
            "date_format": "%Y-%m-%d", "time_format": "%H:%M",
            "decimal_separator": ".", "unit": "kWh",
            "series_type": "interval", "timezone": "Europe/Berlin",
        }},
    )
    assert resp.status_code == 404
