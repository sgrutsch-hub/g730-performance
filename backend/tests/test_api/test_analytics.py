from __future__ import annotations

"""Integration tests for the analytics API endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestAnalyticsSummary:
    """GET /api/v1/analytics/profiles/{id}/summary"""

    async def test_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get(
            "/api/v1/analytics/profiles/fake-id/summary"
        )
        assert response.status_code in (401, 403, 422)

    async def test_full_summary(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Club summaries
        assert len(data["club_summaries"]) >= 1
        club = data["club_summaries"][0]
        assert club["club_name"] == "7 Iron"
        assert club["shot_count"] == 5
        assert float(club["avg_carry"]) > 140

        # Session trends
        assert len(data["session_trends"]) >= 1

        # Improvement summary
        assert isinstance(data["improvement_summary"], list)

        # Handicap estimate
        assert data["handicap_estimate"] is not None
        hc = data["handicap_estimate"]
        assert "estimated_low" in hc
        assert "estimated_high" in hc
        assert hc["confidence"] in ("low", "medium", "high")
        assert hc["total_shots"] == 5

    async def test_summary_empty_profile(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["club_summaries"] == []
        assert data["session_trends"] == []

    async def test_summary_with_club_filter(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/summary",
            headers=auth_headers,
            params={"club": "7 Iron"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["club_summaries"]) == 1
        assert data["club_summaries"][0]["club_name"] == "7 Iron"


@pytest.mark.asyncio
class TestClubSummaries:
    """GET /api/v1/analytics/profiles/{id}/clubs"""

    async def test_club_stats(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/clubs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        clubs = response.json()
        assert len(clubs) == 1
        club = clubs[0]
        assert club["club_name"] == "7 Iron"
        assert club["shot_count"] == 5
        assert club["avg_ball_speed"] is not None
        assert club["avg_spin_rate"] is not None
        assert club["std_offline"] is not None  # dispersion


@pytest.mark.asyncio
class TestSessionTrends:
    """GET /api/v1/analytics/profiles/{id}/trends"""

    async def test_trends(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/trends",
            headers=auth_headers,
        )
        assert response.status_code == 200
        trends = response.json()
        assert len(trends) == 1
        assert trends[0]["session_date"] == "2026-03-18"
        assert trends[0]["shot_count"] == 5


@pytest.mark.asyncio
class TestHandicapEstimate:
    """GET /api/v1/analytics/profiles/{id}/handicap"""

    async def test_handicap_with_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/handicap",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert float(data["estimated_low"]) >= 0
        assert float(data["estimated_high"]) <= 36
        assert data["total_shots"] == 5
        assert len(data["factors"]) >= 1

    async def test_handicap_no_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
    ) -> None:
        response = await client.get(
            f"/api/v1/analytics/profiles/{test_profile.id}/handicap",
            headers=auth_headers,
        )
        assert response.status_code == 404
