"""Format detection orchestrator (P2a): auto-detect file format and produce a reader profile.

Supports CSV, XLSX, and XLS files. For Excel files, cells are converted to
a uniform list[list[str]] before applying the same detection logic as CSV.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Literal

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

# Magic byte signatures
_XLSX_MAGIC = b"PK\x03\x04"
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"

# Keywords that indicate a header row (German + English energy domain)
_HEADER_KEYWORDS = {
    "datum", "uhrzeit", "wert", "date", "time", "value",
    "leistung", "verbrauch", "kwh", "kw", "mwh", "wh",
    "timestamp", "datetime", "zeitstempel", "zeit",
    "zaehlerstand", "power", "energy", "periode",
    "zählerstand", "einheit", "unit", "kanal", "channel",
    "last", "bezug", "einspeisung", "lieferung", "arbeit", "menge",
    "wirkleistung", "von", "bis",
    "startzeit", "endzeit", "beginn", "ende", "start", "end",
    "consumption", "load", "generation", "strom", "ertrag",
    "export", "import",
}


class ParseError(Exception):
    """Raised when file format cannot be determined."""

    def __init__(self, message: str, *, context: dict | None = None):
        super().__init__(message)
        self.context = context or {}


FileType = Literal["csv", "xlsx", "xls"]


def detect_file_type(raw_bytes: bytes) -> FileType:
    """Detect file type from magic bytes."""
    if raw_bytes[:4] == _XLSX_MAGIC:
        return "xlsx"
    if raw_bytes[:4] == _XLS_MAGIC:
        return "xls"
    return "csv"


def _xlsx_to_rows(raw_bytes: bytes) -> list[list[str]]:
    """Read XLSX bytes into list of string rows."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows: list[list[str]] = []
    for row in ws.iter_rows():
        str_row = [str(cell.value) if cell.value is not None else "" for cell in row]
        if any(c.strip() for c in str_row):
            rows.append(str_row)
    wb.close()
    return rows


def _xls_to_rows(raw_bytes: bytes) -> list[list[str]]:
    """Read XLS bytes into list of string rows."""
    import xlrd

    wb = xlrd.open_workbook(file_contents=raw_bytes)
    ws = wb.sheet_by_index(0)
    rows: list[list[str]] = []
    for rx in range(ws.nrows):
        str_row = [str(ws.cell_value(rx, cx)) for cx in range(ws.ncols)]
        if any(c.strip() for c in str_row):
            rows.append(str_row)
    return rows


def _csv_to_rows(
    text: str, delimiter: str
) -> tuple[list[list[str]], list[int]]:
    """Parse CSV text into list of string rows.

    Returns (rows, line_numbers) where line_numbers[i] is the original
    0-based line index for rows[i]. Empty/blank lines are skipped but
    original positions are tracked so header_row maps to raw file lines.
    """
    rows: list[list[str]] = []
    line_numbers: list[int] = []
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    for line_idx, row in enumerate(reader):
        if any(c.strip() for c in row):
            rows.append(row)
            line_numbers.append(line_idx)
    return rows, line_numbers


