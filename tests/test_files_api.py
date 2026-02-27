"""Integration tests for /api/v1/files endpoints."""

import hashlib
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from load_gear.api.app import create_app


def _unique_csv() -> bytes:
    """Generate unique CSV content to avoid SHA-256 dedup across test runs."""
    marker = uuid.uuid4().hex
    return f"timestamp;value;marker\n01.01.2025 00:00;12.5;{marker}\n01.01.2025 00:15;13.2;{marker}\n".encode()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _create_job(client: AsyncClient) -> str:
    """Helper: create a job and return its ID."""
    resp = await client.post("/api/v1/jobs", json={"meter_id": "FILE_TEST_METER"})
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_upload_file(client: AsyncClient) -> None:
    """POST /files/upload with CSV returns 201 + file_id + sha256."""
    job_id = await _create_job(client)
    csv_data = _unique_csv()

    resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("lastgang.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["sha256"] == hashlib.sha256(csv_data).hexdigest()
    assert data["original_name"] == "lastgang.csv"
    assert data["file_size"] == len(csv_data)
    assert data["duplicate"] is False
    assert "id" in data


@pytest.mark.asyncio
async def test_duplicate_upload(client: AsyncClient) -> None:
    """Duplicate upload (same SHA-256) returns existing file_id."""
    job_id = await _create_job(client)
    csv_data = _unique_csv()

    # First upload
    resp1 = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("lastgang.csv", csv_data, "text/csv")},
    )
    assert resp1.status_code == 201
    file_id_1 = resp1.json()["id"]

    # Second upload with same content
    resp2 = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("lastgang_copy.csv", csv_data, "text/csv")},
    )
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["id"] == file_id_1
    assert data2["duplicate"] is True


@pytest.mark.asyncio
async def test_get_file_metadata(client: AsyncClient) -> None:
    """GET /files/{id} returns metadata."""
    job_id = await _create_job(client)
    unique_csv = b"timestamp;value\n01.01.2025 00:00;99.9\n"

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("test_meta.csv", unique_csv, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/files/{file_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == file_id
    assert data["original_name"] == "test_meta.csv"
    assert data["file_size"] == len(unique_csv)
    assert data["sha256"] == hashlib.sha256(unique_csv).hexdigest()
    assert data["mime_type"] == "text/csv"


@pytest.mark.asyncio
async def test_get_file_not_found(client: AsyncClient) -> None:
    """GET /files/{id} with unknown ID returns 404."""
    resp = await client.get("/api/v1/files/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_download_file(client: AsyncClient) -> None:
    """GET /files/{id}/download returns the original file content."""
    job_id = await _create_job(client)
    unique_csv = b"timestamp;value\n02.02.2025 00:00;77.7\n02.02.2025 00:15;78.8\n"

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("download_test.csv", unique_csv, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    resp = await client.get(f"/api/v1/files/{file_id}/download")
    assert resp.status_code == 200
    assert resp.content == unique_csv
    assert "download_test.csv" in resp.headers.get("content-disposition", "")
