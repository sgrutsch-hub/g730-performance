from __future__ import annotations

"""Profile schemas — golfer identity and preferences."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class ProfileCreate(BaseModel):
    """Create a new golfer profile."""

    name: str = Field(min_length=1, max_length=100)
    launch_monitor: str | None = Field(default=None, max_length=50)
    handicap_index: Decimal | None = Field(default=None, ge=-10, le=54)
    default_ball: str | None = Field(default=None, max_length=50)
    elevation_ft: int = Field(default=0, ge=-500, le=15000)


class ProfileUpdate(BaseModel):
    """Partial update — only provided fields are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    launch_monitor: str | None = None
    handicap_index: Decimal | None = Field(default=None, ge=-10, le=54)
    default_ball: str | None = None
    elevation_ft: int | None = Field(default=None, ge=-500, le=15000)
    settings: dict | None = None


class ProfileResponse(BaseModel):
    """Profile as returned by the API."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    is_default: bool
    launch_monitor: str | None
    handicap_index: Decimal | None
    default_ball: str | None
    elevation_ft: int
    settings: dict | None
    clubs: list["ClubResponse"] = []

    model_config = {"from_attributes": True}


class ClubCreate(BaseModel):
    """Add a club to a profile's bag."""

    name: str = Field(min_length=1, max_length=30)
    brand: str | None = Field(default=None, max_length=100)
    loft_degrees: float | None = Field(default=None, ge=0, le=90)
    shaft: str | None = Field(default=None, max_length=100)
    sort_order: int = Field(default=0, ge=0, le=99)


class ClubUpdate(BaseModel):
    """Partial club update."""

    name: str | None = Field(default=None, min_length=1, max_length=30)
    brand: str | None = None
    loft_degrees: float | None = Field(default=None, ge=0, le=90)
    shaft: str | None = None
    sort_order: int | None = Field(default=None, ge=0, le=99)
    is_active: bool | None = None


class ClubResponse(BaseModel):
    """Club as returned by the API."""

    id: uuid.UUID
    name: str
    brand: str | None
    loft_degrees: float | None
    shaft: str | None
    sort_order: int
    is_active: bool

    model_config = {"from_attributes": True}


# Resolve forward reference
ProfileResponse.model_rebuild()
