"""003_analysis_schema

Revision ID: 0ef875775470
Revises: 68d3272b34d8
Create Date: 2026-02-27 18:38:42.933934

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0ef875775470'
down_revision: Union[str, Sequence[str], None] = '68d3272b34d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create analysis schema tables."""

    # --- analysis_profiles ---
    op.create_table('analysis_profiles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('meter_id', sa.Text(), nullable=False),
        sa.Column('day_fingerprints', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('seasonality', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('holiday_rules', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('weather_correlations', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('asset_hints', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('impute_policy', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='analysis'
    )

    # --- quality_findings ---
    op.create_table('quality_findings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('check_id', sa.SmallInteger(), nullable=False),
        sa.Column('check_name', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('ok', 'warn', 'error',
                  name='check_status', schema='analysis', create_constraint=True), nullable=False),
        sa.Column('metric_key', sa.Text(), nullable=False),
        sa.Column('metric_value', sa.Double(), nullable=False),
        sa.Column('threshold', sa.Double(), nullable=True),
        sa.Column('affected_slots', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='analysis'
    )
    op.create_index('ix_quality_findings_job_check', 'quality_findings',
                    ['job_id', 'check_id'], unique=False, schema='analysis')

    # --- imputation_runs ---
    op.create_table('imputation_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('analysis_profile_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('slots_replaced', sa.Integer(), nullable=False),
        sa.Column('method_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_profile_id'], ['analysis.analysis_profiles.id']),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='analysis'
    )


def downgrade() -> None:
    """Drop all analysis schema tables."""
    op.drop_table('imputation_runs', schema='analysis')
    op.drop_index('ix_quality_findings_job_check', table_name='quality_findings', schema='analysis')
    op.drop_table('quality_findings', schema='analysis')
    op.drop_table('analysis_profiles', schema='analysis')
    # Drop enum types
    op.execute("DROP TYPE IF EXISTS analysis.check_status")
