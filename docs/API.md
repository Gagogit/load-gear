# LOAD-GEAR API-Dokumentation

> Version 0.1.0 — Stand: März 2026

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Architektur & Datenfluss](#2-architektur--datenfluss)
3. [Technische Grundlagen](#3-technische-grundlagen)
4. [Datenmodell](#4-datenmodell)
5. [API-Referenz](#5-api-referenz)
   - [Admin](#51-admin)
   - [Jobs](#52-jobs)
   - [Files](#53-files)
   - [Ingest](#54-ingest)
   - [QA](#55-qa)
   - [Analysis](#56-analysis)
   - [Forecasts](#57-forecasts)
   - [HPFC](#58-hpfc)
   - [Financial](#59-financial)
   - [Pipeline](#510-pipeline)
   - [Weather](#511-weather)
6. [Fehlercodes](#6-fehlercodes)

---

## 1. Übersicht

**LOAD-GEAR Energy Intelligence** ist eine Plattform zur Verarbeitung von Energiezähler-Messdaten. Sie deckt den gesamten Workflow ab:

- **Datenimport** — CSV/Excel-Dateien mit Lastgangdaten einlesen und normalisieren
- **Qualitätsprüfung** — 9 automatische Checks (Vollständigkeit, Ausreißer, Lücken, …)
- **Analyse & Imputation** — Tagtyp-Klassifikation (9 Typen), Lücken auffüllen (v2)
- **Prognose** — Day-Matching-Verfahren erzeugt Lastprognose (v3) mit konfigurierbarem Horizont
- **Finanzkalkulation** — Prognose × HPFC-Preiskurve = Beschaffungskosten, Multi-Provider-Vergleich
- **Wetterdaten** — DWD-Stationsdaten importieren und verwalten

### Zentrale Konzepte

| Konzept | Beschreibung |
|---------|-------------|
| **Job** | Zentrale Verarbeitungseinheit. Jeder Workflow wird durch einen Job gesteuert. |
| **MaLo-ID** | Marktlokations-ID (Zählpunkt-Kennung) — identifiziert den Messpunkt. |
| **Datenversionen** | v1 = Rohdaten (normalisiert), v2 = bereinigt/imputiert, v3 = Prognose |
| **HPFC** | Hourly Price Forward Curve — stündliche Strompreis-Prognose je Anbieter |
| **Provider** | Stromanbieter-Kennung für Multi-Provider-Preisvergleich |

---

## 2. Architektur & Datenfluss

```
CSV/Excel  ──►  Ingest (P2)  ──►  QA (P3)  ──►  Analysis (P4)  ──►  Forecast (P5)  ──►  Financial (P6)
                   │                  │                │                    │                    │
                   ▼                  ▼                ▼                    ▼                    ▼
                v1 Reads         QA-Findings      v2 Reads +          v3 Forecast         Kosten-
              (meter_reads)    (quality_findings)  Tagtypen +          (forecast_series)    berechnung
                                                   Profil                                  (financial_runs)
```

### Phasen-Details

| Phase | Name | Input | Output | Job-Status |
|-------|------|-------|--------|------------|
| P2 | Ingest | CSV/Excel-Datei | Normalisierte v1-Zeitreihe | `pending` → `ingesting` |
| P3 | QA | v1-Zeitreihe | 9 Prüf-Findings | `ingesting` → `qa_running` |
| P4 | Analysis | v1 + QA-Ergebnisse | v2-Zeitreihe + Tagtypen + Profil | `qa_running` → `analysis_running` |
| P5 | Forecast | v2-Zeitreihe | v3-Prognose (Day-Matching) | `analysis_running` → `forecast_running` |
| P6 | Financial | v3 + HPFC-Preise | Kostenberechnung je Provider | `forecast_running` → `financial_running` |

### Job-Zustandsmaschine

```
pending → ingesting → qa_running → analysis_running → forecast_running → financial_running → done
                                                                                            → warn
jeder Zustand kann → failed
```

Terminale Zustände: `done`, `warn`, `failed`.

---

## 3. Technische Grundlagen

### Base-URL

```
http://localhost:8000/api/v1
```

### Content-Types

| Richtung | Format |
|----------|--------|
| Request-Body | `application/json` (außer File-Upload: `multipart/form-data`) |
| Response-Body | `application/json` |
| CSV-Export | `text/csv` (UTF-8 BOM, Semikolon-Trennzeichen, Dezimalkomma) |

### Authentifizierung

In v0.1.0 ist **keine Authentifizierung** implementiert. CORS ist auf `*` gesetzt (alle Origins erlaubt).

### Pagination

Endpunkte mit Listendaten unterstützen:

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 50–1000 | Maximale Anzahl Ergebnisse (je nach Endpoint 1–200 oder 1–10000) |
| `offset` | int | 0 | Offset für Pagination |

### Fehlerformat

Alle Fehler werden als JSON zurückgegeben:

```json
{
  "detail": "Fehlermeldung als String"
}
```

---

## 4. Datenmodell

### 3 Schemas, 14 Tabellen

#### Schema `control` — Steuerung

| Tabelle | Beschreibung | PK |
|---------|-------------|-----|
| `jobs` | Verarbeitungsaufträge | `id` (UUID) |
| `files` | Hochgeladene Quelldateien | `id` (UUID) |
| `reader_profiles` | Erkannte/überschriebene Parsing-Regeln | `id` (UUID) |
| `holidays` | Feiertage je Bundesland | `id` (serial) |

#### Schema `data` — Zeitreihen (TimescaleDB Hypertables)

| Tabelle | Beschreibung | PK |
|---------|-------------|-----|
| `meter_reads` | Normalisierte Lastgangdaten (v1 + v2) | `(ts_utc, meter_id, version)` |
| `weather_observations` | DWD-Wetterdaten je Station | `(ts_utc, station_id)` |
| `forecast_runs` | Prognose-Metadaten | `id` (UUID) |
| `forecast_series` | Prognose-Zeitreihe (v3) | `(ts_utc, forecast_id)` |
| `hpfc_snapshots` | HPFC-Preiskurven-Metadaten | `id` (UUID) |
| `hpfc_series` | Stündliche HPFC-Preise | `(ts_utc, snapshot_id)` |
| `financial_runs` | Kostenkalkulation je Provider | `id` (UUID) |

#### Schema `analysis` — Analyseergebnisse

| Tabelle | Beschreibung | PK |
|---------|-------------|-----|
| `analysis_profiles` | Tagtyp-Fingerprints, Saisonalität, Impute-Policy | `id` (UUID) |
| `quality_findings` | Ergebnisse der 9 QA-Checks | `id` (UUID) |
| `imputation_runs` | Imputation-Protokoll (Slots, Methoden) | `id` (UUID) |

### Quality-Flag-Werte (meter_reads)

| Flag | Bedeutung |
|------|----------|
| 0 | Original (Rohdaten) |
| 1 | Interpoliert |
| 2 | Profil-basiert ersetzt |
| 3 | Wetterbasiert ersetzt |

### 9 Tagtypen (Day Classifier)

Störung, Feiertag, Brückentag, Sonntag, Samstag, Werktag-nach-Frei, Werktag-vor-Frei, Werktag-Sommer, Werktag-Winter

---

## 5. API-Referenz

### 5.1 Admin

Basis-Pfad: `/api/v1/admin`

---

#### `GET /api/v1/admin/health`

Health-Check: prüft die Datenbankverbindung.

**Response** `200 OK`

```json
{
  "status": "ok",
  "database": "connected"
}
```

Wenn DB nicht erreichbar:

```json
{
  "status": "degraded",
  "database": "unreachable"
}
```

---

#### `GET /api/v1/admin/config`

Aktuelle QA-Schwellwerte auslesen.

**Response** `200 OK` — `AdminConfigResponse`

```json
{
  "min_kw": 0.0,
  "max_kw": 10000.0,
  "max_jump_kw": 5000.0,
  "top_n_peaks": 10,
  "min_completeness_pct": 95.0,
  "max_gap_duration_min": 180
}
```

---

#### `PUT /api/v1/admin/config`

QA-Schwellwerte aktualisieren.

**Request-Body** — `AdminConfigResponse`

```json
{
  "min_kw": 0.0,
  "max_kw": 15000.0,
  "max_jump_kw": 8000.0,
  "top_n_peaks": 5,
  "min_completeness_pct": 90.0,
  "max_gap_duration_min": 240
}
```

**Response** `200 OK` — Aktualisierte Konfiguration (gleiches Schema).

---

### 5.2 Jobs

Basis-Pfad: `/api/v1/jobs`

---

#### `POST /api/v1/jobs`

Neuen Verarbeitungsjob erstellen.

**Request-Body** — `JobCreateRequest`

| Feld | Typ | Pflicht | Default | Beschreibung |
|------|-----|---------|---------|-------------|
| `project_name` | string | nein | `""` | Projektname |
| `meter_id` | string | **ja** | — | MaLo/Zählpunkt-Kennung (max 100 Zeichen) |
| `company_id` | string | nein | `null` | Firmenkennung |
| `plz` | string | nein | `null` | Postleitzahl (5 Zeichen) |
| `user_id` | string | nein | `""` | Benutzerkennung |
| `tasks` | string[] | nein | `["Statistik"]` | Aufgaben: Statistik, Fehleranalyse, Imputation, Prognose, Aggregation |
| `horizon_months` | int | nein | `null` | Prognosehorizont in Monaten (1–60) |
| `unit` | string | nein | `null` | Zieleinheit: `kW` oder `kWh` |
| `interval_minutes` | int | nein | `null` | Zielintervall: `15` oder `60` |
| `scenarios` | object | nein | `null` | Szenario-Parameter (PV, Batterie, …) |

**Beispiel-Request**

```json
{
  "project_name": "Bürogebäude Berlin",
  "meter_id": "DE0001234567890000000000000012345",
  "company_id": "ACME-001",
  "plz": "10115",
  "tasks": ["Aggregation"],
  "horizon_months": 12
}
```

**Response** `201 Created` — `JobResponse`

```json
{
  "id": "a1b2c3d4-...",
  "status": "pending",
  "project_name": "Bürogebäude Berlin",
  "company_id": "ACME-001",
  "meter_id": "DE0001234567890000000000000012345",
  "plz": "10115",
  "user_id": "",
  "current_phase": null,
  "error_message": null,
  "created_at": "2026-03-01T12:00:00Z",
  "updated_at": "2026-03-01T12:00:00Z"
}
```

---

#### `GET /api/v1/jobs`

Jobs auflisten (mit optionalen Filtern).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `status` | string | `null` | Filter nach Status (pending, ingesting, done, …) |
| `company_id` | string | `null` | Filter nach Firma |
| `meter_id` | string | `null` | Filter nach Zählpunkt |
| `limit` | int | 50 | Max. Ergebnisse (1–200) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `JobListResponse`

```json
{
  "items": [ { "id": "...", "status": "done", ... } ],
  "total": 42
}
```

---

#### `GET /api/v1/jobs/{job_id}`

Job-Details inkl. Payload abrufen.

**Path-Parameter**

| Parameter | Typ | Beschreibung |
|-----------|-----|-------------|
| `job_id` | UUID | Job-ID |

**Response** `200 OK` — `JobDetailResponse` (wie `JobResponse` + `payload`-Feld)

---

#### `DELETE /api/v1/jobs/{job_id}`

Job löschen (nur `pending` oder `failed`).

**Response** `200 OK`

```json
{
  "detail": "Job a1b2c3d4-... deleted"
}
```

**Fehler** `404` wenn Job nicht existiert.

---

### 5.3 Files

Basis-Pfad: `/api/v1/files`

---

#### `POST /api/v1/files/upload`

Quelldatei (CSV/Excel) hochladen. Deduplizierung über SHA-256.

**Content-Type:** `multipart/form-data`

**Parameter**

| Parameter | Typ | In | Pflicht | Beschreibung |
|-----------|-----|-----|---------|-------------|
| `file` | binary | form-data | **ja** | Die Datei |
| `job_id` | UUID | query | **ja** | Zugehöriger Job |

**Beispiel (curl)**

```bash
curl -X POST "http://localhost:8000/api/v1/files/upload?job_id=<UUID>" \
  -F "file=@lastgang.csv"
```

**Response** `201 Created` — `FileUploadResponse`

```json
{
  "id": "f1e2d3c4-...",
  "sha256": "abc123...",
  "original_name": "lastgang.csv",
  "file_size": 102400,
  "duplicate": false
}
```

Bei Duplikat: `duplicate: true`, vorhandene Datei-ID wird zurückgegeben.

---

#### `GET /api/v1/files/{file_id}`

Datei-Metadaten abrufen.

**Response** `200 OK` — `FileResponse`

```json
{
  "id": "f1e2d3c4-...",
  "job_id": "a1b2c3d4-...",
  "storage_uri": "local://raw/2026/f1e2d3c4.csv",
  "original_name": "lastgang.csv",
  "sha256": "abc123...",
  "file_size": 102400,
  "mime_type": "text/csv",
  "meta_data": null,
  "created_at": "2026-03-01T12:00:00Z"
}
```

**Fehler** `404` wenn Datei nicht existiert.

---

#### `GET /api/v1/files/{file_id}/download`

Originaldatei herunterladen.

**Response** `200 OK` — Binärdaten mit `Content-Disposition: attachment`.

**Fehler** `404` wenn Datei nicht existiert.

---

#### `GET /api/v1/files/{file_id}/reader-profile`

Erkannte oder manuell überschriebene Parsing-Regeln für eine Datei abrufen.

**Response** `200 OK` — `ReaderProfileResponse`

```json
{
  "id": "...",
  "file_id": "f1e2d3c4-...",
  "rules": {
    "encoding": "utf-8",
    "delimiter": ";",
    "header_row": 0,
    "timestamp_columns": ["Datum", "Zeit"],
    "value_column": "Wert",
    "date_format": "%d.%m.%Y",
    "time_format": "%H:%M",
    "decimal_separator": ",",
    "unit": "kW",
    "series_type": "interval",
    "timezone": "Europe/Berlin"
  },
  "technical_quality": { ... },
  "is_override": false,
  "created_at": "2026-03-01T12:05:00Z"
}
```

**Fehler** `404` wenn Datei oder Profil nicht existiert.

---

#### `PUT /api/v1/files/{file_id}/reader-profile`

Parsing-Regeln manuell überschreiben (setzt `is_override: true`).

**Request-Body** — `ReaderProfileOverrideRequest`

```json
{
  "rules": {
    "encoding": "iso-8859-1",
    "delimiter": ";",
    "header_row": 2,
    "timestamp_columns": ["Datum"],
    "value_column": "Verbrauch",
    "date_format": "%d.%m.%Y %H:%M",
    "time_format": "%H:%M",
    "decimal_separator": ",",
    "unit": "kWh",
    "series_type": "cumulative",
    "timezone": "Europe/Berlin"
  }
}
```

**Response** `200 OK` — `ReaderProfileResponse` (aktualisiert).

---

### 5.4 Ingest

Basis-Pfad: `/api/v1/ingest`

---

#### `POST /api/v1/ingest`

Ingest-Pipeline starten: Formaterkennung (P2a) + Normalisierung (P2b).

**Request-Body** — `IngestRequest`

```json
{
  "job_id": "a1b2c3d4-...",
  "file_id": "f1e2d3c4-..."
}
```

**Response** `202 Accepted`

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "completed",
  "total_rows": 35040,
  "valid_rows": 35040,
  "invalid_rows": 0
}
```

**Fehlercodes**

| Code | Bedingung |
|------|----------|
| 404 | Job oder Datei nicht gefunden |
| 409 | Job nicht im Status `pending` |
| 422 | Parsing/Normalisierungsfehler |

---

#### `GET /api/v1/ingest/{job_id}/status`

Ingest-Status für einen Job abfragen.

**Response** `200 OK` — `IngestStatusResponse`

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "ingesting",
  "current_phase": "ingesting",
  "total_rows": 35040,
  "valid_rows": 35040,
  "invalid_rows": 0,
  "warnings": [],
  "error_message": null
}
```

---

#### `GET /api/v1/ingest/{job_id}/normalized`

Normalisierte v1-Messdaten abrufen (paginiert).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 1000 | Max. Zeilen (1–10000) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `NormalizedListResponse`

```json
{
  "items": [
    {
      "ts_utc": "2025-01-01T00:00:00Z",
      "meter_id": "DE001...",
      "value": 42.5,
      "unit": "kW",
      "version": 1,
      "quality_flag": 0
    }
  ],
  "total": 35040
}
```

---

### 5.5 QA

Basis-Pfad: `/api/v1/qa`

---

#### `POST /api/v1/qa`

QA-Lauf starten (alle 9 Prüfungen).

**Request-Body** — `QARunRequest`

```json
{
  "job_id": "a1b2c3d4-..."
}
```

**Response** `202 Accepted`

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "completed",
  "overall_status": "ok",
  "checks_completed": 9
}
```

**9 QA-Checks:** Vollständigkeit, Zeitstempel-Lücken, Wertebereich, Sprünge, Peaks, Nullwerte, Duplikate, Lastprofil, Konsistenz.

**Fehlercodes:** `404` (Job nicht gefunden), `409` (falscher Status), `422` (Prüffehler).

---

#### `GET /api/v1/qa/{job_id}/status`

QA-Status abfragen.

**Response** `200 OK` — `QAStatusResponse`

```json
{
  "job_id": "...",
  "status": "qa_running",
  "checks_completed": 5,
  "checks_total": 9,
  "overall_status": null,
  "error_message": null
}
```

---

#### `GET /api/v1/qa/{job_id}/report`

Vollständigen QA-Bericht mit allen 9 Check-Ergebnissen abrufen.

**Response** `200 OK` — `QAReportResponse`

```json
{
  "job_id": "...",
  "findings": [
    {
      "id": "...",
      "job_id": "...",
      "check_id": 1,
      "check_name": "completeness",
      "status": "ok",
      "metric_key": "completeness_pct",
      "metric_value": 99.5,
      "threshold": 95.0,
      "affected_slots": null,
      "recommendation": null,
      "created_at": "2026-03-01T12:10:00Z"
    }
  ],
  "overall_status": "ok",
  "created_at": "2026-03-01T12:10:00Z"
}
```

**Fehler** `404` wenn Job oder Findings nicht existieren.

---

#### `GET /api/v1/qa/{job_id}/findings`

Einzelne QA-Findings als Liste abrufen.

**Response** `200 OK` — `QAFindingResponse[]`

**Fehler** `404` wenn keine Findings für den Job vorhanden.

---

#### `GET /api/v1/qa/{job_id}/profile`

Stunden- und Wochentagsprofil aus QA-Check 8.

**Response** `200 OK` — `QAProfileResponse`

```json
{
  "job_id": "...",
  "hourly_profile": [12.3, 11.8, 10.5, ...],
  "weekday_profile": [45.2, 46.1, 44.8, 43.9, 42.1, 30.5, 28.0]
}
```

`hourly_profile`: 24 Werte (Stunde 0–23). `weekday_profile`: 7 Werte (Mo=0 … So=6).

---

### 5.6 Analysis

Basis-Pfad: `/api/v1/analysis`

---

#### `POST /api/v1/analysis`

Analyse-Lauf starten (P4.1 Tagtypen → P4.2 Wetter → P4.3 Assets → P4.4 Imputation).

**Request-Body** — `AnalysisRunRequest`

```json
{
  "job_id": "a1b2c3d4-..."
}
```

**Response** `202 Accepted`

```json
{
  "job_id": "...",
  "status": "completed",
  "profile_id": "...",
  "imputation_run_id": "..."
}
```

**Fehlercodes:** `404`, `409`, `422` (analog zu QA/Ingest).

---

#### `GET /api/v1/analysis/{job_id}/status`

Analyse-Status abfragen.

**Response** `200 OK` — `AnalysisStatusResponse`

```json
{
  "job_id": "...",
  "status": "analysis_running",
  "current_phase": "analysis_running",
  "sub_phase": "P4.2",
  "error_message": null
}
```

---

#### `GET /api/v1/analysis/{job_id}/profile`

Analyse-Profil abrufen (Tagtyp-Fingerprints, Saisonalität, Wetter-Korrelationen).

**Response** `200 OK` — `AnalysisProfileResponse`

```json
{
  "job_id": "...",
  "meter_id": "DE001...",
  "day_fingerprints": {
    "Werktag-Winter": { "avg_kw": [10.2, 9.8, ...], "count": 120 },
    "Samstag": { "avg_kw": [5.1, 4.8, ...], "count": 52 }
  },
  "seasonality": { ... },
  "weather_correlations": { "temp_sensitivity": null, "data_available": false },
  "asset_hints": null,
  "impute_policy": { ... },
  "created_at": "2026-03-01T12:15:00Z"
}
```

---

#### `GET /api/v1/analysis/{job_id}/day-labels`

Tagtyp-Klassifikation für alle Tage abrufen.

**Response** `200 OK` — `DayLabelsResponse`

```json
{
  "job_id": "...",
  "labels": [
    { "date": "2025-01-01", "label": "Feiertag", "confidence": 1.0 },
    { "date": "2025-01-02", "label": "Werktag-nach-Frei", "confidence": 0.95 }
  ],
  "total": 365
}
```

---

#### `GET /api/v1/analysis/{job_id}/weather`

Wetter-Features und -Korrelationen abrufen.

**Response** `200 OK`

```json
{
  "job_id": "...",
  "features": [],
  "correlations": { "temp_sensitivity": null, "data_available": false }
}
```

> In v0.1 sind noch keine Wetter-Features verfügbar (`features` ist leer).

---

#### `GET /api/v1/analysis/{job_id}/imputation`

Imputations-Bericht abrufen.

**Response** `200 OK` — `ImputationReportResponse`

```json
{
  "job_id": "...",
  "slots_replaced": 48,
  "method_summary": {
    "profile": 30,
    "interpolation": 18,
    "weather": 0
  },
  "total_v2_rows": 35040
}
```

---

#### `GET /api/v1/analysis/{job_id}/normalized-v2`

Bereinigte v2-Zeitreihe abrufen (paginiert).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 1000 | Max. Zeilen (1–10000) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `NormalizedV2Response`

```json
{
  "items": [
    {
      "ts_utc": "2025-01-01T00:00:00Z",
      "meter_id": "DE001...",
      "value": 42.5,
      "unit": "kW",
      "version": 2,
      "quality_flag": 0
    }
  ],
  "total": 35040
}
```

---

### 5.7 Forecasts

Basis-Pfad: `/api/v1/forecasts`

---

#### `POST /api/v1/forecasts`

Prognose starten (Day-Matching-Verfahren).

**Request-Body** — `ForecastRunRequest`

| Feld | Typ | Pflicht | Default | Beschreibung |
|------|-----|---------|---------|-------------|
| `job_id` | UUID | **ja** | — | Job-ID |
| `horizon_start` | datetime | nein | `null` | Start des Prognosehorizonts (auto wenn null) |
| `horizon_end` | datetime | nein | `null` | Ende des Prognosehorizonts (auto wenn null) |
| `strategies` | string[] | nein | `["dst_correct"]` | Post-Processing-Strategien |
| `quantiles` | float[] | nein | `[0.1, 0.5, 0.9]` | Prognose-Quantile |

**Beispiel**

```json
{
  "job_id": "a1b2c3d4-...",
  "horizon_start": "2026-01-01T00:00:00",
  "horizon_end": "2026-12-31T23:45:00",
  "strategies": ["dst_correct"]
}
```

**Response** `202 Accepted`

```json
{
  "job_id": "...",
  "forecast_run_id": "...",
  "status": "ok",
  "total_rows": 35040
}
```

**Fehlercodes:** `404`, `409`, `422`.

---

#### `GET /api/v1/forecasts/{job_id}/status`

Prognose-Status abfragen.

**Response** `200 OK` — `ForecastStatusResponse`

```json
{
  "job_id": "...",
  "status": "forecast_running",
  "current_phase": "forecast_running",
  "forecast_run_id": null,
  "error_message": null
}
```

---

#### `GET /api/v1/forecasts/{job_id}/run`

Prognose-Run-Metadaten abrufen.

**Response** `200 OK`

```json
{
  "id": "...",
  "job_id": "...",
  "meter_id": "DE001...",
  "status": "ok",
  "horizon_start": "2026-01-01T00:00:00+00:00",
  "horizon_end": "2026-12-31T23:45:00+00:00",
  "model_alias": "day_match",
  "data_snapshot_id": "abc123",
  "strategies": ["dst_correct"],
  "quantiles": [0.1, 0.5, 0.9],
  "created_at": "2026-03-01T12:20:00+00:00",
  "completed_at": "2026-03-01T12:20:05+00:00"
}
```

---

#### `GET /api/v1/forecasts/{job_id}/series`

Prognose-Zeitreihe (v3) abrufen (paginiert).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 1000 | Max. Zeilen (1–10000) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `ForecastSeriesListResponse`

```json
{
  "job_id": "...",
  "forecast_id": "...",
  "rows": [
    {
      "ts_utc": "2026-01-01T00:00:00Z",
      "y_hat": 42.5,
      "q10": 42.5,
      "q50": 42.5,
      "q90": 42.5
    }
  ],
  "total": 35040
}
```

> Day-Matching ist deterministisch: `q10 = q50 = q90 = y_hat`.

---

#### `GET /api/v1/forecasts/{job_id}/summary`

Zusammenfassungsstatistiken (Min/Max/Mean je Quantil).

**Response** `200 OK` — `ForecastSummaryResponse`

```json
{
  "job_id": "...",
  "forecast_id": "...",
  "total_rows": 35040,
  "y_hat": { "min": 5.2, "max": 120.0, "mean": 42.5 },
  "q10": { "min": 5.2, "max": 120.0, "mean": 42.5 },
  "q50": { "min": 5.2, "max": 120.0, "mean": 42.5 },
  "q90": { "min": 5.2, "max": 120.0, "mean": 42.5 }
}
```

---

### 5.8 HPFC

Basis-Pfad: `/api/v1/hpfc`

---

#### `POST /api/v1/hpfc/upload`

HPFC-Preiskurve als CSV hochladen.

**Content-Type:** `multipart/form-data`

**Parameter**

| Parameter | Typ | In | Pflicht | Default | Beschreibung |
|-----------|-----|-----|---------|---------|-------------|
| `file` | binary | form-data | **ja** | — | CSV-Datei mit stündlichen Preisen (EUR/MWh) |
| `provider_id` | string | query | nein | `"manual"` | Anbieter-Kennung |
| `curve_type` | string | query | nein | `"HPFC"` | Kurventyp: HPFC, Spot, Intraday |
| `currency` | string | query | nein | `"EUR"` | Währungscode |

**Beispiel (curl)**

```bash
curl -X POST "http://localhost:8000/api/v1/hpfc/upload?provider_id=vattenfall&curve_type=HPFC" \
  -F "file=@hpfc_2026.csv"
```

**Response** `201 Created` — `HpfcUploadResponse`

```json
{
  "snapshot_id": "...",
  "provider_id": "vattenfall",
  "rows_imported": 8760,
  "delivery_start": "2026-01-01T00:00:00",
  "delivery_end": "2026-12-31T23:00:00"
}
```

**Fehler** `422` bei ungültigem CSV-Format.

---

#### `GET /api/v1/hpfc`

Alle HPFC-Snapshots auflisten.

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 50 | Max. Ergebnisse (1–200) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `HpfcSnapshotListResponse`

```json
{
  "items": [
    {
      "id": "...",
      "provider_id": "vattenfall",
      "snapshot_at": "2026-03-01T10:00:00Z",
      "curve_type": "HPFC",
      "delivery_start": "2026-01-01T00:00:00",
      "delivery_end": "2026-12-31T23:00:00",
      "currency": "EUR",
      "file_id": null
    }
  ],
  "total": 3
}
```

---

#### `GET /api/v1/hpfc/providers`

Alle vorhandenen HPFC-Provider-IDs auflisten.

**Response** `200 OK` — `ProviderListResponse`

```json
{
  "providers": ["baseline", "vattenfall", "eon"]
}
```

---

#### `GET /api/v1/hpfc/{snapshot_id}`

HPFC-Snapshot-Metadaten abrufen.

**Response** `200 OK` — `HpfcSnapshotResponse`

**Fehler** `404` wenn Snapshot nicht existiert.

---

#### `GET /api/v1/hpfc/{snapshot_id}/series`

HPFC-Preisreihe eines Snapshots abrufen (paginiert).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `limit` | int | 1000 | Max. Zeilen (1–10000) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `HpfcSeriesListResponse`

```json
{
  "snapshot_id": "...",
  "rows": [
    { "ts_utc": "2026-01-01T00:00:00Z", "price_mwh": 85.50 },
    { "ts_utc": "2026-01-01T01:00:00Z", "price_mwh": 82.30 }
  ],
  "total": 8760
}
```

---

#### `DELETE /api/v1/hpfc/{snapshot_id}`

HPFC-Snapshot und zugehörige Preisreihe löschen.

**Response** `204 No Content`

**Fehler** `404` wenn Snapshot nicht existiert.

---

### 5.9 Financial

Basis-Pfad: `/api/v1/financial`

---

#### `POST /api/v1/financial/calculate`

Finanzkalkulation starten. Unterstützt Multi-Provider-Berechnung. Baseline wird immer berechnet.

**Request-Body** — `FinancialCalcRequest`

| Feld | Typ | Pflicht | Default | Beschreibung |
|------|-----|---------|---------|-------------|
| `job_id` | UUID | **ja** | — | Job-ID |
| `snapshot_id` | UUID | nein | `null` | Bestimmter HPFC-Snapshot (auto wenn null) |
| `provider_ids` | string[] | nein | `null` | Provider-IDs für Multi-Provider-Vergleich |

**Beispiel**

```json
{
  "job_id": "a1b2c3d4-...",
  "provider_ids": ["vattenfall", "eon", "enBW"]
}
```

**Response** `202 Accepted`

```json
{
  "job_id": "...",
  "status": "completed",
  "results": [
    { "provider_id": "baseline", "status": "ok", "total_cost_eur": 125000.50 },
    { "provider_id": "vattenfall", "status": "ok", "total_cost_eur": 118500.20 },
    { "provider_id": "eon", "status": "error", "error": "No HPFC snapshot for provider eon" }
  ]
}
```

**Fehlercodes:** `404`, `409`, `422`.

**Kostenberechnung:**
- `consumption_kwh = y_hat × (interval_minutes / 60)`
- `cost_eur = (consumption_kwh / 1000) × price_mwh`

---

#### `GET /api/v1/financial/{job_id}/result`

Alle Finanzergebnisse (Multi-Provider) abrufen.

**Response** `200 OK` — `FinancialMultiResultResponse`

```json
{
  "job_id": "...",
  "results": [
    {
      "provider_id": "baseline",
      "calc_id": "...",
      "status": "ok",
      "total_cost_eur": 125000.50,
      "monthly_summary": [
        {
          "month": "2026-01",
          "total_cost_eur": 12500.00,
          "total_kwh": 150000.0,
          "avg_price_mwh": 83.33
        }
      ]
    }
  ]
}
```

---

#### `GET /api/v1/financial/{job_id}/result/{provider_id}`

Finanzergebnis für einen bestimmten Provider mit Kosten-Zeitreihe.

**Response** `200 OK` — `FinancialResultResponse`

```json
{
  "calc_id": "...",
  "job_id": "...",
  "provider_id": "vattenfall",
  "total_cost_eur": 118500.20,
  "monthly_summary": [ ... ],
  "rows": [
    {
      "ts_utc": "2026-01-01T00:00:00Z",
      "consumption_kwh": 10.625,
      "price_mwh": 85.50,
      "cost_eur": 0.9084
    }
  ]
}
```

---

#### `GET /api/v1/financial/{job_id}/export`

Finanzergebnis als CSV oder XLSX exportieren.

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `format` | string | `"csv"` | Exportformat: `csv` oder `xlsx` |
| `provider_id` | string | `null` | Provider-ID (Default: jüngster) |

**Response** `200 OK` — Datei-Download mit `Content-Disposition: attachment`.

CSV-Format: Semikolon-Trennzeichen, Dezimalkomma, UTF-8 BOM.

---

### 5.10 Pipeline

Basis-Pfad: `/api/v1/pipeline`

---

#### `POST /api/v1/pipeline/run`

Gesamte Pipeline in einem Schritt ausführen: Upload → Ingest → QA → Analysis → Forecast → Financial.

**Content-Type:** `multipart/form-data`

**Parameter**

| Parameter | Typ | In | Pflicht | Default | Beschreibung |
|-----------|-----|-----|---------|---------|-------------|
| `project_name` | string | form | **ja** | — | Projektname |
| `malo_id` | string | form | **ja** | — | MaLo/Zählpunkt-ID |
| `plz` | string | form | nein | `""` | Postleitzahl |
| `user_id` | string | form | nein | `""` | Benutzerkennung |
| `prognosis_from` | string | form | nein | `""` | Prognosehorizont Start (ISO 8601) |
| `prognosis_to` | string | form | nein | `""` | Prognosehorizont Ende (ISO 8601) |
| `growth_pct` | float | form | nein | `100.0` | Wachstumsfaktor in Prozent (100 = unverändert) |
| `provider_ids` | string | form | nein | `""` | Komma-getrennte Provider-IDs für Multi-Provider |
| `file` | binary | form | **ja** | — | CSV/Excel-Lastgangdatei |

**Beispiel (curl)**

```bash
curl -X POST "http://localhost:8000/api/v1/pipeline/run" \
  -F "project_name=Bürogebäude Berlin" \
  -F "malo_id=DE0001234567890000000000000012345" \
  -F "plz=10115" \
  -F "prognosis_from=2026-01-01" \
  -F "prognosis_to=2026-12-31" \
  -F "growth_pct=105.0" \
  -F "provider_ids=vattenfall,eon" \
  -F "file=@lastgang.csv"
```

**Response** `202 Accepted`

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "done",
  "phases_completed": ["ingest", "qa", "analysis", "forecast", "financial"]
}
```

---

#### `GET /api/v1/pipeline/{job_id}/status`

Pipeline-Status mit 10 LED-Zuständen abfragen.

**Response** `200 OK` — `PipelineStatusResponse`

```json
{
  "job_id": "a1b2c3d4-...",
  "status": "done",
  "error_message": null,
  "error_context": null,
  "leds": {
    "upload": true,
    "format_detect": true,
    "normalize": true,
    "qa": true,
    "day_classify": true,
    "impute": true,
    "forecast": true,
    "financial": true,
    "export": true,
    "done": true
  }
}
```

Jede LED ist `true` (abgeschlossen) oder `false` (noch nicht erreicht/fehlgeschlagen).

---

#### `GET /api/v1/pipeline/{job_id}/download`

Pipeline-Ergebnis herunterladen. Gibt Financial-CSV zurück wenn vorhanden, sonst Forecast-CSV.

**Response** `200 OK` — CSV-Datei-Download.

- **Financial:** Semikolon-Trennzeichen, Dezimalkomma, UTF-8 BOM
- **Forecast-Fallback:** `ts_utc;y_hat;q10;q50;q90` (Semikolon, Dezimalkomma, UTF-8 BOM)

**Fehler** `404` wenn keine Ergebnisse vorhanden.

---

### 5.11 Weather

Basis-Pfad: `/api/v1/weather`

---

#### `POST /api/v1/weather/import`

DWD-Wetterdaten für eine Station importieren.

**Request-Body** — `WeatherImportRequest`

| Feld | Typ | Pflicht | Default | Beschreibung |
|------|-----|---------|---------|-------------|
| `station_id` | string | **ja** | — | DWD-Stations-ID (z.B. `"00433"`) |
| `lat` | float | **ja** | — | Breitengrad (-90 bis 90) |
| `lon` | float | **ja** | — | Längengrad (-180 bis 180) |
| `params` | string[] | nein | `["air_temperature", "solar"]` | DWD-Parameter zum Import |
| `start` | datetime | nein | `null` | Start-Filter (UTC) |
| `end` | datetime | nein | `null` | End-Filter (UTC) |

**Beispiel**

```json
{
  "station_id": "00433",
  "lat": 52.4537,
  "lon": 13.3017,
  "params": ["air_temperature", "solar"],
  "start": "2024-01-01T00:00:00Z",
  "end": "2025-12-31T23:00:00Z"
}
```

**Response** `202 Accepted` — `WeatherImportResponse`

```json
{
  "station_id": "00433",
  "total_inserted": 17520,
  "counts_per_param": {
    "air_temperature": 17520,
    "solar": 17520
  }
}
```

**Fehler** `422` bei Import-Fehler.

---

#### `GET /api/v1/weather/stations`

Alle Wetterstationen mit Beobachtungsstatistiken auflisten.

**Response** `200 OK` — `WeatherStationListResponse`

```json
{
  "items": [
    {
      "station_id": "00433",
      "obs_count": 17520,
      "earliest": "2024-01-01T00:00:00Z",
      "latest": "2025-12-31T23:00:00Z",
      "source": "dwd_cdc"
    }
  ],
  "total": 1
}
```

---

#### `GET /api/v1/weather/stations/{station_id}/observations`

Wetter-Beobachtungen einer Station abrufen (paginiert).

**Query-Parameter**

| Parameter | Typ | Default | Beschreibung |
|-----------|-----|---------|-------------|
| `start` | datetime | `null` | Start-Filter (UTC) |
| `end` | datetime | `null` | End-Filter (UTC) |
| `limit` | int | 1000 | Max. Zeilen (1–10000) |
| `offset` | int | 0 | Offset |

**Response** `200 OK` — `WeatherObservationListResponse`

```json
{
  "station_id": "00433",
  "items": [
    {
      "ts_utc": "2025-01-01T00:00:00Z",
      "station_id": "00433",
      "temp_c": -2.5,
      "ghi_wm2": 0.0,
      "wind_ms": 3.2,
      "cloud_pct": 80.0,
      "confidence": 1.0,
      "source": "dwd_cdc"
    }
  ],
  "total": 17520
}
```

---

#### `DELETE /api/v1/weather/stations/{station_id}`

Alle Beobachtungen einer Wetterstation löschen.

**Response** `204 No Content`

**Fehler** `404` wenn keine Daten für die Station vorhanden.

---

## 6. Fehlercodes

### HTTP-Statuscodes

| Code | Bedeutung | Typische Ursache |
|------|----------|-----------------|
| 200 | OK | Erfolgreiche Abfrage |
| 201 | Created | Ressource erfolgreich erstellt |
| 202 | Accepted | Asynchroner Vorgang gestartet |
| 204 | No Content | Erfolgreiche Löschung |
| 404 | Not Found | Job, Datei, Snapshot, etc. nicht gefunden |
| 409 | Conflict | Job nicht im erwarteten Status für diese Operation |
| 422 | Unprocessable Entity | Ungültige Eingabedaten, Parsing-/Berechnungsfehler |
| 500 | Internal Server Error | Unbehandelte Ausnahme (wird als JSON zurückgegeben) |

### Fehler-Response-Format

Alle Fehler folgen dem gleichen Format:

```json
{
  "detail": "Beschreibung des Fehlers"
}
```

Bei `500`-Fehlern wird der interne Fehler durch den globalen Exception-Handler abgefangen und ebenfalls als JSON zurückgegeben (kein HTML).

### Job-Statusfehler (409)

Jede Phasen-Operation erwartet den Job in einem bestimmten Status:

| Operation | Erwarteter Status |
|-----------|------------------|
| Ingest starten | `pending` |
| QA starten | `qa_running` (wird intern nach Ingest gesetzt) |
| Analysis starten | `analysis_running` |
| Forecast starten | `forecast_running` |
| Financial starten | `financial_running` |
