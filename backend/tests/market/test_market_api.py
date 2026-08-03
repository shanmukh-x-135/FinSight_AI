"""API tests for the market read endpoints and the admin ingestion trigger."""

from __future__ import annotations

from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.dependencies import get_market_client
from app.market.models import DailyPrice, Fundamentals, Indicator, Stock
from app.shared.clients.market_data import FundamentalsData, PriceBar

D1, D2 = date(2024, 1, 1), date(2024, 1, 2)


def _price(stock_id: int, d: date, close: float) -> DailyPrice:
    return DailyPrice(
        stock_id=stock_id, date=d, open=close, high=close + 1, low=close - 1,
        close=close, volume=1000,
    )


@pytest_asyncio.fixture
async def seed_market(db_session: AsyncSession) -> None:
    """Three stocks: A +10% (Tech), B -10% (Tech), C unchanged (Energy)."""
    a = Stock(symbol="AAA.NS", name="Alpha", sector="Technology", exchange="NSE")
    b = Stock(symbol="BBB.NS", name="Beta", sector="Technology", exchange="NSE")
    c = Stock(symbol="CCC.NS", name="Gamma", sector="Energy", exchange="NSE")
    db_session.add_all([a, b, c])
    await db_session.flush()

    db_session.add_all(
        [
            _price(a.id, D1, 100.0), _price(a.id, D2, 110.0),
            _price(b.id, D1, 100.0), _price(b.id, D2, 90.0),
            _price(c.id, D1, 50.0), _price(c.id, D2, 50.0),
        ]
    )
    db_session.add(Fundamentals(stock_id=a.id, market_cap=2000, pe_ratio=25.0, eps=8.0))
    db_session.add_all(
        [
            Indicator(stock_id=a.id, date=D1, rsi_14=50.0, ema_20=100.0),
            Indicator(stock_id=a.id, date=D2, rsi_14=60.0, ema_20=105.0, macd=1.2),
        ]
    )
    await db_session.commit()


# ----- Reads ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_gainers(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/gainers")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data[0]["symbol"] == "AAA.NS"
    assert data[0]["change_percent"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_losers(client: AsyncClient, seed_market: None) -> None:
    data = (await client.get("/api/v1/market/losers")).json()["data"]
    assert data[0]["symbol"] == "BBB.NS"
    assert data[0]["change_percent"] == pytest.approx(-10.0)


@pytest.mark.asyncio
async def test_breadth(client: AsyncClient, seed_market: None) -> None:
    data = (await client.get("/api/v1/market/breadth")).json()["data"]
    assert data["advancers"] == 1
    assert data["decliners"] == 1
    assert data["unchanged"] == 1
    assert data["total"] == 3


@pytest.mark.asyncio
async def test_sector_performance(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/sectors/Technology")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stock_count"] == 2
    assert data["average_change_percent"] == pytest.approx(0.0)  # (+10 + -10)/2
    assert {s["symbol"] for s in data["stocks"]} == {"AAA.NS", "BBB.NS"}


@pytest.mark.asyncio
async def test_sector_not_found(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/sectors/Healthcare")
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "sector_not_found"


@pytest.mark.asyncio
async def test_stock_detail(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/stocks/AAA.NS")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["symbol"] == "AAA.NS"
    assert data["close"] == pytest.approx(110.0)
    assert data["change_percent"] == pytest.approx(10.0)
    assert data["fundamentals"]["pe_ratio"] == pytest.approx(25.0)


@pytest.mark.asyncio
async def test_stock_not_found(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/stocks/ZZZ.NS")
    assert resp.status_code == 404
    assert resp.json()["error"]["type"] == "stock_not_found"


@pytest.mark.asyncio
async def test_stock_indicators_history(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/stocks/AAA.NS/indicators")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["date"] == "2024-01-01"  # oldest first
    assert data[-1]["rsi_14"] == pytest.approx(60.0)


# ----- Admin ingestion trigger ---------------------------------------------
class _FakeIngestClient:
    def fetch_daily_prices(self, symbol: str) -> list[PriceBar]:
        return [
            PriceBar(D1, 10, 11, 9, 10, 100),
            PriceBar(D2, 10, 12, 10, 11, 120),
        ]

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        return FundamentalsData(name="Fake", sector="Technology")


@pytest.mark.asyncio
async def test_admin_ingestion_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/jobs/market-ingestion/run", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_ingestion_runs_with_fake_client(
    client: AsyncClient, test_app
) -> None:
    test_app.dependency_overrides[get_market_client] = lambda: _FakeIngestClient()

    await client.post(
        "/api/v1/auth/register",
        json={"email": "ops@example.com", "password": "S3curePass!"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ops@example.com", "password": "S3curePass!"},
    )
    token = login.json()["data"]["access_token"]

    resp = await client.post(
        "/api/v1/admin/jobs/market-ingestion/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbols": ["FAKE.NS"]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["succeeded"] == ["FAKE.NS"]
    assert data["failed"] == []
