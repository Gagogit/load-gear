"""DWD Climate Data Center (CDC) import service.

Fetches hourly weather observations from DWD open data:
- air_temperature: TT_TU (°C)
- solar: FG_LBERG (J/cm² → W/m²)

Station metadata is parsed from the Beschreibung (description) files.
"""

from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any

import httpx
import polars as pl
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.repositories import weather_observation_repo

logger = logging.getLogger(__name__)

DWD_BASE = "https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/hourly"

# DWD CDC subdirectories and their value columns
DWD_PARAMS: dict[str, dict[str, str]] = {
    "air_temperature": {
        "subdir": "air_temperature/recent",
        "value_col": "TT_TU",
        "target_col": "temp_c",
    },
    "solar": {
        "subdir": "solar",
        "value_col": "FG_LBERG",
        "target_col": "ghi_wm2",
    },
}

# Conversion: J/cm² per hour → W/m²  (1 J/cm² = 10000 J/m², over 3600s = 2.778 W/m²)
JCMS_TO_WM2 = 10_000 / 3_600


class DWDImportError(Exception):
    """Raised when DWD data fetch or parsing fails."""


async def fetch_station_catalog(
    client: httpx.AsyncClient,
    param: str = "air_temperature",
) -> pl.DataFrame:
    """Fetch and parse DWD station metadata catalog.

    Returns DataFrame with columns: station_id, lat, lon, elevation, name, state.
    """
    cfg = DWD_PARAMS.get(param)
    if cfg is None:
        raise DWDImportError(f"Unknown DWD parameter: {param}")

    url = f"{DWD_BASE}/{cfg['subdir']}"

    # Fetch directory listing to find the Beschreibung file
    resp = await client.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Find station description file link
    html = resp.text
    beschreibung_file: str | None = None
    for line in html.splitlines():
        if "Beschreibung_Stationen" in line and ".txt" in line:
            # Extract filename from href
            start = line.find('href="') + 6
            end = line.find('"', start)
            beschreibung_file = line[start:end]
            break

    if beschreibung_file is None:
        raise DWDImportError(f"Station description file not found at {url}")

    catalog_url = f"{url}/{beschreibung_file}"
    resp = await client.get(catalog_url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Parse fixed-width station catalog
    lines = resp.text.strip().splitlines()
    # Skip header lines (first 2 are header + dashes)
    data_lines = [l for l in lines[2:] if l.strip()]

    stations: list[dict[str, Any]] = []
    for line in data_lines:
        parts = line.split()
        if len(parts) < 7:
            continue
        stations.append({
            "station_id": parts[0].zfill(5),
            "elevation": float(parts[3]),
            "lat": float(parts[2]),
            "lon": float(parts[3]) if len(parts) > 3 else 0.0,
        })

    # Re-parse with proper column positions (DWD fixed-width format)
    stations = []
    for line in data_lines:
        try:
            sid = line[0:6].strip().zfill(5)
            # date_from = line[6:15].strip()
            # date_to = line[15:24].strip()
            elev = float(line[24:39].strip())
            lat = float(line[39:51].strip())
            lon = float(line[51:61].strip())
            name = line[61:102].strip()
            state = line[102:].strip() if len(line) > 102 else ""
            stations.append({
                "station_id": sid,
                "lat": lat,
                "lon": lon,
                "elevation": elev,
                "name": name,
                "state": state,
            })
        except (ValueError, IndexError):
            continue

    if not stations:
        raise DWDImportError("No stations parsed from catalog")

    return pl.DataFrame(stations)


async def fetch_station_data(
    client: httpx.AsyncClient,
    station_id: str,
    param: str = "air_temperature",
) -> pl.DataFrame:
    """Fetch recent hourly data for a single DWD station.

    Downloads the ZIP archive, extracts the CSV, returns a Polars DataFrame
    with columns: ts_utc, value (in target unit).
    """
    cfg = DWD_PARAMS.get(param)
    if cfg is None:
        raise DWDImportError(f"Unknown DWD parameter: {param}")

    sid = station_id.zfill(5)
    subdir = cfg["subdir"]
    url = f"{DWD_BASE}/{subdir}"

    # List directory to find the matching ZIP
    resp = await client.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Find ZIP file for this station
    zip_name: str | None = None
    for line in resp.text.splitlines():
        if f"_{sid}_" in line and ".zip" in line:
            start = line.find('href="') + 6
            end = line.find('"', start)
            zip_name = line[start:end]
            break

    if zip_name is None:
        raise DWDImportError(f"No ZIP found for station {sid} in {subdir}")

    zip_url = f"{url}/{zip_name}"
    logger.info("Downloading DWD data: %s", zip_url)

    resp = await client.get(zip_url, follow_redirects=True, timeout=60)
    resp.raise_for_status()

    return _parse_dwd_zip(resp.content, cfg)


def _parse_dwd_zip(zip_bytes: bytes, cfg: dict[str, str]) -> pl.DataFrame:
    """Extract and parse CSV from a DWD CDC ZIP archive."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        # Find the data file (starts with "produkt_")
        data_file: str | None = None
        for name in zf.namelist():
            if name.startswith("produkt_") and name.endswith(".txt"):
                data_file = name
                break

        if data_file is None:
            raise DWDImportError("No produkt_*.txt found in ZIP")

        csv_bytes = zf.read(data_file)

    # Parse CSV with Polars
    df = pl.read_csv(
        io.BytesIO(csv_bytes),
        separator=";",
        encoding="utf8",
        try_parse_dates=False,
        infer_schema_length=0,  # all as strings first
    )

    # Strip whitespace from column names
    df = df.rename({c: c.strip() for c in df.columns})

    value_col = cfg["value_col"]
    if value_col not in df.columns:
        raise DWDImportError(
            f"Column {value_col} not found. Available: {df.columns}"
        )

    # Parse MESS_DATUM → ts_utc (format: YYYYMMDDHH or YYYYMMDDhhmm)
    # Polars requires both hour+minute, so pad 10-char timestamps with "00"
    df = df.with_columns(
        pl.col("MESS_DATUM").str.strip_chars().alias("_raw_ts"),
    )

    df = df.with_columns(
        pl.when(pl.col("_raw_ts").str.len_chars() == 10)
        .then(pl.col("_raw_ts") + "00")  # YYYYMMDDHH → YYYYMMDDHHmm
        .otherwise(pl.col("_raw_ts"))
        .alias("_padded_ts"),
    )

    df = df.with_columns(
        pl.col("_padded_ts")
        .str.strptime(pl.Datetime, "%Y%m%d%H%M", strict=False)
        .alias("ts_local"),
    )

    # Parse value, strip whitespace, handle -999 as null
    df = df.with_columns(
        pl.col(value_col)
        .str.strip_chars()
        .cast(pl.Float64, strict=False)
        .alias("_raw_value"),
    )

    # Filter invalid values (-999 = DWD missing value marker)
    df = df.filter(pl.col("_raw_value") != -999.0)
    df = df.filter(pl.col("ts_local").is_not_null())

    # DWD timestamps are in local German time (CET/CEST) — convert to UTC
    # For recent data, DWD uses MEZ (CET = UTC+1)
    df = df.with_columns(
        (pl.col("ts_local").dt.replace_time_zone("Europe/Berlin")
         .dt.convert_time_zone("UTC"))
        .alias("ts_utc"),
    )

    target_col = cfg["target_col"]
    if target_col == "ghi_wm2":
        # Convert J/cm² → W/m²
        df = df.with_columns(
            (pl.col("_raw_value") * JCMS_TO_WM2).alias("value"),
        )
    else:
        df = df.with_columns(pl.col("_raw_value").alias("value"))

    # Select final columns
    df = df.select([
        "ts_utc",
        "value",
    ])

    return df.sort("ts_utc")


async def import_station(
    session: AsyncSession,
    station_id: str,
    lat: float,
    lon: float,
    *,
    params: list[str] | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """Import weather data for a single DWD station into the database.

    Fetches air_temperature and solar data, merges them, and inserts via
    weather_observation_repo.upsert_with_location().

    Returns dict with counts per parameter.
    """
    if params is None:
        params = ["air_temperature", "solar"]

    result_counts: dict[str, int] = {}

    async with httpx.AsyncClient() as client:
        # Fetch each parameter
        param_dfs: dict[str, pl.DataFrame] = {}
        for param in params:
            try:
                df = await fetch_station_data(client, station_id, param)
                if start is not None:
                    df = df.filter(pl.col("ts_utc") >= start)
                if end is not None:
                    df = df.filter(pl.col("ts_utc") < end)
                param_dfs[param] = df
                logger.info("Fetched %d rows for station %s / %s", len(df), station_id, param)
            except DWDImportError as exc:
                logger.warning("Skipping %s for station %s: %s", param, station_id, exc)
                result_counts[param] = 0

    # Merge temperature and solar into observation rows
    rows = _merge_param_dfs(param_dfs, station_id)

    if rows:
        count = await weather_observation_repo.upsert_with_location(
            session, rows, lat, lon
        )
        result_counts["total_inserted"] = count
    else:
        result_counts["total_inserted"] = 0

    for param, df in param_dfs.items():
        result_counts[param] = len(df)

    return result_counts


def _merge_param_dfs(
    param_dfs: dict[str, pl.DataFrame],
    station_id: str,
) -> list[dict[str, Any]]:
    """Merge per-parameter DataFrames into weather observation rows."""
    if not param_dfs:
        return []

    # Start with first parameter, join others on ts_utc
    merged: pl.DataFrame | None = None
    col_map: dict[str, str] = {}

    for param, df in param_dfs.items():
        cfg = DWD_PARAMS[param]
        target_col = cfg["target_col"]
        renamed = df.rename({"value": target_col})

        if merged is None:
            merged = renamed
        else:
            merged = merged.join(renamed, on="ts_utc", how="full", coalesce=True)
        col_map[param] = target_col

    if merged is None or len(merged) == 0:
        return []

    # Build observation dicts
    rows: list[dict[str, Any]] = []
    for row in merged.iter_rows(named=True):
        ts = row["ts_utc"]
        if ts is None:
            continue
        obs: dict[str, Any] = {
            "ts_utc": ts,
            "station_id": station_id.zfill(5),
            "source": "dwd_cdc",
            "confidence": 1.0,
        }
        # Map parameter columns
        for target in col_map.values():
            obs[target] = row.get(target)

        # Fill missing optional columns
        for col in ("temp_c", "ghi_wm2", "wind_ms", "cloud_pct"):
            if col not in obs:
                obs[col] = None

        rows.append(obs)

    return rows
