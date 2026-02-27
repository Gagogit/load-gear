"""Unit tests for DWD CDC import service (T-035)."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pytest

from load_gear.services.weather.dwd_import import (
    DWD_PARAMS,
    JCMS_TO_WM2,
    _merge_param_dfs,
    _parse_dwd_zip,
)


def _make_dwd_zip(
    value_col: str = "TT_TU",
    rows: int = 24,
    start_hour: int = 0,
    station_id: str = "00433",
) -> bytes:
    """Create a minimal DWD-style ZIP with a produkt CSV."""
    lines = [f"STATIONS_ID;MESS_DATUM; {value_col} ;eor"]
    for i in range(rows):
        h = start_hour + i
        ts = f"2025010{1 + h // 24:01d}{h % 24:02d}"
        val = 5.0 + i * 0.3
        lines.append(f"{station_id};{ts}; {val:.1f} ;eor")
    csv_content = "\n".join(lines).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"produkt_tu_stunde_{station_id}.txt", csv_content)
    return buf.getvalue()


def test_parse_dwd_zip_air_temperature() -> None:
    """Parse a DWD air_temperature ZIP → Polars DataFrame."""
    cfg = DWD_PARAMS["air_temperature"]
    zip_bytes = _make_dwd_zip(value_col="TT_TU", rows=24)
    df = _parse_dwd_zip(zip_bytes, cfg)

    assert len(df) == 24
    assert "ts_utc" in df.columns
    assert "value" in df.columns
    # Values should be raw temps (no conversion)
    assert df["value"][0] == pytest.approx(5.0, abs=0.1)


def test_parse_dwd_zip_solar_conversion() -> None:
    """Parse DWD solar ZIP → values converted from J/cm² to W/m²."""
    cfg = DWD_PARAMS["solar"]
    zip_bytes = _make_dwd_zip(value_col="FG_LBERG", rows=10)
    df = _parse_dwd_zip(zip_bytes, cfg)

    assert len(df) == 10
    # First value: 5.0 J/cm² → 5.0 * JCMS_TO_WM2
    expected = 5.0 * JCMS_TO_WM2
    assert df["value"][0] == pytest.approx(expected, rel=0.01)


def test_parse_dwd_zip_filters_missing_values() -> None:
    """DWD -999 values should be filtered out."""
    lines = [
        "STATIONS_ID;MESS_DATUM; TT_TU ;eor",
        "00433;2025010100; 5.0 ;eor",
        "00433;2025010101; -999.0 ;eor",
        "00433;2025010102; 8.0 ;eor",
    ]
    csv_content = "\n".join(lines).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("produkt_tu_stunde_00433.txt", csv_content)

    cfg = DWD_PARAMS["air_temperature"]
    df = _parse_dwd_zip(buf.getvalue(), cfg)

    assert len(df) == 2  # -999 row filtered


def test_parse_dwd_zip_no_produkt_file() -> None:
    """ZIP without produkt file raises DWDImportError."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "nothing here")

    from load_gear.services.weather.dwd_import import DWDImportError

    cfg = DWD_PARAMS["air_temperature"]
    with pytest.raises(DWDImportError, match="No produkt"):
        _parse_dwd_zip(buf.getvalue(), cfg)


def test_parse_dwd_zip_missing_column() -> None:
    """ZIP with wrong column name raises DWDImportError."""
    lines = ["STATIONS_ID;MESS_DATUM; WRONG_COL ;eor", "00433;2025010100; 5.0 ;eor"]
    csv_content = "\n".join(lines).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("produkt_tu_stunde_00433.txt", csv_content)

    from load_gear.services.weather.dwd_import import DWDImportError

    cfg = DWD_PARAMS["air_temperature"]
    with pytest.raises(DWDImportError, match="Column TT_TU not found"):
        _parse_dwd_zip(buf.getvalue(), cfg)


def test_merge_param_dfs_combines_temp_and_solar() -> None:
    """Merge temperature and solar DataFrames into observation rows."""
    import polars as pl

    temp_df = pl.DataFrame({
        "ts_utc": [datetime(2025, 1, 1, h, tzinfo=timezone.utc) for h in range(3)],
        "value": [5.0, 6.0, 7.0],
    })
    solar_df = pl.DataFrame({
        "ts_utc": [datetime(2025, 1, 1, h, tzinfo=timezone.utc) for h in range(3)],
        "value": [100.0, 200.0, 300.0],
    })

    rows = _merge_param_dfs(
        {"air_temperature": temp_df, "solar": solar_df},
        "00433",
    )

    assert len(rows) == 3
    assert rows[0]["station_id"] == "00433"
    assert rows[0]["source"] == "dwd_cdc"
    assert rows[0]["temp_c"] == 5.0
    assert rows[0]["ghi_wm2"] == 100.0


def test_merge_param_dfs_empty() -> None:
    """Empty input returns empty list."""
    rows = _merge_param_dfs({}, "00433")
    assert rows == []
