from __future__ import annotations

"""
Profile model — a golfer identity within a user account.

Separating profile from user allows:
- Multiple golfers per account (family members, coach's students)
- Golf-specific data (bag, preferences) decoupled from auth
- Future: coach viewing student profiles without sharing accounts
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Profile(Base):
    __tablename__ = "profiles"

    # ── Owner ──
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity ──
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(default=False, server_default="false")

    # ── Golf info ──
    launch_monitor: Mapped[str | None] = mapped_column(String(50))
    handicap_index: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    default_ball: Mapped[str | None] = mapped_column(String(50))
    elevation_ft: Mapped[int] = mapped_column(default=0, server_default="0")

    # ── Settings (flexible JSONB for per-profile preferences) ──
    # Stores: rollout_multipliers, trim_percentage, preferred_units, etc.
    settings: Mapped[dict | None] = mapped_column(JSONB, default=dict)

    # ── Relationships ──
    user: Mapped["User"] = relationship(back_populates="profiles")  # noqa: F821

    clubs: Mapped[list["Club"]] = relationship(  # noqa: F821
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Club.sort_order",
    )

    sessions: Mapped[list["Session"]] = relationship(  # noqa: F821
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="noload",  # Sessions are loaded explicitly — there can be thousands
    )

    __table_args__ = (
        Index("ix_profiles_user_default", "user_id", "is_default"),
    )

    def __repr__(self) -> str:
        return f"<Profile {self.name!r} user_id={self.user_id}>"
