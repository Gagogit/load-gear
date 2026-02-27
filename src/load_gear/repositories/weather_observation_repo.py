"""Async repository for data.weather_observations — CRUD + PostGIS KNN."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, func, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.models.data import WeatherObservation


async def bulk_insert(session: AsyncSession, rows: list[dict]) -> int:
    """Bulk insert weather observation rows using ORM session.add()."""
    if not rows:
        return 0
    for row_data in rows:
        wo = WeatherObservation(**row_data)
        session.add(wo)
    await session.flush()
    return len(rows)


async def get_by_station(
    session: AsyncSession,
    station_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> tuple[list[WeatherObservation], int]:
    """Fetch observations for a station within optional time range. Returns (rows, total)."""
    base = select(WeatherObservation).where(WeatherObservation.station_id == station_id)
    if start is not None:
        base = base.where(WeatherObservation.ts_utc >= start)
    if end is not None:
        base = base.where(WeatherObservation.ts_utc < end)

    count_q = select(func.count()).select_from(base.subquery())
    query = base.order_by(WeatherObservation.ts_utc).limit(limit).offset(offset)

    result = await session.execute(query)
    rows = list(result.scalars().all())
    total_result = await session.execute(count_q)
    total = total_result.scalar_one()

    return rows, total


async def get_all_by_station(
    session: AsyncSession,
    station_id: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[WeatherObservation]:
    """Fetch all observations for a station (no pagination)."""
    query = select(WeatherObservation).where(WeatherObservation.station_id == station_id)
    if start is not None:
        query = query.where(WeatherObservation.ts_utc >= start)
    if end is not None:
        query = query.where(WeatherObservation.ts_utc < end)
    query = query.order_by(WeatherObservation.ts_utc)

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_nearest_observations(
    session: AsyncSession,
    lat: float,
    lon: float,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    max_distance_m: float = 50_000,
    limit: int = 1000,
) -> tuple[list[WeatherObservation], int]:
    """Find weather observations from the nearest station using PostGIS KNN.

    Uses ST_DWithin for index-accelerated distance filter + ST_Distance for ordering.
    Returns observations from the single closest station within max_distance_m.
    """
    point = f"SRID=4326;POINT({lon} {lat})"

    # Step 1: find nearest station_id within radius
    nearest_q = text("""
        SELECT station_id, ST_Distance(source_location, ST_GeogFromText(:point)) AS dist
        FROM data.weather_observations
        WHERE ST_DWithin(source_location, ST_GeogFromText(:point), :max_dist)
            AND source_location IS NOT NULL
        ORDER BY dist
        LIMIT 1
    """)
    result = await session.execute(
        nearest_q, {"point": point, "max_dist": max_distance_m}
    )
    row = result.first()
    if row is None:
        return [], 0

    station_id: str = row[0]

    # Step 2: fetch observations for that station
    return await get_by_station(
        session, station_id, start=start, end=end, limit=limit, offset=0
    )


async def get_nearest_station_id(
    session: AsyncSession,
    lat: float,
    lon: float,
    *,
    max_distance_m: float = 50_000,
) -> str | None:
    """Return the station_id of the nearest weather station, or None."""
    point = f"SRID=4326;POINT({lon} {lat})"
    q = text("""
        SELECT station_id, ST_Distance(source_location, ST_GeogFromText(:point)) AS dist
        FROM data.weather_observations
        WHERE ST_DWithin(source_location, ST_GeogFromText(:point), :max_dist)
            AND source_location IS NOT NULL
        ORDER BY dist
        LIMIT 1
    """)
    result = await session.execute(q, {"point": point, "max_dist": max_distance_m})
    row = result.first()
    return row[0] if row else None


async def count_by_station(session: AsyncSession, station_id: str) -> int:
    """Count observations for a station."""
    q = select(func.count()).select_from(
        select(WeatherObservation)
        .where(WeatherObservation.station_id == station_id)
        .subquery()
    )
    result = await session.execute(q)
    return result.scalar_one()


async def list_stations(session: AsyncSession) -> list[dict]:
    """List all distinct station_ids with their observation count and time range."""
    q = text("""
        SELECT station_id,
               COUNT(*) AS obs_count,
               MIN(ts_utc) AS earliest,
               MAX(ts_utc) AS latest,
               source
        FROM data.weather_observations
        GROUP BY station_id, source
        ORDER BY station_id
    """)
    result = await session.execute(q)
    return [
        {
            "station_id": r[0],
            "obs_count": r[1],
            "earliest": r[2],
            "latest": r[3],
            "source": r[4],
        }
        for r in result.fetchall()
    ]


async def delete_by_station(session: AsyncSession, station_id: str) -> int:
    """Delete all observations for a station. Returns count deleted."""
    result = await session.execute(
        delete(WeatherObservation).where(WeatherObservation.station_id == station_id)
    )
    await session.flush()
    return result.rowcount


async def upsert_with_location(
    session: AsyncSession,
    rows: list[dict],
    lat: float,
    lon: float,
) -> int:
    """Bulk insert weather observations and set source_location via raw SQL.

    Each row dict should have: ts_utc, station_id, temp_c, ghi_wm2, wind_ms,
    cloud_pct, confidence, source. The source_location GEOGRAPHY point is set
    from the provided lat/lon.
    """
    if not rows:
        return 0

    # Insert via ORM first
    for row_data in rows:
        wo = WeatherObservation(**row_data)
        session.add(wo)
    await session.flush()

    # Set source_location for all inserted rows
    station_id = rows[0]["station_id"]
    point_wkt = f"SRID=4326;POINT({lon} {lat})"
    await session.execute(
        text("""
            UPDATE data.weather_observations
            SET source_location = ST_GeogFromText(:point)
            WHERE station_id = :sid AND source_location IS NULL
        """),
        {"point": point_wkt, "sid": station_id},
    )
    await session.flush()
    return len(rows)
