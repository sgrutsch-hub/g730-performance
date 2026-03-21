from __future__ import annotations

"""
JWT token management and password hashing.

Tokens:
  - Access token: short-lived (15 min), used for API auth
  - Refresh token: long-lived (30 days), used only to mint new access tokens
  - Both are JWT with distinct 'type' claims to prevent misuse

Passwords:
  - bcrypt with automatic salt, cost factor 12
  - Async-safe via passlib's CryptContext
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings

settings = get_settings()

# ── Password hashing ──
# bcrypt is deliberately slow (cost factor 12 ≈ ~300ms per hash).
# This is a feature, not a bug — it makes brute-force attacks impractical.
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """Hash a plaintext password. Returns the bcrypt hash string."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ── JWT tokens ──

def create_access_token(
    subject: str | uuid.UUID,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a short-lived access token.

    Args:
        subject: The user ID (stored as 'sub' claim)
        extra_claims: Additional JWT claims (e.g., subscription tier)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)

    payload = {
        "sub": str(subject),
        "type": "access",
        "iat": now,
        "exp": expire,
        **(extra_claims or {}),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | uuid.UUID) -> str:
    """
    Create a long-lived refresh token.

    Only valid for minting new access tokens — cannot be used for API auth.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": str(subject),
        "type": "refresh",
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),  # Unique ID for token revocation
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises JWTError if the token is invalid, expired, or malformed.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode a token and verify it's an access token (not refresh)."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Invalid token type: expected access token")
    return payload


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode a token and verify it's a refresh token."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise JWTError("Invalid token type: expected refresh token")
    return payload
