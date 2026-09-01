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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, PostgresDsn, field_validator, model_validator
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
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str | None = None
    google_oauth_timeout_seconds: float = Field(default=10, gt=0, le=30)

    # Brute-force protection on the login endpoint: at most N attempts per
    # client IP within the rolling window before returning HTTP 429.
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60

    # ----- Historical intelligence (FAISS) ---------------------------------
    # Reconstructable FAISS generation cache. A volume improves warm-start time,
    # but PostgreSQL remains authoritative if ephemeral storage is cleared.
    data_dir: str = "./data"
    history_top_k: int = 10  # neighbours returned by similarity search

    # ----- Market data & EOD control plane ---------------------------------
    market_fetch_max_attempts: int = 3
    market_fetch_timeout_seconds: float = 30.0
    market_bootstrap_lookback_days: int = Field(default=370, ge=90)
    market_incremental_overlap_days: int = Field(default=7, ge=1)
    market_full_reconciliation_days: int = Field(default=30, ge=1)
    market_provider_repair_enabled: bool = False
    market_timezone: str = "Asia/Kolkata"  # NSE/BSE trading timezone (IST)
    market_calendar: str = "NSE"
    market_readiness_symbol: str = "^NSEI"
    research_universe: Literal["NIFTY50", "NIFTYNEXT50", "NIFTY100"] = "NIFTY100"
    market_close_grace_minutes: int = Field(default=60, ge=0)
    pipeline_heartbeat_interval_seconds: float = Field(default=30.0, gt=0)
    pipeline_stale_after_seconds: int = Field(default=900, gt=0)

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
    news_recent_window_days: int = Field(default=7, ge=1, le=30)
    news_retag_window_days: int = Field(default=30, ge=1, le=90)

    # ----- AI intelligence / RAG (Phase 6) ---------------------------------
    # LLM produces prose only; evidence/confidence/risks/rankings are deterministic.
    # Uses Gemini when GEMINI_API_KEY is set (needs requirements-ai.txt); otherwise
    # a deterministic narrator (reproducible, cost-free) renders the prose.
    llm_model: str = Field(default="gemini-3.6-flash", min_length=1)
    llm_max_retries: int = Field(default=2, ge=1, le=5)
    llm_timeout_seconds: float = Field(default=30, gt=0, le=120)
    llm_max_output_tokens: int = Field(default=2048, ge=64, le=8192)
    llm_thinking_budget: int = Field(default=256, ge=0, le=4096)
    llm_request_budget_seconds: float = Field(default=45, gt=0, le=180)
    llm_max_provider_calls: int = Field(default=20, ge=1, le=100)
    top_n_recommendations: int = 5

    # ----- CORS ------------------------------------------------------------
    # ``NoDecode`` stops pydantic-settings from JSON-parsing the env value, so a
    # plain comma-separated string reaches our validator below.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        """Accept provider URLs while selecting asyncpg-compatible TLS options."""
        if not isinstance(value, str):
            return value
        if value.startswith("postgres://"):
            value = value.replace("postgres://", "postgresql+asyncpg://", 1)
        elif value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if not value.startswith("postgresql+asyncpg://"):
            return value

        parsed = urlsplit(value)
        query = parse_qsl(parsed.query, keep_blank_values=True)
        has_asyncpg_ssl = any(key == "ssl" for key, _ in query)
        normalized_query: list[tuple[str, str]] = []
        for key, item in query:
            if key == "sslmode":
                if not has_asyncpg_ssl:
                    normalized_query.append(("ssl", item))
                continue
            # Neon's copied libpq URL currently includes channel_binding. asyncpg
            # does not accept that keyword; TLS remains enforced by ssl=require.
            if key == "channel_binding":
                continue
            normalized_query.append((key, item))
        return urlunsplit(parsed._replace(query=urlencode(normalized_query)))

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, value: PostgresDsn) -> PostgresDsn:
        if not str(value).startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the asyncpg driver")
        return value

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

    @model_validator(mode="after")
    def _validate_production_safety(self) -> "Settings":
        google_values = (
            self.google_oauth_client_id,
            self.google_oauth_client_secret,
            self.google_oauth_redirect_uri,
        )
        if any(google_values) and not all(google_values):
            raise ValueError(
                "Google OAuth requires client id, client secret, and redirect URI together"
            )
        if not self.is_production:
            return self
        if self.debug or self.db_echo:
            raise ValueError("DEBUG and DB_ECHO must be false in production")
        if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must contain at least 32 characters in production"
            )
        if not self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain the production frontend origin")
        if any(not _is_https_origin(origin) for origin in self.cors_origins):
            raise ValueError(
                "Production CORS_ORIGINS must be explicit HTTPS origins without trailing slashes"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def database_url_str(self) -> str:
        """The database URL as a plain string for SQLAlchemy/Alembic."""
        return str(self.database_url)


def _is_https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # force validation of malformed/out-of-range ports
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.username is None
        and parsed.password is None
        and not parsed.path
        and not parsed.query
        and not parsed.fragment
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached, validated settings instance."""
    return Settings()  # type: ignore[call-arg]


# Convenience singleton for direct import: ``from config.settings import settings``
settings = get_settings()
