"""API tests for the news routes (reads + auth-gated ingestion)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.news.dependencies import get_news_client
from tests.news.conftest import FakeNewsClient, make_item

BAD = "Reliance Industries shares plunge after massive loss and dividend cut"
GOOD = "TCS profit surges and beats estimates"


@pytest.mark.asyncio
async def test_recent_news_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/news")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@pytest.mark.asyncio
async def test_ingest_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/jobs/news-ingestion/run")
    assert resp.status_code == 401

    status = await client.get("/api/v1/admin/jobs/news-ingestion/status")
    assert status.status_code == 401


@pytest.mark.asyncio
async def test_ingest_then_read(
    client: AsyncClient,
    test_app,
    seed_stocks: None,
    admin_headers: dict[str, str],
) -> None:
    items = [make_item("http://x/1", BAD), make_item("http://x/2", GOOD)]
    test_app.dependency_overrides[get_news_client] = lambda: FakeNewsClient(items)

    ingested = await client.post(
        "/api/v1/admin/jobs/news-ingestion/run", headers=admin_headers
    )
    assert ingested.status_code == 200
    assert ingested.json()["data"]["new_articles"] == 2
    assert ingested.json()["data"]["tagged_articles"] == 2

    news = await client.get("/api/v1/news")
    data = news.json()["data"]
    assert len(data) == 2
    assert any("RELIANCE.NS" in a["tags"] for a in data)
    reliance_article = next(a for a in data if "RELIANCE.NS" in a["tags"])
    assert reliance_article["event_category"] == "Earnings"
    assert reliance_article["evidence_excerpt"] == BAD
    assert reliance_article["url"] == "http://x/1"
    assert 0 < reliance_article["sentiment_confidence"] < 1

    sentiment = await client.get("/api/v1/news/sentiment/RELIANCE.NS")
    assert sentiment.status_code == 200
    series = sentiment.json()["data"]["series"]
    assert series and series[-1]["avg_sentiment"] < 0  # bad news → negative
    stock_sentiment = sentiment.json()["data"]
    assert stock_sentiment["availability"] == "available"
    assert stock_sentiment["article_count"] == 1
    assert stock_sentiment["negative_count"] == 1
    assert stock_sentiment["evidence"][0]["source_url"] == "http://x/1"
    assert stock_sentiment["evidence"][0]["entity_match_confidence"] > 0

    latest = (await client.get("/api/v1/news/sentiment")).json()["data"]
    by_symbol = {row["symbol"]: row["latest_sentiment"] for row in latest}
    assert by_symbol["RELIANCE.NS"] < 0
    assert by_symbol["TCS.NS"] > 0

    attribution = await client.get("/api/v1/market/stocks/RELIANCE.NS/attribution")
    assert attribution.status_code == 200
    attribution_data = attribution.json()["data"]
    assert attribution_data["certainty"] == "likely_contributors_not_proven_causes"
    company_news = next(
        row for row in attribution_data["drivers"] if row["category"] == "company_news"
    )
    assert company_news["direction"] == "bearish"
    assert company_news["evidence_article_ids"] == [reliance_article["id"]]

    sector = await client.get("/api/v1/news/sentiment/sector/Energy")
    assert sector.status_code == 200
    sector_data = sector.json()["data"]
    assert sector_data["sector"] == "Energy"
    assert sector_data["latest_sentiment"] < 0
    assert sector_data["series"][-1]["article_count"] == 1

    status = await client.get(
        "/api/v1/admin/jobs/news-ingestion/status?recent_window_days=30",
        headers=admin_headers,
    )
    assert status.status_code == 200
    diagnostics = status.json()["data"]
    assert diagnostics == {
        "recent_window_days": 30,
        "total_articles": 2,
        "recent_articles": 0,
        "linked_articles": 2,
        "article_stock_associations": 2,
        "distinct_active_stocks_with_links": 2,
        "sentiment_rows": 2,
        "positive_articles": 1,
        "neutral_articles": 0,
        "negative_articles": 1,
        "active_stocks_with_recent_sentiment": 0,
        "latest_news_ingestion_at": diagnostics["latest_news_ingestion_at"],
        "latest_sentiment_at": diagnostics["latest_sentiment_at"],
    }
    assert diagnostics["latest_news_ingestion_at"] is not None
    assert diagnostics["latest_sentiment_at"] is not None


@pytest.mark.asyncio
async def test_news_diagnostics_empty(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    response = await client.get(
        "/api/v1/admin/jobs/news-ingestion/status", headers=admin_headers
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_articles"] == 0
    assert data["recent_articles"] == 0
    assert data["linked_articles"] == 0
    assert data["sentiment_rows"] == 0
    assert data["latest_news_ingestion_at"] is None
    assert data["latest_sentiment_at"] is None


@pytest.mark.asyncio
async def test_no_news_is_unavailable_not_neutral(
    client: AsyncClient, seed_stocks: None
) -> None:
    sentiment = (
        await client.get("/api/v1/news/sentiment/RELIANCE.NS")
    ).json()["data"]
    assert sentiment["availability"] == "no_relevant_news"
    assert sentiment["latest_sentiment"] is None
    assert sentiment["confidence"] is None
    assert sentiment["article_count"] == 0
    assert sentiment["evidence"] == []

    attribution = (
        await client.get("/api/v1/market/stocks/RELIANCE.NS/attribution")
    ).json()["data"]
    company_news = next(
        row for row in attribution["drivers"] if row["category"] == "company_news"
    )
    assert company_news["direction"] == "unavailable"
    assert "No verified company catalyst" in company_news["observation"]


@pytest.mark.asyncio
async def test_sentiment_unknown_stock_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/news/sentiment/NOPE.NS")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sentiment_unknown_sector_404(
    client: AsyncClient, seed_stocks: None
) -> None:
    resp = await client.get("/api/v1/news/sentiment/sector/Unknown")
    assert resp.status_code == 404
