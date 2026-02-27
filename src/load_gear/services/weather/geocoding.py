"""PLZ Geocoding Service — German postal code to lat/lon.

Loads plz_centroids.csv into memory on first call (lazy singleton).
Provides fast lookup for ~900 PLZ entries covering all German regions.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Default path to PLZ centroids file
# __file__ = src/load_gear/services/weather/geocoding.py → parents[4] = project root
_DEFAULT_CSV = Path(__file__).resolve().parents[4] / "data" / "plz_centroids.csv"


class GeoPoint(NamedTuple):
    """Latitude/longitude pair."""

    lat: float
    lon: float
    city: str = ""


class GeocodingError(Exception):
    """Raised when geocoding fails."""


# Lazy singleton cache
_plz_cache: dict[str, GeoPoint] | None = None


def _load_cache(csv_path: Path | None = None) -> dict[str, GeoPoint]:
    """Load PLZ centroids from CSV into memory."""
    global _plz_cache
    if _plz_cache is not None:
        return _plz_cache

    path = csv_path or _DEFAULT_CSV
    if not path.exists():
        raise GeocodingError(f"PLZ centroids file not found: {path}")

    cache: dict[str, GeoPoint] = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            plz = row["plz"].strip().zfill(5)
            cache[plz] = GeoPoint(
                lat=float(row["lat"]),
                lon=float(row["lon"]),
                city=row.get("city", "").strip(),
            )

    logger.info("Loaded %d PLZ centroids from %s", len(cache), path)
    _plz_cache = cache
    return _plz_cache


def geocode_plz(plz: str, csv_path: Path | None = None) -> GeoPoint:
    """Look up lat/lon for a German postal code.

    Args:
        plz: 5-digit German postal code (e.g. "80331")
        csv_path: optional override for the centroids CSV

    Returns:
        GeoPoint(lat, lon, city)

    Raises:
        GeocodingError: if PLZ not found or file missing
    """
    cache = _load_cache(csv_path)
    normalized = plz.strip().zfill(5)

    point = cache.get(normalized)
    if point is not None:
        return point

    # Fallback: try 3-digit prefix match (coarser region)
    prefix = normalized[:3]
    candidates = [v for k, v in cache.items() if k.startswith(prefix)]
    if candidates:
        # Return centroid of matching region
        avg_lat = sum(c.lat for c in candidates) / len(candidates)
        avg_lon = sum(c.lon for c in candidates) / len(candidates)
        logger.info("PLZ %s not exact — using %d-match region centroid", plz, len(candidates))
        return GeoPoint(lat=round(avg_lat, 6), lon=round(avg_lon, 6), city="")

    # Last fallback: 2-digit prefix
    prefix2 = normalized[:2]
    candidates2 = [v for k, v in cache.items() if k.startswith(prefix2)]
    if candidates2:
        avg_lat = sum(c.lat for c in candidates2) / len(candidates2)
        avg_lon = sum(c.lon for c in candidates2) / len(candidates2)
        logger.info("PLZ %s not found — using %d-match 2-digit region", plz, len(candidates2))
        return GeoPoint(lat=round(avg_lat, 6), lon=round(avg_lon, 6), city="")

    raise GeocodingError(f"PLZ {plz} not found in centroids database")


def geocode_plz_safe(plz: str | None) -> tuple[float, float] | None:
    """Safe wrapper: returns (lat, lon) or None on failure."""
    if not plz:
        return None
    try:
        point = geocode_plz(plz)
        return (point.lat, point.lon)
    except GeocodingError:
        logger.warning("Could not geocode PLZ: %s", plz)
        return None


def reset_cache() -> None:
    """Clear the PLZ cache (for testing)."""
    global _plz_cache
    _plz_cache = None
