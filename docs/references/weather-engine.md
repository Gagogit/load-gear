# Weather Engine Reference
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Architecture: Hybrid Bulk + API Fallback

### Tier 1 — Annual DWD Bulk Import

- **Source:** DWD "CDC" FTP server (opendata.dwd.de)
- **Schedule:** Annual import (January) for the previous year
- **Parameters:** TT_TU (temperature), FG_LUM (global radiation)
- **Format:** CSV/ASCII
- **Processing:** Polars Lazy queries for parsing + type mapping
  - DWD timestamps → ISO-8601 UTC
  - J/cm² → W/m² conversion for radiation
- **Storage:** `data.weather_observations` hypertable with GEOGRAPHY(POINT) index
- **Coverage:** German-wide station network (~400 stations)

### Tier 2 — API Fallback

- **Trigger:** When a spatial-temporal join finds confidence < threshold,
  OR no bulk data exists for the requested time range
- **APIs:** BrightSky (preferred, free), Open-Meteo (backup)
- **Caching:** Do not fetch if data exists within 10km radius
- **Storage:** Same `data.weather_observations` table, `source='brightsky'` or `'open_meteo'`

## Confidence Score (Truth Function)

```
confidence = 1.0 - (distance_meters / 50000.0)
```

| Distance | Confidence | Action |
|----------|------------|--------|
| 0 km | 1.0 | Perfect match |
| 10 km | 0.8 | Good |
| 25 km | 0.5 | Threshold — consider API fallback |
| 50+ km | ≤ 0.0 | Must use API for exact coordinates |

## Spatial-Temporal Join (SQL Reference)

```sql
SELECT
    m.ts_utc AS ds,
    m.value AS y,
    w.temp_c,
    w.ghi_wm2,
    (1.0 - (ST_Distance(m.geom, w.source_location) / 50000.0)) AS confidence
FROM data.meter_reads m
LEFT JOIN LATERAL (
    SELECT temp_c, ghi_wm2, source_location
    FROM data.weather_observations
    WHERE ts_utc = date_trunc('hour', m.ts_utc)
    ORDER BY m.geom <-> source_location
    LIMIT 1
) w ON true
WHERE m.meter_id = :meter_id
  AND m.version = 1
  AND m.ts_utc BETWEEN :start AND :end;
```

Requires: GiST index on `data.weather_observations.source_location`

## DWD Station Data Structure

DWD CDC files contain:
- `STATIONS_ID`: Integer station identifier
- `MESS_DATUM`: Timestamp (YYYYMMDDHH format)
- `TT_TU`: Air temperature at 2m height (°C)
- `FG_LBERG`: Global radiation (J/cm²) — convert to W/m²

Station metadata (separate file): ID, lat, lon, elevation, name, state
