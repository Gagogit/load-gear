# Development Process — Vorlage für phasengesteuerte KI-Entwicklung

> Bewährt an LOAD-GEAR (8 Phasen, 379 Tests, 48 Endpoints).
> Optimiert für Single-Agent + QA-Review-Agent.

---

## 1. Verzeichnisstruktur

```
project-root/
├── CLAUDE.md                      # Projekt-Regeln (wird automatisch geladen)
├── STATUS.md                      # Aktuelle Phase + Tasks
├── docs/
│   ├── LESSONS_LEARNED.md         # Git-versioniertes Erfahrungswissen
│   ├── CHANGES.md                 # Auswirkungen Phase→Phase
│   ├── tasks/
│   │   └── backlog.md             # Alle Tasks aller Phasen
│   └── context/                   # Phasen-spezifisches Know-how
│       ├── _overview.md           # Architektur, Datenfluss, Conventions
│       ├── phase-01-foundation.md
│       ├── phase-02-ingest.md
│       ├── phase-03-qa.md
│       ├── ...
│       └── domain.md              # Fachliches Know-how (Domänenwissen)
└── .claude/
    └── agents/
        └── reviewer.md            # QA-Review-Agent Definition
```

---

## 2. Datei-Zwecke und Inhalte

### 2.1 `CLAUDE.md` (automatisch geladen)

Enthält nur **zeitlose Regeln** — keine Zustände, keine Phasen-Details.

```markdown
# Project Rules

## Architecture
- Controller → Service → Repository (async-first)
- FastAPI + SQLAlchemy 2.0 async
- Polars (NO PANDAS)

## Work Rules
- Lies `docs/context/{aktuelle-phase}.md` vor Arbeitsbeginn
- Am Ende jeder Phase: aktualisiere STATUS.md, backlog.md, CHANGES.md, LESSONS_LEARNED.md
- Commit + Push erst nach grünen Tests
- Phase boundary: stop → wait for approval

## Permissions
- Lese/schreibe alle Dateien unter src/ und tests/ ohne Rückfrage
- git commit/push ohne Rückfrage
- pytest ohne Rückfrage
- Frage nur bei: Datei löschen, DB-Migration ausführen, Architektur-Entscheidungen

## Context Loading
- Für Phase-Arbeit: lies `docs/context/{phase}.md` + `docs/context/_overview.md`
- Für Bugfixes: lies `docs/LESSONS_LEARNED.md` (relevanter Abschnitt)
- Für Folge-Phasen: lies `docs/CHANGES.md` (was hat sich geändert)
```

### 2.2 `STATUS.md` (aktueller Zustand)

```markdown
# STATUS — Current Phase

## Phase 3 — QA Engine (IN PROGRESS)

| Task | Description | Status |
|------|-------------|--------|
| QA-01 | Quality Finding Repository | done |
| QA-02 | 9 QA Checks implementieren | in_progress |
| QA-03 | QA Orchestration Service | pending |
| QA-04 | QA API Endpoints | pending |
| QA-05 | Tests (Ziel: 130+) | pending |

## Voraussetzungen aus Phase 2
→ Siehe docs/CHANGES.md Abschnitt "Phase 2 → Phase 3"
```

### 2.3 `docs/context/_overview.md` (Architektur-Überblick)

Wird bei **jeder** Phase gelesen. Enthält:

```markdown
# Architecture Overview

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0 async, PostgreSQL 16

## Data Flow
v1 (raw) → v2 (cleaned) → v3 (forecast) → cost (financial)

## Database Schemas
- control: jobs, files, reader_profiles, holidays
- data: meter_reads, forecast_series, hpfc_snapshots, ...
- analysis: analysis_profiles, quality_findings, imputation_runs

## Code Conventions
- Async everywhere (no sync DB calls)
- Pydantic for API schemas, ORM for DB
- Tests: ASGITransport + httpx.AsyncClient
- Unique meter_ids per test (uuid4)

## File Naming
- Routes: src/load_gear/api/routes/{domain}.py
- Services: src/load_gear/services/{domain}/{domain}_service.py
- Repos: src/load_gear/repositories/{entity}_repo.py
- Schemas: src/load_gear/models/schemas.py (alle Pydantic)
- ORM: src/load_gear/models/{schema}.py (control/data/analysis)
```

### 2.4 `docs/context/phase-{nn}-{name}.md` (Phasen-Know-how)

Wird **nur** geladen wenn diese Phase bearbeitet wird. Enthält:

