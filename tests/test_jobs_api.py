"""Integration tests for /api/v1/jobs endpoints."""

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
async def test_create_job(client: AsyncClient) -> None:
    """POST /api/v1/jobs with valid payload returns 201."""
    resp = await client.post("/api/v1/jobs", json={
        "meter_id": "DE0001234567890000000000000000001",
        "company_id": "ACME",
        "plz": "80331",
        "tasks": ["Statistik"],
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending"
    assert data["meter_id"] == "DE0001234567890000000000000000001"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_job_missing_meter_id(client: AsyncClient) -> None:
    """POST /api/v1/jobs with missing required field returns 422."""
    resp = await client.post("/api/v1/jobs", json={"company_id": "ACME"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_job(client: AsyncClient) -> None:
    """GET /api/v1/jobs/{id} returns full job with status."""
    # Create a job first
    create_resp = await client.post("/api/v1/jobs", json={
        "meter_id": "METER001",
        "tasks": ["Prognose"],
        "horizon_months": 12,
    })
    job_id = create_resp.json()["id"]

    # Fetch it
    resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job_id
    assert data["status"] == "pending"
    assert data["payload"]["tasks"] == ["Prognose"]
    assert data["payload"]["horizon_months"] == 12


@pytest.mark.asyncio
async def test_get_job_not_found(client: AsyncClient) -> None:
    """GET /api/v1/jobs/{id} with unknown ID returns 404."""
    resp = await client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs(client: AsyncClient) -> None:
    """GET /api/v1/jobs returns list of jobs."""
    # Create two jobs
    await client.post("/api/v1/jobs", json={"meter_id": "M1"})
    await client.post("/api/v1/jobs", json={"meter_id": "M2"})

    resp = await client.get("/api/v1/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


@pytest.mark.asyncio
async def test_delete_pending_job(client: AsyncClient) -> None:
    """DELETE /api/v1/jobs/{id} on pending job returns 200."""
    create_resp = await client.post("/api/v1/jobs", json={"meter_id": "M_DELETE"})
    job_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200

    # Verify it's gone
    get_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_job(client: AsyncClient) -> None:
    """DELETE /api/v1/jobs/{id} with unknown ID returns 404."""
    resp = await client.delete("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
