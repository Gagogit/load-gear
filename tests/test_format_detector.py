"""Unit tests for format detection service (P2a)."""

import io
from pathlib import Path

import pytest

from load_gear.services.ingest.format_detector import (
    detect_format,
    detect_file_type,
    ParseError,
    _find_data_boundary,
    _csv_to_rows,
)
from load_gear.services.ingest.detectors.encoding import detect_encoding
from load_gear.services.ingest.detectors.delimiter import detect_delimiter
from load_gear.services.ingest.detectors.datetime_format import (
    detect_date_format,
    detect_time_format,
)
from load_gear.services.ingest.detectors.numeric import detect_decimal_separator, detect_unit
from load_gear.services.ingest.detectors.series_type import detect_series_type

FIXTURES = Path(__file__).parent / "fixtures"


# --- Encoding detection ---


def test_detect_encoding_utf8() -> None:
    data = "Datum;Uhrzeit;Wert\n01.01.2025;00:00;12,5\n".encode("utf-8")
    enc = detect_encoding(data)
    assert enc in ("utf-8", "ascii")


def test_detect_encoding_iso8859() -> None:
    data = (FIXTURES / "iso8859_german.csv").read_bytes()
    enc = detect_encoding(data)
    assert enc in ("iso-8859-1", "windows-1252", "ascii", "utf-8")


def test_detect_encoding_utf8_bom() -> None:
    data = b"\xef\xbb\xbfDatum;Wert\n01.01.2025;12.5\n"
    enc = detect_encoding(data)
    assert enc == "utf-8-sig"


# --- Delimiter detection ---


def test_detect_delimiter_semicolon() -> None:
    text = "Datum;Uhrzeit;Wert\n01.01.2025;00:00;12,5\n01.01.2025;00:15;13,2\n"
    assert detect_delimiter(text) == ";"


def test_detect_delimiter_comma() -> None:
    text = "timestamp,value_kwh\n2025-01-01 00:00,12.5\n2025-01-01 00:15,13.2\n"
    assert detect_delimiter(text) == ","


def test_detect_delimiter_tab() -> None:
    text = "date\ttime\tpower_kW\n2025-01-01\t00:00\t50.0\n2025-01-01\t00:15\t52.8\n"
    assert detect_delimiter(text) == "\t"


# --- Date format detection ---


def test_detect_date_format_german() -> None:
    samples = ["01.01.2025", "02.01.2025", "03.01.2025"]
    assert detect_date_format(samples) == "%d.%m.%Y"


def test_detect_date_format_iso() -> None:
    samples = ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert detect_date_format(samples) == "%Y-%m-%d"


def test_detect_time_format_24h() -> None:
    samples = ["00:00", "00:15", "01:30", "23:45"]
    assert detect_time_format(samples) == "%H:%M"


# --- Decimal separator ---


def test_detect_decimal_comma() -> None:
    samples = ["12,5", "13,2", "11,8", "12,1"]
    assert detect_decimal_separator(samples) == ","


def test_detect_decimal_dot() -> None:
    samples = ["12.5", "13.2", "11.8", "12.1"]
    assert detect_decimal_separator(samples) == "."


# --- Unit detection ---


def test_detect_unit_kwh() -> None:
    assert detect_unit("Wert (kWh)") == "kWh"


def test_detect_unit_kw() -> None:
    assert detect_unit("power_kW") == "kW"


def test_detect_unit_wh() -> None:
    assert detect_unit("Verbrauch (Wh)") == "Wh"


def test_detect_unit_default() -> None:
    assert detect_unit("value") == "kWh"


# --- Series type detection ---


def test_detect_interval_series() -> None:
    values = [12.5, 13.2, 11.8, 12.1, 10.9, 11.4, 10.2, 9.8]
    assert detect_series_type(values) == "interval"


def test_detect_cumulative_series() -> None:
    values = [1000.0, 1012.5, 1025.7, 1037.5, 1050.4, 1061.3, 1071.5, 1081.3]
    assert detect_series_type(values) == "cumulative"


# --- Full format detection (integration) ---


def test_detect_german_format() -> None:
    """German CSV (;, DD.MM.YYYY, , decimal) → correct profile."""
    data = (FIXTURES / "german_format.csv").read_bytes()
    rules = detect_format(data)
    assert rules["encoding"] in ("utf-8", "ascii")
    assert rules["delimiter"] == ";"
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M"
    assert rules["decimal_separator"] == ","
    assert rules["unit"] == "kWh"
    assert rules["series_type"] == "interval"
    assert rules["timezone"] == "Europe/Berlin"
    assert "Datum" in rules["timestamp_columns"]
    assert "Uhrzeit" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"
    assert rules["file_type"] == "csv"


