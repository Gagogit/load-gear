# Schema: analysis (Intelligence Layer)
Schicht: B
Letzte Aktualisierung: 2026-02-27

The `analysis` schema stores what Prophet and statistical checks have discovered
about a meter's load profile. This is the basis for imputation and forecasting.

---

## Table: `analysis.analysis_profiles`

The central intelligence artifact. One profile per analysis run.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Profile identifier (= analysis_run_id) |
| job_id | UUID (FK → control.jobs) | Parent job |
| meter_id | TEXT | Analyzed meter |
| day_fingerprints | JSONB | Clustering results: Werktag-Sommer, Sonntag-Winter, Feiertag, etc. |
| seasonality | JSONB | `{"daily": true, "weekly": true, "yearly": true}` |
| holiday_rules | JSONB | Mapping: holiday type → load behavior |
| weather_correlations | JSONB | temp_sensitivity, ghi_sensitivity, lag config |
| asset_hints | JSONB | NULL in v0.1 (ADR-005). Future: PV/battery/KWK detection |
| impute_policy | JSONB | Method, max_gap_min, outlier_clip_p |
| created_at | TIMESTAMPTZ | Analysis timestamp |

**day_fingerprints JSONB example:**
```json
{
  "Werktag-Sommer": {"avg_kw": [12.3, 11.8, ...], "count": 120},
  "Sonntag-Winter": {"avg_kw": [8.1, 7.9, ...], "count": 26},
  "Feiertag": {"avg_kw": [6.5, 6.2, ...], "count": 12},
  "Brückentag": {"avg_kw": [7.0, 6.8, ...], "count": 4},
  "Störung": {"avg_kw": [0.0, 0.0, ...], "count": 2}
}
```

**weather_correlations JSONB example:**
```json
{
  "temp_sensitivity": 0.42,
  "ghi_sensitivity": -0.35,
  "lags": {"temp": 2},
  "confidence_threshold": 0.5
}
```

---

## Table: `analysis.quality_findings`

QA check results from P3. Read-only record of what QA found (QA does not modify data).

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Finding identifier |
| job_id | UUID (FK → control.jobs) | Parent job |
| check_id | SMALLINT | Check number (1-9) |
| check_name | TEXT | e.g. interval_completeness, gap_analysis, dst_conformity |
| status | ENUM ('ok', 'warn', 'error') | Check result |
| metric_key | TEXT | e.g. completeness_pct, gap_max_duration_min |
| metric_value | DOUBLE PRECISION | Numeric result |
| threshold | DOUBLE PRECISION | Configured threshold (from admin config) |
| affected_slots | JSONB | List of affected timestamps (gaps, duplicates, etc.) |
| recommendation | TEXT | Auto-imputation recommendation or manual hint |
| created_at | TIMESTAMPTZ | Check execution time |

**Indexes:** (job_id, check_id)

---

## Table: `analysis.imputation_runs`

Tracks each imputation execution for lineage.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Imputation run identifier |
| analysis_profile_id | UUID (FK → analysis_profiles) | Profile used |
| job_id | UUID (FK → control.jobs) | Parent job |
| slots_replaced | INT | Number of intervals imputed |
| method_summary | JSONB | Count per method: profile, weather, interpolation |
| created_at | TIMESTAMPTZ | Run timestamp |
