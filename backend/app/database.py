from __future__ import annotations

"""
Async SQLAlchemy engine and session management.

Uses the async engine with asyncpg for non-blocking database I/O.
Connection pooling is configured via settings for production readiness.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

# Use NullPool in testing to avoid connection leaks.
# In production, use QueuePool (the default) with configured pool size.
engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size if not settings.is_development else 5,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # Verify connections before use (handles stale connections)
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit — we control the lifecycle
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Usage in route handlers:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed after the request completes.
    Commits must be explicit — nothing is auto-committed.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Cleanly shut down the connection pool. Called on app shutdown."""
    await engine.dispose()
