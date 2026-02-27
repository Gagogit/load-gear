"""Integration tests for HPFC API endpoints (P6)."""

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


def _make_hpfc_csv(hours: int = 24, start_date: str = "2025-02-01") -> bytes:
    """Generate a simple HPFC CSV with hourly prices."""
    lines = ["ts_utc;price_mwh"]
    for h in range(hours):
        day_offset = h // 24
        hour = h % 24
        d = int(start_date.split("-")[2]) + day_offset
        month = start_date.split("-")[1]
        year = start_date.split("-")[0]
        price = 40.0 + (h % 12) * 2.5
        lines.append(f"{year}-{month}-{d:02d} {hour:02d}:00:00;{price:.2f}")
    return ("\n".join(lines) + "\n").encode()


@pytest.mark.asyncio
async def test_upload_hpfc_returns_201(client: AsyncClient) -> None:
    """POST /hpfc/upload with valid CSV returns 201."""
    csv_data = _make_hpfc_csv(24)
    resp = await client.post(
        "/api/v1/hpfc/upload?provider_id=epex&curve_type=HPFC",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["rows_imported"] == 24
    assert data["provider_id"] == "epex"
    assert "snapshot_id" in data


@pytest.mark.asyncio
async def test_upload_hpfc_invalid_csv_returns_422(client: AsyncClient) -> None:
    """POST /hpfc/upload with bad CSV returns 422."""
    csv_data = b"garbage;data\nno;valid;columns\n"
    resp = await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("bad.csv", csv_data, "text/csv")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_hpfc_snapshots(client: AsyncClient) -> None:
    """GET /hpfc returns list of snapshots."""
    # Upload one first
    csv_data = _make_hpfc_csv(24)
    await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )

    resp = await client.get("/api/v1/hpfc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_get_hpfc_snapshot(client: AsyncClient) -> None:
    """GET /hpfc/{snapshot_id} returns snapshot metadata."""
    csv_data = _make_hpfc_csv(24)
    upload_resp = await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )
    snapshot_id = upload_resp.json()["snapshot_id"]

    resp = await client.get(f"/api/v1/hpfc/{snapshot_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == snapshot_id
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_get_hpfc_snapshot_404(client: AsyncClient) -> None:
    """GET /hpfc/{snapshot_id} with nonexistent ID returns 404."""
    fake = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/hpfc/{fake}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_hpfc_series(client: AsyncClient) -> None:
    """GET /hpfc/{snapshot_id}/series returns price curve data."""
    csv_data = _make_hpfc_csv(24)
    upload_resp = await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )
    snapshot_id = upload_resp.json()["snapshot_id"]

    resp = await client.get(f"/api/v1/hpfc/{snapshot_id}/series")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 24
    assert len(data["rows"]) == 24
    for row in data["rows"]:
        assert "ts_utc" in row
        assert "price_mwh" in row
        assert row["price_mwh"] > 0


@pytest.mark.asyncio
async def test_get_hpfc_series_pagination(client: AsyncClient) -> None:
    """GET /hpfc/{snapshot_id}/series supports pagination."""
    csv_data = _make_hpfc_csv(48)
    upload_resp = await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )
    snapshot_id = upload_resp.json()["snapshot_id"]

    resp = await client.get(f"/api/v1/hpfc/{snapshot_id}/series?limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 10
    assert data["total"] == 48


@pytest.mark.asyncio
async def test_delete_hpfc_snapshot(client: AsyncClient) -> None:
    """DELETE /hpfc/{snapshot_id} removes snapshot and series."""
    csv_data = _make_hpfc_csv(24)
    upload_resp = await client.post(
        "/api/v1/hpfc/upload",
        files={"file": ("prices.csv", csv_data, "text/csv")},
    )
    snapshot_id = upload_resp.json()["snapshot_id"]

    # Delete
    del_resp = await client.delete(f"/api/v1/hpfc/{snapshot_id}")
    assert del_resp.status_code == 204

    # Verify gone
    get_resp = await client.get(f"/api/v1/hpfc/{snapshot_id}")
    assert get_resp.status_code == 404
