"""Integration tests for Analysis & Imputation API endpoints (P4)."""

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


async def _prepare_for_analysis(client: AsyncClient) -> str:
    """Helper: create job → upload → ingest → QA → return job_id in analysis_running state."""
    meter_id = f"ANA_API_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Imputation"],  # Requires P4
    })
    job_id = job_resp.json()["id"]

    # Generate 96-row CSV (full day)
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for i in range(96):
        h, m = divmod(i * 15, 60)
        hour = h + m / 60.0
        if hour < 6:
            val = 5.0 + random.uniform(0, 2)
        elif hour < 18:
            val = 12.0 + random.uniform(0, 5)
        else:
            val = 7.0 + random.uniform(0, 3)
        val += offset
        val_str = f"{val:.1f}".replace(".", ",")
        lines.append(f"01.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("analysis_test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    # Ingest → qa_running
    ingest_resp = await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    assert ingest_resp.status_code == 202

    # QA → analysis_running (because tasks=["Imputation"])
    qa_resp = await client.post("/api/v1/qa", json={"job_id": job_id})
    assert qa_resp.status_code == 202

    # Verify job is now in analysis_running
    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "analysis_running", (
        f"Expected analysis_running, got {job_check.json()['status']}"
    )

    return job_id


@pytest.mark.asyncio
async def test_post_analysis_returns_202(client: AsyncClient) -> None:
    """POST /analysis with valid job in analysis_running returns 202."""
    job_id = await _prepare_for_analysis(client)

    resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert resp.status_code == 202
    data = resp.json()
    assert data["v2_rows"] >= 1
    assert data["day_types"] >= 1


@pytest.mark.asyncio
async def test_post_analysis_invalid_job_returns_404(client: AsyncClient) -> None:
    """POST /analysis with nonexistent job returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.post("/api/v1/analysis", json={"job_id": fake})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_analysis_wrong_status_returns_409(client: AsyncClient) -> None:
    """POST /analysis on pending job returns 409."""
    meter_id = f"ANA_PEND_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={"meter_id": meter_id})
    job_id = job_resp.json()["id"]

    resp = await client.post("/api/v1/analysis", json={"job_id": job_id})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_analysis_status(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/status returns status after analysis."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("done", "forecast_running")


@pytest.mark.asyncio
async def test_get_analysis_profile(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/profile returns day fingerprints."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/profile")
    assert resp.status_code == 200
    data = resp.json()
    assert data["day_fingerprints"] is not None
    assert len(data["day_fingerprints"]) >= 1
    # Check fingerprint structure
    for label, fp in data["day_fingerprints"].items():
        assert len(fp["avg_kw"]) == 24
        assert fp["count"] >= 1


@pytest.mark.asyncio
async def test_get_analysis_profile_404(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/profile without analysis returns 404."""
    job_id = await _prepare_for_analysis(client)
    resp = await client.get(f"/api/v1/analysis/{job_id}/profile")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_day_labels(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/day-labels returns classification results."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/day-labels")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_weather(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/weather returns correlations (empty in v0.1)."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/weather")
    assert resp.status_code == 200
    data = resp.json()
    assert data["correlations"] is not None
    assert data["correlations"]["data_available"] is False


@pytest.mark.asyncio
async def test_get_imputation_report(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/imputation returns method summary."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/imputation")
    assert resp.status_code == 200
    data = resp.json()
    assert "method_summary" in data
    assert data["total_v2_rows"] >= 1


@pytest.mark.asyncio
async def test_get_normalized_v2(client: AsyncClient) -> None:
    """GET /analysis/{job_id}/normalized-v2 returns v2 rows."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    resp = await client.get(f"/api/v1/analysis/{job_id}/normalized-v2")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    # v2 rows
    for item in data["items"]:
        assert item["version"] == 2


@pytest.mark.asyncio
async def test_analysis_advances_job_to_done(client: AsyncClient) -> None:
    """After analysis, Imputation-only job advances to done."""
    job_id = await _prepare_for_analysis(client)
    await client.post("/api/v1/analysis", json={"job_id": job_id})

    job_resp = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    status = job_resp.json()["status"]
    assert status == "done", f"Expected done, got {status}"
