"""007_add_financial_provider_id

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add provider_id column to financial_runs table."""
    op.add_column(
        'financial_runs',
        sa.Column('provider_id', sa.String(100), nullable=False, server_default='baseline'),
        schema='data',
    )


def downgrade() -> None:
    """Remove provider_id column from financial_runs table."""
    op.drop_column('financial_runs', 'provider_id', schema='data')
