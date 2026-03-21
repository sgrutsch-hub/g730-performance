from __future__ import annotations

"""Pydantic schemas for AI swing analysis API responses."""

from pydantic import BaseModel


class DrillResponse(BaseModel):
    name: str
    focus_area: str
    description: str
    duration_minutes: int
    difficulty: str
    expected_improvement: str


class ClubInsightResponse(BaseModel):
    club_name: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    priority_fix: str


class SwingAnalysisResponse(BaseModel):
    overall_assessment: str
    handicap_context: str
    club_insights: list[ClubInsightResponse]
    top_priorities: list[str]
    drills: list[DrillResponse]
    equipment_notes: list[str]
    next_session_plan: str


class AnalysisRequest(BaseModel):
    additional_context: str | None = None
