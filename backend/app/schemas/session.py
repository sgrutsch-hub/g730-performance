from __future__ import annotations

"""Session and shot schemas — the data pipeline contracts."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    """Session listing — lightweight, no shots included."""

    id: uuid.UUID
    profile_id: uuid.UUID
    source_file: str
    source_format: str
    session_date: date
    ball_type: str | None
    location: str | None
    notes: str | None
    shot_count: int
    imported_at: datetime

    model_config = {"from_attributes": True}


class SessionDetail(SessionResponse):
    """Session with all shots — used for single-session views."""

    shots: list["ShotResponse"] = []


class SessionUpdate(BaseModel):
    """Editable session fields (ball type, notes, location)."""

    ball_type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class ShotResponse(BaseModel):
    """Individual shot data — the full metric set."""

    id: uuid.UUID
    club_name: str
    shot_index: int
    shot_date: date

    # Ball data
    ball_speed_mph: Decimal | None
    launch_angle_deg: Decimal | None
    launch_direction_deg: Decimal | None
    spin_rate_rpm: int | None
    spin_axis_deg: Decimal | None
    back_spin_rpm: int | None
    side_spin_rpm: int | None

    # Club data
    club_speed_mph: Decimal | None
    smash_factor: Decimal | None
    attack_angle_deg: Decimal | None
    club_path_deg: Decimal | None
    face_angle_deg: Decimal | None
    face_to_path_deg: Decimal | None
    dynamic_loft_deg: Decimal | None
    closure_rate_dps: Decimal | None

    # Result data
    carry_yards: Decimal | None
    total_yards: Decimal | None
    offline_yards: Decimal | None
    apex_feet: Decimal | None
    landing_angle_deg: Decimal | None
    hang_time_sec: Decimal | None
    curve_yards: Decimal | None

    # Computed
    theoretical_carry: Decimal | None
    is_filtered: bool
    ball_type: str | None

    model_config = {"from_attributes": True}


class SessionListResponse(BaseModel):
    """Paginated session listing."""

    items: list[SessionResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# Resolve forward reference
SessionDetail.model_rebuild()