```markdown
# Phase 3 — QA Engine

## Ziel
9 automatische Qualitätsprüfungen auf v1-Zeitreihen.

## Input
- v1 meter_reads (aus Phase 2)
- QA-Schwellwerte aus Admin-Config

## Output
- quality_findings (9 Einträge pro Job)
- overall_status: ok / warn / error
- Stunden- und Wochentagsprofil

## Design-Entscheidungen
- Checks laufen sequenziell (nicht parallel) — Reihenfolge egal
- Affected_slots als JSONB — flexibel für verschiedene Check-Typen
- Profile (Check 8) wird auch bei warn/error gespeichert

## Bekannte Fallstricke
- Completeness-Check: Intervall aus reader_profile, nicht hardcoded 15min
- Peak-Detection: kW-Werte in Tests realistisch halten (0.5-50 kW)
- DST: Doppelstunde im Herbst darf nicht als Duplikat zählen

## API-Contracts (Endpoints dieser Phase)
- POST /api/v1/qa {job_id} → 202
- GET /api/v1/qa/{job_id}/status → QAStatusResponse
- GET /api/v1/qa/{job_id}/report → QAReportResponse
- GET /api/v1/qa/{job_id}/findings → QAFindingResponse[]
- GET /api/v1/qa/{job_id}/profile → QAProfileResponse

## Abhängigkeiten
- Braucht: Phase 2 (v1 meter_reads, reader_profile)
- Liefert an: Phase 4 (overall_status entscheidet ob Imputation nötig)
```

### 2.5 `docs/CHANGES.md` (Phasen-Übergabe)

Wird beim **Start einer neuen Phase** gelesen. Akkumuliert über die Projektlaufzeit.

```markdown
# Changes — Auswirkungen zwischen Phasen

## Phase 1 → Phase 2
- Job-Status `pending` ist Voraussetzung für Ingest-Start
- File.id wird als FK in meter_reads.source_file_id referenziert

## Phase 2 → Phase 3
- v1 meter_reads: ts_utc (timestamptz), value (float), unit (kW/kWh)
- reader_profile.rules enthält interval_minutes (15 oder 60)
- Job wechselt zu `qa_running` nach erfolgreichem Ingest

## Phase 3 → Phase 4
- overall_status bestimmt Imputation-Strategie
- QA-Findings sind read-only (Phase 4 liest, ändert nicht)
- Stundenprofil aus Check 8 kann als Impute-Template dienen

## Phase 5 → Phase 6
- forecast_series: y_hat, q10=q50=q90=y_hat (deterministisch)
- model_alias="day_match" (nicht "prophet")
- ForecastRun.strategies ist JSONB-Array
- ACHTUNG: Financial braucht HPFC-Snapshot — fehlt er, wird übersprungen
```

### 2.6 `docs/LESSONS_LEARNED.md` (Erfahrungswissen)

Git-versioniert, wächst mit dem Projekt. Gruppiert nach Bereich.

```markdown
# Lessons Learned

## Ingest & Parsing
- `.replace(".",",")` auf ganzer CSV-Zeile korrumpiert Datumsangaben
  → Nur auf Wert-Strings anwenden
- Test-CSV braucht 8+ Datenzeilen für robuste Formaterkennung
- XLS/XLSX: `str(cell.value)` liefert immer Punkt-Dezimal
- SHA-256 Dedup: Test-CSVs brauchen uuid-Kommentarzeile für Eindeutigkeit

## Async & SQLAlchemy
- `session.add()` + `flush()` für Bulk-Insert, NICHT `pg_insert`
- Keine lazy relationships in async → MissingGreenlet
- Re-Upload: alte v1/v2 meter_reads per meter_id löschen vor Insert

## API & Routing
- Statische Routen VOR dynamischen: `/providers` vor `/{snapshot_id}`
- Globaler Exception-Handler: alle Fehler als JSON (kein HTML 500)

## Forecast & Day-Matching
- Silvester = Werktag-vor-Frei, Neujahr = Feiertag → niedrigere Prognose korrekt
- Störung-Exclusion: Tage < 10% des Werktagsdurchschnitts ausschließen
- DST Fall-Back: `seen_ts` Set dedupliziert vor Bulk-Insert

## Testing
- Unique meter_ids per Test (`uuid4().hex[:8]`)
- Realistische kW-Werte (0.5-50), nicht 1000+ → Schwellwert-Probleme
- HPFC-Test-CSVs: +1h Buffer nach Forecast-Ende für Coverage-Check

## Domain (Energiewirtschaft)
- MaLo-ID = Marktlokations-Kennung (33 Zeichen)
- HPFC = Hourly Price Forward Curve (EUR/MWh, stündlich)
- 9 Tagtypen: Störung, Feiertag, Brückentag, So, Sa, WnF, WvF, WS, WW
```

### 2.7 `docs/context/domain.md` (Fachliches Know-how)

Domänenwissen das **nicht** aus dem Code kommt:

```markdown
# Domain Knowledge — Energiewirtschaft

## Begriffe
- MaLo: Marktlokation (Messpunkt im Stromnetz)
- HPFC: Hourly Price Forward Curve (stündliche Preisprognose)
- Lastgang: Zeitreihe des Stromverbrauchs (typisch 15min oder 1h)
- SLP: Standard-Lastprofil (BDEW)

## Geschäftsregeln
- Baseline-Provider wird IMMER berechnet (Fallback)
- Prognosehorizont: max 60 Monate
- Wachstumsfaktor 100% = keine Änderung, 105% = 5% Wachstum
- Feiertage sind bundeslandspezifisch (state_code)

## Datenqualität
- Reale Lastgänge haben 2-5% Lücken (normal)
- >5% Lücken → warn, >20% → error
- Sommerzeit-Umstellung: 1 fehlende Stunde (Frühjahr), 1 Doppelstunde (Herbst)
```

