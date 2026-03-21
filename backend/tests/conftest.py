from __future__ import annotations

"""
Shared test fixtures.

Provides a test database, async sessions, and a configured FastAPI test client.
For parser tests that don't need a database, these fixtures are available
but not required — pytest only injects fixtures that are requested.

Uses an in-memory SQLite database for fast, isolated tests.
Async fixtures provided via pytest-asyncio.

Note: API/DB fixtures require Python 3.11+ (SQLAlchemy Mapped annotations
use X | None syntax). Parser-only tests work on any Python version.
"""

import sys

# Only import DB/API fixtures on Python 3.11+ where the models can load
if sys.version_info >= (3, 11):
    import uuid
    from datetime import date
    from decimal import Decimal
    from typing import AsyncGenerator

    import pytest
    import pytest_asyncio
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.security import hash_password
    from app.database import get_db
    from app.main import create_app
    from app.models.base import Base
    from app.models.profile import Profile
    from app.models.session import Session
    from app.models.shot import Shot
    from app.models.user import User

    TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
    test_engine = create_async_engine(TEST_DB_URL, echo=False)
    TestSessionLocal = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    @pytest_asyncio.fixture
    async def db() -> AsyncGenerator[AsyncSession, None]:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with TestSessionLocal() as session:
            yield session
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    @pytest_asyncio.fixture
    async def app(db: AsyncSession):
        application = create_app()
        async def override_get_db():
            yield db
        application.dependency_overrides[get_db] = override_get_db
        return application

    @pytest_asyncio.fixture
    async def client(app) -> AsyncGenerator[AsyncClient, None]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    @pytest_asyncio.fixture
    async def test_user(db: AsyncSession) -> User:
        user = User(
            email="test@swingdoctor.com",
            password_hash=hash_password("TestPass123"),
            display_name="Test Golfer",
            is_active=True,
            is_verified=True,
            subscription_tier="pro",
        )
        db.add(user)
        await db.flush()
        profile = Profile(
            user_id=user.id,
            name="Test Golfer",
            is_default=True,
            launch_monitor="Bushnell Launch Pro",
        )
        db.add(profile)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest_asyncio.fixture
    async def test_profile(db: AsyncSession, test_user: User) -> Profile:
        from sqlalchemy import select
        result = await db.execute(
            select(Profile).where(
                Profile.user_id == test_user.id,
                Profile.is_default == True,  # noqa: E712
            )
        )
        return result.scalar_one()

    @pytest_asyncio.fixture
    async def auth_headers(client: AsyncClient, test_user: User) -> dict[str, str]:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@swingdoctor.com", "password": "TestPass123"},
        )
        token = response.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    @pytest_asyncio.fixture
    async def test_session_with_shots(
        db: AsyncSession, test_profile: Profile
    ) -> Session:
        session = Session(
            profile_id=test_profile.id,
            source_file="test-03-18-2026-DrivingRange.csv",
            source_format="bushnell_dr",
            session_date=date(2026, 3, 18),
            ball_type="tp5x",
            shot_count=5,
        )
        db.add(session)
        await db.flush()

        shots_data = [
            {"bs": "107.2", "c": "155.2", "la": "22.5", "sr": 5224, "off": "-3.4", "sf": "1.43"},
            {"bs": "109.8", "c": "162.1", "la": "21.3", "sr": 4950, "off": "1.2", "sf": "1.48"},
            {"bs": "105.1", "c": "148.9", "la": "24.1", "sr": 5580, "off": "-8.1", "sf": "1.42"},
            {"bs": "111.3", "c": "165.5", "la": "20.8", "sr": 4800, "off": "2.5", "sf": "1.47"},
            {"bs": "103.5", "c": "142.3", "la": "25.2", "sr": 5900, "off": "-5.2", "sf": "1.40"},
        ]

        for i, s in enumerate(shots_data):
            shot = Shot(
                session_id=session.id,
                profile_id=test_profile.id,
                club_name="7 Iron",
                shot_index=i,
                shot_date=date(2026, 3, 18),
                ball_speed_mph=Decimal(s["bs"]),
                carry_yards=Decimal(s["c"]),
                launch_angle_deg=Decimal(s["la"]),
                spin_rate_rpm=s["sr"],
                offline_yards=Decimal(s["off"]),
                smash_factor=Decimal(s["sf"]),
                is_filtered=True,
                ball_type="tp5x",
            )
            db.add(shot)

        await db.commit()
        await db.refresh(session)
        return session
