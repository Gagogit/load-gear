# Task 003: Database Schema — Data Tables

Lade:
  `/docs/schema/data.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  SQLAlchemy models + Alembic migration for the data schema:
  meter_reads, weather_observations, forecast_series, forecast_runs,
  hpfc_series, hpfc_snapshots.

Schritte:
  1. Create src/load_gear/models/data.py with SQLAlchemy models
  2. Create Alembic migration: "002_data_schema"
  3. Include TimescaleDB hypertable creation for:
     - meter_reads (1 month chunks on ts_utc)
     - weather_observations (3 month chunks on ts_utc)
     - forecast_series (1 month chunks on ts_utc)
  4. Include PostGIS extension creation (CREATE EXTENSION IF NOT EXISTS postgis)
  5. Include GEOGRAPHY(POINT) column for weather_observations.source_location
  6. Verify migration runs and tables exist

Akzeptanzkriterien:
  - Migration creates all 6 tables with correct types
  - Hypertables are created (requires TimescaleDB extension)
  - PostGIS GEOGRAPHY column on weather_observations
  - GiST index on source_location
  - Unique constraint on meter_reads (ts_utc, meter_id, version)
  - Foreign keys where specified in schema doc

Einschränkungen:
  - If TimescaleDB/PostGIS not installed, migration should handle gracefully
    (try/except or conditional creation)
  - No data insertion in this task
