# Module: QA Service (P3 — Quality Assessment)
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Responsibility

Run 9 statistical checks on the v1 time series and produce a quality report.
QA is **read-only** on time series data — it NEVER writes to `data.meter_reads` (ADR-001).

## The 9 QA Checks

| # | Check | Key Metrics |
|---|-------|-------------|
| 1 | Interval completeness | `interval_count_observed` vs `expected`, `delta` |
| 2 | Completeness % | `completeness_pct`, `missing_count`, list of missing slots |
| 3 | Gaps & duplicates | `gap_count`, `gap_max_duration_min`, duplicate timestamp list |
| 4 | Daily/monthly energy | `kwh_day[]`, `kwh_month[]`, `coverage_pct_day`, `incomplete_sum` flag |
| 5 | Peak load (kW) | `kw_peak_value`, `kw_peak_timestamp`, Top-N peaks |
| 6 | Baseload | `kw_baseload` (P5/P10), optional night 00-04h separate |
| 7 | Load factor | `load_factor = kw_avg / kw_peak`, `stddev_kw` |
| 8 | Hourly/weekday profile | 24-value hour profile, 7-value weekday profile |
| 9 | DST conformity | Per DST day: `expected_local_slots` ∈ {92,96,100} vs `observed` |

## Global Config Parameters

Stored in admin config (GET/PUT /api/v1/admin/config):

| Parameter | Default | Description |
|-----------|---------|-------------|
| min_kw | 0.0 | Minimum valid kW value |
| max_kw | 10000.0 | Maximum valid kW value |
| max_jump_kw | 5000.0 | Maximum allowed jump between consecutive intervals |
| top_n_peaks | 10 | Number of peak values to report |
| min_completeness_pct | 95.0 | Below this → warn |
| max_gap_duration_min | 180 | Gaps longer than this → error |

## Output

- `analysis.quality_findings` — one row per check (9 rows per job)
- Optional: PDF report artifact → GCS `reports/{job_id}/qa_report.pdf`
- QA findings are input for the Analysis service (P4) imputation decisions

## Tools

- SQL aggregation via TimescaleDB (time_bucket, gap detection)
- Polars for in-memory profile calculation (hour/weekday arrays)

## Status Transitions

- Success (all checks ok/warn): job → `analysis_pending`
- Any check = error AND job only requests Statistik: job → `done`
- Fatal failure (can't read data): job → `failed`
