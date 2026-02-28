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
    uid = uuid.uuid4().hex[:8]
    resp = await client.post("/api/v1/jobs", json={"meter_id": f"RP_API_{uid}"})
    job_id = resp.json()["id"]

    # Embed uid as comment to guarantee unique SHA-256 per call
    csv_data = (
        f"# {uid}\n"
        f"Datum;Uhrzeit;Wert (kWh)\n"
        f"01.01.2025;00:00;12,5\n"
        f"01.01.2025;00:15;13,2\n"
        f"01.01.2025;00:30;11,8\n"
        f"01.01.2025;00:45;12,1\n"
        f"01.01.2025;01:00;10,9\n"
        f"01.01.2025;01:15;11,4\n"
        f"01.01.2025;01:30;10,2\n"
        f"01.01.2025;01:45;9,8\n"
    ).encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": (f"test_{uid}.csv", csv_data, "text/csv")},
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
