from __future__ import annotations

"""Integration tests for the auth API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAuthRegister:
    """POST /api/v1/auth/register"""

    async def test_register_success(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@swingdoctor.com",
                "password": "TestPass123",
                "display_name": "New Golfer",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    async def test_register_duplicate_email(
        self, client: AsyncClient, test_user
    ) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@swingdoctor.com",
                "password": "TestPass123",
                "display_name": "Dupe",
            },
        )
        assert response.status_code == 409

    async def test_register_weak_password(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "weak@swingdoctor.com",
                "password": "123",
                "display_name": "Weak",
            },
        )
        assert response.status_code == 422

    async def test_register_invalid_email(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "TestPass123",
                "display_name": "Bad Email",
            },
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestAuthLogin:
    """POST /api/v1/auth/login"""

    async def test_login_success(
        self, client: AsyncClient, test_user
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@swingdoctor.com",
                "password": "TestPass123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_wrong_password(
        self, client: AsyncClient, test_user
    ) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@swingdoctor.com",
                "password": "WrongPass123",
            },
        )
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@swingdoctor.com",
                "password": "TestPass123",
            },
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestAuthRefresh:
    """POST /api/v1/auth/refresh"""

    async def test_refresh_success(
        self, client: AsyncClient, test_user
    ) -> None:
        # First login to get tokens
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@swingdoctor.com", "password": "TestPass123"},
        )
        refresh_token = login.json()["refresh_token"]

        # Use refresh token
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_refresh_invalid_token(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "not.a.real.token"},
        )
        assert response.status_code == 401
