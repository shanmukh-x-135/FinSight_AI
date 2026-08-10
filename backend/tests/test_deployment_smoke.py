"""Tests for the read-only production smoke contract."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import smoke_deployment as smoke  # noqa: E402


def _response(
    body: bytes = b"", *, headers: dict[str, str] | None = None
) -> smoke.Response:
    return smoke.Response(status=200, headers=headers or {}, body=body)


def test_smoke_validates_health_database_cors_and_frontend(monkeypatch) -> None:
    def fake_request(request, timeout):  # type: ignore[no-untyped-def]
        assert timeout == 5
        if request.full_url.endswith("/health"):
            return _response(b'{"status":"ok","env":"production"}')
        if request.full_url.endswith("/health/db"):
            return _response(b'{"status":"ok","database":"reachable"}')
        if request.get_method() == "OPTIONS":
            return _response(
                headers={"access-control-allow-origin": "https://app.example"}
            )
        return _response(b"<title>FinSight AI</title>")

    monkeypatch.setattr(smoke, "_request", fake_request)

    assert smoke.run_smoke(
        backend_url="https://api.example",
        frontend_url="https://app.example",
        timeout=5,
        allow_non_production=False,
    ) == [
        "backend liveness",
        "database readiness",
        "frontend CORS",
        "frontend landing page",
    ]


def test_production_smoke_rejects_plain_http() -> None:
    with pytest.raises(smoke.SmokeFailure, match="HTTPS"):
        smoke.run_smoke(
            backend_url="http://api.example",
            frontend_url="https://app.example",
            timeout=5,
            allow_non_production=False,
        )


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example/path",
        "https://user@api.example",
        "https://api.example:99999",
    ],
)
def test_smoke_rejects_non_origin_base_urls(url: str) -> None:
    with pytest.raises(smoke.SmokeFailure, match="invalid URL"):
        smoke.run_smoke(
            backend_url=url,
            frontend_url="https://app.example",
            timeout=5,
            allow_non_production=False,
        )


def test_smoke_rejects_non_production_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        smoke,
        "_request",
        lambda request, timeout: _response(b'{"status":"ok","env":"development"}'),
    )

    with pytest.raises(smoke.SmokeFailure, match="APP_ENV"):
        smoke.run_smoke(
            backend_url="https://api.example",
            frontend_url="https://app.example",
            timeout=5,
            allow_non_production=False,
        )


def test_smoke_rejects_wrong_cors_origin(monkeypatch) -> None:
    def fake_request(request, timeout):  # type: ignore[no-untyped-def]
        if request.full_url.endswith("/health"):
            return _response(b'{"status":"ok","env":"production"}')
        if request.full_url.endswith("/health/db"):
            return _response(b'{"status":"ok","database":"reachable"}')
        return _response(headers={"access-control-allow-origin": "https://wrong.example"})

    monkeypatch.setattr(smoke, "_request", fake_request)

    with pytest.raises(smoke.SmokeFailure, match="CORS"):
        smoke.run_smoke(
            backend_url="https://api.example",
            frontend_url="https://app.example",
            timeout=5,
            allow_non_production=False,
        )
