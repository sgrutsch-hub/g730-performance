from __future__ import annotations

"""
Profile routes — CRUD for golfer profiles and bag management.

Each user can have multiple profiles (family members, different handicaps, etc.).
Clubs are nested under profiles since they belong to a specific golfer's bag.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.club import Club
from app.models.profile import Profile
from app.models.session import Session
from app.models.user import User
from app.schemas.profile import (
    ClubCreate,
    ClubResponse,
    ClubUpdate,
    ProfileCreate,
    ProfileResponse,
    ProfileUpdate,
)
from app.services.processing import process_session_shots

router = APIRouter(prefix="/profiles", tags=["profiles"])


# ── Profile CRUD ──


@router.get("", response_model=list[ProfileResponse])
async def list_profiles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Profile]:
    """List all profiles for the current user."""
    result = await db.execute(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.created_at)
    )
    return list(result.scalars().all())


@router.post("", response_model=ProfileResponse, status_code=201)
async def create_profile(
    body: ProfileCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Create a new golfer profile."""
    # Check profile limit based on subscription
    result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    existing = list(result.scalars().all())

    max_profiles = {"free": 1, "pro": 3, "pro_plus": 10, "coach": 50, "academy": 999}
    limit = max_profiles.get(user.subscription_tier, 1)

    if len(existing) >= limit:
        raise ValidationError(
            f"Profile limit reached ({limit}). Upgrade your subscription for more profiles."
        )

    profile = Profile(
        user_id=user.id,
        name=body.name,
        launch_monitor=body.launch_monitor,
        handicap_index=body.handicap_index,
        default_ball=body.default_ball,
        elevation_ft=body.elevation_ft,
        is_default=len(existing) == 0,  # First profile is default
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Get a specific profile (must belong to the current user)."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile", str(profile_id))
    return profile


@router.patch("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: uuid.UUID,
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """Update a profile's fields. Only provided fields are changed."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile", str(profile_id))

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    await db.commit()
    await db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a profile and all associated data (sessions, shots, clubs).

    Cannot delete the last remaining profile.
    """
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile", str(profile_id))

    # Prevent deleting the last profile
    count_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    all_profiles = list(count_result.scalars().all())
    if len(all_profiles) <= 1:
        raise ValidationError("Cannot delete your only profile")

    await db.delete(profile)
    await db.commit()


# ── Club (Bag) CRUD ──


@router.get("/{profile_id}/clubs", response_model=list[ClubResponse])
async def list_clubs(
    profile_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Club]:
    """List all clubs in a profile's bag."""
    # Verify ownership
    profile = await _get_owned_profile(db, profile_id, user.id)
    result = await db.execute(
        select(Club).where(Club.profile_id == profile.id).order_by(Club.sort_order)
    )
    return list(result.scalars().all())


@router.post("/{profile_id}/clubs", response_model=ClubResponse, status_code=201)
async def add_club(
    profile_id: uuid.UUID,
    body: ClubCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Club:
    """Add a club to the bag."""
    profile = await _get_owned_profile(db, profile_id, user.id)
    club = Club(
        profile_id=profile.id,
        name=body.name,
        brand=body.brand,
        loft_degrees=body.loft_degrees,
        shaft=body.shaft,
        sort_order=body.sort_order,
    )
    db.add(club)
    await db.commit()
    await db.refresh(club)
    return club


@router.patch("/{profile_id}/clubs/{club_id}", response_model=ClubResponse)
async def update_club(
    profile_id: uuid.UUID,
    club_id: uuid.UUID,
    body: ClubUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Club:
    """Update a club in the bag."""
    await _get_owned_profile(db, profile_id, user.id)
    result = await db.execute(
        select(Club).where(Club.id == club_id, Club.profile_id == profile_id)
    )
    club = result.scalar_one_or_none()
    if not club:
        raise NotFoundError("Club", str(club_id))

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(club, field, value)

    await db.commit()
    await db.refresh(club)
    return club


@router.delete("/{profile_id}/clubs/{club_id}", status_code=204)
async def remove_club(
    profile_id: uuid.UUID,
    club_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a club from the bag."""
    await _get_owned_profile(db, profile_id, user.id)
    result = await db.execute(
        select(Club).where(Club.id == club_id, Club.profile_id == profile_id)
    )
    club = result.scalar_one_or_none()
    if not club:
        raise NotFoundError("Club", str(club_id))
    await db.delete(club)
    await db.commit()


# ── Club Targets ──


class ClubTargetsBody(BaseModel):
    """Bulk-set target carry for multiple clubs."""
    targets: dict[str, Decimal | None] = Field(
        ..., description="Mapping of club name → target carry yards (null to clear)"
    )


@router.put("/{profile_id}/club-targets", response_model=list[ClubResponse])
async def set_club_targets(
    profile_id: uuid.UUID,
    body: ClubTargetsBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Club]:
    """
    Bulk-set target carry distances for clubs in the bag.

    Creates clubs that don't exist yet. Updates target_carry for existing clubs.
    Set a target to null to clear it (reverts to bottom-20% trim for that club).
    """
    profile = await _get_owned_profile(db, profile_id, user.id)

    result = await db.execute(
        select(Club).where(Club.profile_id == profile.id)
    )
    existing = {c.name: c for c in result.scalars()}

    for club_name, target in body.targets.items():
        if club_name in existing:
            existing[club_name].target_carry = target
        else:
            club = Club(
                profile_id=profile.id,
                name=club_name,
                target_carry=target,
                sort_order=0,
            )
            db.add(club)

    await db.commit()

    # Return updated club list
    result = await db.execute(
        select(Club).where(Club.profile_id == profile.id).order_by(Club.sort_order)
    )
    return list(result.scalars().all())


@router.post("/{profile_id}/reprocess", status_code=200)
async def reprocess_sessions(
    profile_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reprocess all sessions for a profile with current club targets.

    Use after updating target carry values to re-trim existing sessions.
    """
    profile = await _get_owned_profile(db, profile_id, user.id)

    # Load club targets
    club_result = await db.execute(
        select(Club).where(Club.profile_id == profile.id, Club.target_carry.isnot(None))
    )
    club_targets = {c.name: c.target_carry for c in club_result.scalars()}

    # Reprocess all sessions
    session_result = await db.execute(
        select(Session).where(Session.profile_id == profile.id)
    )
    sessions = list(session_result.scalars().all())

    for session in sessions:
        await process_session_shots(
            db, session,
            club_targets=club_targets,
            elevation_ft=profile.elevation_ft,
        )

    await db.commit()
    return {"reprocessed": len(sessions)}


# ── Helpers ──


async def _get_owned_profile(
    db: AsyncSession, profile_id: uuid.UUID, user_id: uuid.UUID
) -> Profile:
    """Fetch a profile and verify it belongs to the user."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile", str(profile_id))
    return profile
