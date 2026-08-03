"""Phase 0 smoke tests: health endpoints and DB session lifecycle."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "service" in body


@pytest.mark.asyncio
async def test_health_db_returns_200(client: AsyncClient) -> None:
    resp = await client.get("/health/db")
    assert resp.status_code == 200
    assert resp.json()["database"] == "reachable"


@pytest.mark.asyncio
async def test_request_id_header_echoed(client: AsyncClient) -> None:
    """Every response must carry the correlation ID header."""
    resp = await client.get("/health")
    assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_db_session_opens_and_closes(db_session: AsyncSession) -> None:
    """A DB session can execute a trivial query and be closed cleanly."""
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
