"""
Seed the admin / owner account.

Usage:
    ADMIN_PASSWORD=<password> python -m scripts.seed_admin

Requires ADMIN_PASSWORD env var (no default for safety).
Idempotent — skips creation if the user already exists.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.database import _get_session_factory, dispose_engine
from app.models.profile import Profile
from app.models.user import User

ADMIN_EMAIL = "shane@swing.doctor"


async def seed() -> None:
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        print("ERROR: ADMIN_PASSWORD env var is required.", file=sys.stderr)
        sys.exit(1)

    factory = _get_session_factory()
    async with factory() as session:  # type: AsyncSession
        result = await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Admin user {ADMIN_EMAIL} already exists (id={existing.id}). Skipping.")
            return

        user = User(
            email=ADMIN_EMAIL,
            display_name="Shane",
            password_hash=hash_password(password),
            auth_provider="email",
            is_admin=True,
            subscription_override="pro",
            subscription_tier="free",
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.flush()  # populate user.id for the profile FK

        profile = Profile(
            user_id=user.id,
            name="Shane",
            is_default=True,
        )
        session.add(profile)

        await session.commit()
        print(f"Created admin user {ADMIN_EMAIL} (id={user.id}) with default profile.")


def main() -> None:
    try:
        asyncio.run(seed())
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
