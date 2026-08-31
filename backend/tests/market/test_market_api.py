"""API tests for the market read endpoints and the admin ingestion trigger."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.dependencies import get_economic_calendar_client, get_market_client
from app.market.models import (
    DailyPrice,
    Fundamentals,
    IndexMembership,
    Indicator,
    Stock,
)
from app.shared.clients.economic_calendar import EconomicEventData
from app.shared.clients.market_data import FundamentalsData, PriceBar

D1, D2 = date(2024, 1, 1), date(2024, 1, 2)


def _price(stock_id: int, d: date, close: float) -> DailyPrice:
    return DailyPrice(
        stock_id=stock_id,
        date=d,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
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
            _price(a.id, D1, 100.0),
            _price(a.id, D2, 110.0),
            _price(b.id, D1, 100.0),
            _price(b.id, D2, 90.0),
            _price(c.id, D1, 50.0),
            _price(c.id, D2, 50.0),
        ]
    )
    db_session.add(Fundamentals(stock_id=a.id, market_cap=2000, pe_ratio=25.0, eps=8.0))
    db_session.add_all(
        [
            Indicator(stock_id=a.id, date=D1, rsi_14=50.0, ema_20=100.0),
            Indicator(
                stock_id=a.id,
                date=D2,
                rsi_14=60.0,
                ema_20=105.0,
                ema_50=100.0,
                macd=1.2,
                macd_histogram=0.5,
                atr_14=2.2,
            ),
            Indicator(
                stock_id=b.id,
                date=D2,
                rsi_14=30.0,
                ema_20=95.0,
                ema_50=100.0,
                macd=-1.0,
                macd_histogram=-0.5,
                atr_14=3.0,
            ),
        ]
    )
    await db_session.commit()


# ----- Reads ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_gainers(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/gainers")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["symbol"] == "AAA.NS"
    assert data[0]["change_percent"] == pytest.approx(10.0)


@pytest.mark.asyncio
async def test_losers(client: AsyncClient, seed_market: None) -> None:
    data = (await client.get("/api/v1/market/losers")).json()["data"]
    assert len(data) == 1
    assert data[0]["symbol"] == "BBB.NS"
    assert data[0]["change_percent"] == pytest.approx(-10.0)


@pytest.mark.asyncio
async def test_breadth(client: AsyncClient, seed_market: None) -> None:
    data = (await client.get("/api/v1/market/breadth")).json()["data"]
    assert data["advancers"] == 1
    assert data["decliners"] == 1
    assert data["unchanged"] == 1
    assert data["total"] == 3
    assert data["advance_decline_ratio"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_empty_breadth_is_explicit(client: AsyncClient) -> None:
    data = (await client.get("/api/v1/market/breadth")).json()["data"]
    assert data == {
        "advancers": 0,
        "decliners": 0,
        "unchanged": 0,
        "total": 0,
        "advance_decline_ratio": None,
    }


@pytest.mark.asyncio
async def test_market_stocks_returns_dense_batched_snapshots(
    client: AsyncClient, seed_market: None
) -> None:
    response = await client.get("/api/v1/market/stocks")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["symbol"] for row in rows] == ["AAA.NS", "BBB.NS", "CCC.NS"]
    assert rows[0]["rsi_14"] == pytest.approx(60)
    assert rows[0]["trend"] == "bullish"
    assert rows[1]["trend"] == "bearish"
    assert rows[2]["trend"] is None


@pytest.mark.asyncio
async def test_universe_selector_heatmap_and_rotation_are_membership_scoped(
    client: AsyncClient, db_session: AsyncSession, seed_market: None
) -> None:
    stock = await db_session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
    assert stock is not None
    db_session.add(
        IndexMembership(
            stock_id=stock.id,
            index_code="NIFTY100",
            valid_from=date(2023, 12, 1),
            source="test",
            source_snapshot_date=D2,
        )
    )
    prior_dates = [date(2023, 12, 13) + timedelta(days=index) for index in range(19)]
    db_session.add_all(
        [
            _price(stock.id, day, 81.0 + index)
            for index, day in enumerate(prior_dates)
        ]
    )
    await db_session.commit()

    universes = (await client.get("/api/v1/market/universes")).json()["data"]
    nifty100 = next(item for item in universes if item["code"] == "NIFTY100")
    assert nifty100["preferred"] is True
    assert nifty100["active_constituents"] == 1
    assert nifty100["initialized"] is False

    stocks = (
        await client.get("/api/v1/market/stocks?universe=NIFTY100")
    ).json()["data"]
    assert [row["symbol"] for row in stocks] == ["AAA.NS"]

    heatmap = (
        await client.get("/api/v1/market/heatmap?universe=NIFTY100")
    ).json()["data"]
    assert heatmap[0]["market_cap"] == 2000
    assert heatmap[0]["sentiment_availability"] == "no_relevant_news"

    rotation = (
        await client.get("/api/v1/market/sector-rotation?universe=NIFTY100")
    ).json()["data"]
    assert rotation[0]["sector"] == "Technology"
    assert rotation[0]["return_1d"] == pytest.approx(10.0)
    assert rotation[0]["return_5d"] is not None
    assert rotation[0]["return_20d"] is not None
    assert rotation[0]["momentum_regime"] in {
        "leader",
        "improving",
        "weakening",
        "laggard",
        "mixed",
    }

    workspace_response = await client.get(
        "/api/v1/market/workspace?universe=NIFTY100&days=7"
    )
    assert workspace_response.status_code == 200
    workspace = workspace_response.json()["data"]
    assert workspace["universe"] == "NIFTY100"
    assert [row["symbol"] for row in workspace["stocks"]] == ["AAA.NS"]
    assert workspace["breadth"]["advancers"] == 1
    assert workspace["sectors"][0]["sector"] == "Technology"
    assert workspace["technical"]["stocks_with_indicators"] == 1
    assert workspace["heatmap"][0]["symbol"] == "AAA.NS"
    assert workspace["sector_rotation"][0]["sector"] == "Technology"
    assert [row["symbol"] for row in workspace["sentiment"]] == ["AAA.NS"]
    assert workspace["economic_events"]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_market_rejects_unsupported_universe(client: AsyncClient) -> None:
    response = await client.get("/api/v1/market/heatmap?universe=NIFTY500")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_technical_summary(client: AsyncClient, seed_market: None) -> None:
    data = (await client.get("/api/v1/market/technical-summary")).json()["data"]
    assert data["as_of"] == "2024-01-02"
    assert data["stocks_with_indicators"] == 2
    assert data["average_rsi"] == pytest.approx(45)
    assert data["bullish_rsi_count"] == 1
    assert data["oversold_count"] == 1
    assert data["above_ema20_count"] == 1
    assert data["above_ema50_count"] == 1
    assert data["positive_macd_count"] == 1
    assert data["average_atr_percent"] == pytest.approx(2.666666, rel=1e-5)


class _FakeCalendarClient:
    async def fetch_events(self, start_date: date, end_date: date):
        return [
            EconomicEventData(
                event_id="event-1",
                date=datetime(2026, 8, 7, 6, 30, tzinfo=timezone.utc),
                country="India",
                category="Interest Rate",
                name="RBI Interest Rate Decision",
                importance=3,
                source="Reserve Bank of India",
            )
        ]


class _FailingCalendarClient:
    async def fetch_events(self, start_date: date, end_date: date):
        raise TimeoutError("provider timeout")


@pytest.mark.asyncio
async def test_economic_events_uses_provider(client: AsyncClient, test_app) -> None:
    test_app.dependency_overrides[get_economic_calendar_client] = lambda: (
        _FakeCalendarClient()
    )
    response = await client.get("/api/v1/market/economic-events?days=7")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "ok"
    assert data["events"][0]["name"] == "RBI Interest Rate Decision"


@pytest.mark.asyncio
async def test_economic_events_reports_unconfigured(client: AsyncClient) -> None:
    data = (await client.get("/api/v1/market/economic-events")).json()["data"]
    assert data == {
        "provider": "Trading Economics",
        "status": "not_configured",
        "events": [],
    }


@pytest.mark.asyncio
async def test_economic_events_degrades_on_provider_failure(
    client: AsyncClient, test_app
) -> None:
    test_app.dependency_overrides[get_economic_calendar_client] = lambda: (
        _FailingCalendarClient()
    )
    response = await client.get("/api/v1/market/economic-events")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_sector_performance(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/sectors/Technology")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["stock_count"] == 2
    assert data["average_change_percent"] == pytest.approx(0.0)  # (+10 + -10)/2
    assert {s["symbol"] for s in data["stocks"]} == {"AAA.NS", "BBB.NS"}


@pytest.mark.asyncio
async def test_sectors_overview(client: AsyncClient, seed_market: None) -> None:
    resp = await client.get("/api/v1/market/sectors")
    assert resp.status_code == 200
    data = resp.json()["data"]
    by_sector = {s["sector"]: s for s in data}
    assert by_sector["Technology"]["stock_count"] == 2
    assert by_sector["Technology"]["average_change_percent"] == pytest.approx(0.0)
    assert by_sector["Energy"]["stock_count"] == 1
    assert by_sector["Energy"]["average_change_percent"] == pytest.approx(0.0)
    # Best-performing sector first (both 0.0 here → both present, order stable).
    assert {s["sector"] for s in data} == {"Technology", "Energy"}


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
async def test_movement_attribution_is_deterministic_and_honest_about_missing_news(
    client: AsyncClient, seed_market: None
) -> None:
    response = await client.get("/api/v1/market/stocks/AAA.NS/attribution")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["certainty"] == "likely_contributors_not_proven_causes"
    drivers = {row["category"]: row for row in data["drivers"]}
    assert set(drivers) == {
        "company_news",
        "sector",
        "market",
        "technical",
        "volume",
        "historical",
        "macro",
        "corporate_action",
    }
    assert drivers["company_news"]["direction"] == "unavailable"
    assert "No verified company catalyst" in drivers["company_news"]["observation"]
    assert drivers["sector"]["value_percent"] == pytest.approx(0)
    assert drivers["market"]["value_percent"] == pytest.approx(0)
    assert drivers["technical"]["direction"] == "bullish"
    assert drivers["volume"]["observation"] == "Volume was 1.00× its prior-session average"
    assert data["evidence_conflict"]["signals"][1]["direction"] == "unavailable"


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


@pytest.mark.asyncio
async def test_stock_price_history_is_bounded_and_oldest_first(
    client: AsyncClient, seed_market: None
) -> None:
    response = await client.get("/api/v1/market/stocks/AAA.NS/prices?limit=2")
    assert response.status_code == 200
    data = response.json()["data"]
    assert [row["date"] for row in data] == ["2024-01-01", "2024-01-02"]
    assert data[-1]["close"] == pytest.approx(110)
    assert set(data[-1]) == {"date", "open", "high", "low", "close", "volume"}


# ----- Admin ingestion trigger ---------------------------------------------
class _FakeIngestClient:
    def fetch_daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        current = date.today()
        return [
            PriceBar(
                current - timedelta(days=59 - index),
                10 + index,
                11 + index,
                9 + index,
                10.5 + index,
                100 + index,
            )
            for index in range(60)
        ]

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        return FundamentalsData(name="Fake", sector="Technology")


@pytest.mark.asyncio
async def test_admin_ingestion_requires_auth(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/admin/jobs/market-ingestion/run", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_ingestion_runs_with_fake_client(
    client: AsyncClient, test_app, admin_headers: dict[str, str]
) -> None:
    test_app.dependency_overrides[get_market_client] = lambda: _FakeIngestClient()

    resp = await client.post(
        "/api/v1/admin/jobs/market-ingestion/run",
        headers=admin_headers,
        json={"symbols": ["FAKE.NS"]},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["succeeded"] == ["FAKE.NS"]
    assert data["failed"] == []
