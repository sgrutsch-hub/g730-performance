"""Add content_hash to sessions for duplicate detection.

Revision ID: 002
Revises: 001
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("content_hash", sa.String(64), nullable=True))
    op.create_index("ix_sessions_profile_hash", "sessions", ["profile_id", "content_hash"])


def downgrade() -> None:
    op.drop_index("ix_sessions_profile_hash", table_name="sessions")
    op.drop_column("sessions", "content_hash")
