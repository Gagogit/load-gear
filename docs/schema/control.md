# Schema: control (Job Orchestration & Metadata)
Schicht: B
Letzte Aktualisierung: 2026-02-27

The `control` schema manages job lifecycle, file tracking, and reader profiles.
It is the "command center" — no time series data lives here.

---

## Table: `control.jobs`

The entry point for every action. Created by POST /api/v1/jobs.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Job identifier |
| status | ENUM | pending, ingesting, qa_running, analysis_running, forecast_running, done, warn, failed |
| company_id | TEXT | Company identifier (future: row-level security) |
| meter_id | TEXT | MaLo/Zählpunkt identifier |
| plz | TEXT (5) | Postal code for geo-matching |
| payload | JSONB | All frontend parameters: horizon, unit, interval, tasks[], scenarios{} |
| current_phase | TEXT | Currently executing phase (P2/P3/P4/P5/P6) |
| error_message | TEXT | NULL unless status=failed |
| created_at | TIMESTAMPTZ | Default: now() |
| updated_at | TIMESTAMPTZ | Auto-updated on status change |

**Indexes:** status, company_id, meter_id, created_at

---

## Table: `control.files`

Tracks physical files (uploads). Linked to GCS raw/ path.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | File identifier |
| job_id | UUID (FK → jobs) | Owning job |
| storage_uri | TEXT | GCS path, e.g. `raw/2026/abc123.csv` |
| original_name | TEXT | User's filename |
| sha256 | TEXT | Integrity hash (duplicate detection) |
| file_size | BIGINT | Bytes |
| mime_type | TEXT | Detected MIME type |
| meta_data | JSONB | Import source, encoding, extra info |
| created_at | TIMESTAMPTZ | Upload timestamp |

**Indexes:** job_id, sha256

---

## Table: `control.reader_profiles`

Parser rules detected during P2a (format recognition). One profile per file.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Profile identifier |
| file_id | UUID (FK → files) | Source file |
| rules | JSONB | Delimiter, encoding, date format, column mapping, unit, timezone |
| technical_quality | JSONB | Row counts (valid/invalid), warnings, detection confidence |
| is_override | BOOLEAN | True if manually corrected via PUT endpoint |
| created_at | TIMESTAMPTZ | Detection timestamp |

**rules JSONB structure:**
```json
{
  "delimiter": ";",
  "encoding": "UTF-8",
  "date_format": "DD.MM.YYYY",
  "time_format": "HH:MM",
  "decimal_separator": ",",
  "unit_detected": "kWh",
  "timezone": "Europe/Berlin",
  "cumulative": false,
  "header_row": 0,
  "column_mapping": {
    "timestamp": 0,
    "value": 1
  }
}
```

---

## Table: `control.holidays`

Cached holiday data for calendar/bridge-day logic.

| Column | Type | Description |
|--------|------|-------------|
| date | DATE (PK part) | Holiday date |
| state_code | TEXT (PK part) | ISO state code (DE, BY, NW, ...) or 'DE' for federal |
| name | TEXT | Holiday name |
| is_custom | BOOLEAN | True if manually added (Betriebsferien) |
| year | INT | Year (for indexing) |

**Indexes:** (date, state_code) PK, year
