"""Application configuration.

All runtime configuration is read from environment variables (or a local
``.env`` file) and validated once at startup via a Pydantic ``BaseSettings``
model. Importing :data:`settings` anywhere in the app returns the same
validated, cached instance.

Adding a new setting? Add the field here *and* to ``.env.example`` so the two
never drift — Phase 0's Definition of Done requires that parity.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings.

    Required variables have no default and will raise a clear
    ``ValidationError`` at startup if missing, rather than failing silently
    deep inside a request.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.development", ".env.production"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- Core app ---------------------------------------------------------
    app_name: str = "FinSight AI"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # ----- Database (required) ---------------------------------------------
    # Async SQLAlchemy URL, e.g.
    #   postgresql+asyncpg://finsight:finsight@localhost:5432/finsight
    database_url: PostgresDsn = Field(...)

    # Connection pool tuning
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_echo: bool = False

    # ----- Security (used from Phase 1 onward) -----------------------------
    jwt_secret: str = Field("change-me-in-production", min_length=8)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Brute-force protection on the login endpoint: at most N attempts per
    # client IP within the rolling window before returning HTTP 429.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60

    # ----- Historical intelligence (FAISS) ---------------------------------
    # Directory for the persisted FAISS index + normalizer (mount a volume in
    # production so it survives container restarts). Relative to the backend CWD.
    data_dir: str = "./data"
    history_top_k: int = 10          # neighbours returned by similarity search

    # ----- Market data & scheduler -----------------------------------------
    market_fetch_max_attempts: int = 3
    scheduler_enabled: bool = True
    market_timezone: str = "Asia/Kolkata"      # NSE/BSE trading timezone (IST)
    # Post-market-close ingestion time (local to market_timezone). NSE closes
    # 15:30 IST; run after settlement to catch finalized end-of-day data.
    market_ingestion_hour: int = 18
    market_ingestion_minute: int = 30

    # ----- AI / external providers (used from later phases) ----------------
    gemini_api_key: str | None = None
    trading_economics_api_key: str | None = None
    economic_calendar_timeout_seconds: int = 10

    # ----- News & sentiment (Phase 5) --------------------------------------
    # Sentiment scorer: "lexicon" (dependency-free default) or "finbert"
    # (design doc's model; requires the ML extras in requirements-ml.txt).
    # FinBERT auto-falls back to lexicon if transformers/torch are unavailable.
    sentiment_backend: str = "lexicon"
    news_max_articles_per_feed: int = 50

    # ----- AI intelligence / RAG (Phase 6) ---------------------------------
    # LLM produces prose only; evidence/confidence/risks/rankings are deterministic.
    # Uses Gemini when GEMINI_API_KEY is set (needs requirements-ai.txt); otherwise
    # a deterministic narrator (reproducible, cost-free) renders the prose.
    llm_model: str = "gemini-2.0-flash"
    llm_max_retries: int = 2
    llm_timeout_seconds: int = 30
    top_n_recommendations: int = 5

    # ----- CORS ------------------------------------------------------------
    # ``NoDecode`` stops pydantic-settings from JSON-parsing the env value, so a
    # plain comma-separated string reaches our validator below.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Allow CORS origins as a comma-separated string in ``.env``."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url_str(self) -> str:
        """The database URL as a plain string for SQLAlchemy/Alembic."""
        return str(self.database_url)


@lru_cache
def get_settings() -> Settings:
    """Return the cached, validated settings instance."""
    return Settings()  # type: ignore[call-arg]


# Convenience singleton for direct import: ``from config.settings import settings``
settings = get_settings()
