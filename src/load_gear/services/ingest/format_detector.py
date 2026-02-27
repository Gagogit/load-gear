"""Format detection orchestrator (P2a): auto-detect file format and produce a reader profile."""

from __future__ import annotations

import csv
import io
import logging
import re

from load_gear.services.ingest.detectors.encoding import detect_encoding
from load_gear.services.ingest.detectors.delimiter import detect_delimiter
from load_gear.services.ingest.detectors.datetime_format import (
    detect_date_format,
    detect_time_format,
    detect_datetime_format,
)
from load_gear.services.ingest.detectors.numeric import detect_decimal_separator, detect_unit
from load_gear.services.ingest.detectors.series_type import detect_series_type

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Raised when file format cannot be determined."""
    pass


def detect_format(raw_bytes: bytes) -> dict:
    """Detect file format from raw bytes and return a rules dict.

    Returns a dict matching ReaderProfileRules fields:
      encoding, delimiter, header_row, timestamp_columns, value_column,
      date_format, time_format, decimal_separator, unit, series_type, timezone
    """
    # 1. Encoding detection
    encoding = detect_encoding(raw_bytes)
    try:
        text = raw_bytes.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        # Fallback
        try:
            text = raw_bytes.decode("utf-8", errors="replace")
            encoding = "utf-8"
        except Exception as exc:
            raise ParseError(f"Cannot decode file with any supported encoding") from exc

    # Strip BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]

    lines = [l for l in text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        raise ParseError("File has fewer than 2 lines (need header + at least 1 data row)")

    # 2. Delimiter detection
    delimiter = detect_delimiter(text)

    # 3. Header row detection — first row with mostly non-numeric content
    header_row = _detect_header_row(lines, delimiter)
    header_line = lines[header_row]
    columns = _split_line(header_line, delimiter)

    data_lines = lines[header_row + 1:]
    if not data_lines:
        raise ParseError("No data rows found after header")

    # 4. Column mapping: find timestamp and value columns
    timestamp_cols, value_col, is_combined_ts = _map_columns(columns, data_lines, delimiter)

    # 5. Date/time format detection
    if is_combined_ts:
        ts_samples = _get_column_samples(data_lines, delimiter, columns.index(timestamp_cols[0]))
        dt_format, _ = detect_datetime_format(ts_samples)
        date_format = dt_format
        time_format = ""
    else:
        date_samples = _get_column_samples(
            data_lines, delimiter, columns.index(timestamp_cols[0])
        )
        date_format = detect_date_format(date_samples)

        if len(timestamp_cols) > 1:
            time_samples = _get_column_samples(
                data_lines, delimiter, columns.index(timestamp_cols[1])
            )
            time_format = detect_time_format(time_samples)
        else:
            time_format = ""

    # 6. Value column analysis
    value_idx = columns.index(value_col)
    value_samples = _get_column_samples(data_lines, delimiter, value_idx)

    # 7. Decimal separator
    decimal_separator = detect_decimal_separator(value_samples)

    # 8. Unit detection from header
    unit = detect_unit(header_line)

    # 9. Series type (cumulative vs interval)
    parsed_values = _parse_values(value_samples, decimal_separator)
    series_type = detect_series_type(parsed_values)

    return {
        "encoding": encoding,
        "delimiter": delimiter,
        "header_row": header_row,
        "timestamp_columns": timestamp_cols,
        "value_column": value_col,
        "date_format": date_format,
        "time_format": time_format,
        "decimal_separator": decimal_separator,
        "unit": unit,
        "series_type": series_type,
        "timezone": "Europe/Berlin",
    }


def _detect_header_row(lines: list[str], delimiter: str) -> int:
    """Find the header row index. Heuristic: first row where most cells are non-numeric."""
    for i, line in enumerate(lines[:5]):
        cells = _split_line(line, delimiter)
        non_numeric = sum(1 for c in cells if not _is_numeric(c.strip()))
        if non_numeric > len(cells) * 0.5:
            return i
    return 0


def _split_line(line: str, delimiter: str) -> list[str]:
    """Split a CSV line respecting quotes."""
    reader = csv.reader(io.StringIO(line), delimiter=delimiter)
    for row in reader:
        return row
    return []


def _is_numeric(s: str) -> bool:
    """Check if a string looks numeric (with either comma or dot decimal)."""
    s = s.strip()
    return bool(re.match(r"^-?\d+([.,]\d+)?$", s))


def _map_columns(
    columns: list[str], data_lines: list[str], delimiter: str
) -> tuple[list[str], str, bool]:
    """Map columns to timestamp and value roles.

    Returns (timestamp_columns, value_column, is_combined_timestamp).
    """
    col_lower = [c.lower().strip() for c in columns]

    # Known timestamp column names
    ts_names = {"datum", "date", "timestamp", "zeit", "time", "datetime", "zeitstempel", "uhrzeit"}
    value_names = {"wert", "value", "verbrauch", "leistung", "zaehlerstand", "power", "energy"}

    timestamp_cols: list[str] = []
    value_col: str | None = None
    is_combined = False

    # Try to find named columns
    for i, name in enumerate(col_lower):
        clean = re.sub(r"\s*\(.*\)", "", name).strip()
        if clean in ts_names:
            timestamp_cols.append(columns[i].strip())
        elif any(vn in clean for vn in value_names):
            value_col = columns[i].strip()

    # If we found a combined datetime column
    if len(timestamp_cols) == 1 and timestamp_cols[0].lower().strip() in (
        "timestamp", "datetime", "zeitstempel"
    ):
        is_combined = True
    elif len(timestamp_cols) == 1:
        # Check if the single column contains both date and time
        sample = _get_column_samples(data_lines, delimiter, col_lower.index(timestamp_cols[0].lower().strip()))
        if sample and " " in sample[0].strip():
            is_combined = True

    # Fallback: if no named columns found, use positional heuristics
    if not timestamp_cols:
        # First column(s) are usually timestamps
        if len(columns) >= 2:
            first_samples = _get_column_samples(data_lines, delimiter, 0)
            if first_samples and _looks_like_datetime(first_samples[0]):
                timestamp_cols = [columns[0].strip()]
                is_combined = True
            elif first_samples and _looks_like_date(first_samples[0]):
                timestamp_cols = [columns[0].strip()]
                if len(columns) >= 3:
                    second_samples = _get_column_samples(data_lines, delimiter, 1)
                    if second_samples and _looks_like_time(second_samples[0]):
                        timestamp_cols.append(columns[1].strip())

    if not value_col:
        # Take the last numeric column
        for i in range(len(columns) - 1, -1, -1):
            if columns[i].strip() not in timestamp_cols:
                samples = _get_column_samples(data_lines, delimiter, i)
                if samples and _is_numeric(samples[0].strip()):
                    value_col = columns[i].strip()
                    break

    if not timestamp_cols:
        raise ParseError("Cannot identify timestamp column(s)")
    if not value_col:
        raise ParseError("Cannot identify value column")

    return timestamp_cols, value_col, is_combined


def _get_column_samples(data_lines: list[str], delimiter: str, col_idx: int) -> list[str]:
    """Extract sample values from a specific column index."""
    samples: list[str] = []
    for line in data_lines[:20]:
        cells = _split_line(line, delimiter)
        if col_idx < len(cells):
            samples.append(cells[col_idx])
    return samples


def _looks_like_date(s: str) -> bool:
    """Check if string looks like a date."""
    s = s.strip()
    return bool(re.match(r"\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", s))


def _looks_like_time(s: str) -> bool:
    """Check if string looks like a time."""
    s = s.strip()
    return bool(re.match(r"\d{1,2}:\d{2}(:\d{2})?", s))


def _looks_like_datetime(s: str) -> bool:
    """Check if string looks like a combined datetime."""
    s = s.strip()
    return bool(re.match(
        r"(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4})[T ]\d{1,2}:\d{2}", s
    ))


def _parse_values(samples: list[str], decimal_separator: str) -> list[float]:
    """Parse numeric samples using detected decimal separator."""
    values: list[float] = []
    for s in samples:
        s = s.strip()
        if not s:
            continue
        if decimal_separator == ",":
            s = s.replace(".", "").replace(",", ".")
        try:
            values.append(float(s))
        except ValueError:
            continue
    return values