### 2.8 `.claude/agents/reviewer.md` (QA-Review-Agent)

```markdown
---
name: QA Reviewer
model: sonnet
tools:
  - Read
  - Glob
  - Grep
  - Bash(git diff *)
  - Bash(.venv/bin/python -m pytest *)
---

# QA Reviewer

Du bist ein Code-Reviewer für dieses Projekt.

## Aufgabe
Prüfe den Code der aktuellen Phase auf:
1. Konsistenz mit `docs/context/_overview.md` (Architektur-Patterns)
2. Bekannte Fallstricke aus `docs/LESSONS_LEARNED.md`
3. Vollständigkeit der Tests
4. Korrekte Fehlerbehandlung (404/409/422)
5. Keine lazy-loading in async Pfaden
6. Unique meter_ids in Tests

## Output
Erstelle eine kurze Review-Liste:
- OK: was passt
- WARN: was verbessert werden sollte
- FAIL: was gefixt werden muss

## Regeln
- Ändere KEINEN Code — nur lesen und berichten
- Sei konkret: Datei + Zeile + Problem
- Priorisiere: Bugs > Patterns > Style
```

---

## 3. Workflow pro Phase

```
┌─────────────────────────────────────────────────────┐
│ 1. VORBEREITUNG                                     │
│    Mensch: definiert Phase + Tasks in STATUS.md      │
│    Agent:  liest _overview.md + phase-{n}.md         │
│            liest CHANGES.md (was hat sich geändert)  │
│            liest LESSONS_LEARNED.md (relevanter Teil) │
├─────────────────────────────────────────────────────┤
│ 2. IMPLEMENTIERUNG                                   │
│    Agent:  arbeitet Tasks sequenziell ab              │
│            nutzt Phase-Kontext als Leitplanke         │
│            updated STATUS.md nach jedem Task          │
├─────────────────────────────────────────────────────┤
│ 3. QUALITÄTSKONTROLLE                                │
│    Agent:  führt Tests aus (pytest)                   │
│    QA-Agent: reviewed Code gegen Patterns + Lessons   │
│    Mensch: prüft QA-Report, gibt Freigabe             │
├─────────────────────────────────────────────────────┤
│ 4. ABSCHLUSS                                         │
│    Agent:  aktualisiert:                              │
│            → CHANGES.md (Auswirkungen auf Phase N+1)  │
│            → LESSONS_LEARNED.md (neue Erkenntnisse)   │
│            → STATUS.md (Phase = DONE)                 │
│            → backlog.md (Tasks abhaken)                │
│    Agent:  commit + push                              │
│    Mensch: Freigabe für nächste Phase                  │
└─────────────────────────────────────────────────────┘
```

---

## 4. Prompt-Vorlagen

### Phase starten

```
Projekt [NAME]. Wir starten Phase [N] — [Name].
Lies: docs/context/_overview.md, docs/context/phase-{N}-{name}.md,
docs/CHANGES.md (Abschnitt Phase N-1 → Phase N).
Die Tasks stehen in STATUS.md. Arbeite sie der Reihe nach ab.
```

### Phase fortsetzen (neue Session)

```
Projekt [NAME]. Wir sind mitten in Phase [N].
Lies STATUS.md für den aktuellen Stand und
docs/context/phase-{N}-{name}.md für den Kontext.
Mach weiter beim ersten offenen Task.
```

### QA-Review auslösen

```
Führe den QA-Reviewer auf die Änderungen dieser Phase aus.
git diff main..HEAD zeigt was sich geändert hat.
```

### Phase abschließen

```
Phase [N] ist fertig. Aktualisiere:
1. STATUS.md → Phase = DONE
2. docs/tasks/backlog.md → Tasks abhaken
3. docs/CHANGES.md → Abschnitt "Phase N → Phase N+1"
4. docs/LESSONS_LEARNED.md → neue Erkenntnisse
Dann commit und push.
```

---

## 5. Token-Effizienz

| Was wird geladen | Wann | Ca. Tokens |
|-----------------|------|-----------|
| CLAUDE.md | Immer (automatisch) | ~300 |
| STATUS.md | Immer (Agent liest) | ~200 |
| _overview.md | Bei jeder Phase | ~400 |
| phase-{n}.md | Nur aktuelle Phase | ~300 |
| CHANGES.md | Nur relevanter Abschnitt | ~100 |
| LESSONS_LEARNED.md | Bei Bugs / Unsicherheit | ~500 |
| domain.md | Bei fachlichen Fragen | ~300 |
| **Total pro Phase-Start** | | **~1300** |

Zum Vergleich: Die MEMORY.md von LOAD-GEAR hatte ~6000 Tokens (alles auf einmal).
Diese Struktur lädt **nur was gebraucht wird** → ~80% Token-Ersparnis.
