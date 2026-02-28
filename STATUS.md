# STATUS — Current Phase

Phases 1–7 complete. Phase 6 archived to docs/status/STATUS_phase6.md.

## Ingest Rework — XLS/XLSX Support + Variable Header Detection (DONE)

| Task | Description | Status |
|------|-------------|--------|
| IR-01 | Install clevercsv + xlrd dependencies | done |
| IR-02 | File-type detection (magic bytes: XLSX/XLS/CSV) + Excel→rows conversion | done |
| IR-03 | New `_find_data_boundary()` algorithm (skip metadata, find header) | done |
| IR-04 | Refactor `detect_format()` to work on uniform `list[list[str]]` rows | done |
| IR-05 | clevercsv fallback in delimiter detector | done |
| IR-06 | Normalizer XLS/XLSX reading path (`_read_excel()`) | done |
| IR-07 | Test fixtures + 18 new tests (310 total) | done |

### Key Deliverables
- **File type detection**: magic bytes (`PK\x03\x04`=XLSX, `\xd0\xcf\x11\xe0`=XLS, else CSV)
- **Excel conversion**: openpyxl (XLSX) / xlrd (XLS) → uniform `list[list[str]]` rows
- **Header detection rework**: `_find_data_boundary()` scans up to 50 rows for first data row (date+numeric), searches backwards for header using domain keywords (Datum, Wert, kWh, etc.)
- **clevercsv**: fallback between csv.Sniffer and frequency analysis for messy CSV dialects
- **Normalizer**: separate `_read_csv()` / `_read_excel()` paths, `file_type` in rules dict
- **New fixture**: `german_with_header.csv` (5-line metadata preamble)
- **310 tests** all passing

## Phase 7 — Weather Integration & Asset Intelligence (DONE)

| Task | Description | Status |
|------|-------------|--------|
| T-035 | DWD Weather Station Import Service | done |
| T-036 | Weather API Fallback (BrightSky + Open-Meteo) | done |
| T-037 | Spatial-Temporal Join + Weather Correlation Engine | done |
| T-038 | Asset Fingerprinting Implementation (PV/Battery/KWK) | done |
| T-039 | Enhanced Imputation (flag=3) + Forecast Strategies | done |
| T-040 | Weather Admin Endpoints (4 on /api/v1/weather) | done |
| T-041 | PLZ Geocoding Service (909 centroids) | done |
| T-042 | Phase 7 Tests + Integration Test (62 new → 292 total) | done |

### Key Deliverables
- **weather_observation_repo**: 8 async functions (CRUD + PostGIS KNN)
- **DWD import**: Polars CSV parser, J/cm²→W/m², CET→UTC, station catalog
- **API fallback**: BrightSky (conf=0.8) → Open-Meteo (conf=0.6), 10km cache dedup
- **Correlation engine**: temp/GHI/wind sensitivity, lag analysis (-3h to +3h)
- **Asset fingerprinting**: PV (midday dip + GHI corr), Battery (night charge + variance), KWK (baseload CV + seasonal)
- **Weather imputation**: flag=3 (profile × weather regression), clamped ±30%
- **Forecast strategies**: weather_conditioned (temp/GHI deviation), asset_scenarios (PV/battery/KWK modifiers)
- **PLZ geocoding**: 909 centroids, 3-digit/2-digit prefix fallback
- **4 admin endpoints**: POST import, GET stations, GET observations, DELETE station

## Platform Summary (after Phase 7)
- **14 tables** across 3 schemas (control/4, data/7, analysis/3)
- **4 Alembic migrations**
- **9 job states**: PENDING → INGESTING → QA_RUNNING → ANALYSIS_RUNNING → FORECAST_RUNNING → FINANCIAL_RUNNING → DONE/WARN/FAILED
- **35 API endpoints** across 10 routers
- **13 repositories**
- **292 tests** all passing
- **Full pipeline**: job → ingest → QA → analysis (with weather + assets) → forecast → financial → done
