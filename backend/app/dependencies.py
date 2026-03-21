from __future__ import annotations

"""
FastAPI dependencies — shared across all route handlers.

The dependency injection chain:
  get_db() → yields AsyncSession
  get_current_user(db, token) → resolves JWT to User
  require_subscription(user, tier) → gates premium features
"""

import uuid

from fastapi import Depends, Header
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthenticationError, AuthorizationError, SubscriptionRequiredError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User

settings = get_settings()

# Subscription tier hierarchy — higher index = more access
TIER_HIERARCHY = ["free", "pro", "pro_plus", "coach", "academy"]


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    """
    Extract and validate the JWT from the Authorization header.
    Returns the authenticated User or raises AuthenticationError.

    Usage in routes:
        async def my_route(user: User = Depends(get_current_user)):
            ...
    """
    if not authorization:
        raise AuthenticationError("Missing authorization header")

    # Support "Bearer <token>" format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":  # noqa: PLR2004
        raise AuthenticationError("Invalid authorization header format")

    token = parts[1]

    try:
        payload = decode_access_token(token)
    except JWTError as e:
        raise AuthenticationError(f"Invalid or expired token: {e}") from e

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing subject claim")

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError as e:
        raise AuthenticationError("Invalid user ID in token") from e

    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")
    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    return user


def require_tier(minimum_tier: str):
    """
    Dependency factory that gates routes by subscription tier.

    Usage:
        @router.get("/premium-feature", dependencies=[Depends(require_tier("pro"))])
        async def premium_feature(...):
            ...
    """
    minimum_index = TIER_HIERARCHY.index(minimum_tier) if minimum_tier in TIER_HIERARCHY else 0

    async def _check_tier(user: User = Depends(get_current_user)) -> User:
        # Admin subscription override bypasses normal tier check
        effective = user.subscription_override or user.subscription_tier
        user_index = (
            TIER_HIERARCHY.index(effective)
            if effective in TIER_HIERARCHY
            else 0
        )
        if user_index < minimum_index:
            raise SubscriptionRequiredError(required_tier=minimum_tier)
        return user

    return _check_tier
