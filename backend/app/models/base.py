from __future__ import annotations

"""
Base model with common columns and conventions.

Every table gets:
- UUID primary key (no auto-increment integers leaking sequence info)
- created_at / updated_at timestamps with timezone
- A consistent __repr__ for debugging
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    # Common columns inherited by every table
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-100,  # Always show id first
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
    )

    def __repr__(self) -> str:
        """Auto-generate repr from table name + id."""
        return f"<{self.__class__.__name__} id={self.id}>"
