"""Deployment-critical settings normalization and fail-closed validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from config.settings import Settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql://user:password@db.internal/finsight",
        "app_env": "production",
        "jwt_secret": "a-secure-production-secret-with-32-chars",
        "cors_origins": "https://app.finsight.example",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://"])
def test_managed_postgres_urls_are_normalized_to_asyncpg(scheme: str) -> None:
    configured = _settings(database_url=f"{scheme}user:password@db.internal/finsight")

    assert configured.database_url_str.startswith("postgresql+asyncpg://")


def test_explicit_asyncpg_url_is_preserved() -> None:
    configured = _settings(
        database_url="postgresql+asyncpg://user:password@db.internal/finsight"
    )

    assert configured.database_url_str.startswith("postgresql+asyncpg://")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"jwt_secret": "too-short"}, "JWT_SECRET"),
        ({"cors_origins": ""}, "CORS_ORIGINS"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"cors_origins": "http://app.example"}, "CORS_ORIGINS"),
        ({"cors_origins": "https://app.example/"}, "CORS_ORIGINS"),
        ({"cors_origins": "https://app.example/path"}, "CORS_ORIGINS"),
        ({"cors_origins": "https://user@app.example"}, "CORS_ORIGINS"),
        ({"cors_origins": "https://app.example?preview=1"}, "CORS_ORIGINS"),
        ({"cors_origins": "https://app.example:99999"}, "CORS_ORIGINS"),
        ({"debug": True}, "DEBUG"),
        ({"db_echo": True}, "DB_ECHO"),
    ],
)
def test_production_configuration_fails_closed(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _settings(**overrides)


def test_development_keeps_local_defaults() -> None:
    configured = Settings(
        database_url="postgresql://user:password@localhost/finsight",
        app_env="development",
        jwt_secret="dev-only",
        cors_origins="http://localhost:3000",
        _env_file=None,
    )

    assert configured.cors_origins == ["http://localhost:3000"]


def test_environment_example_covers_every_setting() -> None:
    template = (BACKEND_ROOT / ".env.example").read_text()
    missing = [
        name.upper()
        for name in Settings.model_fields
        if f"{name.upper()}=" not in template
    ]

    assert missing == []
