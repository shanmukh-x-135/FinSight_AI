"""API tests: watchlist CRUD, quotes, pin/sort, and cross-user ownership."""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Indicator, Stock

PW = "S3curePass!"
WL = "/api/v1/watchlist"


async def _token(client: AsyncClient, email: str) -> str:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return r.json()["data"]["access_token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seed_stocks(db_session: AsyncSession) -> None:
    aaa = Stock(symbol="AAA.NS", name="Alpha", sector="Technology", exchange="NSE")
    bbb = Stock(symbol="BBB.NS", name="Beta", sector="Energy", exchange="NSE")
    db_session.add_all([aaa, bbb])
    await db_session.flush()
    d1, d2 = date(2024, 1, 1), date(2024, 1, 2)
    db_session.add_all([
        DailyPrice(stock_id=aaa.id, date=d1, open=100, high=101, low=99, close=100, volume=1),
        DailyPrice(stock_id=aaa.id, date=d2, open=104, high=106, low=103, close=105, volume=1),
        DailyPrice(stock_id=bbb.id, date=d2, open=200, high=201, low=199, close=200, volume=1),
        Indicator(
            stock_id=aaa.id,
            date=d2,
            rsi_14=61,
            ema_20=102,
            macd_histogram=0.5,
        ),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_watchlist_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(WL)).status_code == 401


@pytest.mark.asyncio
async def test_watchlist_add_list_with_quote(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "w1@example.com"))
    add = await client.post(WL, headers=h, json={"symbol": "AAA.NS"})
    assert add.status_code == 201

    data = (await client.get(WL, headers=h)).json()["data"]
    assert len(data) == 1
    item = data[0]
    assert item["symbol"] == "AAA.NS"
    assert item["current_price"] == pytest.approx(105.0)
    assert item["change"] == pytest.approx(5.0)          # 105 - 100
    assert item["change_percent"] == pytest.approx(5.0)  # 5/100 * 100
    assert item["rsi_14"] == pytest.approx(61)
    assert item["trend"] == "bullish"


@pytest.mark.asyncio
async def test_watchlist_duplicate_and_untracked(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "w2@example.com"))
    await client.post(WL, headers=h, json={"symbol": "AAA.NS"})
    dup = await client.post(WL, headers=h, json={"symbol": "AAA.NS"})
    assert dup.status_code == 409
    assert dup.json()["error"]["type"] == "duplicate_watchlist_item"

    untracked = await client.post(WL, headers=h, json={"symbol": "NOPE.NS"})
    assert untracked.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_pin_sorts_first(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "w3@example.com"))
    a = (await client.post(WL, headers=h, json={"symbol": "AAA.NS"})).json()["data"]["id"]
    await client.post(WL, headers=h, json={"symbol": "BBB.NS"})

    # Pin AAA (added first) — pinning keeps it; pin BBB and it should lead.
    b_id = (await client.get(WL, headers=h)).json()["data"]
    bbb_id = next(x["id"] for x in b_id if x["symbol"] == "BBB.NS")
    patched = await client.patch(f"{WL}/{bbb_id}", headers=h, json={"pinned": True})
    assert patched.json()["data"]["pinned"] is True

    ordered = (await client.get(WL, headers=h)).json()["data"]
    assert ordered[0]["symbol"] == "BBB.NS"  # pinned first
    assert a is not None


@pytest.mark.asyncio
async def test_watchlist_delete(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "w4@example.com"))
    item_id = (await client.post(WL, headers=h, json={"symbol": "AAA.NS"})).json()["data"]["id"]
    assert (await client.delete(f"{WL}/{item_id}", headers=h)).status_code == 200
    assert (await client.get(WL, headers=h)).json()["data"] == []
    # Deleting again → 404
    assert (await client.delete(f"{WL}/{item_id}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_watchlist_ownership(client: AsyncClient, seed_stocks: None) -> None:
    a = _hdr(await _token(client, "wa@example.com"))
    b = _hdr(await _token(client, "wb@example.com"))
    item_id = (await client.post(WL, headers=a, json={"symbol": "AAA.NS"})).json()["data"]["id"]

    # Bob can't see, patch, or delete Alice's watchlist item.
    assert (await client.get(WL, headers=b)).json()["data"] == []
    assert (await client.patch(f"{WL}/{item_id}", headers=b, json={"pinned": True})).status_code == 404
    assert (await client.delete(f"{WL}/{item_id}", headers=b)).status_code == 404
    # Alice's item survives.
    assert len((await client.get(WL, headers=a)).json()["data"]) == 1
