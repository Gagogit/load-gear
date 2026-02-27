"""HPFC CSV upload + management service."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import polars as pl
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import HpfcSnapshot
from load_gear.repositories import hpfc_snapshot_repo, hpfc_series_repo

logger = logging.getLogger(__name__)


class HpfcError(Exception):
    """Raised when HPFC processing fails."""
    pass


def parse_hpfc_csv(content: bytes, filename: str) -> pl.DataFrame:
    """Parse HPFC CSV into a Polars DataFrame with columns [ts_utc, price_mwh].

    Supports:
    - Semicolon and comma delimiters
    - German decimal format (comma as decimal separator)
    - Column names: ts_utc/timestamp/Zeitstempel + price_mwh/price/Preis
    """
    text = content.decode("utf-8-sig")

    # Try semicolon first, then comma
    for separator in [";", ","]:
        try:
            df = pl.read_csv(
                text.encode(),
                separator=separator,
                try_parse_dates=False,
                infer_schema_length=0,  # Read all as strings first
            )
            if len(df.columns) >= 2:
                break
        except Exception:
            continue
    else:
        raise HpfcError(f"Cannot parse HPFC CSV '{filename}': no valid delimiter found")

    # Normalize column names
    col_map: dict[str, str] = {}
    for col in df.columns:
        lower = col.strip().lower()
        if lower in ("ts_utc", "timestamp", "zeitstempel", "datum", "date", "datetime"):
            col_map[col] = "ts_utc"
        elif lower in ("price_mwh", "price", "preis", "eur_mwh", "eur/mwh"):
            col_map[col] = "price_mwh"

    if "ts_utc" not in col_map.values():
        raise HpfcError(f"No timestamp column found in '{filename}'. "
                        f"Expected: ts_utc, timestamp, Zeitstempel, datum, date. Got: {df.columns}")
    if "price_mwh" not in col_map.values():
        raise HpfcError(f"No price column found in '{filename}'. "
                        f"Expected: price_mwh, price, Preis, EUR_MWh. Got: {df.columns}")

    df = df.rename(col_map)

    # Select only needed columns
    df = df.select(["ts_utc", "price_mwh"])

    # Parse price: handle German decimal (comma → dot)
    df = df.with_columns(
        pl.col("price_mwh").str.strip_chars().str.replace(",", ".").cast(pl.Float64).alias("price_mwh")
    )

    # Parse timestamps
    ts_col = df["ts_utc"].str.strip_chars()
    parsed = None
    for fmt in [
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M:%S",
        "%d.%m.%Y %H:%M",
    ]:
        try:
            parsed = ts_col.str.to_datetime(fmt, strict=True, time_zone="UTC")
            break
        except Exception:
            continue

    if parsed is None:
        # Try Polars auto-parsing as last resort
        try:
            parsed = ts_col.str.to_datetime(strict=False, time_zone="UTC")
        except Exception:
            raise HpfcError(f"Cannot parse timestamps in '{filename}'")

    df = df.with_columns(parsed.alias("ts_utc"))

    # Drop nulls
    df = df.drop_nulls()

    if df.is_empty():
        raise HpfcError(f"No valid data rows in '{filename}'")

    return df.sort("ts_utc")


def validate_hpfc(df: pl.DataFrame) -> None:
    """Validate HPFC data: positive prices, no duplicates."""
    # Check for negative prices
    neg_count = df.filter(pl.col("price_mwh") < 0).height
    if neg_count > 0:
        logger.warning("HPFC contains %d negative prices (allowed for spot/intraday)", neg_count)

    # Check for duplicate timestamps
    dup_count = df.height - df.unique(subset=["ts_utc"]).height
    if dup_count > 0:
        raise HpfcError(f"HPFC contains {dup_count} duplicate timestamps")


async def upload_hpfc(
    session: AsyncSession,
    content: bytes,
    filename: str,
    *,
    provider_id: str = "manual",
    curve_type: str = "HPFC",
    currency: str = "EUR",
) -> dict:
    """Parse, validate, and store an HPFC CSV file.

    Returns a summary dict.
    """
    # 1. Parse CSV
    df = parse_hpfc_csv(content, filename)

    # 2. Validate
    validate_hpfc(df)

    # 3. Determine delivery range
    delivery_start = df["ts_utc"].min()
    delivery_end = df["ts_utc"].max()

    # 4. Create snapshot
    snapshot = HpfcSnapshot(
        id=uuid.uuid4(),
        provider_id=provider_id,
        snapshot_at=datetime.now(timezone.utc),
        curve_type=curve_type,
        delivery_start=delivery_start,
        delivery_end=delivery_end,
        currency=currency,
    )
    await hpfc_snapshot_repo.create(session, snapshot)

    # 5. Bulk insert series
    rows = [
        {
            "ts_utc": row["ts_utc"],
            "snapshot_id": snapshot.id,
            "price_mwh": row["price_mwh"],
        }
        for row in df.iter_rows(named=True)
    ]
    inserted = await hpfc_series_repo.bulk_insert(session, rows)

    return {
        "snapshot_id": str(snapshot.id),
        "provider_id": provider_id,
        "rows_imported": inserted,
        "delivery_start": delivery_start.isoformat(),
        "delivery_end": delivery_end.isoformat(),
    }


async def get_snapshot(session: AsyncSession, snapshot_id: uuid.UUID) -> HpfcSnapshot:
    """Get an HPFC snapshot by ID."""
    snapshot = await hpfc_snapshot_repo.get_by_id(session, snapshot_id)
    if snapshot is None:
        raise HpfcError(f"HPFC snapshot {snapshot_id} not found")
    return snapshot


async def list_snapshots(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[HpfcSnapshot], int]:
    """List all HPFC snapshots."""
    return await hpfc_snapshot_repo.list_all(session, limit=limit, offset=offset)


async def get_series(
    session: AsyncSession,
    snapshot_id: uuid.UUID,
    *,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list, int]:
    """Get HPFC price series for a snapshot (paginated)."""
    # Verify snapshot exists
    await get_snapshot(session, snapshot_id)
    return await hpfc_series_repo.get_by_snapshot_id(
        session, snapshot_id, limit=limit, offset=offset
    )


async def delete_snapshot_cascade(session: AsyncSession, snapshot_id: uuid.UUID) -> None:
    """Delete an HPFC snapshot and all its series data."""
    snapshot = await get_snapshot(session, snapshot_id)
    await hpfc_series_repo.delete_by_snapshot_id(session, snapshot_id)
    await hpfc_snapshot_repo.delete_snapshot(session, snapshot)
