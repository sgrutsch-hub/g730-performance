from __future__ import annotations

"""
Session routes — upload, list, detail, delete, export.

The upload endpoint is the gateway for all data ingestion.
It auto-detects the CSV format, parses shots, deduplicates at
the shot level, merges into existing sessions when appropriate,
and applies processing (trim, theoretical carry, shot score).
"""

import csv
import hashlib
import io
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError, ValidationError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.club import Club
from app.models.profile import Profile
from app.models.session import Session
from app.models.shot import Shot
from app.models.user import User
from app.parsers import detect_and_parse
from app.schemas.session import (
    DateWarning,
    SessionDetail,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)
from app.services.dedup import (
    find_duplicate_shots,
    find_existing_session_for_date,
    get_max_shot_index,
)
from app.services.processing import process_session_shots

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/upload", status_code=201)
async def upload_csv(
    file: UploadFile,
    profile_id: uuid.UUID = Query(..., description="Target profile for the imported data"),
    ball_type: str | None = Query(default=None, description="Ball type for this session"),
    override_date: date | None = Query(default=None, description="Override parsed date if it differs from actual session date"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse] | DateWarning:
    """
    Upload a CSV file from any supported launch monitor.

    The file format is auto-detected. Shots are deduplicated at the
    shot level (date + club + ball_speed). New shots are merged into
    existing sessions for the same date.

    If the parsed date differs from today and override_date is not set,
    returns a date_warning response for the frontend to confirm.
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

    if text.startswith("\ufeff"):
        text = text[1:]

    filename = file.filename or "unknown.csv"

    # Auto-detect format and parse
    parsed_sessions = detect_and_parse(text, filename)
    if not parsed_sessions:
        raise ValidationError("No shot data found in file")

    # Apply date override if provided
    if override_date:
        for parsed in parsed_sessions:
            parsed.session_date = override_date

    # Date mismatch warning: if parsed date != today, ask user to confirm
    today = datetime.now(timezone.utc).date()
    parsed_dates = {p.session_date for p in parsed_sessions}
    if not override_date and parsed_dates and today not in parsed_dates:
        previews = []
        for p in parsed_sessions:
            clubs = {}
            for s in p.shots:
                clubs[s.club_name] = clubs.get(s.club_name, 0) + 1
            previews.append({
                "date": str(p.session_date),
                "shot_count": len(p.shots),
                "clubs": list(clubs.keys()),
            })
        return DateWarning(
            parsed_date=list(parsed_dates)[0],
            message=f"File contains data from {', '.join(str(d) for d in sorted(parsed_dates))}, not today. "
                    f"Re-upload with the correct date to confirm.",
            sessions_preview=previews,
        )

    # Check session count limits for free tier
    effective_tier = user.subscription_override or user.subscription_tier
    if effective_tier == "free":
        existing_count = await db.scalar(
            select(func.count()).select_from(Session).where(Session.profile_id == profile_id)
        )
        new_dates = set()
        for p in parsed_sessions:
            existing_for_date = await find_existing_session_for_date(db, profile_id, p.session_date)
            if not existing_for_date:
                new_dates.add(p.session_date)
        if (existing_count or 0) + len(new_dates) > 3:
            raise ValidationError(
                f"Free tier allows 3 sessions. You have {existing_count} and are uploading "
                f"{len(new_dates)} new date(s). Upgrade to Pro for unlimited sessions."
            )

    content_hash = hashlib.sha256(text.encode()).hexdigest()
    created_sessions: list[Session] = []
    sessions_to_process: list[Session] = []
    total_new_shots = 0

    for parsed in parsed_sessions:
        session_date = parsed.session_date

        # Find existing shots for dedup
        existing_fps = await find_duplicate_shots(db, profile_id, session_date)

        # Filter out duplicate shots
        new_shots = []
        for shot_data in parsed.shots:
            fp = (shot_data.club_name, shot_data.ball_speed_mph)
            if fp not in existing_fps:
                new_shots.append(shot_data)
                existing_fps.add(fp)  # Prevent intra-file dupes too

        if not new_shots:
            continue

        # Find or create session for this date
        session = await find_existing_session_for_date(db, profile_id, session_date)

        if session:
            # Merge into existing session
            start_idx = await get_max_shot_index(db, session.id) + 1
        else:
            # Create new session
            session = Session(
                profile_id=profile_id,
                source_file=f"{filename}_{session_date.isoformat()}",
                source_format=parsed.source_format,
                content_hash=content_hash,
                raw_csv=text if len(text) < 500_000 else None,
                session_date=session_date,
                ball_type=ball_type or parsed.ball_type,
                shot_count=0,
                imported_at=func.now(),
            )
            db.add(session)
            await db.flush()
            start_idx = 0
            created_sessions.append(session)

        # Insert new shots
        for i, shot_data in enumerate(new_shots):
            shot = Shot(
                session_id=session.id,
                profile_id=profile_id,
                club_name=shot_data.club_name,
                shot_index=start_idx + i,
                shot_date=session_date,
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

        # Update shot count
        session.shot_count = (session.shot_count or 0) + len(new_shots)
        total_new_shots += len(new_shots)
        sessions_to_process.append(session)

    if not sessions_to_process:
        raise ValidationError("All shots in this file have already been imported (no new data)")

    # Load club targets for processing
    club_result = await db.execute(
        select(Club).where(Club.profile_id == profile_id, Club.target_carry.isnot(None))
    )
    club_targets = {c.name: c.target_carry for c in club_result.scalars()}

    # Process all affected sessions (trim, theoretical carry, shot score)
    await db.flush()
    for session in sessions_to_process:
        await process_session_shots(db, session, club_targets=club_targets)

    await db.commit()

    for session in sessions_to_process:
        await db.refresh(session)

    return [SessionResponse.model_validate(s) for s in sessions_to_process]


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


@router.get("/export")
async def export_csv(
    profile_id: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all shots as a clean CSV for offline analysis."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise NotFoundError("Profile", str(profile_id))

    result = await db.execute(
        select(Shot, Session.source_format)
        .join(Session, Shot.session_id == Session.id)
        .where(Shot.profile_id == profile_id)
        .order_by(Shot.shot_date, Shot.club_name, Shot.shot_index)
    )
    rows = result.all()

    FORMAT_LABELS = {
        "bushnell_dr": "Square LM",
        "bushnell_sa": "Foresight",
        "bushnell_session": "Foresight",
        "seed_import": "Import",
    }

    def _fmt(val: object) -> str:
        if val is None:
            return ""
        return str(round(float(val), 1)) if isinstance(val, (float, int)) or hasattr(val, "__float__") else str(val)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Date", "Club", "Ball Speed", "Club Speed", "Smash Factor",
        "Carry", "Total", "Offline", "Launch Angle", "Spin Rate",
        "Spin Axis", "Attack Angle", "Club Path", "Face Angle",
        "Dynamic Loft", "Apex", "Landing Angle", "Ball Type",
        "Filtered", "Shot Score",
    ])

    for shot, source_format in rows:
        writer.writerow([
            shot.shot_date.strftime("%m-%d-%Y"),
            shot.club_name,
            _fmt(shot.ball_speed_mph),
            _fmt(shot.club_speed_mph),
            _fmt(shot.smash_factor),
            _fmt(shot.carry_yards),
            _fmt(shot.total_yards),
            _fmt(shot.offline_yards),
            _fmt(shot.launch_angle_deg),
            _fmt(shot.spin_rate_rpm),
            _fmt(shot.spin_axis_deg),
            _fmt(shot.attack_angle_deg),
            _fmt(shot.club_path_deg),
            _fmt(shot.face_angle_deg),
            _fmt(shot.dynamic_loft_deg),
            _fmt(shot.apex_feet),
            _fmt(shot.landing_angle_deg),
            shot.ball_type or "",
            "Yes" if shot.is_filtered else "No",
            _fmt(shot.shot_score),
        ])

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="swing-doctor-export-{today_str}.csv"'},
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
