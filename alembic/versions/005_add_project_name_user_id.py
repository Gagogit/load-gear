"""005_add_project_name_user_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add project_name and user_id columns to jobs table."""
    op.add_column(
        'jobs',
        sa.Column('project_name', sa.String(200), nullable=False, server_default=''),
        schema='control',
    )
    op.add_column(
        'jobs',
        sa.Column('user_id', sa.String(100), nullable=False, server_default=''),
        schema='control',
    )


def downgrade() -> None:
    """Remove project_name and user_id columns from jobs table."""
    op.drop_column('jobs', 'user_id', schema='control')
    op.drop_column('jobs', 'project_name', schema='control')
