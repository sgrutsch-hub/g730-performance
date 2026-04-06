"""Add target_carry to clubs for target-based trim.

Revision ID: 003
Revises: 002
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("target_carry", sa.Numeric(5, 1), nullable=True))


def downgrade() -> None:
    op.drop_column("clubs", "target_carry")
