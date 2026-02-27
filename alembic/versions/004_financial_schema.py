"""004_financial_schema

Revision ID: a1b2c3d4e5f6
Revises: 0ef875775470
Create Date: 2026-02-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0ef875775470'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add financial_running status and financial_runs table."""

    # Add FINANCIAL_RUNNING to job_status enum
    op.execute("ALTER TYPE control.job_status ADD VALUE IF NOT EXISTS 'FINANCIAL_RUNNING' BEFORE 'DONE'")

    # --- data.financial_runs ---
    op.create_table('financial_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('forecast_run_id', sa.UUID(), nullable=False),
        sa.Column('hpfc_snapshot_id', sa.UUID(), nullable=False),
        sa.Column('meter_id', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='running'),
        sa.Column('total_cost_eur', sa.Double(), nullable=True),
        sa.Column('monthly_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['control.jobs.id']),
        sa.ForeignKeyConstraint(['forecast_run_id'], ['data.forecast_runs.id']),
        sa.ForeignKeyConstraint(['hpfc_snapshot_id'], ['data.hpfc_snapshots.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='data'
    )
    op.create_index('ix_financial_runs_job_id', 'financial_runs',
                    ['job_id'], unique=False, schema='data')


def downgrade() -> None:
    """Drop financial_runs table."""
    op.drop_index('ix_financial_runs_job_id', table_name='financial_runs', schema='data')
    op.drop_table('financial_runs', schema='data')
    # Note: Cannot remove enum value from PostgreSQL enum type
