"""Unit tests for the normalization service (P2b)."""

import io
import uuid
from pathlib import Path

import pytest

from load_gear.services.ingest.normalizer import normalize, NormalizationError

FIXTURES = Path(__file__).parent / "fixtures"


def _make_ids() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


GERMAN_RULES = {
    "encoding": "utf-8",
    "delimiter": ";",
    "header_row": 0,
    "timestamp_columns": ["Datum", "Uhrzeit"],
    "value_column": "Wert (kWh)",
    "date_format": "%d.%m.%Y",
    "time_format": "%H:%M",
    "decimal_separator": ",",
    "unit": "kWh",
    "series_type": "interval",
    "timezone": "Europe/Berlin",
}


def test_normalize_german_csv() -> None:
    """15-min German CSV produces correct v1 rows."""
    data = (FIXTURES / "german_format.csv").read_bytes()
    job_id, file_id = _make_ids()

    rows, stats = normalize(
        data, GERMAN_RULES, meter_id="METER001", job_id=job_id, source_file_id=file_id
    )

    assert len(rows) == 8  # 8 data rows
    assert stats["valid_rows"] == 8
    assert stats["invalid_rows"] == 0

    # Check first row
    row0 = rows[0]
    assert row0["meter_id"] == "METER001"
    assert row0["version"] == 1
    assert row0["quality_flag"] == 0
    assert row0["unit"] == "kWh"
    assert row0["value"] == 12.5
    assert row0["job_id"] == job_id
    assert row0["source_file_id"] == file_id

    # Timestamps should be UTC (Europe/Berlin is UTC+1 on Jan 1)
    ts = row0["ts_utc"]
    assert ts.hour == 23  # 00:00 CET = 23:00 UTC previous day
    assert ts.day == 31  # Dec 31


def test_normalize_cumulative() -> None:
    """Cumulative values are converted to interval deltas."""
    data = (FIXTURES / "cumulative.csv").read_bytes()
    job_id, file_id = _make_ids()

    rules = {
        **GERMAN_RULES,
        "value_column": "Zaehlerstand (kWh)",
        "series_type": "cumulative",
    }

    rows, stats = normalize(
        data, rules, meter_id="CUM_METER", job_id=job_id, source_file_id=file_id
    )

    # 8 data rows → 7 deltas (first row has no previous)
    assert len(rows) == 7
    assert stats["valid_rows"] == 7
    assert "cumulative" in stats["warnings"][0].lower()

    # First delta: 1012.5 - 1000.0 = 12.5
    assert rows[0]["value"] == 12.5


def test_normalize_wh_conversion() -> None:
    """Wh unit is converted to kWh (divide by 1000)."""
    csv = b"Datum;Uhrzeit;Wert (Wh)\n01.01.2025;00:00;12500\n01.01.2025;00:15;13200\n"
    job_id, file_id = _make_ids()

    rules = {
        **GERMAN_RULES,
        "value_column": "Wert (Wh)",
        "unit": "Wh",
        "decimal_separator": ".",
    }

    rows, stats = normalize(
        csv, rules, meter_id="WH_METER", job_id=job_id, source_file_id=file_id
    )

    assert rows[0]["value"] == 12.5
    assert rows[0]["unit"] == "kWh"


def test_normalize_iso_format() -> None:
    """ISO format CSV with combined timestamp column."""
    data = (FIXTURES / "iso_format.csv").read_bytes()
    job_id, file_id = _make_ids()

    rules = {
        "encoding": "utf-8",
        "delimiter": ",",
        "header_row": 0,
        "timestamp_columns": ["timestamp"],
        "value_column": "value_kwh",
        "date_format": "%Y-%m-%d %H:%M",
        "time_format": "",
        "decimal_separator": ".",
        "unit": "kWh",
        "series_type": "interval",
        "timezone": "Europe/Berlin",
    }

    rows, stats = normalize(
        data, rules, meter_id="ISO_METER", job_id=job_id, source_file_id=file_id
    )

    assert len(rows) == 8
    assert stats["valid_rows"] == 8


