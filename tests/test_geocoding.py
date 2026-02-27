"""Unit tests for PLZ geocoding service (T-041)."""

from __future__ import annotations

import pytest

from load_gear.services.weather.geocoding import (
    GeocodingError,
    GeoPoint,
    geocode_plz,
    geocode_plz_safe,
    reset_cache,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset geocoding cache between tests."""
    reset_cache()
    yield
    reset_cache()


def test_geocode_known_plz() -> None:
    """Known PLZ returns correct city."""
    point = geocode_plz("80331")
    assert point.city == "München"
    assert 48.0 < point.lat < 48.3
    assert 11.4 < point.lon < 11.8


def test_geocode_berlin() -> None:
    """Berlin Mitte PLZ."""
    point = geocode_plz("10115")
    assert point.city == "Berlin-Mitte"
    assert 52.4 < point.lat < 52.6


def test_geocode_hamburg() -> None:
    """Hamburg PLZ."""
    point = geocode_plz("20095")
    assert point.city == "Hamburg-Mitte"
    assert 53.4 < point.lat < 53.7


def test_geocode_prefix_fallback() -> None:
    """Unknown exact PLZ falls back to 3-digit prefix region."""
    # 80999 not in exact list, but 80xxx region exists
    point = geocode_plz("80999")
    assert 47.5 < point.lat < 49.0  # Should be in Bayern
    assert point.city == ""  # Prefix match has no city


def test_geocode_two_digit_fallback() -> None:
    """Unknown 3-digit prefix falls back to 2-digit region."""
    # 13999 — 139xx not in exact list, but 13xxx region exists (Berlin-Wedding area)
    point = geocode_plz("13999")
    # Should fall back to 13xxx region
    assert 52.0 < point.lat < 53.0


def test_geocode_leading_zeros() -> None:
    """PLZ with leading zeros handled correctly."""
    point = geocode_plz("01067")
    assert point.city == "Dresden"


def test_geocode_zero_padded() -> None:
    """Short PLZ is zero-padded."""
    # "1067" → "01067"
    point = geocode_plz("1067")
    assert point.city == "Dresden"


def test_geocode_unknown_plz_raises() -> None:
    """Completely unknown PLZ region raises GeocodingError."""
    # No German PLZ starts with 00
    with pytest.raises(GeocodingError):
        geocode_plz("00000")


def test_geocode_plz_safe_valid() -> None:
    """Safe wrapper returns (lat, lon) tuple."""
    result = geocode_plz_safe("80331")
    assert result is not None
    lat, lon = result
    assert 48.0 < lat < 48.3


def test_geocode_plz_safe_none() -> None:
    """Safe wrapper returns None for None input."""
    assert geocode_plz_safe(None) is None


def test_geocode_plz_safe_empty() -> None:
    """Safe wrapper returns None for empty string."""
    assert geocode_plz_safe("") is None


def test_geocode_plz_safe_invalid() -> None:
    """Safe wrapper returns None for invalid PLZ."""
    assert geocode_plz_safe("00000") is None


def test_geopoint_named_tuple() -> None:
    """GeoPoint is a proper NamedTuple."""
    p = GeoPoint(lat=48.13, lon=11.58, city="München")
    assert p.lat == 48.13
    assert p.lon == 11.58
    assert p.city == "München"
