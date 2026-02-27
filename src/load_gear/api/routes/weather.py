"""Weather admin endpoints: /api/v1/weather."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from load_gear.core.database import get_session
from load_gear.models.schemas import (
    WeatherImportRequest,
    WeatherImportResponse,
    WeatherObservationListResponse,
    WeatherObservationRow,
    WeatherStationInfo,
    WeatherStationListResponse,
)
from load_gear.repositories import weather_observation_repo
from load_gear.services.weather.dwd_import import DWDImportError, import_station

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])


@router.post("/import", status_code=202, response_model=WeatherImportResponse)
async def import_weather(
    body: WeatherImportRequest,
    session: AsyncSession = Depends(get_session),
) -> WeatherImportResponse:
    """Import DWD weather data for a station."""
    try:
        result = await import_station(
            session,
            body.station_id,
            body.lat,
            body.lon,
            params=body.params,
            start=body.start,
            end=body.end,
        )
        return WeatherImportResponse(
            station_id=body.station_id,
            total_inserted=result.get("total_inserted", 0),
            counts_per_param={
                k: v for k, v in result.items() if k != "total_inserted"
            },
        )
    except DWDImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/stations", response_model=WeatherStationListResponse)
async def list_stations(
    session: AsyncSession = Depends(get_session),
) -> WeatherStationListResponse:
    """List all weather stations with observation counts."""
    stations = await weather_observation_repo.list_stations(session)
    items = [WeatherStationInfo(**s) for s in stations]
    return WeatherStationListResponse(items=items, total=len(items))


@router.get("/stations/{station_id}/observations", response_model=WeatherObservationListResponse)
async def get_station_observations(
    station_id: str,
    start: datetime | None = Query(None, description="Start datetime (UTC)"),
    end: datetime | None = Query(None, description="End datetime (UTC)"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> WeatherObservationListResponse:
    """Get weather observations for a station (paginated)."""
    rows, total = await weather_observation_repo.get_by_station(
        session, station_id, start=start, end=end, limit=limit, offset=offset,
    )
    items = [WeatherObservationRow.model_validate(r) for r in rows]
    return WeatherObservationListResponse(
        station_id=station_id, items=items, total=total,
    )


@router.delete("/stations/{station_id}", status_code=204)
async def delete_station(
    station_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    """Delete all observations for a weather station."""
    count = await weather_observation_repo.delete_by_station(session, station_id)
    if count == 0:
        raise HTTPException(status_code=404, detail=f"No data for station {station_id}")
