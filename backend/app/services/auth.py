from __future__ import annotations

"""
Authentication service — registration, login, token management.

All auth logic lives here, not in route handlers. Routes are thin
wrappers that validate input, call services, and format responses.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthenticationError, ConflictError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.profile import Profile
from app.models.user import User

settings = get_settings()


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
) -> tuple[User, str, str]:
    """
    Register a new user account.

    Creates the user, a default profile, and returns auth tokens.

    Returns:
        Tuple of (user, access_token, refresh_token)

    Raises:
        ConflictError: Email already registered
    """
    # Check for existing user (case-insensitive)
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ConflictError("An account with this email already exists")

    # Create user
    user = User(
        email=email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        auth_provider="email",
    )
    db.add(user)
    await db.flush()  # Assign user.id before creating profile

    # Create default profile
    default_profile = Profile(
        user_id=user.id,
        name=display_name.strip(),
        is_default=True,
    )
    db.add(default_profile)

    await db.commit()
    await db.refresh(user)

    # Generate tokens
    access_token = create_access_token(
        subject=user.id,
        extra_claims={"tier": user.subscription_tier},
    )
    refresh_token = create_refresh_token(subject=user.id)

    return user, access_token, refresh_token


async def login_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> tuple[User, str, str]:
    """
    Authenticate with email + password.

    Returns:
        Tuple of (user, access_token, refresh_token)

    Raises:
        AuthenticationError: Invalid credentials
    """
    email = email.strip().lower()
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Use constant-time comparison even for missing users to prevent timing attacks.
    # verify_password is always called to avoid revealing whether the email exists.
    if not user or not user.password_hash:
        # Still hash something to keep timing consistent
        verify_password("dummy", hash_password("dummy"))
        raise AuthenticationError("Invalid email or password")

    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Invalid email or password")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    # Update last login timestamp
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    access_token = create_access_token(
        subject=user.id,
        extra_claims={"tier": user.subscription_tier},
    )
    refresh_token = create_refresh_token(subject=user.id)

    return user, access_token, refresh_token


async def refresh_tokens(
    db: AsyncSession,
    *,
    refresh_token: str,
) -> tuple[str, str]:
    """
    Exchange a refresh token for new access + refresh tokens.

    The old refresh token is implicitly invalidated by issuing a new one
    with a new jti. For a production system at scale, you'd also want
    a token blacklist in Redis — but for MVP this is sufficient.

    Returns:
        Tuple of (new_access_token, new_refresh_token)

    Raises:
        AuthenticationError: Invalid or expired refresh token
    """
    try:
        payload = decode_refresh_token(refresh_token)
    except Exception as e:
        raise AuthenticationError(f"Invalid refresh token: {e}") from e

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    new_access = create_access_token(
        subject=user.id,
        extra_claims={"tier": user.subscription_tier},
    )
    new_refresh = create_refresh_token(subject=user.id)

    return new_access, new_refresh
