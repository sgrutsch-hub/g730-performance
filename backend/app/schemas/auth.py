from __future__ import annotations

"""
Auth schemas — registration, login, token responses.

Strict validation ensures clean data from the start.
Email normalization and password strength rules live here,
not in the service layer — fail fast at the API boundary.
"""

import re
import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """New user registration."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Require at least one letter and one number."""
        if not re.search(r"[a-zA-Z]", v):
            msg = "Password must contain at least one letter"
            raise ValueError(msg)
        if not re.search(r"[0-9]", v):
            msg = "Password must contain at least one number"
            raise ValueError(msg)
        return v

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, v: str) -> str:
        return v.strip()


class LoginRequest(BaseModel):
    """Email + password login."""

    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RefreshRequest(BaseModel):
    """Token refresh — exchange a refresh token for a new access token."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class UserResponse(BaseModel):
    """Public user representation (never includes password hash)."""

    id: uuid.UUID
    email: str
    display_name: str | None
    subscription_tier: str
    is_verified: bool
    timezone: str

    model_config = {"from_attributes": True}
