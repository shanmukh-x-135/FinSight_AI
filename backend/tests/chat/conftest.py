"""Seeded real analytics inputs for grounded chat tests."""

from __future__ import annotations

from datetime import date

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Stock
from tests.auth_utils import access_token_from_cookie


async def authenticated_headers(client: AsyncClient, email: str) -> dict[str, str]:
    password = "S3curePass!"
    registered = await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert registered.status_code == 201
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    return {"Authorization": f"Bearer {access_token_from_cookie(client)}"}


@pytest_asyncio.fixture
async def seeded_chat_market(db_session: AsyncSession) -> None:
    first, second = date(2026, 8, 3), date(2026, 8, 4)
    specs = [
        ("AAA.NS", "Technology", 100.0, 110.0),
        ("BBB.NS", "Energy", 100.0, 90.0),
        ("CCC.NS", "Technology", 50.0, 50.0),
    ]
    for symbol, sector, previous, latest in specs:
        stock = Stock(symbol=symbol, name=symbol.split(".")[0], sector=sector)
        db_session.add(stock)
        await db_session.flush()
        db_session.add_all(
            [
                DailyPrice(
                    stock_id=stock.id,
                    date=first,
                    open=previous,
                    high=previous,
                    low=previous,
                    close=previous,
                    volume=1_000,
                ),
                DailyPrice(
                    stock_id=stock.id,
                    date=second,
                    open=latest,
                    high=latest,
                    low=latest,
                    close=latest,
                    volume=1_000,
                ),
            ]
        )
    await db_session.commit()


async def provision_personal_context(
    client: AsyncClient, headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/v1/portfolios", json={"name": "Core"}, headers=headers
    )
    assert created.status_code == 201
    portfolio_id = created.json()["data"]["id"]
    holding = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/items",
        json={"symbol": "AAA.NS", "quantity": 10, "avg_buy_price": 100},
        headers=headers,
    )
    assert holding.status_code == 201
    watched = await client.post(
        "/api/v1/watchlist",
        json={"symbol": "BBB.NS", "pinned": True},
        headers=headers,
    )
    assert watched.status_code == 201