def _find_data_boundary(rows: list[list[str]]) -> tuple[int, int]:
    """Find the header row and data start row.

    Algorithm:
    1. Scan rows (up to 50) for the first row that looks like data:
       has a date-like cell AND a numeric cell.
    2. Search backwards from there for a header row (contains known keywords
       or >50% short non-numeric non-empty text cells).
    3. Return (header_row_idx, data_start_idx).
    """
    limit = min(len(rows), 50)
    data_start = -1

    for i in range(limit):
        row = rows[i]
        has_date = any(_looks_like_date(c) or _looks_like_datetime(c) for c in row)
        has_numeric = any(_is_numeric(c.strip()) for c in row if c.strip())
        if has_date and has_numeric:
            data_start = i
            break

    if data_start == -1:
        # No clear data row found — fall back to first row with mostly non-numeric
        return 0, 1

    # Search backwards for header row
    for i in range(data_start - 1, -1, -1):
        row = rows[i]
        non_empty = [c.strip() for c in row if c.strip()]
        if not non_empty:
            continue
        # Check for known header keywords
        lower_cells = {c.lower() for c in non_empty}
        # Also check cleaned versions (strip units like "(kWh)")
        cleaned = set()
        for c in lower_cells:
            cleaned.add(re.sub(r"\s*\(.*\)", "", c).strip())
        if cleaned & _HEADER_KEYWORDS:
            return i, data_start
        # Check if >50% are short non-numeric text (likely labels)
        short_text = sum(1 for c in non_empty if not _is_numeric(c) and len(c) < 40)
        if short_text > len(non_empty) * 0.5:
            return i, data_start

    # No header found above data — use the row just before data if it exists
    if data_start > 0:
        return data_start - 1, data_start
    return 0, 1 if len(rows) > 1 else 0


