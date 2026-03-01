"""Integration tests for multi-provider financial calculation (Phase 8)."""

import uuid
import random
from datetime import datetime, timedelta

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


async def _prepare_job_to_financial(client: AsyncClient) -> tuple[str, str, str]:
    """Create job → ingest → QA → analysis → forecast.

    Returns (job_id, horizon_start, horizon_end).
    Job ends up in financial_running state.
    """
    meter_id = f"MULTI_{uuid.uuid4().hex[:8]}"
    job_resp = await client.post("/api/v1/jobs", json={
        "meter_id": meter_id,
        "tasks": ["Aggregation"],
        "horizon_months": 1,
    })
    job_id = job_resp.json()["id"]

    # 7-day CSV
    offset = random.uniform(0.1, 0.9)
    lines = ["Datum;Uhrzeit;Wert (kWh)"]
    for day in range(7):
        d = 1 + day
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
            lines.append(f"{d:02d}.01.2025;{h:02d}:{m:02d};{val_str}")
    csv_data = ("\n".join(lines) + "\n").encode()

    upload_resp = await client.post(
        f"/api/v1/files/upload?job_id={job_id}",
        files={"file": ("multi_test.csv", csv_data, "text/csv")},
    )
    file_id = upload_resp.json()["id"]

    await client.post("/api/v1/ingest", json={"job_id": job_id, "file_id": file_id})
    await client.post("/api/v1/qa", json={"job_id": job_id})
    await client.post("/api/v1/analysis", json={"job_id": job_id})
    await client.post("/api/v1/forecasts", json={"job_id": job_id})

    job_check = await client.get(f"/api/v1/jobs/{job_id}")
    assert job_check.json()["status"] == "financial_running"

    run_resp = await client.get(f"/api/v1/forecasts/{job_id}/run")
    run_data = run_resp.json()

    return job_id, run_data["horizon_start"], run_data["horizon_end"]


def _make_hpfc_csv(start_iso: str, end_iso: str, price_base: float = 45.0) -> bytes:
    """Generate HPFC CSV covering the given horizon hourly (+ 1h buffer)."""
    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

    lines = ["ts_utc;price_mwh"]
    current = start_dt.replace(minute=0, second=0, microsecond=0)
    # Extend 1h past end to ensure delivery_end >= forecast end
    end_plus = end_dt + timedelta(hours=1)
    while current <= end_plus:
        price = price_base + (current.hour % 12) * 2.0 + random.uniform(-1, 1)
        ts_str = current.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{ts_str};{price:.2f}")
        current += timedelta(hours=1)

    return ("\n".join(lines) + "\n").encode()


async def _upload_hpfc(
    client: AsyncClient,
    start_iso: str,
    end_iso: str,
    provider_id: str,
    price_base: float = 45.0,
) -> str:
    """Upload HPFC and return snapshot_id."""
    hpfc_csv = _make_hpfc_csv(start_iso, end_iso, price_base)
    resp = await client.post(
        f"/api/v1/hpfc/upload?provider_id={provider_id}",
        files={"file": ("hpfc.csv", hpfc_csv, "text/csv")},
    )
    assert resp.status_code == 201
    return resp.json()["snapshot_id"]


@pytest.mark.asyncio
async def test_financial_multi_provider_ok_and_error(client: AsyncClient) -> None:
    """POST /financial/calculate with 3 provider_ids: 2 ok, 1 missing HPFC."""
    job_id, h_start, h_end = await _prepare_job_to_financial(client)

    # Upload HPFCs for provider_a and provider_b, NOT for provider_missing
    await _upload_hpfc(client, h_start, h_end, "provider_a", price_base=40.0)
    await _upload_hpfc(client, h_start, h_end, "provider_b", price_base=60.0)

    resp = await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "provider_ids": ["provider_a", "provider_b", "provider_missing"],
    })
    assert resp.status_code == 202
    data = resp.json()

    assert "results" in data
    results = data["results"]

    # baseline + 3 provider entries = 4 results
    assert len(results) == 4

    by_pid = {r["provider_id"]: r for r in results}

    # Baseline should be ok (any snapshot covers)
    assert by_pid["baseline"]["status"] == "ok"
    assert by_pid["baseline"]["total_cost_eur"] > 0

    # provider_a ok
    assert by_pid["provider_a"]["status"] == "ok"
    assert by_pid["provider_a"]["total_cost_eur"] > 0

    # provider_b ok (higher prices → higher cost)
    assert by_pid["provider_b"]["status"] == "ok"
    assert by_pid["provider_b"]["total_cost_eur"] > by_pid["provider_a"]["total_cost_eur"]

    # provider_missing error
    assert by_pid["provider_missing"]["status"] == "error"
    assert "provider_missing" in by_pid["provider_missing"]["error"]


