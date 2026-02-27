# Module: Ingest Service (P2 — Homogenization)
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Responsibility

Parse uploaded energy data files, detect format, normalize into a unified time series,
and write v1 to `data.meter_reads`.

## Sub-phases

### P2a — Format Recognition (Reader Profile)

Auto-detect file properties and produce a `reader_profile` (JSONB):

| Detection | Details |
|-----------|---------|
| File type | CSV, Excel (.xlsx/.xls), EDIFACT-MSCONS, TSV |
| Encoding | UTF-8, ISO-8859-1, Windows-1252 (auto-detect via chardet) |
| Delimiter | `;` `,` `\t` — sniffing |
| Decimal separator | `,` vs `.` |
| Date format | DD.MM.YYYY, YYYY-MM-DD, MM/DD/YYYY |
| Time format | 00:15, 0:15, AM/PM |
| Unit | kW vs kWh vs Wh (heuristic from header/values) |
| Timezone/DST | Europe/Berlin → UTC mapping |
| Cumulative | Cumulative vs interval values (monotonic check) |

Output: `control.reader_profiles` row + warnings in `technical_quality` JSONB.

### P2b — Normalization

Transform parsed data into the golden row format:

```
meter_id | ts_utc | value | unit | version=1 | quality_flag=0 | job_id | source_file_id
```

Rules:
- All timestamps → UTC (including DST resolution: 92/96/100 intervals)
- Inclusive/exclusive boundaries made consistent
- Cumulative values → interval delta
- Unit normalization (Wh → kWh if needed)
- Original file → GCS `raw/` (WORM, SHA-256 verified)
- Normalized series → `data.meter_reads` with `version=1`

## Tools / Libraries

- **Polars** (Lazy API) for all CSV/Excel parsing and transformation
- **chardet** for encoding detection
- No Pandas — project constraint

## Persistence

| Data | Destination |
|------|-------------|
| Original file | GCS `raw/{year}/{file_id}.{ext}` (immutable) |
| File metadata | `control.files` |
| Reader profile | `control.reader_profiles` |
| Normalized v1 | `data.meter_reads` (version=1) |

## Error Cases

- Unknown file format → job status=failed, error_message describes issue
- Encoding detection fails → try UTF-8, ISO-8859-1 fallback chain
- Zero valid rows after parse → job status=failed
