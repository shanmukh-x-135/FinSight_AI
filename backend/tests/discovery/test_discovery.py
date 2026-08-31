"""Validated parsing, reproducibility, filtering, and saved-screen ownership."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.exceptions import UnsupportedScreenerQueryError
from app.discovery.parser import parse_screener_query
from app.market.models import DailyPrice, Fundamentals, IndexMembership, Indicator, Stock
from app.news.models import SentimentDaily

START = date(2026, 7, 1)


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    password = "S3curePass!"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed(db: AsyncSession) -> None:
    alpha = Stock(
        symbol="AAA.NS",
        exchange_symbol="AAA",
        name="Alpha Systems",
        sector="Technology",
        exchange="NSE",
    )
    beta = Stock(
        symbol="BBB.NS",
        exchange_symbol="BBB",
        name="Beta Bank",
        sector="Financial Services",
        exchange="NSE",
    )
    db.add_all([alpha, beta])
    await db.flush()
    for stock in (alpha, beta):
        db.add(
            IndexMembership(
                stock_id=stock.id,
                index_code="NIFTY100",
                valid_from=START,
                source="test",
                source_snapshot_date=START,
            )
        )
    db.add_all(
        [
            Fundamentals(stock_id=alpha.id, pe_ratio=20, eps=12),
            Fundamentals(stock_id=beta.id, pe_ratio=35, eps=-2),
        ]
    )
    for offset in range(21):
        day = START + timedelta(days=offset)
        db.add_all(
            [
                DailyPrice(
                    stock_id=alpha.id,
                    date=day,
                    open=100,
                    high=112,
                    low=99,
                    close=110 if offset == 20 else 100,
                    volume=3000 if offset == 20 else 1000,
                ),
                DailyPrice(
                    stock_id=beta.id,
                    date=day,
                    open=100,
                    high=101,
                    low=88,
                    close=90 if offset == 20 else 100,
                    volume=1000,
                ),
            ]
        )
    db.add_all(
        [
            Indicator(
                stock_id=alpha.id,
                date=START + timedelta(days=20),
                rsi_14=55,
                ema_20=105,
                ema_50=102,
                macd_histogram=1.2,
            ),
            Indicator(
                stock_id=beta.id,
                date=START + timedelta(days=20),
                rsi_14=35,
                ema_20=95,
                ema_50=98,
                macd_histogram=-1.0,
            ),
            SentimentDaily(
                stock_id=alpha.id,
                date=START + timedelta(days=20),
                avg_sentiment=0.3,
                article_count=2,
                positive_count=1,
                negative_count=0,
                neutral_count=1,
            ),
            SentimentDaily(
                stock_id=beta.id,
                date=START + timedelta(days=20),
                avg_sentiment=-0.4,
                article_count=1,
                positive_count=0,
                negative_count=1,
                neutral_count=0,
            ),
        ]
    )
    await db.commit()


def test_parser_builds_only_supported_ast() -> None:
    ast = parse_screener_query(
        "Find NIFTY 100 profitable stocks above EMA50, RSI 45-65, with non-negative recent news sentiment"
    )
    assert ast.universe == "NIFTY100"
    assert [(item.field, item.operator) for item in ast.conditions] == [
        ("rsi_14", "between"),
        ("price_vs_ema50", "above"),
        ("eps", "positive"),
        ("news_sentiment", "non_negative"),
    ]


def test_parser_rejects_unsupported_fields_and_empty_filters() -> None:
    with pytest.raises(UnsupportedScreenerQueryError, match="unsupported"):
        parse_screener_query("Find stocks with ROE above 20 and low debt")
    with pytest.raises(UnsupportedScreenerQueryError):
        parse_screener_query("Find interesting NIFTY 100 stocks")


@pytest.mark.asyncio
async def test_screen_is_deterministic_and_missing_values_do_not_match(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    headers = await _headers(client, "discover@example.com")
    await _seed(db_session)
    query = "Find NIFTY 100 profitable stocks above EMA50, RSI 45-65, volume above 2x, with non-negative recent news sentiment"
    first = await client.post(
        "/api/v1/discovery/screen", headers=headers, json={"query": query}
    )
    second = await client.post(
        "/api/v1/discovery/screen", headers=headers, json={"query": query}
    )
    assert first.status_code == 200
    assert [row["symbol"] for row in first.json()["data"]["rows"]] == ["AAA.NS"]
    assert first.json()["data"]["result_hash"] == second.json()["data"]["result_hash"]


@pytest.mark.asyncio
async def test_saved_screens_are_validated_and_user_scoped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = await _headers(client, "screen-owner@example.com")
    other = await _headers(client, "screen-other@example.com")
    await _seed(db_session)
    query = "NIFTY 100 profitable stocks above EMA50"
    screened = (
        await client.post(
            "/api/v1/discovery/screen", headers=owner, json={"query": query}
        )
    ).json()["data"]
    created = await client.post(
        "/api/v1/discovery/screens",
        headers=owner,
        json={
            "name": "Quality trend",
            "query_text": query,
            "filter_ast": screened["ast"],
        },
    )
    assert created.status_code == 201
    screen_id = created.json()["data"]["id"]
    assert (
        len((await client.get("/api/v1/discovery/screens", headers=owner)).json()["data"])
        == 1
    )
    assert (await client.get("/api/v1/discovery/screens", headers=other)).json()[
        "data"
    ] == []
    assert (
        await client.post(f"/api/v1/discovery/screens/{screen_id}/run", headers=other)
    ).status_code == 404
    replay = await client.post(
        f"/api/v1/discovery/screens/{screen_id}/run", headers=owner
    )
    assert replay.json()["data"]["result_hash"] == screened["result_hash"]
    assert (
        await client.delete(f"/api/v1/discovery/screens/{screen_id}", headers=owner)
    ).status_code == 200


@pytest.mark.asyncio
async def test_tampered_saved_ast_is_rejected(client: AsyncClient) -> None:
    headers = await _headers(client, "tamper@example.com")
    response = await client.post(
        "/api/v1/discovery/screens",
        headers=headers,
        json={
            "name": "Tampered",
            "query_text": "NIFTY 100 profitable stocks",
            "filter_ast": {
                "version": "screener_ast_v1",
                "universe": "NIFTY100",
                "conditions": [{"field": "eps", "operator": "negative"}],
            },
        },
    )
    assert response.status_code == 422
