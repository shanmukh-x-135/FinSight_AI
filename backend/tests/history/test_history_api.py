"""API tests for the history routes (similarity query + admin rebuild)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_similar_before_build_returns_409(
    client: AsyncClient, seeded_market: None, tmp_data_dir: str
) -> None:
    resp = await client.get("/api/v1/history/similar")
    assert resp.status_code == 409
    assert resp.json()["error"]["type"] == "history_index_not_built"


@pytest.mark.asyncio
async def test_rebuild_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/jobs/history-rebuild/run")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rebuild_then_query_full_flow(
    client: AsyncClient,
    seeded_market: None,
    tmp_data_dir: str,
    admin_headers: dict[str, str],
) -> None:
    rebuilt = await client.post(
        "/api/v1/admin/jobs/history-rebuild/run", headers=admin_headers
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json()["data"]["sessions_indexed"] == 19

    resp = await client.get("/api/v1/history/similar", params={"k": 5})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["query_date"] == "2024-02-10"  # latest session
    assert len(data["similar_sessions"]) == 5
    assert "statistics" in data
    # Each similar session carries an outcome-based next-day return field.
    assert all("next_day_return" in s for s in data["similar_sessions"])
