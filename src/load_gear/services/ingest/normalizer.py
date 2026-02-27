"""Normalization service (P2b): parse file using reader_profile rules, produce v1 meter_reads."""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

logger = logging.getLogger(__name__)


class NormalizationError(Exception):
    """Raised when normalization fails."""
    pass


def normalize(
    raw_bytes: bytes,
    rules: dict,
    *,
    meter_id: str,
    job_id: uuid.UUID,
    source_file_id: uuid.UUID,
) -> tuple[list[dict], dict]:
    """Normalize raw file bytes into v1 meter_read rows using detected rules.

    Returns (rows, quality_stats) where:
      rows: list of dicts ready for bulk_insert
      quality_stats: {total_rows, valid_rows, invalid_rows, warnings}
    """
    encoding = rules["encoding"]
    delimiter = rules["delimiter"]
    header_row = rules.get("header_row", 0)
    timestamp_columns = rules["timestamp_columns"]
    value_column = rules["value_column"]
    date_format = rules["date_format"]
    time_format = rules.get("time_format", "")
    decimal_separator = rules["decimal_separator"]
    unit = rules["unit"]
    series_type = rules["series_type"]
    tz_name = rules.get("timezone", "Europe/Berlin")

    # Decode
    try:
        text = raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise NormalizationError(f"Cannot decode file with encoding {encoding}: {exc}") from exc

    if text.startswith("\ufeff"):
        text = text[1:]

    # Skip lines before header
    lines = text.split("\n")
    if header_row > 0:
        text = "\n".join(lines[header_row:])

    # Read with Polars
    try:
        lf = pl.read_csv(
            io.StringIO(text),
            separator=delimiter,
            has_header=True,
            infer_schema_length=0,  # read everything as string first
        ).lazy()
    except Exception as exc:
        raise NormalizationError(f"Polars CSV parsing failed: {exc}") from exc

    # Collect column names
    df = lf.collect()
    total_rows = len(df)

    if total_rows == 0:
        raise NormalizationError("File contains no data rows")

    warnings: list[str] = []

    # Build timestamp column
    try:
        df = _build_timestamps(df, timestamp_columns, date_format, time_format, tz_name)
    except Exception as exc:
        raise NormalizationError(f"Timestamp parsing failed: {exc}") from exc

    # Parse value column
    try:
        df = _parse_values(df, value_column, decimal_separator)
    except Exception as exc:
        raise NormalizationError(f"Value parsing failed: {exc}") from exc

    # Filter out rows with null timestamps or values
    before_filter = len(df)
    df = df.filter(
        pl.col("ts_utc").is_not_null() & pl.col("parsed_value").is_not_null()
    )
    invalid_rows = before_filter - len(df)
    if invalid_rows > 0:
        warnings.append(f"{invalid_rows} rows dropped due to parse errors")

    valid_rows = len(df)
    if valid_rows == 0:
        raise NormalizationError("Zero valid rows after parsing — check format rules")

    # Convert cumulative to interval if needed
    if series_type == "cumulative":
        df = _cumulative_to_interval(df)
        valid_rows = len(df)
        warnings.append("Converted cumulative values to interval deltas")

    # Normalize unit (Wh → kWh, MWh → kWh)
    target_unit = unit
    if unit == "Wh":
        df = df.with_columns(pl.col("parsed_value") / 1000.0)
        target_unit = "kWh"
        warnings.append("Converted Wh to kWh")
    elif unit == "MWh":
        df = df.with_columns(pl.col("parsed_value") * 1000.0)
        target_unit = "kWh"
        warnings.append("Converted MWh to kWh")

    # Build output rows
    job_id_str = str(job_id)
    file_id_str = str(source_file_id)

    rows: list[dict] = []
    for row in df.iter_rows(named=True):
        rows.append({
            "ts_utc": row["ts_utc"],
            "meter_id": meter_id,
            "version": 1,
            "job_id": job_id,
            "value": round(row["parsed_value"], 4),
            "unit": target_unit,
            "quality_flag": 0,
            "source_file_id": source_file_id,
        })

    quality_stats = {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "warnings": warnings,
    }

    return rows, quality_stats


def _build_timestamps(
    df: pl.DataFrame,
    timestamp_columns: list[str],
    date_format: str,
    time_format: str,
    tz_name: str,
) -> pl.DataFrame:
    """Parse and combine timestamp columns, convert to UTC."""
    tz = ZoneInfo(tz_name)

    if len(timestamp_columns) == 1 and (not time_format or time_format == ""):
        # Combined datetime column
        col_name = timestamp_columns[0]
        fmt = date_format  # already a combined format like %Y-%m-%d %H:%M
        df = df.with_columns(
            pl.col(col_name).str.strip_chars().str.strptime(
                pl.Datetime, fmt, strict=False
            ).alias("ts_local")
        )
    elif len(timestamp_columns) == 2:
        # Separate date + time columns
        date_col, time_col = timestamp_columns[0], timestamp_columns[1]
        combined_fmt = f"{date_format} {time_format}"
        df = df.with_columns(
            (pl.col(date_col).str.strip_chars() + pl.lit(" ") + pl.col(time_col).str.strip_chars())
            .str.strptime(pl.Datetime, combined_fmt, strict=False)
            .alias("ts_local")
        )
    elif len(timestamp_columns) == 1 and time_format:
        # Single date column + time in the format
        col_name = timestamp_columns[0]
        combined_fmt = f"{date_format} {time_format}"
        df = df.with_columns(
            pl.col(col_name).str.strip_chars().str.strptime(
                pl.Datetime, combined_fmt, strict=False
            ).alias("ts_local")
        )
    else:
        raise NormalizationError(
            f"Unsupported timestamp column configuration: {timestamp_columns}"
        )

    # Convert local time to UTC using Python datetime (handles DST correctly)
    ts_utc_values: list[datetime | None] = []
    for ts_local in df["ts_local"].to_list():
        if ts_local is None:
            ts_utc_values.append(None)
            continue
        # Make timezone-aware, then convert to UTC
        try:
            local_dt = ts_local.replace(tzinfo=tz)
            utc_dt = local_dt.astimezone(timezone.utc)
            ts_utc_values.append(utc_dt)
        except Exception:
            ts_utc_values.append(None)

    df = df.with_columns(
        pl.Series("ts_utc", ts_utc_values, dtype=pl.Datetime("us", "UTC"))
    )

    return df


def _parse_values(
    df: pl.DataFrame, value_column: str, decimal_separator: str
) -> pl.DataFrame:
    """Parse the value column into floats."""
    if decimal_separator == ",":
        df = df.with_columns(
            pl.col(value_column)
            .str.strip_chars()
            .str.replace_all(r"\.", "")  # remove thousands dots
            .str.replace(",", ".")
            .cast(pl.Float64, strict=False)
            .alias("parsed_value")
        )
    else:
        df = df.with_columns(
            pl.col(value_column)
            .str.strip_chars()
            .str.replace_all(",", "")  # remove thousands commas
            .cast(pl.Float64, strict=False)
            .alias("parsed_value")
        )
    return df


def _cumulative_to_interval(df: pl.DataFrame) -> pl.DataFrame:
    """Convert cumulative meter readings to interval deltas."""
    df = df.sort("ts_utc")
    df = df.with_columns(
        (pl.col("parsed_value") - pl.col("parsed_value").shift(1)).alias("parsed_value_delta")
    )
    # Drop first row (no delta) and use delta as the value
    df = df.slice(1)
    df = df.with_columns(pl.col("parsed_value_delta").alias("parsed_value"))
    df = df.drop("parsed_value_delta")
    return df
