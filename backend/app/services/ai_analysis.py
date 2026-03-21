from __future__ import annotations

"""
AI-powered swing analysis using Claude.

Generates personalized coaching advice, drill recommendations,
and performance insights from shot data. This is the core
differentiator — no other golf analytics app does this.

Architecture:
  - Takes analytics engine output (club summaries, trends, etc.)
  - Constructs a rich prompt with the golfer's data context
  - Calls Claude API for structured analysis
  - Returns typed advice objects

Pricing:
  - Free tier: basic summary only (no drills, no detailed advice)
  - Pro tier: full analysis with drills and equipment suggestions
  - Pro+ tier: session-by-session coaching with video reference links
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.analytics.engine import ClubSummary, FullAnalytics, HandicapEstimate, TrendSummary
from app.config import get_settings


@dataclass
class DrillRecommendation:
    """A specific practice drill with instructions."""

    name: str
    focus_area: str  # e.g., "consistency", "distance", "accuracy"
    description: str
    duration_minutes: int
    difficulty: str  # "beginner", "intermediate", "advanced"
    expected_improvement: str


@dataclass
class ClubInsight:
    """AI-generated insight for a specific club."""

    club_name: str
    summary: str  # 1-2 sentence overview
    strengths: list[str]
    weaknesses: list[str]
    priority_fix: str  # single most impactful thing to work on


@dataclass
class SwingAnalysis:
    """Complete AI-generated swing analysis."""

    overall_assessment: str  # 2-3 sentence overview
    handicap_context: str  # what the handicap estimate means
    club_insights: list[ClubInsight]
    top_priorities: list[str]  # top 3 things to work on
    drills: list[DrillRecommendation]
    equipment_notes: list[str]  # observations about equipment
    next_session_plan: str  # what to focus on next time


def _build_analysis_prompt(
    analytics: FullAnalytics,
    golfer_name: str | None = None,
    launch_monitor: str | None = None,
    additional_context: str | None = None,
) -> str:
    """Build a rich prompt for Claude with the golfer's complete data context."""

    # Format club summaries
    club_lines = []
    for cs in analytics.club_summaries:
        parts = [f"  {cs.club_name}: {cs.shot_count} shots"]
        if cs.avg_carry:
            parts.append(f"avg carry {cs.avg_carry}yds")
        if cs.avg_ball_speed:
            parts.append(f"avg ball speed {cs.avg_ball_speed}mph")
        if cs.avg_spin_rate:
            parts.append(f"avg spin {cs.avg_spin_rate}rpm")
        if cs.avg_launch_angle:
            parts.append(f"avg launch {cs.avg_launch_angle}°")
        if cs.avg_smash:
            parts.append(f"smash {cs.avg_smash}")
        if cs.std_offline:
            parts.append(f"dispersion std {cs.std_offline}yds")
        if cs.left_miss_pct and cs.right_miss_pct:
            parts.append(f"miss pattern {cs.left_miss_pct}% left / {cs.right_miss_pct}% right")
        if cs.avg_apex:
            parts.append(f"avg apex {cs.avg_apex}ft")
        if cs.avg_landing_angle:
            parts.append(f"avg landing {cs.avg_landing_angle}°")
        club_lines.append(", ".join(parts))

    # Format improvement trends
    trend_lines = []
    for t in analytics.improvement_summary:
        if t.current is not None:
            arrow = {"up": "↑ improving", "down": "↓ declining", "flat": "→ stable"}[t.direction]
            delta_str = f" ({'+' if t.delta and t.delta > 0 else ''}{t.delta})" if t.delta else ""
            trend_lines.append(f"  {t.metric}: {t.current}{delta_str} {arrow}")

    # Format handicap
    hc = analytics.handicap_estimate
    hc_str = "Not enough data"
    if hc:
        hc_str = f"{hc.estimated_low}-{hc.estimated_high} ({hc.confidence} confidence)"
        hc_str += "\n  Factors: " + "; ".join(hc.factors)

    golfer_str = golfer_name or "the golfer"
    monitor_str = f" (using {launch_monitor})" if launch_monitor else ""

    prompt = f"""You are an expert PGA-certified golf instructor and launch monitor data analyst.
Analyze the following shot data for {golfer_str}{monitor_str} and provide detailed, actionable coaching advice.

## Shot Data Summary

### Club Statistics (filtered, bottom 20% trimmed):
{chr(10).join(club_lines) if club_lines else "  No club data available"}

### Improvement Trends (recent vs earlier sessions):
{chr(10).join(trend_lines) if trend_lines else "  Not enough sessions to compare"}

### Estimated Handicap: {hc_str}

{f"### Additional Context from Golfer: {additional_context}" if additional_context else ""}

## Instructions

Analyze this data and provide:

1. **Overall Assessment** (2-3 sentences): What does this data tell you about this golfer's game? Be specific about what's working and what isn't.

2. **Handicap Context**: Explain what their estimated handicap range means and what the biggest gaps are between their current game and the next level.

3. **Club Insights**: For each club with data, provide:
   - A brief summary of performance
   - Specific strengths (backed by data)
   - Specific weaknesses (backed by data)
   - The single highest-priority fix

4. **Top 3 Priorities**: The three most impactful things this golfer should work on, ranked by expected improvement.

5. **Drill Recommendations**: 3-5 specific practice drills with:
   - Name and focus area
   - Clear step-by-step instructions
   - Duration and difficulty level
   - What improvement to expect

6. **Equipment Notes**: Any observations about equipment (e.g., spin rates suggesting wrong shaft flex, gaps in yardage coverage, etc.)

7. **Next Session Plan**: A specific plan for their next practice session (what clubs, what to focus on, how many shots).

Be direct and specific. Use their actual numbers. Don't hedge with "it depends" — commit to recommendations based on the data.

Respond in JSON format:
{{
  "overall_assessment": "...",
  "handicap_context": "...",
  "club_insights": [
    {{
      "club_name": "...",
      "summary": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "priority_fix": "..."
    }}
  ],
  "top_priorities": ["...", "...", "..."],
  "drills": [
    {{
      "name": "...",
      "focus_area": "...",
      "description": "...",
      "duration_minutes": 15,
      "difficulty": "intermediate",
      "expected_improvement": "..."
    }}
  ],
  "equipment_notes": ["..."],
  "next_session_plan": "..."
}}"""

    return prompt


