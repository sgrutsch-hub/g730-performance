from __future__ import annotations

"""
Club model — individual clubs in a golfer's bag.

Tracked per-profile so each golfer has their own bag configuration.
Sort order allows custom bag arrangement (driver first, putter last).
"""

import uuid

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Club(Base):
    __tablename__ = "clubs"

    # ── Owner ──
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Club identity ──
    name: Mapped[str] = mapped_column(String(30), nullable=False)  # "7 Iron", "Driver"
    brand: Mapped[str | None] = mapped_column(String(100))  # "Titleist T200"
    loft_degrees: Mapped[float | None] = mapped_column()
    shaft: Mapped[str | None] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    target_carry: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 1),
        comment="Target carry distance in yards. Used for +/-15% trim window.",
    )

    # ── Relationships ──
    profile: Mapped["Profile"] = relationship(back_populates="clubs")  # noqa: F821

    __table_args__ = (
        Index("ix_clubs_profile_active", "profile_id", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Club {self.name!r} brand={self.brand!r}>"
