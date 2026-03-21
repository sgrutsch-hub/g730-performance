from __future__ import annotations

"""
Auth routes — registration, login, token refresh.

These are the only unauthenticated endpoints. Everything else
requires a valid access token via the get_current_user dependency.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import login_user, refresh_tokens, register_user

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Create a new user account.

    Returns JWT tokens on success. A default golfer profile is
    automatically created with the user's display name.
    """
    user, access_token, refresh_token = await register_user(
        db,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Authenticate with email and password.

    Returns JWT tokens on success. The access token should be included
    in subsequent requests as: Authorization: Bearer <token>
    """
    user, access_token, refresh_token = await login_user(
        db,
        email=body.email,
        password=body.password,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Exchange a refresh token for new access + refresh tokens.

    Call this when the access token expires. The old refresh token
    is invalidated and a new pair is issued.
    """
    access_token, refresh_token = await refresh_tokens(
        db,
        refresh_token=body.refresh_token,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )
