#!/usr/bin/env python3
"""Non-mutating smoke checks for a deployed FinSight frontend and API."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

MAX_BODY_BYTES = 2 * 1024 * 1024


class SmokeFailure(RuntimeError):
    """A deployment contract failed without exposing a response body."""


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    try:
        _ = parsed.port
    except ValueError:
        raise SmokeFailure(f"invalid URL: {url!r}") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise SmokeFailure(f"invalid URL: {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def _request(request: Request, timeout: float) -> Response:
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise SmokeFailure(f"{request.full_url} response exceeded size limit")
            return Response(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=body,
            )
    except HTTPError as exc:
        raise SmokeFailure(f"{request.full_url} returned HTTP {exc.code}") from None
    except (TimeoutError, URLError) as exc:
        raise SmokeFailure(
            f"{request.full_url} is unreachable ({type(exc).__name__})"
        ) from None


def _json(response: Response, url: str) -> dict[str, Any]:
    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SmokeFailure(f"{url} did not return valid JSON") from None
    if not isinstance(payload, dict):
        raise SmokeFailure(f"{url} returned a non-object JSON payload")
    return payload


def run_smoke(
    *,
    backend_url: str,
    frontend_url: str,
    timeout: float,
    allow_non_production: bool,
) -> list[str]:
    backend = _origin(backend_url)
    frontend = _origin(frontend_url)
    if not allow_non_production and (
        not backend.startswith("https://") or not frontend.startswith("https://")
    ):
        raise SmokeFailure("production smoke targets must use HTTPS")

    checks: list[str] = []
    health_url = urljoin(f"{backend}/", "health")
    health = _json(_request(Request(health_url), timeout), health_url)
    if health.get("status") != "ok":
        raise SmokeFailure("backend liveness status is not ok")
    if not allow_non_production and health.get("env") != "production":
        raise SmokeFailure("backend is not running with APP_ENV=production")
    checks.append("backend liveness")

    db_url = urljoin(f"{backend}/", "health/db")
    database = _json(_request(Request(db_url), timeout), db_url)
    if database.get("status") != "ok" or database.get("database") != "reachable":
        raise SmokeFailure("backend database readiness status is not ok")
    checks.append("database readiness")

    cors_url = urljoin(f"{backend}/", "api/v1/auth/login")
    cors = _request(
        Request(
            cors_url,
            method="OPTIONS",
            headers={
                "Origin": frontend,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        ),
        timeout,
    )
    if cors.headers.get("access-control-allow-origin") != frontend:
        raise SmokeFailure("backend CORS does not allow the deployed frontend origin")
    checks.append("frontend CORS")

    page = _request(Request(f"{frontend}/"), timeout)
    if page.status < 200 or page.status >= 400 or b"FinSight AI" not in page.body:
        raise SmokeFailure("frontend landing page contract failed")
    checks.append("frontend landing page")
    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", required=True)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--allow-non-production",
        action="store_true",
        help="permit HTTP/local APP_ENV values for pre-deploy verification",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout <= 0:
        print("smoke failed: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        checks = run_smoke(
            backend_url=args.backend_url,
            frontend_url=args.frontend_url,
            timeout=args.timeout,
            allow_non_production=args.allow_non_production,
        )
    except SmokeFailure as exc:
        print(f"smoke failed: {exc}", file=sys.stderr)
        return 1
    print(f"deployment smoke passed ({', '.join(checks)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
