from __future__ import annotations

"""
Swing Doctor — FastAPI application factory.

This is the single entry point for the entire backend.
All middleware, exception handlers, and routes are configured here.
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ParseError,
    SubscriptionRequiredError,
    SwingDoctorError,
    ValidationError,
)
from app.database import dispose_engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan — runs once on startup and once on shutdown.

    Startup: initialize connections, warm caches
    Shutdown: clean up connection pools
    """
    # Startup
    yield
    # Shutdown
    await dispose_engine()


def create_app() -> FastAPI:
    """
    Application factory — creates and configures the FastAPI instance.

    Using a factory function (instead of a module-level `app`) allows:
    - Testing with different configurations
    - Multiple app instances (e.g., for worker processes)
    - Clean dependency injection
    """
    app = FastAPI(
        title="Swing Doctor API",
        description="Golf sim performance analytics platform",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # ── CORS ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ──
    # Map our typed exceptions to HTTP responses.
    # This keeps business logic free of HTTP concepts.

    @app.exception_handler(AuthenticationError)
    async def auth_error_handler(request: Request, exc: AuthenticationError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": "authentication_error", "message": exc.message},
        )

    @app.exception_handler(AuthorizationError)
    async def authz_error_handler(request: Request, exc: AuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content={"error": "authorization_error", "message": exc.message},
        )

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found", "message": exc.message},
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "conflict", "message": exc.message},
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "message": exc.message},
        )

    @app.exception_handler(SubscriptionRequiredError)
    async def subscription_handler(
        request: Request, exc: SubscriptionRequiredError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=402,
            content={
                "error": "subscription_required",
                "message": exc.message,
                "required_tier": exc.required_tier,
            },
        )

    @app.exception_handler(ParseError)
    async def parse_handler(request: Request, exc: ParseError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"error": "parse_error", "message": exc.message},
        )

    @app.exception_handler(SwingDoctorError)
    async def generic_app_error(request: Request, exc: SwingDoctorError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"error": "server_error", "message": exc.message},
        )

    # ── Routes ──
    from app.api.v1.router import router as v1_router

    app.include_router(v1_router, prefix=settings.api_prefix)

    # ── Health check ──
    @app.get("/health", tags=["system"])
    async def health() -> dict[str, Any]:
        return {"status": "healthy", "version": "0.1.0", "environment": settings.environment}

    return app


# Module-level app instance for uvicorn
app = create_app()
