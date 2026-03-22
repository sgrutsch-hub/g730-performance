from __future__ import annotations

"""
Application configuration via pydantic-settings.

All settings are loaded from environment variables (or .env file).
Validated at startup — the app refuses to start with invalid config.
"""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Core ──
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    secret_key: str = "CHANGE-ME"
    allowed_origins: list[str] = ["http://localhost:3000", "https://swing.doctor"]
    api_prefix: str = "/api/v1"

    # ── Database ──
    database_url: str = "postgresql+asyncpg://swingdoctor:swingdoctor@localhost:5432/swingdoctor"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_echo: bool = False

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300  # 5 minutes default

    # ── JWT ──
    jwt_secret_key: str = "CHANGE-ME"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # ── Stripe ──
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro_monthly: str = ""
    stripe_price_pro_yearly: str = ""
    stripe_price_pro_plus_monthly: str = ""
    stripe_price_pro_plus_yearly: str = ""
    stripe_trial_coupon: str = ""
    stripe_publishable_key: str = ""

    # ── AI ──
    anthropic_api_key: str = ""

    # ── Email ──
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "noreply@swing.doctor"

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | list[str]) -> list[str]:
        """Accept comma-separated string or list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Call this everywhere — it's free after first load."""
    return Settings()
