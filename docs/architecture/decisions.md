# Architectural Decisions
Schicht: B
Letzte Aktualisierung: 2026-02-27

This document records binding architectural decisions. Every decision here is final
unless explicitly superseded by a new entry with rationale.

---

## ADR-001: v2 Ownership — Analysis owns v2, not QA

**Context:** Both QA (P3) and Analysis (P4) could write the cleaned time series (v2)
into `data.meter_reads`. The original specs were ambiguous about ownership.

**Decision:**
- **QA (P3)** produces `quality_findings` (JSON report) and flags problematic slots.
  QA NEVER writes to `data.meter_reads`. QA is read-only on time series data.
- **Analysis (P4)** owns the imputation step and writes v2 to `data.meter_reads`
  with `version=2`. It uses QA findings as input to decide what to impute.
- The imputation chain is: day-type profile (4.1) → weather-sensitive value (4.2) →
  skip asset-adjustment (4.3 stubbed) → fallback interpolation.

**Consequence:** Clear single-writer for v2. QA can run repeatedly without side effects.

---

## ADR-002: Single Source of Truth — TimescaleDB for time series, GCS for archives

**Context:** The specs mentioned both TimescaleDB and GCS/MinIO for time series storage,
creating ambiguity about which system holds the authoritative data.

**Decision:**
- **TimescaleDB** is the single source of truth for all queryable time series:
  - `data.meter_reads` (v1 + v2, distinguished by `version` column)
  - `data.weather_observations` (DWD station data)
  - `data.forecast_series` (v3, Prophet output)
- **GCS/MinIO** is used ONLY for:
  - `raw/` — original uploaded files (WORM, immutable, SHA-256 verified)
  - `reports/` — generated PDF/JSON report artifacts
  - `models/` — serialized Prophet model artifacts
- No time series is ever duplicated across both systems.
- Cold data archival (Parquet export from TimescaleDB) is a future optimization, not v0.1.

**Consequence:** No synchronization problems. All API queries hit one system.

---

## ADR-003: Orchestration v0.1 — DB state machine, no message queue

**Context:** Container-to-container communication needs a mechanism. Options:
message queue (Celery/RabbitMQ) or database-driven state polling.

**Decision:**
- v0.1 runs as a **single monolithic FastAPI application** (not separate containers).
- Job progression is driven by a **state machine in `control.jobs`** with these states:
  ```
  pending → ingesting → qa_running → analysis_running → forecast_running → done
                ↓            ↓              ↓                 ↓
              failed       failed          failed            failed
  ```
- Each async endpoint (POST /ingest, /qa, /analysis, /forecasts) advances the job
  to the next state and runs the service synchronously within an async task.
- The `warn` terminal state is used when results exist but quality flags are set.
- A job without `Prognose` in `tasks[]` transitions: `analysis_running → done`
  (skips forecast entirely).

**Future:** When performance requires it, extract services into containers with a
Redis/RabbitMQ queue. The state machine in `control.jobs` remains the canonical state
regardless of orchestration method.

**Consequence:** Simple deployment (single process), easy debugging, no infrastructure
dependencies beyond PostgreSQL and GCS.

---

## ADR-004: Task routing — skip matrix for jobs without all phases

**Context:** A job's `tasks[]` array can request a subset of processing
(e.g., only Statistik without Prognose). The pipeline must know which phases to skip.

**Decision:**
Phase execution is determined by the `tasks[]` array in the job payload:

| tasks[] contains     | Phases executed        | Terminal state after |
|----------------------|------------------------|----------------------|
| Statistik            | P2 → P3               | done (after QA)      |
| Fehleranalyse        | P2 → P3               | done (after QA)      |
| Imputation           | P2 → P3 → P4          | done (after analysis)|
| Prognose             | P2 → P3 → P4 → P5    | done (after forecast)|
| Aggregation          | P2 → P3 → P4 → P5 → P6 | done (after financial)|

Rules:
- P2 (ingest/homogenize) ALWAYS runs — you cannot analyze what you haven't parsed.
- P3 (QA) ALWAYS runs — quality assessment is mandatory.
- Each higher phase implies all lower phases.
- `Umformatierung` is a P2 export variant (output v1 in requested format), not a separate phase.

**Consequence:** Simple linear pipeline. No conditional branching logic needed —
just check "how far up the chain does this job go?"

---

## ADR-005: Asset-Fingerprinting (P4.3) — stub with null contract

**Context:** Phase 4.3 (PV/battery/generator detection) is marked `(not yet)` in the
specs, but the imputation chain references it as step 3.

**Decision:**
- Implement `AssetFingerprintService` as a **pass-through stub** that returns:
  ```python
  {"asset_hints": None, "pv": None, "battery": None, "kwk": None}
  ```
- The imputation pipeline checks `asset_hints is None` and skips the
  asset-adjustment step, falling through to interpolation fallback.
- The `analysis_profiles.asset_hints` column accepts JSONB null.
- The stub has a proper service interface so it can be replaced without
  touching the imputation pipeline.

**Consequence:** No dead code, no broken references. Clean extension point for future.

---

## ADR-006: Monolith-first deployment

**Context:** The specs describe 4 containers (kats-ingest, kats-qa, kats-analyse,
kats-forecast). Building and orchestrating 4 containers from day one adds complexity
without immediate benefit.

**Decision:**
- v0.1 is a single FastAPI application with all services in-process.
- The service layer is structured as if services were separate (no cross-service imports
  except through defined interfaces).
- Docker setup provides a single Dockerfile for the monolith + PostgreSQL + MinIO.
- Container extraction happens when: (a) Prophet jobs block the API thread, or
  (b) scaling requires independent service instances.

**Consequence:** Fast development, easy debugging, deferred infrastructure complexity.

---

## ADR-007: Authentication — deferred, but interfaces prepared

**Context:** Auth is marked `(not yet)` for the presentation phase.

**Decision:**
- No JWT/OAuth in v0.1.
- All endpoints are open.
- A `current_user` dependency placeholder exists in the API layer that returns
  a default user/company. When auth is added, only this dependency changes.
- `company_id` is stored on all relevant records for future row-level security.

**Consequence:** Zero auth overhead now, clean migration path later.
