from __future__ import annotations

"""
Shot model — a single golf shot with all measurable metrics.

This is the core data table. Every launch monitor produces some subset of
these fields. The schema is a superset — nullable columns handle monitors
that don't measure certain metrics (e.g., Garmin R10 doesn't report
face angle, SkyTrak doesn't report club path).

Sign conventions (standardized across all parsers):
  - Offline/lateral: negative = LEFT of target, positive = RIGHT
  - Club path: negative = out-to-in (pull), positive = in-to-out (push)
  - Face angle: negative = closed/left, positive = open/right
  - Spin axis: negative = draw spin, positive = fade spin
  - Launch direction: negative = left, positive = right

This consistency is critical — each parser must normalize its source
format to these conventions regardless of how the monitor reports them.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Shot(Base):
    __tablename__ = "shots"

    # ── Ownership ──
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalized from session for query performance.
    # Avoids a JOIN on every filtered shot query.
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # ── Shot identity ──
    club_name: Mapped[str] = mapped_column(String(30), nullable=False)
    shot_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    shot_date: Mapped[date] = mapped_column(Date, nullable=False)

    # ════════════════════════════════════════
    # Ball data — measured at launch
    # ════════════════════════════════════════
    ball_speed_mph: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    launch_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    launch_direction_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    spin_rate_rpm: Mapped[int | None] = mapped_column(Integer)
    spin_axis_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    back_spin_rpm: Mapped[int | None] = mapped_column(Integer)
    side_spin_rpm: Mapped[int | None] = mapped_column(Integer)

    # ════════════════════════════════════════
    # Club data — measured at impact
    # ════════════════════════════════════════
    club_speed_mph: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    smash_factor: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    attack_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    club_path_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    face_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    face_to_path_deg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    dynamic_loft_deg: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    closure_rate_dps: Mapped[Decimal | None] = mapped_column(Numeric(6, 1))

    # ════════════════════════════════════════
    # Result data — measured or computed flight
    # ════════════════════════════════════════
    carry_yards: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    total_yards: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    offline_yards: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    apex_feet: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    landing_angle_deg: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    hang_time_sec: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    curve_yards: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))

    # ════════════════════════════════════════
    # Computed fields — set during processing
    # ════════════════════════════════════════
    theoretical_carry: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1),
        comment="Physics-based carry estimate from ball speed + launch angle + spin",
    )
    is_filtered: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="true",
        comment="False if trimmed by bottom-N% filter",
    )
    ball_type: Mapped[str | None] = mapped_column(String(50))

    # ── Relationships ──
    session: Mapped["Session"] = relationship(back_populates="shots")  # noqa: F821

    __table_args__ = (
        # THE critical index — every analytics query filters by profile + club + date range
        Index("ix_shots_profile_club_date", "profile_id", "club_name", "shot_date"),
        # Session-level queries (get all shots in a session)
        Index("ix_shots_session", "session_id"),
        # Filtered-only queries (skip trimmed shots)
        Index("ix_shots_filtered", "profile_id", "is_filtered", "club_name"),
    )

    def __repr__(self) -> str:
        return f"<Shot {self.club_name} carry={self.carry_yards} idx={self.shot_index}>"
