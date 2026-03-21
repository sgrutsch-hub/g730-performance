from __future__ import annotations

"""
V1 API router — aggregates all v1 route modules.

All routes are mounted under /api/v1 via the main app factory.
"""

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.profiles import router as profiles_router
from app.api.v1.sessions import router as sessions_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(profiles_router)
router.include_router(sessions_router)
