# API Endpoint Reference
Schicht: B
Letzte Aktualisierung: 2026-02-27

Base path: `/api/v1/`
Auth: none in v0.1 (ADR-007)

## A — Job Management `/api/v1/jobs`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /jobs | Create job | P1 | sync |
| GET | /jobs | List jobs (filter: company, status, meter_id) | P1 | sync |
| GET | /jobs/{job_id} | Job status + phase + errors | ALL | sync |
| DELETE | /jobs/{job_id} | Cancel or delete job | P1 | sync |
| GET | /jobs/{job_id}/log | Phase execution log | ALL | stream |
| GET | /jobs/{job_id}/lineage | Full data lineage (v1→v2→v3) | ALL | sync |

## B — File Upload `/api/v1/files`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /files/upload | Upload source file (CSV/Excel) | P2 | multipart |
| GET | /files/{file_id} | File metadata | P2 | sync |
| GET | /files/{file_id}/download | Download raw file from GCS | P2 | stream |
| GET | /files/{file_id}/reader-profile | Detected reader profile | P2a | sync |
| PUT | /files/{file_id}/reader-profile | Override reader profile | P2a | sync |

## C — Ingestion `/api/v1/ingest`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /ingest | Start ingest (job_id + file_id) | P2 | async |
| GET | /ingest/{job_id}/status | Ingest progress | P2 | sync |
| GET | /ingest/{job_id}/normalized | v1 series (JSON/CSV) | P2b | stream |

## D — QA `/api/v1/qa`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /qa | Start QA run | P3 | async |
| GET | /qa/{job_id}/status | QA progress | P3 | sync |
| GET | /qa/{job_id}/report | Full QA report (9 checks) | P3 | sync |
| GET | /qa/{job_id}/findings | Individual findings list | P3 | sync |
| GET | /qa/{job_id}/profile | Hour/weekday profiles | P3 | sync |

## E — Analysis `/api/v1/analysis`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /analysis | Start analysis + imputation | P4 | async |
| GET | /analysis/{job_id}/status | Analysis phase progress | P4 | sync |
| GET | /analysis/{job_id}/profile | Analysis profile JSON | P4 | sync |
| GET | /analysis/{job_id}/day-labels | Day classification results | P4.1 | sync |
| GET | /analysis/{job_id}/weather | Weather features per timestamp | P4.2 | sync |
| GET | /analysis/{job_id}/imputation | Imputation report | P4 | sync |
| GET | /analysis/{job_id}/normalized-v2 | Cleaned v2 series | P4 | stream |

## F — Forecast `/api/v1/forecasts`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /forecasts | Create forecast job | P5 | async |
| GET | /forecasts | List forecasts | P5 | sync |
| GET | /forecasts/{id} | Forecast metadata + status | P5 | sync |
| GET | /forecasts/{id}/series | Forecast series (q10/q50/q90) | P5 | sync |
| GET | /forecasts/{id}/export | Export CSV/Excel | P5 | stream |
| GET | /forecasts/{id}/report | Forecast report JSON | P5 | sync |
| DELETE | /forecasts/{id} | Delete forecast | P5 | sync |

## G — Financial `/api/v1/financial`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /financial/calculate | Cost calculation | P6 | async |
| GET | /financial/{calc_id}/result | Cost time series + monthly sums | P6 | sync |
| GET | /financial/{calc_id}/export | Export CSV/Excel | P6 | stream |

## H — HPFC `/api/v1/hpfc`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| POST | /hpfc/upload | Upload HPFC file | P6 | multipart |
| GET | /hpfc | List snapshots | P6 | sync |
| GET | /hpfc/{snapshot_id} | Snapshot metadata | P6 | sync |
| GET | /hpfc/{snapshot_id}/series | Hourly price curve | P6 | sync |
| DELETE | /hpfc/{snapshot_id} | Delete snapshot | P6 | sync |

## I — Meters `/api/v1/meters`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| GET | /meters | List known meters | P1 | sync |
| GET | /meters/{meter_id} | Meter details (PLZ, coords) | P1 | sync |
| GET | /meters/{meter_id}/jobs | Job history for meter | P1 | sync |
| GET | /meters/{meter_id}/series | Historical series (v1/v2) | P2-4 | sync |

## J — Weather `/api/v1/weather`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| GET | /weather/stations | List DWD stations | P4.2 | sync |
| GET | /weather/stations/nearest | Find nearest station to PLZ/coords | P4.2 | sync |
| GET | /weather/observations | Station weather series | P4.2 | sync |
| POST | /weather/fetch | Trigger API fallback pull | P4.2 | async |
| POST | /weather/bulk-import | Annual DWD bulk import (admin) | P4.2 | admin |

## K — Calendar `/api/v1/calendar`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| GET | /calendar/holidays | Get holidays (state, year) | P4.1 | sync |
| POST | /calendar/holidays | Add custom holidays | P4.1 | admin |
| GET | /calendar/bridge-days | Calculate bridge days | P4.1 | sync |

## L — Admin `/api/v1/admin`

| Method | Path | Description | Phase | Type |
|--------|------|-------------|-------|------|
| GET | /admin/config | QA configuration | P3 | admin |
| PUT | /admin/config | Update QA config | P3 | admin |
| GET | /admin/health | System health check | ALL | ops |
| GET | /admin/queue | Worker queue status | ALL | ops |