async def analyze_swing(
    analytics: FullAnalytics,
    *,
    golfer_name: str | None = None,
    launch_monitor: str | None = None,
    additional_context: str | None = None,
) -> SwingAnalysis:
    """
    Generate AI-powered swing analysis from analytics data.

    Calls Claude API with structured prompt and returns typed analysis.
    """
    import anthropic

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    prompt = _build_analysis_prompt(
        analytics,
        golfer_name=golfer_name,
        launch_monitor=launch_monitor,
        additional_context=additional_context,
    )

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse the JSON response
    response_text = message.content[0].text

    # Handle potential markdown code fences
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]

    data = json.loads(response_text)

    return SwingAnalysis(
        overall_assessment=data.get("overall_assessment", ""),
        handicap_context=data.get("handicap_context", ""),
        club_insights=[
            ClubInsight(
                club_name=ci["club_name"],
                summary=ci.get("summary", ""),
                strengths=ci.get("strengths", []),
                weaknesses=ci.get("weaknesses", []),
                priority_fix=ci.get("priority_fix", ""),
            )
            for ci in data.get("club_insights", [])
        ],
        top_priorities=data.get("top_priorities", []),
        drills=[
            DrillRecommendation(
                name=d["name"],
                focus_area=d.get("focus_area", ""),
                description=d.get("description", ""),
                duration_minutes=d.get("duration_minutes", 15),
                difficulty=d.get("difficulty", "intermediate"),
                expected_improvement=d.get("expected_improvement", ""),
            )
            for d in data.get("drills", [])
        ],
        equipment_notes=data.get("equipment_notes", []),
        next_session_plan=data.get("next_session_plan", ""),
    )