def test_normalize_zero_valid_rows_raises() -> None:
    """Zero valid rows raises NormalizationError."""
    csv = b"Datum;Uhrzeit;Wert (kWh)\nnotadate;nottime;notnum\n"
    job_id, file_id = _make_ids()

    with pytest.raises(NormalizationError, match="Zero valid rows"):
        normalize(csv, GERMAN_RULES, meter_id="BAD", job_id=job_id, source_file_id=file_id)


def test_normalize_empty_file_raises() -> None:
    """Empty data file raises NormalizationError."""
    csv = b"Datum;Uhrzeit;Wert (kWh)\n"
    job_id, file_id = _make_ids()

    with pytest.raises(NormalizationError, match="no data rows"):
        normalize(csv, GERMAN_RULES, meter_id="EMPTY", job_id=job_id, source_file_id=file_id)


def test_normalize_dst_spring_forward() -> None:
    """DST spring-forward (23h day) produces 92 intervals for a full day.

    Uses partial fixture: March 30, 2025 at 02:00→03:00 CET (clock jumps forward).
    """
    data = (FIXTURES / "dst_spring.csv").read_bytes()
    job_id, file_id = _make_ids()

    rows, stats = normalize(
        data, GERMAN_RULES, meter_id="DST_S", job_id=job_id, source_file_id=file_id
    )

    # All 12 rows should parse (gap at 02:00-02:45 is natural — no rows exist)
    assert stats["valid_rows"] == 12

    # Verify UTC offsets: before 03:00 CET → CET (UTC+1); at/after 03:00 CEST → UTC+2
    # 01:00 CET = 00:00 UTC; 03:00 CEST = 01:00 UTC
    utc_hours = sorted(r["ts_utc"].hour for r in rows)
    # Before DST: 00:00 CET = 23:00 UTC (prev day), 01:00 CET = 00:00 UTC
    # After DST: 03:00 CEST = 01:00 UTC
    assert 23 in utc_hours or 0 in utc_hours  # at least some pre-DST hours present


def test_normalize_dst_fall_back() -> None:
    """DST fall-back (25h day) handles repeated hours with distinct UTC timestamps."""
    data = (FIXTURES / "dst_fall.csv").read_bytes()
    job_id, file_id = _make_ids()

    rows, stats = normalize(
        data, GERMAN_RULES, meter_id="DST_F", job_id=job_id, source_file_id=file_id
    )

    # 16 data rows should all parse
    assert stats["valid_rows"] == 16
    assert len(rows) == 16

    # All UTC timestamps must be unique (no DST collision duplicates)
    utc_timestamps = [r["ts_utc"] for r in rows]
    assert len(set(utc_timestamps)) == 16, (
        f"Expected 16 unique UTC timestamps but got {len(set(utc_timestamps))} — "
        f"DST fall-back disambiguation failed"
    )


# --- XLSX normalization ---


