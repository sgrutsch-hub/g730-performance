from __future__ import annotations

"""
User model — authentication identity.

A user can have multiple profiles (e.g., parent account with kids).
Auth is decoupled from golf identity so we can support OAuth providers
without polluting the golf data model.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    # ── Identity ──
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(100))

    # ── Auth ──
    # Nullable for OAuth-only users who never set a password.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    auth_provider: Mapped[str] = mapped_column(
        String(20),
        default="email",
        server_default="email",
    )
    auth_provider_id: Mapped[str | None] = mapped_column(String(255))

    # ── Subscription ──
    subscription_tier: Mapped[str] = mapped_column(
        String(20),
        default="free",
        server_default="free",
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255))

    # ── Account state ──
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    is_verified: Mapped[bool] = mapped_column(default=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Preferences ──
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="America/Chicago",
        server_default="America/Chicago",
    )

    # ── Relationships ──
    profiles: Mapped[list["Profile"]] = relationship(  # noqa: F821
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_users_email_lower", func.lower(email), unique=True),
        Index("ix_users_stripe", "stripe_customer_id", unique=True),
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
