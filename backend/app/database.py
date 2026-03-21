from __future__ import annotations

"""
Async SQLAlchemy engine and session management.

Uses the async engine with asyncpg for non-blocking database I/O.
Connection pooling is configured via settings for production readiness.

The engine is created lazily to avoid import-time database connections,
which allows test suites to override the dependency without asyncpg installed.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        from app.config import get_settings
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size if not settings.is_development else 5,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Usage in route handlers:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...

    The session is automatically closed after the request completes.
    Commits must be explicit — nothing is auto-committed.
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def dispose_engine() -> None:
    """Cleanly shut down the connection pool. Called on app shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
