# Lastgang-Kalkulator: Fachlicher Ablauf (Agent-Kontext)

Sprache: Python | Stack: PostgreSQL \+ TimescaleDB \+ GCS/MinIO | Core-ML: Prophet   
Jede Phase ist ein eigenständiger Container-Service mit JSON-Input/Output.

---

## Phase 1 — INPUT (Eingabe & Parametrisierung)

**Zweck:** Auftrag aus Frontend erfassen → validiertes Job-JSON erzeugen.

**Input:** Nutzer-Formular (Web/Mobile, Spracheingabe, Drag-and-Drop)

**Kern-Parameter:**

- `meter_id` (MaLo/Zählpunkt), `company`, `plz`

- `horizon_start` / `horizon_end` (Prognosezeitraum)

- `unit` ∈ {kWh, kW}, `interval_min` (z. B. 15\)

- `tasks[]` ∈ {Statistik, Fehleranalyse, Umformatierung, Imputation, Prognose, Aggregation}

- `scenarios{}`: Wachstum %, PV an/aus, Speicher-Config

- `output_format` ∈ {CSV, , Excel, EDIFACT}

**Output:** Validiertes `job.json` mit `job_id` (UUID)

**Persistenz:** `PostgreSQL` → Schema `control`, Tabelle `jobs`

## 

## Phase 2 — HOMOGENISIERUNG (Eingangsanalyse \+ Normierung)

**Zweck:** Quelldatei erkennen, parsen und in einheitliches Arbeitsformat überführen.

**2a – Eingangsanalyse (Format-Erkennung):**

| Erkennungsaufgabe | Details |
| :---- | :---- |
| Dateityp | CSV / Excel / EDIFACT-MSCONS / TSV |
| Encoding | UTF-8, ISO-8859-1, Win-1252 (auto-detect) |
| Delimiter / Dezimal | `;` `,` `.` — Sniffing |
| Datumsformat | `DD.MM.YYYY`, `YYYY-MM-DD`, US `MM/DD` |
| Zeitformat | `00:15`, `0:15`, `AM/PM` |
| Einheit | kW vs. kWh vs. Wh (heuristisch) |
| Zeitzone / DST | Europe/Berlin → UTC-Mapping |
| Kumulation | kumulativ vs. Intervallwerte |

**Output `ReaderProfil`:** JSON mit allen erkannten Parser-Regeln \+ Warnungen

**2b – Homogenisierung (Normierung):**

Zielschema nach Parse:

meter\_id | ts\_utc | ts\_start | ts\_end | duration\_min | energy\_kWh | power\_kW | unit\_src | quality | src\_format | timezone

- Alle Timestamps → UTC (inkl. DST-Auflösung)

- Inklusiv/Exklusiv-Grenzen konsistent

- Normierung auf Intervallenergie

**Persistenz:**

- Original → GCS `raw/` (WORM, unveränderlich) \+ SHA-256

- Metadaten → `PostgreSQL` (`control.files`, `control.imports`)

- Parser-Entscheidungen → `PostgreSQL` (`control.import_rules`, `control.import_logs`)

- Normierte Serie → TimescaleDB \+ Object-Storage 

---

## 

## Phase 3 — QA / STATISTIK (Profil der Quelldatei)

**Zweck:** Objektiver Qualitätsbericht der homogenisierten Zeitreihe (9 Checks).

**Tool:** PostgreSQL \+ TimescaleDB (SQL-Aggregation)

| \# | Check | Kern-Output |
| :---- | :---- | :---- |
| 1 | Intervall-Vollzähligkeit | `interval_count_observed` vs `expected`, `delta` |
| 2 | Vollständigkeit % | `completeness_pct`, `missing_count`, Liste fehlender Slots |
| 3 | Lücken / Duplikate | `gap_count`, `gap_max_duration_min`, Duplikat-Zeitstempel-Liste |
| 4 | Tages-/Monatsenergie | `kwh_day[]`, `kwh_month[]`, `coverage_pct_day`, Flag `incomplete_sum` |
| 5 | Spitzenlast (kW) | `kw_peak_value`, `kw_peak_timestamp`, Top-N Peaks |
| 6 | Baseload | `kw_baseload` (P5/P10), optional Nacht 00–04 Uhr separat |
| 7 | Lastfaktor | `load_factor = kw_avg / kw_peak`, `stddev_kw` |
| 8 | Stunden-/Wochentag-Profil | 24-Werte-Stundenprofil, 7-Werte-WTG-Profil, opt. Heatmap |
| 9 | DST-Konformität | Je Umstelltag: `expected_local_slots` ∈ {92,96,100} vs. `observed`, `dst_mismatch` |

**Globale Konfig-Parameter:** Min/Max kW/kWh je Slot, Max-Sprung ΔkW, Imputations-Regel, Rundung, Top-N.

**Output:** QA-Report (JSON \+ opt. PDF/CSV)

**Persistenz:**

- QA-Lauf-Header → `PostgreSQL` (`quality_runs`)

- Findings/Kennzahlen → `PostgreSQL` (`quality_findings`)

- Unveränderlicher Report → GCS `reports/` (Artefakt)

- Korrigierte Serie → `normalized` \+ Verweis in `quality_runs`

---

## 

## Phase 4 — ANALYSE (Lastgang-Analyse & Datenqualität)

**Zweck:** Semantischen Fingerabdruck der Zeitreihe erzeugen → Grundlage für Imputation und Forecast.

**Tool:** Facebook Prophet (Python-Container, Prophet-Spezialist)

### 4.1 Tagesklassifizierung & Kalendermatching

- **Top-down:** Bekannte Spezialtage (Feiertage/Bundesland, Brückentage, Betriebsferien) → gezielte Prüfung

