"""API tests for the news routes (reads + auth-gated ingestion)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.news.dependencies import get_news_client
from tests.news.conftest import FakeNewsClient, make_item

PW = "S3curePass!"
BAD = "Reliance shares plunge as company reports massive loss and cuts dividend"
GOOD = "TCS profit surges and beats estimates"


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_recent_news_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/news")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_ingest_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/jobs/news-ingestion/run")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_ingest_then_read(client: AsyncClient, test_app, seed_stocks: None) -> None:
    items = [make_item("http://x/1", BAD), make_item("http://x/2", GOOD)]
    test_app.dependency_overrides[get_news_client] = lambda: FakeNewsClient(items)

    headers = {"Authorization": f"Bearer {await _token(client, 'news@example.com')}"}
    ingested = await client.post("/api/v1/admin/jobs/news-ingestion/run", headers=headers)
    assert ingested.status_code == 200
    assert ingested.json()["data"]["new_articles"] == 2
    assert ingested.json()["data"]["tagged_articles"] == 2

    news = await client.get("/api/v1/news")
    data = news.json()["data"]
    assert len(data) == 2
    assert any("RELIANCE.NS" in a["tags"] for a in data)

    sentiment = await client.get("/api/v1/news/sentiment/RELIANCE.NS")
    assert sentiment.status_code == 200
    series = sentiment.json()["data"]["series"]
    assert series and series[-1]["avg_sentiment"] < 0  # bad news → negative


@pytest.mark.asyncio
async def test_sentiment_unknown_stock_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/news/sentiment/NOPE.NS")
    assert resp.status_code == 404