@pytest.mark.asyncio
async def test_financial_baseline_always(client: AsyncClient) -> None:
    """POST /financial/calculate without provider_ids computes only baseline."""
    job_id, h_start, h_end = await _prepare_job_to_financial(client)
    await _upload_hpfc(client, h_start, h_end, "solo_provider")

    resp = await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
    })
    assert resp.status_code == 202
    data = resp.json()

    results = data["results"]
    assert len(results) == 1
    assert results[0]["provider_id"] == "baseline"
    assert results[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_financial_provider_filter(client: AsyncClient) -> None:
    """Snapshot with provider_id=X is only used for provider X."""
    job_id, h_start, h_end = await _prepare_job_to_financial(client)
    await _upload_hpfc(client, h_start, h_end, "exclusive_prov", price_base=50.0)

    resp = await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "provider_ids": ["exclusive_prov", "other_prov"],
    })
    data = resp.json()
    by_pid = {r["provider_id"]: r for r in data["results"]}

    assert by_pid["exclusive_prov"]["status"] == "ok"
    assert by_pid["other_prov"]["status"] == "error"


@pytest.mark.asyncio
async def test_provider_list_endpoint(client: AsyncClient) -> None:
    """GET /hpfc/providers returns distinct provider IDs."""
    # Upload two different providers
    uid = uuid.uuid4().hex[:6]
    lines = ["ts_utc;price_mwh", "2025-01-01 00:00:00;50.00"]
    csv = ("\n".join(lines) + "\n").encode()

    await client.post(
        f"/api/v1/hpfc/upload?provider_id=prov_{uid}_a",
        files={"file": ("a.csv", csv, "text/csv")},
    )
    await client.post(
        f"/api/v1/hpfc/upload?provider_id=prov_{uid}_b",
        files={"file": ("b.csv", csv, "text/csv")},
    )

    resp = await client.get("/api/v1/hpfc/providers")
    assert resp.status_code == 200
    data = resp.json()
    assert f"prov_{uid}_a" in data["providers"]
    assert f"prov_{uid}_b" in data["providers"]


@pytest.mark.asyncio
async def test_financial_result_per_provider(client: AsyncClient) -> None:
    """GET /financial/{job_id}/result/{provider_id} returns single provider result."""
    job_id, h_start, h_end = await _prepare_job_to_financial(client)
    await _upload_hpfc(client, h_start, h_end, "detail_prov", price_base=42.0)

    await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "provider_ids": ["detail_prov"],
    })

    # Get multi result
    resp_multi = await client.get(f"/api/v1/financial/{job_id}/result")
    assert resp_multi.status_code == 200
    multi_data = resp_multi.json()
    assert len(multi_data["results"]) == 2  # baseline + detail_prov

    # Get single provider result
    resp_single = await client.get(f"/api/v1/financial/{job_id}/result/detail_prov")
    assert resp_single.status_code == 200
    single_data = resp_single.json()
    assert single_data["provider_id"] == "detail_prov"
    assert single_data["total_cost_eur"] > 0
    assert len(single_data["rows"]) > 0

    # Non-existent provider
    resp_404 = await client.get(f"/api/v1/financial/{job_id}/result/nonexistent")
    assert resp_404.status_code == 404


@pytest.mark.asyncio
async def test_financial_export_with_provider(client: AsyncClient) -> None:
    """GET /financial/{job_id}/export?provider_id=X returns CSV for that provider."""
    job_id, h_start, h_end = await _prepare_job_to_financial(client)
    await _upload_hpfc(client, h_start, h_end, "export_prov", price_base=48.0)

    await client.post("/api/v1/financial/calculate", json={
        "job_id": job_id,
        "provider_ids": ["export_prov"],
    })

    resp = await client.get(f"/api/v1/financial/{job_id}/export?format=csv&provider_id=export_prov")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.content.decode("utf-8-sig")
    assert "ts_utc" in content
    assert "cost_eur" in content
