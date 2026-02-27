"""Integration tests for reader profile API endpoints (Task-009)."""

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
    resp = await client.post("/api/v1/jobs", json={"meter_id": f"RP_API_{uuid.uuid4().hex[:8]}"})
    job_id = resp.json()["id"]

    import random
    v = random.randint(1, 999)
    csv_data = (
        f"Datum;Uhrzeit;Wert (kWh)\n01.01.2025;00:00;{v},5\n"
        f"01.01.2025;00:15;{v-1},2\n"
    ).encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]
    return job_id, file_id


@pytest.mark.asyncio
async def test_get_reader_profile_returns_detected_rules(client: AsyncClient) -> None:
    """GET /files/{id}/reader-profile returns detected rules after ingest."""
    job_id, file_id = await _create_job_and_upload(client)

    # Run ingest
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rules"]["delimiter"] == ";"
    assert data["technical_quality"] is not None
    assert data["technical_quality"]["valid_rows"] >= 1


@pytest.mark.asyncio
async def test_put_reader_profile_sets_override(client: AsyncClient) -> None:
    """PUT /files/{id}/reader-profile sets is_override=True."""
    job_id, file_id = await _create_job_and_upload(client)
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    override = {
        "rules": {
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
    }
    resp = await client.put(f"/api/v1/files/{file_id}/reader-profile", json=override)
    assert resp.status_code == 200
    assert resp.json()["is_override"] is True


@pytest.mark.asyncio
async def test_get_reader_profile_404_no_file(client: AsyncClient) -> None:
    """GET reader-profile on nonexistent file returns 404."""
    fake = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/api/v1/files/{fake}/reader-profile")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_reader_profile_404_no_profile(client: AsyncClient) -> None:
    """GET reader-profile on file without profile returns 404."""
    _, file_id = await _create_job_and_upload(client)
    resp = await client.get(f"/api/v1/files/{file_id}/reader-profile")
    assert resp.status_code == 404
