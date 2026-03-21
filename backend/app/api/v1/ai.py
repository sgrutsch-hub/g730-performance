from __future__ import annotations

"""AI swing analysis API endpoint."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engine import get_full_analytics
from app.core.exceptions import AuthorizationError, NotFoundError, SubscriptionRequiredError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.profile import Profile
from app.models.user import User
from app.schemas.ai_analysis import AnalysisRequest, SwingAnalysisResponse, ClubInsightResponse, DrillResponse
from app.services.ai_analysis import analyze_swing

router = APIRouter(prefix="/ai", tags=["ai"])


async def _get_owned_profile(
    profile_id: str, user: User, db: AsyncSession
) -> Profile:
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile not found")
    if str(profile.user_id) != str(user.id):
        raise AuthorizationError("Not your profile")
    return profile


@router.post(
    "/profiles/{profile_id}/analyze",
    response_model=SwingAnalysisResponse,
    summary="AI-powered swing analysis",
)
async def swing_analysis(
    profile_id: str,
    body: AnalysisRequest | None = None,
    club: str | None = Query(None, description="Focus analysis on a single club"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    ball_type: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SwingAnalysisResponse:
    """
    Generate AI-powered swing analysis with personalized coaching advice.

    Uses Claude to analyze shot data patterns and provide:
    - Overall performance assessment
    - Per-club insights (strengths, weaknesses, priority fixes)
    - Top 3 improvement priorities
    - Specific drill recommendations
    - Equipment observations
    - Next session practice plan

    Requires Pro tier or higher subscription.
    """
    # Check subscription
    if user.subscription_tier == "free":
        raise SubscriptionRequiredError(
            "AI analysis requires a Pro subscription",
            required_tier="pro",
        )

    profile = await _get_owned_profile(profile_id, user, db)

    # Get analytics data
    analytics = await get_full_analytics(
        db, profile_id,
        club_name=club, date_from=date_from,
        date_to=date_to, ball_type=ball_type,
    )

    if not analytics.club_summaries:
        raise NotFoundError("No shot data available for analysis. Import some sessions first.")

    # Run AI analysis
    additional_context = body.additional_context if body else None
    analysis = await analyze_swing(
        analytics,
        golfer_name=profile.name,
        launch_monitor=profile.launch_monitor,
        additional_context=additional_context,
    )

    return SwingAnalysisResponse(
        overall_assessment=analysis.overall_assessment,
        handicap_context=analysis.handicap_context,
        club_insights=[
            ClubInsightResponse(**ci.__dict__)
            for ci in analysis.club_insights
        ],
        top_priorities=analysis.top_priorities,
        drills=[
            DrillResponse(**d.__dict__)
            for d in analysis.drills
        ],
        equipment_notes=analysis.equipment_notes,
        next_session_plan=analysis.next_session_plan,
    )