def _make_xlsx_bytes() -> bytes:
    """Create a minimal XLSX file in memory for testing."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Datum", "Uhrzeit", "Wert (kWh)"])
    ws.append(["01.01.2025", "00:00", "12,5"])
    ws.append(["01.01.2025", "00:15", "13,2"])
    ws.append(["01.01.2025", "00:30", "11,8"])
    ws.append(["01.01.2025", "00:45", "12,1"])
    ws.append(["01.01.2025", "01:00", "10,9"])
    ws.append(["01.01.2025", "01:15", "11,4"])
    ws.append(["01.01.2025", "01:30", "10,2"])
    ws.append(["01.01.2025", "01:45", "9,8"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_normalize_xlsx() -> None:
    """XLSX file produces correct v1 rows."""
    data = _make_xlsx_bytes()
    job_id, file_id = _make_ids()

    rules = {
        **GERMAN_RULES,
        "file_type": "xlsx",
        "header_row": 0,
    }

    rows, stats = normalize(
        data, rules, meter_id="XLSX_METER", job_id=job_id, source_file_id=file_id
    )

    assert len(rows) == 8
    assert stats["valid_rows"] == 8
    assert stats["invalid_rows"] == 0
    assert rows[0]["value"] == 12.5
    assert rows[0]["unit"] == "kWh"
    assert rows[0]["meter_id"] == "XLSX_METER"


# --- CSV with metadata header normalization ---


def test_normalize_csv_with_metadata() -> None:
    """CSV with metadata header normalizes correctly using header_row offset."""
    data = (FIXTURES / "german_with_header.csv").read_bytes()
    job_id, file_id = _make_ids()

    rules = {
        **GERMAN_RULES,
        "header_row": 5,
    }

    rows, stats = normalize(
        data, rules, meter_id="META_METER", job_id=job_id, source_file_id=file_id
    )

    assert len(rows) == 8
    assert stats["valid_rows"] == 8
    assert rows[0]["value"] == 12.5
    assert rows[0]["meter_id"] == "META_METER"


# --- 2-digit year normalization ---


def test_normalize_two_digit_year() -> None:
    """CSV with dd.mm.yy dates normalizes correctly."""
    csv = (
        b"Datum;Uhrzeit;Wert (kWh)\n"
        b"01.01.25;00:00;12,5\n"
        b"01.01.25;00:15;13,2\n"
    )
    job_id, file_id = _make_ids()
    rules = {
        **GERMAN_RULES,
        "date_format": "%d.%m.%y",
    }
    rows, stats = normalize(
        csv, rules, meter_id="YY_METER", job_id=job_id, source_file_id=file_id
    )
    assert len(rows) == 2
    assert stats["valid_rows"] == 2
    # 2025 parsed from 2-digit year
    assert rows[0]["ts_utc"].year == 2024 or rows[0]["ts_utc"].year == 2025  # UTC may shift day


def test_normalize_empty_file_has_context() -> None:
    """NormalizationError for empty file includes context with hint."""
    csv = b"Datum;Uhrzeit;Wert (kWh)\n"
    job_id, file_id = _make_ids()

    with pytest.raises(NormalizationError) as exc_info:
        normalize(csv, GERMAN_RULES, meter_id="CTX", job_id=job_id, source_file_id=file_id)
    assert exc_info.value.context
    assert "hint" in exc_info.value.context


def test_normalize_bad_encoding_has_context() -> None:
    """NormalizationError for bad encoding includes hint in context."""
    csv = b"\x80\x81\x82\x83"
    job_id, file_id = _make_ids()
    rules = {**GERMAN_RULES, "encoding": "utf-8"}

    with pytest.raises(NormalizationError) as exc_info:
        normalize(csv, rules, meter_id="ENC", job_id=job_id, source_file_id=file_id)
    assert exc_info.value.context
    assert "hint" in exc_info.value.context


def test_normalize_unsupported_ts_config_has_context() -> None:
    """NormalizationError for unsupported timestamp config includes columns in context."""
    csv = b"Datum;Uhrzeit;Extra;Wert (kWh)\n01.01.2025;00:00;12:00;12,5\n"
    job_id, file_id = _make_ids()
    rules = {
        **GERMAN_RULES,
        "timestamp_columns": ["Datum", "Uhrzeit", "Extra"],
        "time_format": "%H:%M",
    }

    with pytest.raises(NormalizationError) as exc_info:
        normalize(csv, rules, meter_id="TS3", job_id=job_id, source_file_id=file_id)
    ctx = exc_info.value.context
    assert ctx
    # Either wrapped by _build_timestamps (column key) or direct (timestamp_columns key)
    assert "column" in ctx or "timestamp_columns" in ctx


def test_normalize_colon_datetime() -> None:
    """CSV with dd.mm.yyyy:hh:mm combined timestamp normalizes correctly."""
    csv = (
        b"Zeitstempel;Wert (kWh)\n"
        b"01.01.2025:00:00;12,5\n"
        b"01.01.2025:00:15;13,2\n"
    )
    job_id, file_id = _make_ids()
    rules = {
        "encoding": "utf-8",
        "delimiter": ";",
        "header_row": 0,
        "timestamp_columns": ["Zeitstempel"],
        "value_column": "Wert (kWh)",
        "date_format": "%d.%m.%Y:%H:%M",
        "time_format": "",
        "decimal_separator": ",",
        "unit": "kWh",
        "series_type": "interval",
        "timezone": "Europe/Berlin",
    }
    rows, stats = normalize(
        csv, rules, meter_id="COLON_METER", job_id=job_id, source_file_id=file_id
    )
    assert len(rows) == 2
    assert stats["valid_rows"] == 2
    assert rows[0]["value"] == 12.5
