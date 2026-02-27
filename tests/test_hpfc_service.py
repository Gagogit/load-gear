"""Unit tests for HPFC CSV parsing and validation."""

import pytest

from load_gear.services.financial.hpfc_service import HpfcError, parse_hpfc_csv, validate_hpfc


class TestParseHpfcCsv:
    """Test HPFC CSV parsing with various formats."""

    def test_semicolon_german_decimal(self) -> None:
        """Parse semicolon-delimited CSV with German decimal format."""
        csv = (
            "timestamp;price_mwh\n"
            "2025-01-01 00:00:00;45,50\n"
            "2025-01-01 01:00:00;42,30\n"
            "2025-01-01 02:00:00;38,10\n"
        ).encode()
        df = parse_hpfc_csv(csv, "test.csv")
        assert df.height == 3
        assert abs(df["price_mwh"][0] - 45.50) < 0.01

    def test_comma_delimiter_dot_decimal(self) -> None:
        """Parse comma-delimited CSV with dot decimal format."""
        csv = (
            "ts_utc,price_mwh\n"
            "2025-01-01 00:00:00,45.50\n"
            "2025-01-01 01:00:00,42.30\n"
        ).encode()
        df = parse_hpfc_csv(csv, "test.csv")
        assert df.height == 2
        assert abs(df["price_mwh"][0] - 45.50) < 0.01

    def test_german_column_names(self) -> None:
        """Parse CSV with German column names (Zeitstempel, Preis)."""
        csv = (
            "Zeitstempel;Preis\n"
            "01.01.2025 00:00;50,00\n"
            "01.01.2025 01:00;48,50\n"
        ).encode()
        df = parse_hpfc_csv(csv, "test.csv")
        assert df.height == 2
        assert abs(df["price_mwh"][0] - 50.00) < 0.01

    def test_iso_timestamps(self) -> None:
        """Parse CSV with ISO 8601 timestamps."""
        csv = (
            "ts_utc;price_mwh\n"
            "2025-01-01T00:00:00;45.50\n"
            "2025-01-01T01:00:00;42.30\n"
        ).encode()
        df = parse_hpfc_csv(csv, "test.csv")
        assert df.height == 2

    def test_missing_timestamp_column_raises(self) -> None:
        """CSV without timestamp column raises HpfcError."""
        csv = b"foo;price_mwh\n1;45.50\n"
        with pytest.raises(HpfcError, match="No timestamp column"):
            parse_hpfc_csv(csv, "bad.csv")

    def test_missing_price_column_raises(self) -> None:
        """CSV without price column raises HpfcError."""
        csv = b"ts_utc;foo\n2025-01-01 00:00:00;45.50\n"
        with pytest.raises(HpfcError, match="No price column"):
            parse_hpfc_csv(csv, "bad.csv")


class TestValidateHpfc:
    """Test HPFC data validation."""

    def test_duplicate_timestamps_raises(self) -> None:
        """Duplicate timestamps raise HpfcError."""
        csv = (
            "ts_utc;price_mwh\n"
            "2025-01-01 00:00:00;45.50\n"
            "2025-01-01 00:00:00;42.30\n"
        ).encode()
        df = parse_hpfc_csv(csv, "test.csv")
        with pytest.raises(HpfcError, match="duplicate timestamps"):
            validate_hpfc(df)
