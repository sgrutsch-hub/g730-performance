"""Initial schema — users, profiles, clubs, sessions, shots.

Revision ID: 001
Revises:
Create Date: 2026-03-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Users ──
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("auth_provider", sa.String(20), server_default="email", nullable=False),
        sa.Column("auth_provider_id", sa.String(255), nullable=True),
        sa.Column("subscription_tier", sa.String(20), server_default="free", nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(50), server_default="America/Chicago", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_index("ix_users_stripe", "users", ["stripe_customer_id"], unique=True)

    # ── Profiles ──
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("launch_monitor", sa.String(50), nullable=True),
        sa.Column("handicap_index", sa.Numeric(4, 1), nullable=True),
        sa.Column("default_ball", sa.String(50), nullable=True),
        sa.Column("elevation_ft", sa.Integer(), server_default="0", nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])
    op.create_index("ix_profiles_user_default", "profiles", ["user_id", "is_default"])

    # ── Clubs ──
    op.create_table(
        "clubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("brand", sa.String(100), nullable=True),
        sa.Column("loft_degrees", sa.Float(), nullable=True),
        sa.Column("shaft", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_clubs_profile_id", "clubs", ["profile_id"])
    op.create_index("ix_clubs_profile_active", "clubs", ["profile_id", "is_active"])

    # ── Sessions ──
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file", sa.String(255), nullable=False),
        sa.Column("source_format", sa.String(30), nullable=False, comment="Parser that produced this data"),
        sa.Column("raw_csv", sa.Text(), nullable=True, comment="Original CSV for re-parsing"),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("ball_type", sa.String(50), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("shot_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_profile_id", "sessions", ["profile_id"])
    op.create_index("ix_sessions_session_date", "sessions", ["session_date"])
    op.create_index("uq_sessions_profile_file", "sessions", ["profile_id", "source_file"], unique=True)
    op.create_index("ix_sessions_profile_date", "sessions", ["profile_id", "session_date"])

    # ── Shots ──
    op.create_table(
        "shots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("club_name", sa.String(30), nullable=False),
        sa.Column("shot_index", sa.SmallInteger(), nullable=False),
        sa.Column("shot_date", sa.Date(), nullable=False),
        # Ball data
        sa.Column("ball_speed_mph", sa.Numeric(5, 1), nullable=True),
        sa.Column("launch_angle_deg", sa.Numeric(4, 1), nullable=True),
        sa.Column("launch_direction_deg", sa.Numeric(5, 1), nullable=True),
        sa.Column("spin_rate_rpm", sa.Integer(), nullable=True),
        sa.Column("spin_axis_deg", sa.Numeric(5, 1), nullable=True),
        sa.Column("back_spin_rpm", sa.Integer(), nullable=True),
        sa.Column("side_spin_rpm", sa.Integer(), nullable=True),
        # Club data
        sa.Column("club_speed_mph", sa.Numeric(5, 1), nullable=True),
        sa.Column("smash_factor", sa.Numeric(3, 2), nullable=True),
        sa.Column("attack_angle_deg", sa.Numeric(4, 1), nullable=True),
        sa.Column("club_path_deg", sa.Numeric(5, 1), nullable=True),
        sa.Column("face_angle_deg", sa.Numeric(5, 1), nullable=True),
        sa.Column("face_to_path_deg", sa.Numeric(5, 1), nullable=True),
        sa.Column("dynamic_loft_deg", sa.Numeric(4, 1), nullable=True),
        sa.Column("closure_rate_dps", sa.Numeric(6, 1), nullable=True),
        # Result data
        sa.Column("carry_yards", sa.Numeric(5, 1), nullable=True),
        sa.Column("total_yards", sa.Numeric(5, 1), nullable=True),
        sa.Column("offline_yards", sa.Numeric(5, 1), nullable=True),
        sa.Column("apex_feet", sa.Numeric(5, 1), nullable=True),
        sa.Column("landing_angle_deg", sa.Numeric(4, 1), nullable=True),
        sa.Column("hang_time_sec", sa.Numeric(3, 1), nullable=True),
        sa.Column("curve_yards", sa.Numeric(5, 1), nullable=True),
        # Computed
        sa.Column("theoretical_carry", sa.Numeric(5, 1), nullable=True,
                  comment="Physics-based carry estimate"),
        sa.Column("is_filtered", sa.Boolean(), server_default="true", nullable=False,
                  comment="False if trimmed by bottom-N% filter"),
        sa.Column("ball_type", sa.String(50), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_shots_profile_club_date", "shots", ["profile_id", "club_name", "shot_date"])
    op.create_index("ix_shots_session", "shots", ["session_id"])
    op.create_index("ix_shots_filtered", "shots", ["profile_id", "is_filtered", "club_name"])


def downgrade() -> None:
    op.drop_table("shots")
    op.drop_table("sessions")
    op.drop_table("clubs")
    op.drop_table("profiles")
    op.drop_table("users")
