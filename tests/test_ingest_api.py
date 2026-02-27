"""Integration tests for ingest orchestration API (Task-011)."""

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


async def _create_job_and_upload(
    client: AsyncClient, *, meter_id: str | None = None
) -> tuple[str, str]:
    """Helper: create job + upload CSV, return (job_id, file_id)."""
    if meter_id is None:
        meter_id = f"INGEST_{uuid.uuid4().hex[:8]}"
    resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Statistik"],
    })
    job_id = resp.json()["id"]

    import random
    v = random.randint(1, 999)
    csv_data = (
        f"Datum;Uhrzeit;Wert (kWh)\n"
        f"01.01.2025;00:00;{v},5\n"
        f"01.01.2025;00:15;{v+3},2\n"
        f"01.01.2025;00:30;{v-1},8\n"
        f"01.01.2025;00:45;{v+2},1\n"
    ).encode()
    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("lastgang.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]
    return job_id, file_id


@pytest.mark.asyncio
async def test_post_ingest_returns_202(client: AsyncClient) -> None:
    """POST /ingest with valid job+file returns 202."""
    job_id, file_id = await _create_job_and_upload(client)
    resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "completed"
    assert data["valid_rows"] >= 1


@pytest.mark.asyncio
async def test_post_ingest_advances_job_status(client: AsyncClient) -> None:
    """After ingest, job status advances past 'ingesting'."""
    job_id, file_id = await _create_job_and_upload(client)
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    status = job_resp.json()["status"]
    assert status in ("qa_running", "done")


@pytest.mark.asyncio
async def test_post_ingest_invalid_job_returns_404(client: AsyncClient) -> None:
    """POST /ingest with nonexistent job_id returns 404."""
    fake_job = str(uuid.uuid4())
    fake_file = str(uuid.uuid4())
    resp = await client.post("/api/v1/ingest", json={"job_id": fake_job, "file_id": fake_file})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_ingest_non_pending_job_returns_409(client: AsyncClient) -> None:
    """POST /ingest on already-ingested job returns 409."""
    job_id, file_id = await _create_job_and_upload(client)

    # First ingest succeeds
    resp1 = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert resp1.status_code == 202

    # Second ingest should fail (job is no longer pending)
    resp2 = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_get_ingest_status(client: AsyncClient) -> None:
    """GET /ingest/{job_id}/status returns progress."""
    job_id, file_id = await _create_job_and_upload(client)
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    resp = await client.get(f"/api/v1/ingest/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job_id
    assert data["valid_rows"] >= 1


@pytest.mark.asyncio
async def test_get_ingest_status_404(client: AsyncClient) -> None:
    """GET /ingest/{job_id}/status with unknown job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/ingest/{fake}/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_normalized_data(client: AsyncClient) -> None:
    """GET /ingest/{job_id}/normalized returns v1 rows."""
    job_id, file_id = await _create_job_and_upload(client)
    ingest_resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert ingest_resp.status_code == 202
    ingest_data = ingest_resp.json()
    assert ingest_data["valid_rows"] >= 1, f"Ingest produced no valid rows: {ingest_data}"

    resp = await client.get(f"/api/v1/ingest/{job_id}/normalized")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1, f"Expected rows, got: {data}. Ingest was: {ingest_data}"
    assert len(data["items"]) >= 1
    item = data["items"][0]
    assert item["version"] == 1
    assert item["quality_flag"] == 0
    assert item["unit"] == "kWh"


@pytest.mark.asyncio
async def test_get_normalized_data_pagination(client: AsyncClient) -> None:
    """GET /ingest/{job_id}/normalized supports pagination."""
    job_id, file_id = await _create_job_and_upload(client)
    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})

    # Request with limit=2
    resp = await client.get(f"/api/v1/ingest/{job_id}/normalized?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2
    assert data["total"] >= 3  # we uploaded 4 data rows
