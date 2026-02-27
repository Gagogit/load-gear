"""Integration tests for QA API endpoints (P3)."""

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


async def _ingest_job(client: AsyncClient) -> tuple[str, str]:
    """Helper: create job → upload CSV → ingest → return (job_id, file_id).

    After this, job is in qa_running state.
    """
    meter_id = f"QA_API_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Statistik"],
    })
    job_id = job_resp.json()["id"]

    # Generate 24-row CSV (6 hours of 15-min data)
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
        files={"file": ("qa_test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest → job goes to qa_running
    ingest_resp = await client.post("/api/v1/ingest", json={
        "job_id": job_id, "file_id": file_id,
    })
    assert ingest_resp.status_code == 202, f"Ingest failed: {ingest_resp.json()}"

    return job_id, file_id


@pytest.mark.asyncio
async def test_post_qa_returns_202(client: AsyncClient) -> None:
    """POST /qa with valid job in qa_running returns 202."""
    job_id, _ = await _ingest_job(client)

    resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert resp.status_code == 202
    data = resp.json()
    assert data["checks_completed"] == 9
    assert data["overall_status"] in ("ok", "warn", "error")


@pytest.mark.asyncio
async def test_post_qa_invalid_job_returns_404(client: AsyncClient) -> None:
    """POST /qa with nonexistent job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.post("/api/v1/qa", json={"job_id": fake})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_qa_wrong_status_returns_409(client: AsyncClient) -> None:
    """POST /qa on job not in qa_running returns 409."""
    # Create job but don't ingest (still pending)
    meter_id = f"QA_PEND_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={"meter_id": meter_id})
    job_id = job_resp.json()["id"]

    resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_qa_status(client: AsyncClient) -> None:
    """GET /qa/{job_id}/status returns status after QA run."""
    job_id, _ = await _ingest_job(client)
    await client.post("/api/v1/qa", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/qa/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checks_completed"] == 9
    assert data["overall_status"] is not None


@pytest.mark.asyncio
async def test_get_qa_report(client: AsyncClient) -> None:
    """GET /qa/{job_id}/report returns full report with 9 findings."""
    job_id, _ = await _ingest_job(client)
    await client.post("/api/v1/qa", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/qa/{job_id}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["findings"]) == 9
    assert data["overall_status"] in ("ok", "warn", "error")

    # Verify check names
    check_names = {f["check_name"] for f in data["findings"]}
    assert "interval_completeness" in check_names
    assert "peak_load" in check_names
    assert "hourly_weekday_profile" in check_names


@pytest.mark.asyncio
async def test_get_qa_report_404_no_findings(client: AsyncClient) -> None:
    """GET /qa/{job_id}/report without QA run returns 404."""
    job_id, _ = await _ingest_job(client)
    resp = await client.get(f"/api/v1/qa/{job_id}/report")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_qa_findings(client: AsyncClient) -> None:
    """GET /qa/{job_id}/findings returns all findings."""
    job_id, _ = await _ingest_job(client)
    await client.post("/api/v1/qa", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/qa/{job_id}/findings")
    assert resp.status_code == 200
    findings = resp.json()
    assert len(findings) == 9
    # Check ordered by check_id
    check_ids = [f["check_id"] for f in findings]
    assert check_ids == sorted(check_ids)


@pytest.mark.asyncio
async def test_get_qa_profile(client: AsyncClient) -> None:
    """GET /qa/{job_id}/profile returns hourly+weekday arrays."""
    job_id, _ = await _ingest_job(client)
    await client.post("/api/v1/qa", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/qa/{job_id}/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["hourly_profile"]) == 24
    assert len(data["weekday_profile"]) == 7


@pytest.mark.asyncio
async def test_get_qa_profile_404(client: AsyncClient) -> None:
    """GET /qa/{job_id}/profile without QA run returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/qa/{fake}/profile")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_config_get(client: AsyncClient) -> None:
    """GET /admin/config returns default thresholds."""
    resp = await client.get("/api/v1/admin/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["min_completeness_pct"] == 95.0
    assert data["top_n_peaks"] == 10


@pytest.mark.asyncio
async def test_admin_config_put(client: AsyncClient) -> None:
    """PUT /admin/config updates thresholds."""
    resp = await client.put("/api/v1/admin/config", json={
        "min_kw": 0.0,
        "max_kw": 5000.0,
        "max_jump_kw": 2500.0,
        "top_n_peaks": 5,
        "min_completeness_pct": 90.0,
        "max_gap_duration_min": 120,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_kw"] == 5000.0
    assert data["top_n_peaks"] == 5

    # Reset for other tests
    await client.put("/api/v1/admin/config", json={
        "min_kw": 0.0,
        "max_kw": 10000.0,
        "max_jump_kw": 5000.0,
        "top_n_peaks": 10,
        "min_completeness_pct": 95.0,
        "max_gap_duration_min": 180,
    })


@pytest.mark.asyncio
async def test_qa_advances_job_to_done(client: AsyncClient) -> None:
    """After QA, Statistik-only job advances to done or warn."""
    job_id, _ = await _ingest_job(client)
    await client.post("/api/v1/qa", json={"job_id": job_id})

    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    status = job_resp.json()["status"]
    assert status in ("done", "warn"), f"Unexpected job status: {status}"
