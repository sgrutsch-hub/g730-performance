# ═══════════════════════════════════════════
# Swing Doctor API — Production Dockerfile
# ═══════════════════════════════════════════
# Multi-stage build for minimal image size.
# Final image: ~120MB (python:3.12-slim base)

# ── Stage 1: Build dependencies ──
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: Runtime image ──
FROM python:3.12-slim

WORKDIR /app

# Runtime dependencies only (libpq for asyncpg)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/* && \
    # Create non-root user
    addgroup --system appuser && \
    adduser --system --ingroup appuser appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with uvicorn
# Workers are set via environment variable for flexibility.
# Default: 1 worker (appropriate for Railway/Fly.io with horizontal scaling)
ENV UVICORN_WORKERS=1
ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host $UVICORN_HOST --port $UVICORN_PORT --workers $UVICORN_WORKERS"]
