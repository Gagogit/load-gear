"""Weather API fallback — BrightSky + Open-Meteo.

Used when DWD bulk data is unavailable or confidence < threshold.
Trigger logic:
  1. No DWD observations within 10 km radius for the requested time range
  2. Existing observations have avg confidence < 0.5

BrightSky is tried first (better German coverage), Open-Meteo as second fallback.
Both return hourly data that maps to the WeatherObservation model.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.repositories import weather_observation_repo

logger = logging.getLogger(__name__)

BRIGHTSKY_BASE = "https://api.brightsky.dev"
OPENMETEO_BASE = "https://api.open-meteo.com/v1"

CONFIDENCE_THRESHOLD = 0.5
CACHE_RADIUS_M = 10_000  # 10 km dedup radius


class WeatherFallbackError(Exception):
    """Raised when all fallback sources fail."""


async def needs_fallback(
    session: AsyncSession,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> bool:
    """Check whether fallback fetch is needed for a location + time range.

    Returns True if:
    - No observations exist in the time range at all, OR
    - No observations within 10 km, OR
    - Average confidence of existing observations < 0.5
    """
    from sqlalchemy import select, func
    from load_gear.models.data import WeatherObservation

    # Fast check: any weather data at all in this time range?
    count_q = select(func.count()).select_from(
        select(WeatherObservation).where(
            WeatherObservation.ts_utc >= start,
            WeatherObservation.ts_utc < end,
        ).limit(1).subquery()
    )
    result = await session.execute(count_q)
    if result.scalar_one() == 0:
        return True

    # PostGIS KNN check: data within radius?
    obs, total = await weather_observation_repo.get_nearest_observations(
        session, lat, lon,
        start=start, end=end,
        max_distance_m=CACHE_RADIUS_M,
        limit=10_000,
    )

    if total == 0:
        return True

    avg_conf = sum(
        (o.confidence or 0.0) for o in obs
    ) / len(obs)

    return avg_conf < CONFIDENCE_THRESHOLD


async def fetch_brightsky(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Fetch hourly weather from BrightSky API.

    Returns list of observation dicts ready for weather_observation_repo.
    """
    # BrightSky expects date strings in YYYY-MM-DD format
    params = {
        "lat": lat,
        "lon": lon,
        "date": start.strftime("%Y-%m-%d"),
        "last_date": end.strftime("%Y-%m-%d"),
    }

    resp = await client.get(
        f"{BRIGHTSKY_BASE}/weather",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    weather_list = data.get("weather", [])
    if not weather_list:
        return []

    rows: list[dict[str, Any]] = []
    for entry in weather_list:
        ts_str = entry.get("timestamp")
        if not ts_str:
            continue

        # BrightSky returns ISO timestamps with timezone
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)

        # BrightSky station source_id as station_id
        source_id = str(entry.get("source_id", "brightsky"))

        rows.append({
            "ts_utc": ts,
            "station_id": f"bs_{source_id}",
            "temp_c": entry.get("temperature"),
            "ghi_wm2": entry.get("solar", entry.get("sunshine")),
            "wind_ms": entry.get("wind_speed"),
            "cloud_pct": entry.get("cloud_cover"),
            "confidence": 0.8,  # API data slightly lower than DWD bulk
            "source": "brightsky",
        })

    return rows


async def fetch_openmeteo(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Fetch hourly weather from Open-Meteo API.

    Returns list of observation dicts ready for weather_observation_repo.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,shortwave_radiation,wind_speed_10m,cloud_cover",
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": end.strftime("%Y-%m-%d"),
        "timezone": "UTC",
    }

    resp = await client.get(
        f"{OPENMETEO_BASE}/forecast",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    ghis = hourly.get("shortwave_radiation", [])
    winds = hourly.get("wind_speed_10m", [])
    clouds = hourly.get("cloud_cover", [])

    if not times:
        return []

    rows: list[dict[str, Any]] = []
    for i, ts_str in enumerate(times):
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Convert wind from km/h to m/s
        wind_kmh = winds[i] if i < len(winds) else None
        wind_ms = wind_kmh / 3.6 if wind_kmh is not None else None

        rows.append({
            "ts_utc": ts,
            "station_id": f"om_{lat:.2f}_{lon:.2f}",
            "temp_c": temps[i] if i < len(temps) else None,
            "ghi_wm2": ghis[i] if i < len(ghis) else None,
            "wind_ms": wind_ms,
            "cloud_pct": clouds[i] if i < len(clouds) else None,
            "confidence": 0.6,  # model-based, lower than station data
            "source": "open_meteo",
        })

    return rows


async def fetch_fallback(
    session: AsyncSession,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    """Try BrightSky first, then Open-Meteo. Insert results into DB.

    Returns dict with source used and count inserted.
    """
    async with httpx.AsyncClient() as client:
        # Try BrightSky first
        rows: list[dict[str, Any]] = []
        source_used = "none"

        try:
            rows = await fetch_brightsky(client, lat, lon, start, end)
            if rows:
                source_used = "brightsky"
                logger.info("BrightSky returned %d rows for (%.2f, %.2f)", len(rows), lat, lon)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.warning("BrightSky failed for (%.2f, %.2f): %s", lat, lon, exc)

        # Fallback to Open-Meteo if BrightSky returned nothing
        if not rows:
            try:
                rows = await fetch_openmeteo(client, lat, lon, start, end)
                if rows:
                    source_used = "open_meteo"
                    logger.info("Open-Meteo returned %d rows for (%.2f, %.2f)", len(rows), lat, lon)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning("Open-Meteo failed for (%.2f, %.2f): %s", lat, lon, exc)

    if not rows:
        raise WeatherFallbackError(
            f"All weather API sources failed for ({lat:.4f}, {lon:.4f}) "
            f"from {start.isoformat()} to {end.isoformat()}"
        )

    # Insert into DB with location
    count = await weather_observation_repo.upsert_with_location(
        session, rows, lat, lon
    )

    return {
        "source": source_used,
        "rows_inserted": count,
        "lat": lat,
        "lon": lon,
    }


async def ensure_weather_data(
    session: AsyncSession,
    lat: float,
    lon: float,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """High-level entry point: check cache, fetch if needed, return summary.

    Called by analysis/forecast services to ensure weather data is available
    for a given location + time range.
    """
    if not await needs_fallback(session, lat, lon, start, end):
        # Data already available within 10 km
        station_id = await weather_observation_repo.get_nearest_station_id(
            session, lat, lon, max_distance_m=CACHE_RADIUS_M
        )
        return {
            "source": "cache",
            "station_id": station_id,
            "rows_inserted": 0,
            "cache_hit": True,
        }

    # Fetch from APIs
    result = await fetch_fallback(session, lat, lon, start, end)
    result["cache_hit"] = False
    return result
