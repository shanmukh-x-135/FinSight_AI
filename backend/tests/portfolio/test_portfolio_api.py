"""API tests: portfolio CRUD, holdings, analytics, and cross-user ownership."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Fundamentals, IndexMembership, Stock

PW = "S3curePass!"


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
        DailyPrice(stock_id=aaa.id, date=d1, open=105, high=106, low=104, close=105, volume=1),
        DailyPrice(stock_id=aaa.id, date=d2, open=108, high=111, low=107, close=110, volume=1),
        DailyPrice(stock_id=bbb.id, date=d1, open=200, high=201, low=199, close=200, volume=1),
        DailyPrice(stock_id=bbb.id, date=d2, open=182, high=183, low=179, close=180, volume=1),
    ])
    await db_session.commit()


# ----- Auth gate -----------------------------------------------------------
@pytest.mark.asyncio
async def test_portfolio_endpoints_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/portfolios")).status_code == 401
    assert (await client.post("/api/v1/portfolios", json={"name": "x"})).status_code == 401


# ----- Full lifecycle ------------------------------------------------------
@pytest.mark.asyncio
async def test_portfolio_full_lifecycle(client: AsyncClient, seed_stocks: None) -> None:
    tok = await _token(client, "owner@example.com")
    h = _hdr(tok)

    created = await client.post("/api/v1/portfolios", json={"name": "Growth"}, headers=h)
    assert created.status_code == 201
    pid = created.json()["data"]["id"]

    listed = await client.get("/api/v1/portfolios", headers=h)
    assert listed.json()["data"][0]["id"] == pid

    add = await client.post(
        f"/api/v1/portfolios/{pid}/items",
        headers=h,
        json={"symbol": "AAA.NS", "quantity": 10, "avg_buy_price": 100},
    )
    assert add.status_code == 201
    item_id = add.json()["data"]["id"]

    detail = await client.get(f"/api/v1/portfolios/{pid}", headers=h)
    assert len(detail.json()["data"]["holdings"]) == 1
    assert detail.json()["data"]["holdings"][0]["symbol"] == "AAA.NS"

    updated = await client.put(
        f"/api/v1/portfolios/{pid}/items/{item_id}", headers=h, json={"quantity": 20}
    )
    assert updated.json()["data"]["quantity"] == 20

    removed = await client.delete(f"/api/v1/portfolios/{pid}/items/{item_id}", headers=h)
    assert removed.status_code == 200

    deleted = await client.delete(f"/api/v1/portfolios/{pid}", headers=h)
    assert deleted.status_code == 200
    assert (await client.get(f"/api/v1/portfolios/{pid}", headers=h)).status_code == 404


@pytest.mark.asyncio
async def test_analytics_reflects_real_prices(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "an@example.com"))
    pid = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=h)).json()["data"]["id"]
    await client.post(
        f"/api/v1/portfolios/{pid}/items",
        headers=h,
        json={"symbol": "AAA.NS", "quantity": 10, "avg_buy_price": 100},
    )
    a = (await client.get(f"/api/v1/portfolios/{pid}/analytics", headers=h)).json()["data"]
    # current 110, prev 105, qty 10 @ 100
    assert a["total_value"] == pytest.approx(1100.0)
    assert a["total_cost"] == pytest.approx(1000.0)
    assert a["total_return_percent"] == pytest.approx(10.0)
    assert a["daily_pnl"] == pytest.approx(50.0)   # 10 * (110 - 105)
    assert a["risk_level"] == "high"               # single holding
    assert a["holdings"][0]["current_price"] == pytest.approx(110.0)


@pytest.mark.asyncio
async def test_risk_stress_and_counterfactual_are_populated_and_labeled(
    client: AsyncClient, seed_stocks: None, db_session: AsyncSession
) -> None:
    aaa = await db_session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
    bbb = await db_session.scalar(select(Stock).where(Stock.symbol == "BBB.NS"))
    assert aaa is not None and bbb is not None
    benchmark = Stock(symbol="^NSEI", name="NIFTY 50", exchange="GLOBAL")
    db_session.add(benchmark)
    await db_session.flush()
    db_session.add_all(
        [
            IndexMembership(
                stock_id=stock.id,
                index_code="NIFTY100",
                valid_from=date(2024, 1, 1),
                source="test",
                source_snapshot_date=date(2024, 1, 1),
            )
            for stock in (aaa, bbb)
        ]
        + [
            Fundamentals(stock_id=aaa.id, market_cap=600),
            Fundamentals(stock_id=bbb.id, market_cap=400),
        ]
    )
    for index in range(2, 45):
        day = date(2024, 1, 1) + timedelta(days=index)
        for stock, close in (
            (aaa, 110 * (1.004**index)),
            (bbb, 180 * (1.002**index)),
            (benchmark, 200 * (1.003**index)),
        ):
            db_session.add(
                DailyPrice(
                    stock_id=stock.id,
                    date=day,
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1000,
                )
            )
    for index in range(2):
        day = date(2024, 1, 1) + timedelta(days=index)
        close = 200 * (1.003**index)
        db_session.add(
            DailyPrice(
                stock_id=benchmark.id,
                date=day,
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000,
            )
        )
    await db_session.commit()
    headers = _hdr(await _token(client, "risk@example.com"))
    portfolio_id = (
        await client.post("/api/v1/portfolios", json={"name": "Risk"}, headers=headers)
    ).json()["data"]["id"]
    await client.post(
        f"/api/v1/portfolios/{portfolio_id}/items",
        headers=headers,
        json={"symbol": "AAA.NS", "quantity": 10, "avg_buy_price": 100},
    )

    risk = await client.get(
        f"/api/v1/portfolios/{portfolio_id}/risk", headers=headers
    )
    assert risk.status_code == 200
    data = risk.json()["data"]
    assert data["data_complete"] is True
    assert data["observations"] >= 30
    assert data["beta"] is not None
    assert data["correlation"]
    assert data["holding_contributions"][0]["risk_contribution_percent"] == 100
    assert len(data["stress_scenarios"]) == 5
    assert all(item["is_prediction"] is False for item in data["stress_scenarios"])
    assert "not actual portfolio performance" in data["methodology"]

    scenario = await client.post(
        f"/api/v1/portfolios/{portfolio_id}/counterfactual",
        headers=headers,
        json={
            "changes": [
                {"symbol": "AAA.NS", "quantity_delta": -5},
                {"symbol": "BBB.NS", "quantity_delta": 5},
            ]
        },
    )
    assert scenario.status_code == 200
    result = scenario.json()["data"]
    assert result["label"] == "Scenario estimate, not a prediction"
    assert result["after"]["concentration_hhi"] < result["before"]["concentration_hhi"]
    assert result["deltas"]["concentration_hhi"] < 0


# ----- Validation / business errors ----------------------------------------
@pytest.mark.asyncio
async def test_add_untracked_stock_404(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "u1@example.com"))
    pid = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=h)).json()["data"]["id"]
    resp = await client.post(
        f"/api/v1/portfolios/{pid}/items",
        headers=h,
        json={"symbol": "NOPE.NS", "quantity": 1, "avg_buy_price": 1},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "stock_not_tracked"


@pytest.mark.asyncio
async def test_duplicate_holding_409(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "u2@example.com"))
    pid = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=h)).json()["data"]["id"]
    body = {"symbol": "AAA.NS", "quantity": 1, "avg_buy_price": 1}
    assert (await client.post(f"/api/v1/portfolios/{pid}/items", headers=h, json=body)).status_code == 201
    dup = await client.post(f"/api/v1/portfolios/{pid}/items", headers=h, json=body)
    assert dup.status_code == 409
    assert dup.json()["error"]["type"] == "duplicate_holding"


@pytest.mark.asyncio
async def test_rename_portfolio(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "ren@example.com"))
    pid = (await client.post("/api/v1/portfolios", json={"name": "Old"}, headers=h)).json()["data"]["id"]
    resp = await client.put(f"/api/v1/portfolios/{pid}", headers=h, json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "New"


@pytest.mark.asyncio
async def test_update_holding_avg_price_and_missing(client: AsyncClient, seed_stocks: None) -> None:
    h = _hdr(await _token(client, "upd@example.com"))
    pid = (await client.post("/api/v1/portfolios", json={"name": "P"}, headers=h)).json()["data"]["id"]
    item_id = (await client.post(
        f"/api/v1/portfolios/{pid}/items", headers=h,
        json={"symbol": "AAA.NS", "quantity": 10, "avg_buy_price": 100},
    )).json()["data"]["id"]

    upd = await client.put(
        f"/api/v1/portfolios/{pid}/items/{item_id}", headers=h, json={"avg_buy_price": 90}
    )
    assert upd.json()["data"]["avg_buy_price"] == 90

    # Updating / removing a non-existent holding → 404.
    assert (await client.put(
        f"/api/v1/portfolios/{pid}/items/999999", headers=h, json={"quantity": 1}
    )).status_code == 404
    assert (await client.delete(
        f"/api/v1/portfolios/{pid}/items/999999", headers=h
    )).status_code == 404


# ----- Ownership (the critical security property) ---------------------------
@pytest.mark.asyncio
async def test_user_cannot_access_others_portfolio(client: AsyncClient, seed_stocks: None) -> None:
    a = _hdr(await _token(client, "alice@example.com"))
    b = _hdr(await _token(client, "bob@example.com"))

    pid = (await client.post("/api/v1/portfolios", json={"name": "Alice"}, headers=a)).json()["data"]["id"]
    await client.post(
        f"/api/v1/portfolios/{pid}/items", headers=a,
        json={"symbol": "AAA.NS", "quantity": 5, "avg_buy_price": 100},
    )

    # Bob must not read, mutate, or even confirm existence of Alice's portfolio.
    assert (await client.get(f"/api/v1/portfolios/{pid}", headers=b)).status_code == 404
    assert (await client.get(f"/api/v1/portfolios/{pid}/analytics", headers=b)).status_code == 404
    assert (await client.get(f"/api/v1/portfolios/{pid}/risk", headers=b)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/portfolios/{pid}/counterfactual",
            headers=b,
            json={"changes": [{"symbol": "BBB.NS", "quantity_delta": 1}]},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/v1/portfolios/{pid}", headers=b)).status_code == 404
    assert (
        await client.post(
            f"/api/v1/portfolios/{pid}/items", headers=b,
            json={"symbol": "BBB.NS", "quantity": 1, "avg_buy_price": 1},
        )
    ).status_code == 404

    # Bob's own listing does not include Alice's portfolio.
    assert (await client.get("/api/v1/portfolios", headers=b)).json()["data"] == []
    # Alice's portfolio is untouched.
    assert len((await client.get(f"/api/v1/portfolios/{pid}", headers=a)).json()["data"]["holdings"]) == 1