- **Bottom-up:** Ähnliche Lastformen clustern → Abgleich mit Kalendertabelle

- **Labels:** `Werktag-Sommer`, `Sonntag-Winter`, `Feiertag`, `Brückentag`, `Störung` etc.

- **Store:** `day_labels` (SQL), `reports/.../day_fingerprints.json`

### 4.2 Wetteranreicherung

- **Features:** Temp (dry-bulb), GHI, Bewölkung, Wind, Niederschlag, Sonnenauf/-untergang

- **Matching:** Nächste Wetterstation (Haversine), stündliche Interpolation, Temperatur-Trägheits-Lags

- **Quellen:** DWD .CDC API (deutscher Wetterdienst)

- **API-Abruf:** als bulk 1 mal pro Jahr / 1000 Messpunkte in D / sonst fallweise

- **Store:** `weather_features` Hypertable (SQL), `correlations` (JSON), `reports/.../weather_features_summary.json`

### 4.3 (not yet) Asset-Fingerprinting (Erzeuger/Speicher-Einflüsse)

- **PV:** Mittags-Delle korreliert mit GHI (Vergleich Sonnentage vs. bedeckte Tage)

- **Batterie:** Nächtliche Ladeplateaus, Peak-Shaving-Muster tagsüber

- **KWK/Generator:** Flache Grundlast-Spitzen zu Betriebszeiten

- **Store:** `asset_signals` (SQL), `reports/.../asset_fingerprints.json`

### 4.4 Analysis Profile (konsolidiert)

Zentrales JSON-Beispiel aus 4.1–4.3 als Grundlage für Imputation und Forecast:

`{`

  `"day_profiles": {"Werktag-Sommer": {...}},`

  `"seasonality": {"daily": true, "weekly": true, "yearly": true},`

  `"holiday_rules": ["Feiertag->low_base"],`

  `"weather_links": {"temp_sensitivity": 0.42, "ghi_sensitivity": -0.35, "lags": {"temp": 2}},`

  `"asset_hints": {"pv": {"midday_dip": true}, "battery": {"night_charge": true}},`

  `"impute_policy": {"method": "profile+weather", "max_gap_min": 180, "outlier_clip_p": 0.995}`

`}`

- **Store:** `analysis_params` (SQL: `analysis_run_id`, `meter_id`, `params JSONB`), 

### Imputation (nach 4.1–4.3)

Ersatzwert-Entscheidung je fehlendem/fehlerhaftem Intervall:

1. Tagestyp-Profil (4.1) → 2\. Wetter-sensitiver Erwartungswert (4.2) → 3\. Asset-bereinigt (4.3) → 4\. Fallback (Interpolation)

- **Store:** `normalized` (korrigiert, v1 \= Original bleibt), `imputation_runs` (SQL), `reports/.../imputation_report.json`

- **SoR-Load:** Nur v2 → TimescaleDB `meter_reads` Hypertable mit vollständiger Lineage (`file_id_v1`, `file_id_v2`, `analysis_run_id`, `imputation_run_id`)

---

## Phase 5 — FORECAST (Ausrollen / Projektion)

**Zweck:** Historische Muster via Prophet auf Zielzeitraum projizieren.

**Tool:** Prophet | liest nur kompakte Artefakte aus Phase 4

**Strategien (kombinierbar):**

1. **Kalender-Mapping:** Tagesklassen (Mo–So, Feiertage) → 1:1 / Nearest-Neighbor auf Zieltage

2. **Wetter-konditioniert:** k-NN auf `[Temp, GHI, Tagestyp]` aus Historik → ähnliche Wetterlagen

3. **DST-korrekt:** Zielland-DST → 92/96/100 Intervalle an Umstelltagen

**Strategien (optional):**

4. **Skalierung:** Wachstum %, Lastverschiebung, Effizienzmaßnahmen (aus Job-Parametern)

5. **Asset-Szenarien:** PV/Speicher-Profile hinzufügen oder entfernen

6. **Energie-/Monatsbudgets:** Optionale Nebenbedingungen (monatliche Summen-Constraints)

**Output:** Ziellastgang (15-min-Intervallreihe) \+ Konfidenzintervalle (q10/q50/q90) \+ Metadaten/Provenienz

**SQL-Metadaten (`forecasts`\-Tabelle):**

- `forecast_id` (UUID v7), `issue_time`, `horizon_start_utc`, `horizon_end_utc`

- `model_alias` (z. B. `prophet`), `model_version` (Semver/Git-Hash)

- `data_snapshot_id` (SHA-256 aus Meter-ID \+ Zeitraum \+ v2-Hash \+ Analysis-Params-Hash)

- `analysis_run_id`, `quantiles` (JSONB), `files` (JSONB mit URIs), `status` ∈ {ok, warn, failed}

**Export-Formate:** CSV / Excel / opt. EDIFACT; Einheit, Intervalllänge, Rundung konfigurierbar **Beilagen:** JSON-Report (Parameter, Statistiken, Warnungen, Tageslabels, Strategien/Constraints, Audit-Trail)

## Container-Schnitt (Deployment)

| Container | Phasen | Liest | Schreibt |
| :---- | :---- | :---- | :---- |
| `kats-ingest` | 1 \+ 2 | Quelldatei (GCS) \+ job.json | `raw/`, `normalized/_v1`, SQL control-Schema |
| `kats-qa` | 3 | `normalized/_v1` | `quality_findings`, `reports/`, `normalized/_v2` |
| `kats-analyse` | 4 | `normalized/_v2` | `analysis_params`, `day_labels`, `weather_features`, `reports/` |
| `kats-forecast` | 5 | `analysis_params` | `forecasts/`, SQL `forecasts`\-Tabelle |

