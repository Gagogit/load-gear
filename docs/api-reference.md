# LOAD-GEAR API Reference — Input Fields & Status Points

## Job Status Flow

```
PENDING → INGESTING → QA_RUNNING → ANALYSIS_RUNNING → FORECAST_RUNNING → FINANCIAL_RUNNING → DONE
                                                                                              → WARN
                                                                     ↘ (Prognose task)→ DONE   → FAILED
```

## All 35 API Endpoints

### 1. Jobs (`/api/v1/jobs`) — 4 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/jobs` | `name: str`, `task: str` (Aggregation/Prognose), `plz: str?`, `description: str?` | 201 → job with `status=pending` |
| `GET` | `/jobs` | query: `status?: str`, `skip: int=0`, `limit: int=100` | list of jobs with current status |
| `GET` | `/jobs/{job_id}` | path: `job_id: UUID` | single job with status |
| `DELETE` | `/jobs/{job_id}` | path: `job_id: UUID` | 204 no content |

### 2. Files (`/api/v1/files`) — 3 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/files/upload` | form: `file: UploadFile`, query: `job_id: UUID` | 201 → file record, job stays `pending` |
| `GET` | `/files/{file_id}` | path: `file_id: UUID` | file metadata |
| `GET` | `/files/{file_id}/reader-profile` | path: `file_id: UUID` | detected reader profile |

### 3. Ingest (`/api/v1/ingest`) — 3 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/ingest` | `job_id: UUID`, `file_id: UUID` | job → `ingesting` → `qa_running` (auto-chains QA) |
| `GET` | `/ingest/status/{job_id}` | path: `job_id: UUID` | ingest progress |
| `GET` | `/ingest/normalized/{file_id}` | path: `file_id: UUID`, query: `limit: int=100`, `offset: int=0` | normalized v1 rows |

### 4. QA (`/api/v1/qa`) — 5 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/qa` | `job_id: UUID` | job → `qa_running` |
| `GET` | `/qa/status/{job_id}` | path: `job_id: UUID` | QA progress |
| `GET` | `/qa/report/{job_id}` | path: `job_id: UUID` | full QA report (9 checks) |
| `GET` | `/qa/findings/{job_id}` | path: `job_id: UUID`, query: `severity?: str` | quality findings list |
| `GET` | `/qa/profile/{job_id}` | path: `job_id: UUID` | statistical profile |

### 5. Admin (`/api/v1/admin`) — 2 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `GET` | `/admin/config` | — | current config |
| `PUT` | `/admin/config` | JSON body: config key-value pairs | updated config |

### 6. Analysis (`/api/v1/analysis`) — 7 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/analysis` | `job_id: UUID` | job → `analysis_running` |
| `GET` | `/analysis/status/{job_id}` | path: `job_id: UUID` | analysis progress |
| `GET` | `/analysis/profile/{job_id}` | path: `job_id: UUID` | analysis profile (day types, weather, assets) |
| `GET` | `/analysis/day-types/{job_id}` | path: `job_id: UUID` | day classification results |
| `GET` | `/analysis/weather/{job_id}` | path: `job_id: UUID` | weather correlations |
| `GET` | `/analysis/imputation/{job_id}` | path: `job_id: UUID` | imputation run details |
| `GET` | `/analysis/v2/{job_id}` | path: `job_id: UUID`, query: `limit: int=100`, `offset: int=0` | imputed v2 rows |

### 7. Forecasts (`/api/v1/forecasts`) — 5 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/forecasts` | `job_id: UUID`, `horizon_days: int=365`, `strategies: list[str]?` | job → `forecast_running` |
| `GET` | `/forecasts/status/{job_id}` | path: `job_id: UUID` | forecast progress |
| `GET` | `/forecasts/runs/{job_id}` | path: `job_id: UUID` | forecast run metadata |
| `GET` | `/forecasts/series/{job_id}` | path: `job_id: UUID`, query: `limit: int=100`, `offset: int=0` | v3 forecast rows (y_hat, q10, q50, q90) |
| `GET` | `/forecasts/summary/{job_id}` | path: `job_id: UUID` | forecast summary stats |

### 8. HPFC (`/api/v1/hpfc`) — 5 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/hpfc/upload` | form: `file: UploadFile`, body: `name: str`, `year: int` | 201 → snapshot created |
| `GET` | `/hpfc/snapshots` | query: `year?: int` | list of HPFC snapshots |
| `GET` | `/hpfc/snapshots/{id}` | path: `snapshot_id: UUID` | snapshot metadata |
| `GET` | `/hpfc/snapshots/{id}/series` | path: `snapshot_id: UUID`, query: `limit: int=100`, `offset: int=0` | hourly price series |
| `DELETE` | `/hpfc/snapshots/{id}` | path: `snapshot_id: UUID` | 204 no content |

### 9. Financial (`/api/v1/financial`) — 3 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/financial` | `job_id: UUID`, `hpfc_snapshot_id: UUID` | job → `financial_running` → `done` |
| `GET` | `/financial/runs/{job_id}` | path: `job_id: UUID` | financial run + monthly summary |
| `GET` | `/financial/export/{job_id}` | path: `job_id: UUID`, query: `format: str` (csv/xlsx) | file download |

### 10. Weather (`/api/v1/weather`) — 4 endpoints

| Method | Path | Input Fields | Response Status |
|--------|------|-------------|-----------------|
| `POST` | `/weather/import` | `station_id: str`, `start_date: date`, `end_date: date`, `params: list[str]?` | import result (rows imported, station info) |
| `GET` | `/weather/stations` | — | list of weather stations |
| `GET` | `/weather/stations/{id}/observations` | path: `station_id: str`, query: `start?: datetime`, `end?: datetime`, `limit: int=100` | observation rows |
| `DELETE` | `/weather/stations/{id}` | path: `station_id: str` | 204 no content |

## Quality Flags (`meter_reads.quality_flag`)

| Flag | Meaning | Set By |
|------|---------|--------|
| 0 | Original data | Ingest (P2) |
| 1 | Linear interpolation | Imputer (P4) |
| 2 | Profile-based fill | Imputer (P4) |
| 3 | Weather-adjusted profile | Imputer (P4) |

## Data Versions

| Version | Table | Phase |
|---------|-------|-------|
| v1 | `data.meter_reads` (raw) | P2 Ingest |
| v2 | `data.meter_reads` (imputed) | P4 Analysis |
| v3 | `data.forecast_series` | P5 Forecast |
| cost | `data.financial_runs` | P6 Financial |
