# Module: Forecast Service (P5 — Projection)
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Responsibility

Project historical patterns onto a target time range using Prophet.
Reads v2 + analysis_profile, writes v3 to `data.forecast_series`.

## Input

- `data.meter_reads` (version=2) — cleaned historical series
- `analysis.analysis_profiles` — day fingerprints, weather correlations, seasonality
- Job parameters: horizon_start, horizon_end, strategies[], scenarios{}, quantiles[]

## Strategies (combinable)

| # | Strategy | Description |
|---|----------|-------------|
| 1 | Calendar-Mapping | Map day classes (Mo-So, holidays) 1:1/nearest-neighbor onto target dates |
| 2 | Weather-conditioned | k-NN on [Temp, GHI, day_type] from history → similar weather situations |
| 3 | DST-correct | Respect target timezone DST: 92/96/100 intervals on transition days |
| 4 | Scaling (optional) | Growth %, load shifting, efficiency measures from job parameters |
| 5 | Asset scenarios (optional) | Add/remove PV/battery profiles (future, depends on P4.3) |
| 6 | Energy budgets (optional) | Monthly sum constraints (kWh) as post-processing adjustment |

## Prophet Configuration

- **Regressors:** `temp_c`, `ghi_wm2` (from weather correlations in analysis_profile)
- **Seasonality:** daily, weekly, yearly (flags from analysis_profile)
- **Holidays:** German holidays + bridge days (from P4.1 day labels)
- **Changepoints:** Auto-detected by Prophet
- **Quantiles:** Configurable, default [0.1, 0.5, 0.9]

## Worker Constraint

Prophet computation MUST NOT run in the main API thread (ADR-003/006).
In v0.1 monolith: run in asyncio executor (thread pool).
Future: dedicated worker container.

## Output

| Data | Destination |
|------|-------------|
| Forecast metadata | `data.forecast_runs` |
| Forecast time series | `data.forecast_series` (q10, q50, q90) |
| Model artifact | GCS `models/{forecast_id}/prophet_model.json` |
| Report | GCS `reports/{job_id}/forecast_report.json` |

## Export Formats

- JSON (default, via API)
- CSV (configurable columns, unit, rounding)
- Excel (.xlsx)
- EDIFACT/MSCONS (future — needs subset specification, see open points)

## Reproducibility

Each forecast run has a `data_snapshot_id` = SHA-256 of:
meter_id + horizon + v2 data hash + analysis_params hash.
Same inputs → same snapshot_id → results are comparable.
