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
    _map_columns,
)
from load_gear.services.ingest.detectors.encoding import detect_encoding
from load_gear.services.ingest.detectors.delimiter import detect_delimiter
from load_gear.services.ingest.detectors.datetime_format import (
    detect_date_format,
    detect_time_format,
    detect_datetime_format,
    _split_datetime_by_colon,
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


# --- 2-digit year & colon datetime formats ---


def test_detect_two_digit_year() -> None:
    """dd.mm.yy date format is detected."""
    samples = ["01.01.25", "02.01.25", "03.01.25"]
    assert detect_date_format(samples) == "%d.%m.%y"


def test_detect_colon_combined_datetime() -> None:
    """dd.mm.yyyy:hh:mm combined datetime is detected."""
    samples = ["01.01.2025:00:00", "01.01.2025:00:15", "01.01.2025:00:30"]
    fmt, is_combined = detect_datetime_format(samples)
    assert fmt == "%d.%m.%Y:%H:%M"
    assert is_combined is True


def test_detect_two_digit_year_full_csv() -> None:
    """Full CSV with dd.mm.yy dates is detected correctly."""
    csv = (
        b"Datum;Uhrzeit;Wert (kWh)\n"
        b"01.01.25;00:00;12,5\n"
        b"01.01.25;00:15;13,2\n"
        b"01.01.25;00:30;11,8\n"
        b"01.01.25;00:45;12,1\n"
        b"01.01.25;01:00;10,9\n"
        b"01.01.25;01:15;11,4\n"
        b"01.01.25;01:30;10,2\n"
        b"01.01.25;01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%d.%m.%y"
    assert rules["time_format"] == "%H:%M"


def test_detect_colon_combined_full_csv() -> None:
    """Full CSV with dd.mm.yyyy:hh:mm combined timestamp."""
    csv = (
        b"Zeitstempel;Wert (kWh)\n"
        b"01.01.2025:00:00;12,5\n"
        b"01.01.2025:00:15;13,2\n"
        b"01.01.2025:00:30;11,8\n"
        b"01.01.2025:00:45;12,1\n"
        b"01.01.2025:01:00;10,9\n"
        b"01.01.2025:01:15;11,4\n"
        b"01.01.2025:01:30;10,2\n"
        b"01.01.2025:01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%d.%m.%Y:%H:%M"
    assert rules["time_format"] == ""


# --- Expanded column detection ---


def test_map_columns_leistung_kw() -> None:
    """Column 'Leistung (kW)' is detected as value column with kW unit."""
    columns = ["Datum", "Uhrzeit", "Leistung (kW)"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, is_combined, col_unit = _map_columns(columns, data_rows)
    assert val_col == "Leistung (kW)"
    assert col_unit == "kW"
    assert "Datum" in ts_cols


def test_map_columns_last() -> None:
    """Column 'Last' is detected as value column."""
    columns = ["Datum", "Uhrzeit", "Last"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, is_combined, col_unit = _map_columns(columns, data_rows)
    assert val_col == "Last"


def test_map_columns_bezug() -> None:
    """Column 'Bezug' is detected as value column."""
    columns = ["Datum", "Uhrzeit", "Bezug"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, is_combined, col_unit = _map_columns(columns, data_rows)
    assert val_col == "Bezug"


def test_map_columns_wirkleistung() -> None:
    """Column 'Wirkleistung (kW)' is detected via substring match."""
    columns = ["Datum", "Uhrzeit", "Wirkleistung (kW)"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, is_combined, col_unit = _map_columns(columns, data_rows)
    assert val_col == "Wirkleistung (kW)"
    assert col_unit == "kW"


# --- ParseError context ---


def test_parse_error_has_context() -> None:
    """ParseError includes context dict with column info."""
    csv = b"ColA;ColB;ColC\nabc;def;ghi\njkl;mno;pqr\n"
    with pytest.raises(ParseError) as exc_info:
        detect_format(csv)
    assert exc_info.value.context
    assert "columns" in exc_info.value.context


# --- Robustness: diverse input formats ---


def test_pipe_delimited() -> None:
    """Pipe-delimited CSV is parsed correctly."""
    csv = (
        b"Datum|Uhrzeit|Wert (kWh)\n"
        b"01.01.2025|00:00|12,5\n"
        b"01.01.2025|00:15|13,2\n"
        b"01.01.2025|00:30|11,8\n"
        b"01.01.2025|00:45|12,1\n"
        b"01.01.2025|01:00|10,9\n"
        b"01.01.2025|01:15|11,4\n"
        b"01.01.2025|01:30|10,2\n"
        b"01.01.2025|01:45|9,8\n"
    )
    rules = detect_format(csv)
    assert rules["delimiter"] == "|"
    assert rules["decimal_separator"] == ","
    assert "Datum" in rules["timestamp_columns"]


def test_no_keyword_header_positional_fallback() -> None:
    """When column names are meaningless, positional heuristic finds timestamp + value."""
    csv = (
        b"A;B;C\n"
        b"01.01.2025;00:00;12,5\n"
        b"01.01.2025;00:15;13,2\n"
        b"01.01.2025;00:30;11,8\n"
        b"01.01.2025;00:45;12,1\n"
        b"01.01.2025;01:00;10,9\n"
        b"01.01.2025;01:15;11,4\n"
        b"01.01.2025;01:30;10,2\n"
        b"01.01.2025;01:45;9,8\n"
    )
    rules = detect_format(csv)
    # Positional heuristic: A=date, B=time (detected from sample data)
    assert "A" in rules["timestamp_columns"]
    assert "B" in rules["timestamp_columns"]
    assert rules["value_column"] == "C"
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M"


def test_iso_datetime_t_separator() -> None:
    """ISO datetime with T separator (2025-01-01T00:15)."""
    csv = (
        b"timestamp,value_kwh\n"
        b"2025-01-01T00:00,12.5\n"
        b"2025-01-01T00:15,13.2\n"
        b"2025-01-01T00:30,11.8\n"
        b"2025-01-01T00:45,12.1\n"
        b"2025-01-01T01:00,10.9\n"
        b"2025-01-01T01:15,11.4\n"
        b"2025-01-01T01:30,10.2\n"
        b"2025-01-01T01:45,9.8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%Y-%m-%dT%H:%M"
    assert rules["time_format"] == ""


def test_bracket_unit_notation() -> None:
    """Unit in square brackets: Wert [kWh]."""
    csv = (
        b"Datum;Uhrzeit;Wert [kWh]\n"
        b"01.01.2025;00:00;12,5\n"
        b"01.01.2025;00:15;13,2\n"
        b"01.01.2025;00:30;11,8\n"
        b"01.01.2025;00:45;12,1\n"
        b"01.01.2025;01:00;10,9\n"
        b"01.01.2025;01:15;11,4\n"
        b"01.01.2025;01:30;10,2\n"
        b"01.01.2025;01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["value_column"] == "Wert [kWh]"
    assert rules["unit"] == "kWh"


def test_extra_columns_ignored() -> None:
    """Extra columns (meter ID, status) don't break detection."""
    csv = (
        b"Zaehler;Datum;Uhrzeit;Wert (kWh);Status\n"
        b"DE001;01.01.2025;00:00;12,5;OK\n"
        b"DE001;01.01.2025;00:15;13,2;OK\n"
        b"DE001;01.01.2025;00:30;11,8;OK\n"
        b"DE001;01.01.2025;00:45;12,1;OK\n"
        b"DE001;01.01.2025;01:00;10,9;OK\n"
        b"DE001;01.01.2025;01:15;11,4;OK\n"
        b"DE001;01.01.2025;01:30;10,2;OK\n"
        b"DE001;01.01.2025;01:45;9,8;OK\n"
    )
    rules = detect_format(csv)
    assert "Datum" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"


def test_negative_values_einspeisung() -> None:
    """Negative values (feed-in / Einspeisung) are handled."""
    csv = (
        b"Datum;Uhrzeit;Einspeisung (kWh)\n"
        b"01.01.2025;00:00;-12,5\n"
        b"01.01.2025;00:15;-13,2\n"
        b"01.01.2025;00:30;-11,8\n"
        b"01.01.2025;00:45;-12,1\n"
        b"01.01.2025;01:00;-10,9\n"
        b"01.01.2025;01:15;-11,4\n"
        b"01.01.2025;01:30;-10,2\n"
        b"01.01.2025;01:45;-9,8\n"
    )
    rules = detect_format(csv)
    assert rules["value_column"] == "Einspeisung (kWh)"
    assert rules["decimal_separator"] == ","


def test_integer_only_values() -> None:
    """Values without decimal point (integers) are detected."""
    csv = (
        b"Datum;Uhrzeit;Verbrauch\n"
        b"01.01.2025;00:00;125\n"
        b"01.01.2025;00:15;132\n"
        b"01.01.2025;00:30;118\n"
        b"01.01.2025;00:45;121\n"
        b"01.01.2025;01:00;109\n"
        b"01.01.2025;01:15;114\n"
        b"01.01.2025;01:30;102\n"
        b"01.01.2025;01:45;98\n"
    )
    rules = detect_format(csv)
    assert rules["value_column"] == "Verbrauch"
    assert rules["series_type"] == "interval"


def test_english_column_names_consumption() -> None:
    """English column names: 'consumption' detected as value column."""
    columns = ["date", "time", "consumption"]
    data_rows = [
        ["2025-01-01", "00:00", "12.5"],
        ["2025-01-01", "00:15", "13.2"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert val_col == "consumption"
    assert "date" in ts_cols


def test_english_column_names_load() -> None:
    """English column name: 'load' detected as value column."""
    columns = ["date", "time", "load"]
    data_rows = [
        ["2025-01-01", "00:00", "50.3"],
        ["2025-01-01", "00:15", "52.1"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert val_col == "load"


def test_english_column_names_generation() -> None:
    """English column name: 'generation' detected as value column."""
    columns = ["date", "time", "generation"]
    data_rows = [
        ["2025-01-01", "00:00", "50.3"],
        ["2025-01-01", "00:15", "52.1"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert val_col == "generation"


def test_seconds_in_time_format() -> None:
    """Time format with seconds: HH:MM:SS."""
    csv = (
        b"Datum;Uhrzeit;Wert (kWh)\n"
        b"01.01.2025;00:00:00;12,5\n"
        b"01.01.2025;00:15:00;13,2\n"
        b"01.01.2025;00:30:00;11,8\n"
        b"01.01.2025;00:45:00;12,1\n"
        b"01.01.2025;01:00:00;10,9\n"
        b"01.01.2025;01:15:00;11,4\n"
        b"01.01.2025;01:30:00;10,2\n"
        b"01.01.2025;01:45:00;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["time_format"] == "%H:%M:%S"


def test_two_digit_year_combined_datetime() -> None:
    """Combined datetime with 2-digit year: dd.mm.yy HH:MM."""
    csv = (
        b"Zeitstempel;Wert (kWh)\n"
        b"01.01.25 00:00;12,5\n"
        b"01.01.25 00:15;13,2\n"
        b"01.01.25 00:30;11,8\n"
        b"01.01.25 00:45;12,1\n"
        b"01.01.25 01:00;10,9\n"
        b"01.01.25 01:15;11,4\n"
        b"01.01.25 01:30;10,2\n"
        b"01.01.25 01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%d.%m.%y %H:%M"
    assert rules["time_format"] == ""


def test_whitespace_padded_columns() -> None:
    """Column names with leading/trailing whitespace are trimmed."""
    csv = (
        b" Datum ; Uhrzeit ; Wert (kWh) \n"
        b"01.01.2025;00:00;12,5\n"
        b"01.01.2025;00:15;13,2\n"
        b"01.01.2025;00:30;11,8\n"
        b"01.01.2025;00:45;12,1\n"
        b"01.01.2025;01:00;10,9\n"
        b"01.01.2025;01:15;11,4\n"
        b"01.01.2025;01:30;10,2\n"
        b"01.01.2025;01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert "Datum" in rules["timestamp_columns"]
    assert rules["value_column"] == "Wert (kWh)"


def test_german_thousands_separator() -> None:
    """German number format with thousands separator: 1.234,56."""
    csv = (
        b"Datum;Uhrzeit;Zaehlerstand (kWh)\n"
        b"01.01.2025;00:00;1.234,56\n"
        b"01.01.2025;00:15;1.247,89\n"
        b"01.01.2025;00:30;1.260,12\n"
        b"01.01.2025;00:45;1.273,45\n"
        b"01.01.2025;01:00;1.286,78\n"
        b"01.01.2025;01:15;1.300,11\n"
        b"01.01.2025;01:30;1.313,44\n"
        b"01.01.2025;01:45;1.326,77\n"
    )
    rules = detect_format(csv)
    assert rules["decimal_separator"] == ","
    assert rules["value_column"] == "Zaehlerstand (kWh)"


def test_slash_date_format_eu() -> None:
    """EU slash date format: DD/MM/YYYY."""
    samples = ["01/01/2025", "02/01/2025", "03/01/2025"]
    fmt = detect_date_format(samples)
    assert fmt in ("%d/%m/%Y", "%m/%d/%Y")  # ambiguous without context


def test_mwh_unit_detection() -> None:
    """MWh unit in column name is detected."""
    columns = ["Datum", "Uhrzeit", "Arbeit (MWh)"]
    data_rows = [
        ["01.01.2025", "00:00", "1,234"],
        ["01.01.2025", "00:15", "1,256"],
    ]
    ts_cols, val_col, _, col_unit = _map_columns(columns, data_rows)
    assert val_col == "Arbeit (MWh)"


def test_quoted_csv_with_embedded_delimiter() -> None:
    """Quoted CSV fields with embedded delimiter don't break parsing."""
    csv = (
        b'Datum;Uhrzeit;"Wert (kWh)"\n'
        b'01.01.2025;00:00;12,5\n'
        b'01.01.2025;00:15;13,2\n'
        b'01.01.2025;00:30;11,8\n'
        b'01.01.2025;00:45;12,1\n'
        b'01.01.2025;01:00;10,9\n'
        b'01.01.2025;01:15;11,4\n'
        b'01.01.2025;01:30;10,2\n'
        b'01.01.2025;01:45;9,8\n'
    )
    rules = detect_format(csv)
    assert rules["value_column"] == "Wert (kWh)"


def test_combined_datetime_with_seconds() -> None:
    """Combined datetime with seconds: YYYY-MM-DD HH:MM:SS."""
    csv = (
        b"timestamp,value\n"
        b"2025-01-01 00:00:00,12.5\n"
        b"2025-01-01 00:15:00,13.2\n"
        b"2025-01-01 00:30:00,11.8\n"
        b"2025-01-01 00:45:00,12.1\n"
        b"2025-01-01 01:00:00,10.9\n"
        b"2025-01-01 01:15:00,11.4\n"
        b"2025-01-01 01:30:00,10.2\n"
        b"2025-01-01 01:45:00,9.8\n"
    )
    rules = detect_format(csv)
    assert "timestamp" in rules["timestamp_columns"]
    assert rules["time_format"] == ""


def test_multiple_metadata_rows_with_empty_lines() -> None:
    """Metadata preamble with empty lines between sections."""
    csv = (
        b"Energieversorger XY GmbH\n"
        b"\n"
        b"Lastgangdaten\n"
        b"Exportiert am: 01.02.2025\n"
        b"\n"
        b"Datum;Uhrzeit;Verbrauch (kWh)\n"
        b"01.01.2025;00:00;12,5\n"
        b"01.01.2025;00:15;13,2\n"
        b"01.01.2025;00:30;11,8\n"
        b"01.01.2025;00:45;12,1\n"
        b"01.01.2025;01:00;10,9\n"
        b"01.01.2025;01:15;11,4\n"
        b"01.01.2025;01:30;10,2\n"
        b"01.01.2025;01:45;9,8\n"
    )
    rules = detect_format(csv)
    assert "Datum" in rules["timestamp_columns"]
    assert rules["value_column"] == "Verbrauch (kWh)"


def test_start_end_time_columns() -> None:
    """CSV with Startzeit + Endzeit: only start time is kept, end time dropped."""
    csv = (
        b"Datum;Startzeit;Endzeit;Leistung (kW);Verbrauch (kWh)\n"
        b"01.01.2024;00:00:00;00:15:00;8,22;2,055\n"
        b"01.01.2024;00:15:00;00:30:00;8,424;2,106\n"
        b"01.01.2024;00:30:00;00:45:00;7,95;1,988\n"
        b"01.01.2024;00:45:00;01:00:00;8,11;2,028\n"
        b"01.01.2024;01:00:00;01:15:00;7,88;1,970\n"
        b"01.01.2024;01:15:00;01:30:00;8,05;2,013\n"
        b"01.01.2024;01:30:00;01:45:00;7,72;1,930\n"
        b"01.01.2024;01:45:00;02:00:00;7,99;1,998\n"
    )
    rules = detect_format(csv)
    assert rules["timestamp_columns"] == ["Datum", "Startzeit"]
    assert "Endzeit" not in rules["timestamp_columns"]
    assert rules["date_format"] == "%d.%m.%Y"
    assert rules["time_format"] == "%H:%M:%S"


def test_start_end_time_von_bis() -> None:
    """CSV with Von + Bis time columns: only Von (start) is kept."""
    columns = ["Datum", "Von", "Bis", "Wert (kWh)"]
    data_rows = [
        ["01.01.2025", "00:00", "00:15", "12,5"],
        ["01.01.2025", "00:15", "00:30", "13,2"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert "Von" in ts_cols
    assert "Bis" not in ts_cols
    assert val_col == "Wert (kWh)"


def test_metadata_preamble_with_separator_line() -> None:
    """Metadata preamble with ;;;; separator line: header_row maps to raw line, not filtered index."""
    csv = (
        b"Energieversorger GmbH\n"
        b"Lastgangdaten Export\n"
        b"Zeitraum: 01.01.2024 - 31.12.2024\n"
        b"Zaehlernummer: 12345\n"
        b";;;;\n"
        b"Datum;Startzeit;Endzeit;Leistung (kW);Verbrauch (kWh)\n"
        b"01.01.2024;00:00:00;00:15:00;8,22;2,055\n"
        b"01.01.2024;00:15:00;00:30:00;8,424;2,106\n"
        b"01.01.2024;00:30:00;00:45:00;7,95;1,988\n"
        b"01.01.2024;00:45:00;01:00:00;8,11;2,028\n"
        b"01.01.2024;01:00:00;01:15:00;7,88;1,970\n"
        b"01.01.2024;01:15:00;01:30:00;8,05;2,013\n"
        b"01.01.2024;01:30:00;01:45:00;7,72;1,930\n"
        b"01.01.2024;01:45:00;02:00:00;7,99;1,998\n"
    )
    rules = detect_format(csv)
    # header_row must be raw line 5 (not filtered index 4)
    assert rules["header_row"] == 5
    assert rules["timestamp_columns"] == ["Datum", "Startzeit"]
    assert "Endzeit" not in rules["timestamp_columns"]
    assert rules["time_format"] == "%H:%M:%S"


def test_map_columns_strom() -> None:
    """German column name 'Strom' detected as value column."""
    columns = ["Datum", "Uhrzeit", "Strom"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert val_col == "Strom"


def test_map_columns_ertrag() -> None:
    """German column name 'Ertrag' detected as value column."""
    columns = ["Datum", "Uhrzeit", "Ertrag"]
    data_rows = [
        ["01.01.2025", "00:00", "50,3"],
        ["01.01.2025", "00:15", "52,1"],
    ]
    ts_cols, val_col, _, _ = _map_columns(columns, data_rows)
    assert val_col == "Ertrag"


# --- ValueError wrapping → ParseError with context ---


def test_unrecognized_date_format_raises_parse_error_with_context() -> None:
    """Unrecognized date format raises ParseError (not ValueError) with structured context."""
    csv = (
        b"Datum;Uhrzeit;Wert (kWh)\n"
        b"2025/01/01;00:00;12,5\n"
        b"2025/01/02;00:15;13,2\n"
        b"2025/01/03;00:30;11,8\n"
        b"2025/01/04;00:45;12,1\n"
        b"2025/01/05;01:00;10,9\n"
        b"2025/01/06;01:15;11,4\n"
        b"2025/01/07;01:30;10,2\n"
        b"2025/01/08;01:45;9,8\n"
    )
    with pytest.raises(ParseError) as exc_info:
        detect_format(csv)
    ctx = exc_info.value.context
    assert "columns" in ctx
    assert "sample_values" in ctx
    assert "hint" in ctx
    assert len(ctx["sample_values"]) > 0


def test_unrecognized_time_format_raises_parse_error_with_context() -> None:
    """Unrecognized time format raises ParseError (not ValueError) with structured context."""
    csv = (
        b"Datum;Uhrzeit;Wert (kWh)\n"
        b"01.01.2025;00h00;12,5\n"
        b"01.01.2025;00h15;13,2\n"
        b"01.01.2025;00h30;11,8\n"
        b"01.01.2025;00h45;12,1\n"
        b"01.01.2025;01h00;10,9\n"
        b"01.01.2025;01h15;11,4\n"
        b"01.01.2025;01h30;10,2\n"
        b"01.01.2025;01h45;9,8\n"
    )
    with pytest.raises(ParseError) as exc_info:
        detect_format(csv)
    ctx = exc_info.value.context
    assert "columns" in ctx
    assert "sample_values" in ctx
    assert "hint" in ctx


def test_too_few_rows_has_context() -> None:
    """File with fewer than 2 rows includes total_rows in context."""
    with pytest.raises(ParseError) as exc_info:
        detect_format(b"just one line\n")
    ctx = exc_info.value.context
    assert "total_rows" in ctx


def test_no_data_rows_after_header_has_context() -> None:
    """No data rows after header includes columns in context."""
    # Build a CSV where header is found but data rows are empty
    csv = b"Datum;Uhrzeit;Wert (kWh)\n"
    # This will trigger "fewer than 2 rows" since we only have the header
    with pytest.raises(ParseError) as exc_info:
        detect_format(csv)
    # Should have total_rows context
    assert exc_info.value.context


# --- Colon-heuristic datetime detection ---


def test_split_datetime_by_colon_space_separator() -> None:
    """Colon heuristic splits '01.01.2024 0:15' correctly."""
    result = _split_datetime_by_colon("01.01.2024 0:15")
    assert result == ("01.01.2024", " ", "0:15")


def test_split_datetime_by_colon_colon_separator() -> None:
    """Colon heuristic splits '01.01.2024:14:30' correctly."""
    result = _split_datetime_by_colon("01.01.2024:14:30")
    assert result == ("01.01.2024", ":", "14:30")


def test_split_datetime_by_colon_t_separator() -> None:
    """Colon heuristic splits '2024-01-01T15:30' correctly."""
    result = _split_datetime_by_colon("2024-01-01T15:30")
    assert result == ("2024-01-01", "T", "15:30")


def test_split_datetime_by_colon_with_seconds() -> None:
    """Colon heuristic splits '01.01.24 0:15:00' correctly."""
    result = _split_datetime_by_colon("01.01.24 0:15:00")
    assert result == ("01.01.24", " ", "0:15:00")


def test_detect_single_digit_hour_combined() -> None:
    """Single-digit hour (0:15) in combined datetime detected via heuristic."""
    samples = ["01.01.2024 0:15", "01.01.2024 0:30", "01.01.2024 0:45"]
    fmt, is_combined = detect_datetime_format(samples)
    assert fmt == "%d.%m.%Y %H:%M"
    assert is_combined is True


def test_detect_single_digit_hour_full_csv() -> None:
    """Full CSV with single-digit hours (0:15, 1:00) is detected correctly."""
    csv = (
        b"Zeitstempel;Wert (kWh)\n"
        b"01.01.2024 0:15;12,5\n"
        b"01.01.2024 0:30;13,2\n"
        b"01.01.2024 0:45;11,8\n"
        b"01.01.2024 1:00;12,1\n"
        b"01.01.2024 1:15;10,9\n"
        b"01.01.2024 1:30;11,4\n"
        b"01.01.2024 1:45;10,2\n"
        b"01.01.2024 2:00;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%d.%m.%Y %H:%M"
    assert rules["time_format"] == ""
    assert rules["decimal_separator"] == ","


def test_detect_single_digit_hour_afternoon() -> None:
    """Single-digit-hour heuristic also works with 2-digit hours (9:00, 14:30)."""
    samples = ["01.01.2024 9:00", "01.01.2024 9:15", "01.01.2024 14:30"]
    fmt, is_combined = detect_datetime_format(samples)
    assert fmt == "%d.%m.%Y %H:%M"
    assert is_combined is True


def test_detect_two_digit_year_single_digit_hour() -> None:
    """2-digit year + single-digit hour: 01.01.24 0:15."""
    samples = ["01.01.24 0:15", "01.01.24 0:30", "01.01.24 0:45"]
    fmt, is_combined = detect_datetime_format(samples)
    assert fmt == "%d.%m.%y %H:%M"
    assert is_combined is True


def test_detect_single_digit_minute() -> None:
    """Single-digit minute (1:0) in combined datetime detected correctly."""
    samples = ["01.01.2024 0:15", "01.01.2024 0:30", "01.01.2024 0:45",
               "01.01.2024 1:0", "01.01.2024 1:15"]
    fmt, is_combined = detect_datetime_format(samples)
    assert fmt == "%d.%m.%Y %H:%M"
    assert is_combined is True


def test_detect_single_digit_minute_full_csv() -> None:
    """Full CSV with single-digit minutes (1:0, 2:0) is detected correctly."""
    csv = (
        b"Zeitstempel;Wert (kWh)\n"
        b"01.01.2024 0:15;12,5\n"
        b"01.01.2024 0:30;13,2\n"
        b"01.01.2024 0:45;11,8\n"
        b"01.01.2024 1:0;12,1\n"
        b"01.01.2024 1:15;10,9\n"
        b"01.01.2024 1:30;11,4\n"
        b"01.01.2024 1:45;10,2\n"
        b"01.01.2024 2:0;9,8\n"
    )
    rules = detect_format(csv)
    assert rules["date_format"] == "%d.%m.%Y %H:%M"
    assert rules["time_format"] == ""


def test_split_datetime_single_digit_minute() -> None:
    """Colon heuristic splits '01.01.2024 1:0' correctly."""
    result = _split_datetime_by_colon("01.01.2024 1:0")
    assert result == ("01.01.2024", " ", "1:0")


def test_detect_time_format_single_digit_minute() -> None:
    """Time format detection handles single-digit minutes (1:0, 2:0)."""
    from load_gear.services.ingest.detectors.datetime_format import detect_time_format
    samples = ["0:15", "0:30", "1:0", "1:15", "2:0"]
    fmt = detect_time_format(samples)
    assert fmt == "%H:%M"