def detect_format(raw_bytes: bytes) -> dict:
    """Detect file format from raw bytes and return a rules dict.

    Supports CSV, XLSX, and XLS files.

    Returns a dict matching ReaderProfileRules fields:
      file_type, encoding, delimiter, header_row, timestamp_columns, value_column,
      date_format, time_format, decimal_separator, unit, series_type, timezone
    """
    file_type = detect_file_type(raw_bytes)

    if file_type == "xlsx":
        rows = _xlsx_to_rows(raw_bytes)
        line_numbers = list(range(len(rows)))
        encoding = "utf-8"
        delimiter = ";"  # dummy for Excel
    elif file_type == "xls":
        rows = _xls_to_rows(raw_bytes)
        line_numbers = list(range(len(rows)))
        encoding = "utf-8"
        delimiter = ";"  # dummy for Excel
    else:
        # CSV path
        encoding = detect_encoding(raw_bytes)
        try:
            text = raw_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            try:
                text = raw_bytes.decode("utf-8", errors="replace")
                encoding = "utf-8"
            except Exception as exc:
                raise ParseError("Cannot decode file with any supported encoding") from exc

        if text.startswith("\ufeff"):
            text = text[1:]

        delimiter = detect_delimiter(text)
        rows, line_numbers = _csv_to_rows(text, delimiter)

    if len(rows) < 2:
        raise ParseError("File has fewer than 2 rows (need header + at least 1 data row)")

    # Find header and data boundary (indices into filtered rows list)
    header_row_idx, data_start_idx = _find_data_boundary(rows)
    columns = [c.strip() for c in rows[header_row_idx]]
    data_rows = rows[data_start_idx:]

    # Map filtered-row index to raw line number for the normalizer
    header_row = line_numbers[header_row_idx] if header_row_idx < len(line_numbers) else 0

    if not data_rows:
        raise ParseError("No data rows found after header")

    # Column mapping
    timestamp_cols, value_col, is_combined_ts, col_unit = _map_columns(columns, data_rows)

    # Date/time format detection
    if is_combined_ts:
        ts_idx = columns.index(timestamp_cols[0])
        ts_samples = _get_column_samples_from_rows(data_rows, ts_idx)
        dt_format, _ = detect_datetime_format(ts_samples)
        date_format = dt_format
        time_format = ""
    else:
        date_idx = columns.index(timestamp_cols[0])
        date_samples = _get_column_samples_from_rows(data_rows, date_idx)
        date_format = detect_date_format(date_samples)

        if len(timestamp_cols) > 1:
            time_idx = columns.index(timestamp_cols[1])
            time_samples = _get_column_samples_from_rows(data_rows, time_idx)
            time_format = detect_time_format(time_samples)
        else:
            time_format = ""

    # Value analysis
    value_idx = columns.index(value_col)
    value_samples = _get_column_samples_from_rows(data_rows, value_idx)

    decimal_separator = detect_decimal_separator(value_samples)

    # Unit detection: prefer column-name-based detection, fall back to header scan
    if col_unit:
        unit = col_unit
    else:
        header_text = " ".join(columns)
        unit = detect_unit(header_text)

    # Series type
    parsed_values = _parse_values(value_samples, decimal_separator)
    series_type = detect_series_type(parsed_values)

    return {
        "file_type": file_type,
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


# ---------- Internal helpers ----------


def _get_column_samples_from_rows(data_rows: list[list[str]], col_idx: int) -> list[str]:
    """Extract sample values from a specific column index in parsed rows."""
    samples: list[str] = []
    for row in data_rows[:20]:
        if col_idx < len(row):
            samples.append(row[col_idx])
    return samples


def _map_columns(
    columns: list[str], data_rows: list[list[str]]
) -> tuple[list[str], str, bool, str | None]:
    """Map columns to timestamp and value roles.

    Returns (timestamp_columns, value_column, is_combined_timestamp, detected_unit).
    """
    col_lower = [c.lower().strip() for c in columns]

    ts_names = {"datum", "date", "timestamp", "zeit", "time", "datetime",
                "zeitstempel", "uhrzeit", "von", "bis", "periode",
                "startzeit", "endzeit", "beginn", "ende", "start", "end"}
    value_names = {"wert", "value", "verbrauch", "leistung", "zaehlerstand",
                   "power", "energy", "last", "bezug", "einspeisung",
                   "lieferung", "arbeit", "menge", "wirkleistung",
                   "consumption", "load", "generation", "strom", "ertrag",
                   "export", "import"}
    # Keywords that mark the END of an interval (use start column instead)
    _end_time_names = {"endzeit", "bis", "ende", "end"}

    # Unit pattern for stripping _kW, _kWh style suffixes (requires separator)
    _unit_re = re.compile(r"[\s_]+k?[wW]h?$|[\s_]+[mM][wW]h?$")

    timestamp_cols: list[str] = []
    value_col: str | None = None
    is_combined = False
    detected_unit_from_col: str | None = None

    for i, name in enumerate(col_lower):
        # Strip units aggressively: (kW), (kWh), [kW], [kWh], _kW, _kWh
        clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", name).strip()
        clean = _unit_re.sub("", clean).strip()
        if clean in ts_names:
            timestamp_cols.append(columns[i])
        elif clean in value_names or any(vn in clean for vn in value_names):
            value_col = columns[i]
            # Detect kW vs kWh from original column name
            name_upper = columns[i]
            if re.search(r"[\(\[_\s]kWh[\)\]\s]?", name_upper, re.IGNORECASE):
                detected_unit_from_col = "kWh"
            elif re.search(r"[\(\[_\s]kW[\)\]\s]?", name_upper, re.IGNORECASE):
                detected_unit_from_col = "kW"

    # --- Handle start/end time pairs (e.g., Startzeit + Endzeit) ---
    # If we have >2 timestamp columns, filter out end-time columns.
    # Also handles the case of exactly 3 cols: date + start_time + end_time.
    if len(timestamp_cols) > 2:
        # Separate date-like and time-like columns
        date_cols = []
        time_cols = []
        for tc in timestamp_cols:
            tc_lower = tc.lower().strip()
            tc_clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", tc_lower).strip()
            tc_clean = _unit_re.sub("", tc_clean).strip()
            idx = columns.index(tc)
            samples = _get_column_samples_from_rows(data_rows, idx)
            if samples and _looks_like_time(samples[0].strip()):
                time_cols.append(tc)
            else:
                date_cols.append(tc)

        if len(time_cols) >= 2:
            # Keep only start-time: remove columns matching end-time keywords
            start_times = []
            for tc in time_cols:
                tc_clean = re.sub(r"\s*[\(\[].*?[\)\]]", "", tc.lower().strip()).strip()
                tc_clean = _unit_re.sub("", tc_clean).strip()
                if tc_clean not in _end_time_names:
                    start_times.append(tc)
            # If all time cols removed or none identified, keep the first one
            if not start_times:
                start_times = [time_cols[0]]
            timestamp_cols = date_cols + start_times[:1]
            logger.info(
                "Start/end time pair detected: keeping %s, dropped end-time columns",
                timestamp_cols,
            )

    if len(timestamp_cols) == 1 and timestamp_cols[0].lower().strip() in (
        "timestamp", "datetime", "zeitstempel"
    ):
        is_combined = True
    elif len(timestamp_cols) == 1:
        sample = _get_column_samples_from_rows(
            data_rows, col_lower.index(timestamp_cols[0].lower().strip())
        )
        if sample and (" " in sample[0].strip() or re.match(
            r"\d{2}\.\d{2}\.\d{2,4}:\d", sample[0].strip()
        )):
            is_combined = True

    # Fallback: positional heuristics
    if not timestamp_cols:
        if len(columns) >= 2:
            first_samples = _get_column_samples_from_rows(data_rows, 0)
            if first_samples and _looks_like_datetime(first_samples[0]):
                timestamp_cols = [columns[0]]
                is_combined = True
            elif first_samples and _looks_like_date(first_samples[0]):
                timestamp_cols = [columns[0]]
                if len(columns) >= 3:
                    second_samples = _get_column_samples_from_rows(data_rows, 1)
                    if second_samples and _looks_like_time(second_samples[0]):
                        timestamp_cols.append(columns[1])

    if not value_col:
        for i in range(len(columns) - 1, -1, -1):
            if columns[i] not in timestamp_cols:
                samples = _get_column_samples_from_rows(data_rows, i)
                if samples and _is_numeric(samples[0].strip()):
                    value_col = columns[i]
                    break

    if not timestamp_cols:
        raise ParseError(
            "Cannot identify timestamp column(s)",
            context={"columns": columns, "hint": "No column matched timestamp keywords"},
        )
    if not value_col:
        raise ParseError(
            "Cannot identify value column",
            context={"columns": columns, "hint": "No column matched value keywords"},
        )

    return timestamp_cols, value_col, is_combined, detected_unit_from_col


def _split_line(line: str, delimiter: str) -> list[str]:
    """Split a CSV line respecting quotes."""
    reader = csv.reader(io.StringIO(line), delimiter=delimiter)
    for row in reader:
        return row
    return []


def _is_numeric(s: str) -> bool:
    """Check if a string looks numeric (with either comma or dot decimal).

    Handles:
      - Simple: 12,5 / 12.5 / 125
      - German thousands: 1.234,56 (dots as thousands, comma as decimal)
      - English thousands: 1,234.56 (commas as thousands, dot as decimal)
      - Negative: -12,5
    """
    s = s.strip()
    return bool(re.match(
        r"^-?(\d{1,3}(\.\d{3})*,\d+|\d{1,3}(,\d{3})*\.\d+|\d+([.,]\d+)?)$",
        s,
    ))


def _looks_like_date(s: str) -> bool:
    """Check if string looks like a date."""
    s = s.strip()
    return bool(re.match(r"\d{2}\.\d{2}\.\d{2,4}|\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", s))


def _looks_like_time(s: str) -> bool:
    """Check if string looks like a time."""
    s = s.strip()
    return bool(re.match(r"\d{1,2}:\d{2}(:\d{2})?", s))


def _looks_like_datetime(s: str) -> bool:
    """Check if string looks like a combined datetime."""
    s = s.strip()
    return bool(re.match(
        r"(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{2,4})[T :]\d{1,2}:\d{2}", s
    ))


def _get_column_samples(data_lines: list[str], delimiter: str, col_idx: int) -> list[str]:
    """Extract sample values from a specific column index (legacy CSV line-based)."""
    samples: list[str] = []
    for line in data_lines[:20]:
        cells = _split_line(line, delimiter)
        if col_idx < len(cells):
            samples.append(cells[col_idx])
    return samples


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
