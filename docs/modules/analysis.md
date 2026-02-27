# Module: Analysis Service (P4 — Analysis & Imputation)
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Responsibility

Create a semantic fingerprint of the time series, enrich with weather data,
and produce v2 (imputed/cleaned) in `data.meter_reads`.

Analysis is the **sole owner of v2** (ADR-001).

## Sub-phases

### P4.1 — Day Classification & Calendar Matching

**Top-down:** Mark known special days using holiday/bridge-day logic:
- Federal holidays (DE) and state holidays (BY, NW, etc.) from `control.holidays`
- Bridge days: identified by static rules, verified by load comparison (>20% drop)
- Custom closures (Betriebsferien) from job parameters

**Bottom-up:** Cluster similar load shapes via daily profiles:
- Labels: `Werktag-Sommer`, `Werktag-Winter`, `Samstag`, `Sonntag`, `Feiertag`,
  `Brückentag`, `Störung`
- Score each day's confidence in its label

**Bridge day verification (Phase B):**
- Compare potential bridge day load vs normal weekday reference (same season)
- Fall 1: Load drops >20% → confirmed bridge day
- Fall 2: Load unchanged → ignored (e.g., retail, nursing home)
- Fall 3: Load rises → special operations flag

**Output:** `analysis.analysis_profiles.day_fingerprints` + day_labels stored in profile

### P4.2 — Weather Enrichment

**Spatial-Temporal Join:** For each meter timestamp, find the geographically nearest
weather observation using PostGIS:

```sql
SELECT m.ts_utc, m.value, w.temp_c, w.ghi_wm2,
       (1.0 - (ST_Distance(m.geom, w.source_location) / 50000.0)) AS confidence
FROM data.meter_reads m
LEFT JOIN LATERAL (
    SELECT temp_c, ghi_wm2, source_location
    FROM data.weather_observations
    WHERE ts_utc = date_trunc('hour', m.ts_utc)
    ORDER BY m.geom <-> source_location
    LIMIT 1
) w ON true
WHERE m.meter_id = :meter_id AND m.version = 1
```

**Confidence check:** If confidence < 0.5, trigger async API fallback
(BrightSky/Open-Meteo) for exact coordinates.

**Features for Prophet:**
- `temp_c` and `ghi_wm2` as additional regressors
- Lag features (e.g., `temp_c_lag_2h`) for thermal inertia if profile demands it

**Output:** `analysis.analysis_profiles.weather_correlations`

### P4.3 — Asset Fingerprinting (STUB — ADR-005)

Returns `{"asset_hints": null}`. Pass-through, no processing.
Future: detect PV midday dip, battery night charge, KWK patterns.

### P4.4 — Imputation

Replace missing/flagged intervals using this priority chain:

1. **Day-type profile** (from P4.1) — use average for this hour + day label
2. **Weather-sensitive value** (from P4.2) — adjust by temperature/GHI regression
3. **Asset-adjusted** (from P4.3) — SKIPPED (stub returns null)
4. **Fallback** — linear interpolation between nearest valid neighbors

Each imputed value gets a `quality_flag` in `data.meter_reads`:
- 0 = original, 1 = interpolated, 2 = profile-based, 3 = weather-based

**Output:** v2 rows in `data.meter_reads` (version=2) + `analysis.imputation_runs` record

## Persistence

| Data | Destination |
|------|-------------|
| Analysis profile | `analysis.analysis_profiles` |
| Imputation log | `analysis.imputation_runs` |
| Cleaned series v2 | `data.meter_reads` (version=2) |
| Reports | GCS `reports/{job_id}/analysis_report.json` |

## Tools

- PostGIS for spatial joins (KNN operator `<->`)
- Polars for in-memory profile computation
- Python `holidays` library for German federal/state holidays
- Prophet for seasonality detection (used in P4.1 clustering)
