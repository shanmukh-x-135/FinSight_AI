"""API tests for the combined dashboard-summary endpoint (Phase 7)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

PW = "S3curePass!"


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_dashboard_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/dashboard/summary")).status_code == 401


@pytest.mark.asyncio
async def test_dashboard_summary_batches_everything(client: AsyncClient, seed_market) -> None:
    headers = {"Authorization": f"Bearer {await _token(client, 'd7@example.com')}"}
    added = await client.post(
        "/api/v1/watchlist",
        headers=headers,
        json={"symbol": "AAA.NS", "pinned": True},
    )
    assert added.status_code == 201
    other_headers = {
        "Authorization": f"Bearer {await _token(client, 'd7-other@example.com')}"
    }
    other_added = await client.post(
        "/api/v1/watchlist",
        headers=other_headers,
        json={"symbol": "BBB.NS"},
    )
    assert other_added.status_code == 201

    resp = await client.get("/api/v1/dashboard/summary", headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]

    # Market slice + breadth (2 advancers, 1 decliner from the seed).
    assert data["market"]["breadth"]["advancers"] == 1  # AAA up; CCC flat; BBB down
    assert {g["symbol"] for g in data["market"]["gainers"]} >= {"AAA.NS"}

    # Deterministic AI market summary is present (narrator fallback, never empty).
    assert isinstance(data["ai_market_summary"], str) and data["ai_market_summary"]

    # No portfolio for a fresh account.
    assert data["portfolio"] is None

    # User-scoped watchlist data is included; the other user's BBB is excluded.
    assert len(data["watchlist"]) == 1
    watched = data["watchlist"][0]
    assert watched["symbol"] == "AAA.NS"
    assert watched["pinned"] is True
    assert watched["current_price"] == 110
    assert watched["change_percent"] == pytest.approx(10)

    # Opportunities are evidence-backed with a rendered explanation.
    assert "AAA.NS" in {o["symbol"] for o in data["opportunities"]}
    assert all(o["evidence"] and o["explanation"] for o in data["opportunities"])


@pytest.mark.asyncio
async def test_dashboard_summary_is_deterministic(client: AsyncClient, seed_market) -> None:
    headers = {"Authorization": f"Bearer {await _token(client, 'd7b@example.com')}"}
    first = (await client.get("/api/v1/dashboard/summary", headers=headers)).json()["data"]
    second = (await client.get("/api/v1/dashboard/summary", headers=headers)).json()["data"]
    assert [o["symbol"] for o in first["opportunities"]] == [
        o["symbol"] for o in second["opportunities"]
    ]
    assert [o["score"] for o in first["opportunities"]] == [
        o["score"] for o in second["opportunities"]
    ]
