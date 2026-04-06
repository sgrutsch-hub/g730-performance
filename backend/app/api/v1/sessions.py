from __future__ import annotations

"""
Session routes — upload, list, detail, delete.

The upload endpoint is the gateway for all data ingestion.
It auto-detects the CSV format, parses shots, applies the
bottom-N% trim, and stores everything in a single transaction.
"""

import hashlib
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.profile import Profile
from app.models.session import Session
from app.models.shot import Shot
from app.models.user import User
from app.parsers import detect_and_parse
from app.schemas.session import (
    SessionDetail,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)
from app.services.processing import process_session_shots

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/upload", response_model=list[SessionResponse], status_code=201)
async def upload_csv(
    file: UploadFile,
    profile_id: uuid.UUID = Query(..., description="Target profile for the imported data"),
    ball_type: str | None = Query(default=None, description="Ball type for this session"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Session]:
    """
    Upload a CSV file from any supported launch monitor.

    The file format is auto-detected. A single file may contain
    multiple sessions (e.g., Bushnell DrivingRange format groups
    shots by date). Each session is stored separately.

    Returns the created session(s).
    """
    # Verify profile ownership
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile", str(profile_id))

    # Read and decode file
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError as e:
            raise ValidationError("Unable to read file — unsupported encoding") from e

    # Strip BOM if present
    if text.startswith("\ufeff"):
        text = text[1:]

    filename = file.filename or "unknown.csv"

    # Content-hash duplicate check: reject the entire file if already imported
    content_hash = hashlib.sha256(text.encode()).hexdigest()
    existing_hash = await db.execute(
        select(Session).where(
            Session.profile_id == profile_id,
            Session.content_hash == content_hash,
        )
    )
    if existing_hash.scalar_one_or_none():
        raise ValidationError("This file has already been imported (duplicate content detected)")

    # Auto-detect format and parse
    parsed_sessions = detect_and_parse(text, filename)

    if not parsed_sessions:
        raise ValidationError("No shot data found in file")

    # Check session count limits for free tier
    effective_tier = user.subscription_override or user.subscription_tier
    if effective_tier == "free":
        existing_count = await db.scalar(
            select(func.count()).select_from(Session).where(Session.profile_id == profile_id)
        )
        if (existing_count or 0) + len(parsed_sessions) > 3:
            raise ValidationError(
                f"Free tier allows 3 sessions. You have {existing_count} and are uploading "
                f"{len(parsed_sessions)}. Upgrade to Pro for unlimited sessions."
            )

    created_sessions: list[Session] = []

    for parsed in parsed_sessions:
        # Check for duplicate
        existing = await db.execute(
            select(Session).where(
                Session.profile_id == profile_id,
                Session.source_file == parsed.source_file,
            )
        )
        if existing.scalar_one_or_none():
            continue  # Skip duplicates silently

        # Create session
        session = Session(
            profile_id=profile_id,
            source_file=parsed.source_file,
            source_format=parsed.source_format,
            content_hash=content_hash,
            raw_csv=text if len(text) < 500_000 else None,  # Don't store huge files
            session_date=parsed.session_date,
            ball_type=ball_type or parsed.ball_type,
            shot_count=len(parsed.shots),
            imported_at=func.now(),
        )
        db.add(session)
        await db.flush()  # Get session.id

        # Create shots
        for idx, shot_data in enumerate(parsed.shots):
            shot = Shot(
                session_id=session.id,
                profile_id=profile_id,
                club_name=shot_data.club_name,
                shot_index=idx,
                shot_date=parsed.session_date,
                ball_speed_mph=shot_data.ball_speed_mph,
                launch_angle_deg=shot_data.launch_angle_deg,
                launch_direction_deg=shot_data.launch_direction_deg,
                spin_rate_rpm=shot_data.spin_rate_rpm,
                spin_axis_deg=shot_data.spin_axis_deg,
                back_spin_rpm=shot_data.back_spin_rpm,
                side_spin_rpm=shot_data.side_spin_rpm,
                club_speed_mph=shot_data.club_speed_mph,
                smash_factor=shot_data.smash_factor,
                attack_angle_deg=shot_data.attack_angle_deg,
                club_path_deg=shot_data.club_path_deg,
                face_angle_deg=shot_data.face_angle_deg,
                face_to_path_deg=shot_data.face_to_path_deg,
                dynamic_loft_deg=shot_data.dynamic_loft_deg,
                closure_rate_dps=shot_data.closure_rate_dps,
                carry_yards=shot_data.carry_yards,
                total_yards=shot_data.total_yards,
                offline_yards=shot_data.offline_yards,
                apex_feet=shot_data.apex_feet,
                landing_angle_deg=shot_data.landing_angle_deg,
                hang_time_sec=shot_data.hang_time_sec,
                curve_yards=shot_data.curve_yards,
                ball_type=ball_type or parsed.ball_type,
            )
            db.add(shot)

        created_sessions.append(session)

    if not created_sessions:
        raise ValidationError("All sessions in this file have already been imported")

    # Apply bottom-20% trim and compute theoretical carry
    await db.flush()
    for session in created_sessions:
        await process_session_shots(db, session)

    await db.commit()

    # Refresh to get final state
    for session in created_sessions:
        await db.refresh(session)

    return created_sessions


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    profile_id: uuid.UUID = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    ball_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """List sessions with optional date/ball filters and pagination."""
    # Verify ownership
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Profile", str(profile_id))

    # Build query
    query = select(Session).where(Session.profile_id == profile_id)
    count_query = select(func.count()).select_from(Session).where(
        Session.profile_id == profile_id
    )

    if date_from:
        query = query.where(Session.session_date >= date_from)
        count_query = count_query.where(Session.session_date >= date_from)
    if date_to:
        query = query.where(Session.session_date <= date_to)
        count_query = count_query.where(Session.session_date <= date_to)
    if ball_type:
        query = query.where(Session.ball_type == ball_type)
        count_query = count_query.where(Session.ball_type == ball_type)

    total = await db.scalar(count_query) or 0

    query = query.order_by(Session.session_date.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await db.execute(query)
    sessions = list(result.scalars().all())

    return SessionListResponse(
        items=sessions,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Session:
    """Get session detail with all shots."""
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.shots))
        .join(Profile)
        .where(Session.id == session_id, Profile.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Session", str(session_id))
    return session


@router.patch("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Session:
    """Update session metadata (ball type, notes, location)."""
    result = await db.execute(
        select(Session)
        .join(Profile)
        .where(Session.id == session_id, Profile.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Session", str(session_id))

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(session, field, value)

    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a session and all its shots."""
    result = await db.execute(
        select(Session)
        .join(Profile)
        .where(Session.id == session_id, Profile.user_id == user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("Session", str(session_id))

    await db.delete(session)
    await db.commit()
