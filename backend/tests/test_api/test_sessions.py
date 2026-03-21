from __future__ import annotations

"""Integration tests for the sessions API endpoints."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient

SAMPLE_DR_CSV = """Dates,03-18-2026,Place,,Player,,
Club,Index,Ball Speed,Launch Direction,Launch Angle,Spin Rate,Spin Axis,Back Spin,Side Spin,Apex,Carry,Total,Offline,Landing Angle,Club Path,Face Angle,Attack Angle,Dynamic Loft
7i,1,107.2,L1.2,22.5,5224,R3.1,5220,168,82.1,155.2,167.6,L3.4,42.1,L2.1,L0.8,2.3,24.1
7i,2,109.8,R0.5,21.3,4950,L1.2,4945,105,85.6,162.1,174.7,R1.2,43.5,R0.3,R0.5,1.8,23.2
"""


@pytest.mark.asyncio
class TestSessionUpload:
    """POST /api/v1/sessions/upload"""

    async def test_upload_requires_auth(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/sessions/upload")
        assert response.status_code in (401, 403, 422)

    async def test_upload_csv_success(
        self, client: AsyncClient, auth_headers: dict, test_profile
    ) -> None:
        files = {
            "file": ("test.csv", io.BytesIO(SAMPLE_DR_CSV.encode()), "text/csv"),
        }
        response = await client.post(
            "/api/v1/sessions/upload",
            headers=auth_headers,
            params={"profile_id": str(test_profile.id)},
            files=files,
        )
        assert response.status_code == 201
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        session = data[0]
        assert session["source_format"] == "bushnell_dr"
        assert session["shot_count"] == 2

    async def test_upload_unsupported_format(
        self, client: AsyncClient, auth_headers: dict, test_profile
    ) -> None:
        files = {
            "file": (
                "random.csv",
                io.BytesIO(b"foo,bar,baz\n1,2,3\n"),
                "text/csv",
            ),
        }
        response = await client.post(
            "/api/v1/sessions/upload",
            headers=auth_headers,
            params={"profile_id": str(test_profile.id)},
            files=files,
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestSessionList:
    """GET /api/v1/sessions"""

    async def test_list_requires_auth(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/sessions")
        assert response.status_code in (401, 403, 422)

    async def test_list_empty(
        self, client: AsyncClient, auth_headers: dict, test_profile
    ) -> None:
        response = await client.get(
            "/api/v1/sessions",
            headers=auth_headers,
            params={"profile_id": str(test_profile.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["sessions"] == []
        assert data["has_more"] is False

    async def test_list_with_data(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_profile,
        test_session_with_shots,
    ) -> None:
        response = await client.get(
            "/api/v1/sessions",
            headers=auth_headers,
            params={"profile_id": str(test_profile.id)},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["shot_count"] == 5


@pytest.mark.asyncio
class TestSessionDetail:
    """GET /api/v1/sessions/{id}"""

    async def test_detail_with_shots(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_session_with_shots,
    ) -> None:
        session_id = str(test_session_with_shots.id)
        response = await client.get(
            f"/api/v1/sessions/{session_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert len(data["shots"]) == 5
        # Verify shot data
        shot = data["shots"][0]
        assert shot["club_name"] == "7 Iron"
        assert float(shot["ball_speed_mph"]) == 107.2

    async def test_detail_not_found(
        self, client: AsyncClient, auth_headers: dict
    ) -> None:
        response = await client.get(
            "/api/v1/sessions/00000000-0000-0000-0000-000000000000",
            headers=auth_headers,
        )
        assert response.status_code == 404
