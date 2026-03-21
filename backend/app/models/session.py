from __future__ import annotations

"""
Session model — a single practice session or range visit.

A session maps 1:1 to an imported CSV file. We store the raw CSV content
so we can re-parse if formats change or parsers improve. The source_format
field identifies which parser produced the data.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Session(Base):
    __tablename__ = "sessions"

    # ── Owner ──
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Source ──
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Parser that produced this data: bushnell_dr, bushnell_sa, garmin_r10, etc.",
    )
    raw_csv: Mapped[str | None] = mapped_column(
        Text,
        comment="Original CSV content for re-parsing. Nullable for API-ingested sessions.",
    )

    # ── Session metadata ──
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ball_type: Mapped[str | None] = mapped_column(String(50))
    location: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    # ── Computed aggregates (denormalized for fast listing) ──
    shot_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # ── Processing state ──
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Relationships ──
    profile: Mapped["Profile"] = relationship(back_populates="sessions")  # noqa: F821

    shots: Mapped[list["Shot"]] = relationship(  # noqa: F821
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="noload",  # Shots loaded explicitly — can be 100+ per session
        order_by="Shot.shot_index",
    )

    __table_args__ = (
        # Prevent duplicate imports of the same file for the same profile
        Index("uq_sessions_profile_file", "profile_id", "source_file", unique=True),
        # Fast lookup by profile + date range (most common query pattern)
        Index("ix_sessions_profile_date", "profile_id", "session_date"),
    )

    def __repr__(self) -> str:
        return f"<Session {self.source_file!r} date={self.session_date}>"
