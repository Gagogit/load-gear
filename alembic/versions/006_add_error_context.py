"""006_add_error_context

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add error_context JSONB column to jobs table."""
    op.add_column(
        'jobs',
        sa.Column('error_context', JSONB, nullable=True),
        schema='control',
    )


def downgrade() -> None:
    """Remove error_context column from jobs table."""
    op.drop_column('jobs', 'error_context', schema='control')