def test_detect_iso_format() -> None:
    """ISO CSV (,, YYYY-MM-DD HH:MM, . decimal) → correct profile."""
    data = (FIXTURES / "iso_format.csv").read_bytes()
    rules = detect_format(data)
    assert rules["delimiter"] == ","
    assert "." in rules["decimal_separator"]
    assert rules["series_type"] == "interval"
    assert rules["file_type"] == "csv"


def test_detect_cumulative_format() -> None:
    """Cumulative CSV detected correctly."""
    data = (FIXTURES / "cumulative.csv").read_bytes()
    rules = detect_format(data)
    assert rules["series_type"] == "cumulative"
    assert rules["delimiter"] == ";"
    assert rules["decimal_separator"] == ","


def test_detect_tab_delimited() -> None:
    """Tab-delimited file detected correctly."""
    data = (FIXTURES / "tab_delimited.csv").read_bytes()
    rules = detect_format(data)
    assert rules["delimiter"] == "\t"
    assert rules["unit"] == "kW"


def test_detect_sample_lastgang() -> None:
    """The original sample_lastgang.csv fixture is detected correctly."""
    data = (FIXTURES / "sample_lastgang.csv").read_bytes()
    rules = detect_format(data)
    assert rules["delimiter"] == ";"
    assert rules["decimal_separator"] == ","
    assert rules["unit"] == "kWh"
    assert rules["date_format"] == "%d.%m.%Y"


def test_detect_empty_file_raises() -> None:
    """Empty or too-short file raises ParseError."""
    with pytest.raises(ParseError):
        detect_format(b"")

    with pytest.raises(ParseError):
        detect_format(b"just one line\n")


def test_detect_iso8859_encoding() -> None:
    """ISO-8859-1 encoded file is handled correctly."""
    data = (FIXTURES / "iso8859_german.csv").read_bytes()
    rules = detect_format(data)
    assert rules["delimiter"] == ";"
    assert rules["decimal_separator"] == ","


# --- File type detection ---


def test_detect_file_type_csv() -> None:
    assert detect_file_type(b"Datum;Wert\n01.01.2025;12,5\n") == "csv"


def test_detect_file_type_xlsx() -> None:
    assert detect_file_type(b"PK\x03\x04something") == "xlsx"


def test_detect_file_type_xls() -> None:
    assert detect_file_type(b"\xd0\xcf\x11\xe0something") == "xls"


# --- Data boundary detection ---


def test_find_data_boundary_simple() -> None:
    """Simple CSV without metadata → header=0, data_start=1."""
    rows = [
        ["Datum", "Uhrzeit", "Wert (kWh)"],
        ["01.01.2025", "00:00", "12,5"],
        ["01.01.2025", "00:15", "13,2"],
    ]
    header, data_start = _find_data_boundary(rows)
    assert header == 0
    assert data_start == 1


def test_find_data_boundary_with_metadata() -> None:
    """CSV with 5 metadata lines → header found at correct row."""
    rows = [
        ["Stadtwerke Musterstadt GmbH", "", ""],
        ["Lastgangdaten Export", "", ""],
        ["Zeitraum: 01.01.2025 - 31.01.2025", "", ""],
        ["Zählernummer: 1ESY1234567890", "", ""],
        ["---", "", ""],
        ["Datum", "Uhrzeit", "Wert (kWh)"],
        ["01.01.2025", "00:00", "12,5"],
        ["01.01.2025", "00:15", "13,2"],
    ]
    header, data_start = _find_data_boundary(rows)
    assert header == 5
    assert data_start == 6


# --- CSV with metadata header (integration) ---


def test_detect_csv_with_metadata_header() -> None:
    """CSV with 5 metadata lines before actual data header → correct header_row."""
    data = (FIXTURES / "german_with_header.csv").read_bytes()
    rules = detect_format(data)
    assert rules["header_row"] == 5
    assert rules["delimiter"] == ";"
    assert "Datum" in rules["timestamp_columns"]
    assert "Uhrzeit" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"
    assert rules["decimal_separator"] == ","
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M"


# --- XLSX detection (integration) ---


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


def test_detect_xlsx_format() -> None:
    """XLSX file → correct rules extracted."""
    data = _make_xlsx_bytes()
    rules = detect_format(data)
    assert rules["file_type"] == "xlsx"
    assert "Datum" in rules["timestamp_columns"]
    assert "Uhrzeit" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M"
    assert rules["decimal_separator"] == ","
    assert rules["unit"] == "kWh"
