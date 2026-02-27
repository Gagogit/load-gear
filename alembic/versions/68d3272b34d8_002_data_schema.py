"""002_data_schema

Revision ID: 68d3272b34d8
Revises: 28166ec29553
Create Date: 2026-02-27 18:30:44.980915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '68d3272b34d8'
down_revision: Union[str, Sequence[str], None] = '28166ec29553'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create data schema tables with TimescaleDB hypertables and PostGIS."""

    # --- weather_observations ---
    op.create_table('weather_observations',
        sa.Column('ts_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('station_id', sa.String(length=20), nullable=False),
        sa.Column('temp_c', sa.Double(), nullable=True),
        sa.Column('ghi_wm2', sa.Double(), nullable=True),
        sa.Column('wind_ms', sa.Double(), nullable=True),
        sa.Column('cloud_pct', sa.Double(), nullable=True),
        sa.Column('confidence', sa.Double(), nullable=True),
        sa.Column('source', sa.Enum('dwd_cdc', 'brightsky', 'open_meteo',
                  name='weather_source', schema='data', create_constraint=True), nullable=False),
        sa.Column('ingested_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('ts_utc', 'station_id'),
        schema='data'
    )
    op.create_index('ix_weather_obs_station_ts', 'weather_observations',
                    ['station_id', 'ts_utc'], unique=False, schema='data')

    # PostGIS: add GEOGRAPHY(POINT) column + GiST index
    op.execute("ALTER TABLE data.weather_observations "
               "ADD COLUMN source_location GEOGRAPHY(POINT, 4326)")
    op.execute("CREATE INDEX ix_weather_obs_location ON data.weather_observations "
               "USING GIST (source_location)")

    # --- forecast_runs ---
    op.create_table('forecast_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('meter_id', sa.String(length=100), nullable=False),
        sa.Column('analysis_run_id', sa.UUID(), nullable=True),
        sa.Column('horizon_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('model_alias', sa.String(length=50), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=True),
        sa.Column('data_snapshot_id', sa.String(length=64), nullable=True),
        sa.Column('strategies', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('quantiles', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('status', sa.Enum('queued', 'running', 'ok', 'warn', 'failed',
                  name='forecast_status', schema='data', create_constraint=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='data'
    )
    op.create_index('ix_forecast_runs_job_id', 'forecast_runs',
                    ['job_id'], unique=False, schema='data')

    # --- forecast_series ---
    op.create_table('forecast_series',
        sa.Column('ts_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('forecast_id', sa.UUID(), nullable=False),
        sa.Column('y_hat', sa.Double(), nullable=False),
        sa.Column('q10', sa.Double(), nullable=True),
        sa.Column('q50', sa.Double(), nullable=True),
        sa.Column('q90', sa.Double(), nullable=True),
        sa.ForeignKeyConstraint(['forecast_id'], ['data.forecast_runs.id']),
        sa.PrimaryKeyConstraint('ts_utc', 'forecast_id'),
        schema='data'
    )
    op.create_index('ix_forecast_series_forecast_ts', 'forecast_series',
                    ['forecast_id', 'ts_utc'], unique=False, schema='data')

    # --- hpfc_snapshots ---
    op.create_table('hpfc_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider_id', sa.String(length=100), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('curve_type', sa.Enum('HPFC', 'Spot', 'Intraday',
                  name='curve_type', schema='data', create_constraint=True), nullable=False),
        sa.Column('delivery_start', sa.DateTime(), nullable=False),
        sa.Column('delivery_end', sa.DateTime(), nullable=False),
        sa.Column('currency', sa.String(length=10), nullable=False),
        sa.Column('file_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['file_id'], ['control.files.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='data'
    )

    # --- hpfc_series ---
    op.create_table('hpfc_series',
        sa.Column('ts_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('snapshot_id', sa.UUID(), nullable=False),
        sa.Column('price_mwh', sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(['snapshot_id'], ['data.hpfc_snapshots.id']),
        sa.PrimaryKeyConstraint('ts_utc', 'snapshot_id'),
        schema='data'
    )
    op.create_index('ix_hpfc_series_snapshot_ts', 'hpfc_series',
                    ['snapshot_id', 'ts_utc'], unique=False, schema='data')

    # --- meter_reads ---
    op.create_table('meter_reads',
        sa.Column('ts_utc', sa.DateTime(timezone=True), nullable=False),
        sa.Column('meter_id', sa.String(length=100), nullable=False),
        sa.Column('version', sa.SmallInteger(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('value', sa.Double(), nullable=False),
        sa.Column('unit', sa.Enum('kW', 'kWh', name='energy_unit', schema='data',
                  create_constraint=True), nullable=False),
        sa.Column('quality_flag', sa.SmallInteger(), nullable=False),
        sa.Column('source_file_id', sa.UUID(), nullable=True),
        sa.Column('analysis_run_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.ForeignKeyConstraint(['source_file_id'], ['control.files.id']),
        sa.PrimaryKeyConstraint('ts_utc', 'meter_id', 'version'),
        sa.UniqueConstraint('ts_utc', 'meter_id', 'version',
                            name='uq_meter_reads_ts_meter_version'),
        schema='data'
    )
    op.create_index('ix_meter_reads_job_id', 'meter_reads',
                    ['job_id'], unique=False, schema='data')
    op.create_index('ix_meter_reads_meter_ts_ver', 'meter_reads',
                    ['meter_id', 'ts_utc', 'version'], unique=False, schema='data')

    # --- TimescaleDB hypertables ---
    op.execute("SELECT create_hypertable('data.meter_reads', 'ts_utc', "
               "chunk_time_interval => INTERVAL '1 month', migrate_data => true)")
    op.execute("SELECT create_hypertable('data.weather_observations', 'ts_utc', "
               "chunk_time_interval => INTERVAL '3 months', migrate_data => true)")
    op.execute("SELECT create_hypertable('data.forecast_series', 'ts_utc', "
               "chunk_time_interval => INTERVAL '1 month', migrate_data => true)")


def downgrade() -> None:
    """Drop all data schema tables."""
    op.drop_index('ix_hpfc_series_snapshot_ts', table_name='hpfc_series', schema='data')
    op.drop_table('hpfc_series', schema='data')
    op.drop_index('ix_meter_reads_meter_ts_ver', table_name='meter_reads', schema='data')
    op.drop_index('ix_meter_reads_job_id', table_name='meter_reads', schema='data')
    op.drop_table('meter_reads', schema='data')
    op.drop_table('hpfc_snapshots', schema='data')
    op.drop_index('ix_forecast_series_forecast_ts', table_name='forecast_series', schema='data')
    op.drop_table('forecast_series', schema='data')
    op.drop_index('ix_forecast_runs_job_id', table_name='forecast_runs', schema='data')
    op.drop_table('forecast_runs', schema='data')
    op.execute("DROP INDEX IF EXISTS data.ix_weather_obs_location")
    op.drop_index('ix_weather_obs_station_ts', table_name='weather_observations', schema='data')
    op.drop_table('weather_observations', schema='data')
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS data.energy_unit")
    op.execute("DROP TYPE IF EXISTS data.weather_source")
    op.execute("DROP TYPE IF EXISTS data.forecast_status")
    op.execute("DROP TYPE IF EXISTS data.curve_type")
