"""Versioning, ownership, replay persistence, and benchmark API coverage."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, IndexMembership, Indicator, Stock
from app.news.models import NewsArticle, NewsArticleStock
from app.strategy.data import BacktestDataLoader
from app.strategy.models import (
    BacktestMetric,
    BacktestRun,
    BacktestTrade,
    StrategyVersion,
)

START = date(2026, 1, 1)


async def _headers(client: AsyncClient, email: str) -> dict[str, str]:
    password = "S3curePass!"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {login.json()['data']['access_token']}"}


async def _seed_prices(db: AsyncSession) -> None:
    equity = Stock(
        symbol="AAA.NS",
        exchange_symbol="AAA",
        name="Alpha",
        sector="Technology",
        exchange="NSE",
    )
    benchmark = Stock(
        symbol="^NSEI",
        name="NIFTY 50 benchmark",
        sector="Macro",
        exchange="GLOBAL",
        is_active=False,
    )
    db.add_all([equity, benchmark])
    await db.flush()
    db.add(
        IndexMembership(
            stock_id=equity.id,
            index_code="NIFTY100",
            valid_from=START,
            source="test",
            source_snapshot_date=START,
        )
    )
    for index in range(45):
        day = START + timedelta(days=index)
        close = 100 + index
        db.add_all(
            [
                DailyPrice(
                    stock_id=equity.id,
                    date=day,
                    open=close - 0.5,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=1000 + index * 10,
                ),
                DailyPrice(
                    stock_id=benchmark.id,
                    date=day,
                    open=200 + index - 0.5,
                    high=201 + index,
                    low=199 + index,
                    close=200 + index,
                    volume=10_000,
                ),
                Indicator(
                    stock_id=equity.id,
                    date=day,
                    ema_20=close - 2,
                    ema_50=close - 5,
                    rsi_14=80 if index in {10, 25, 40} else 55,
                    macd_histogram=1,
                ),
            ]
        )
    await db.commit()


def _strategy_payload(name: str = "EMA momentum") -> dict:
    return {
        "name": name,
        "description": "Close-confirmed momentum with next-session execution.",
        "definition": {
            "entry": {
                "operator": "AND",
                "rules": [
                    {
                        "field": "price_vs_ema50",
                        "operator": "above",
                    },
                    {
                        "field": "rsi",
                        "operator": "between",
                        "value": 45,
                        "upper_value": 65,
                    },
                ],
            },
            "exit": {
                "operator": "OR",
                "rules": [{"field": "rsi", "operator": "gt", "value": 75}],
            },
            "execution": {
                "initial_capital": 100000,
                "max_positions": 5,
                "transaction_cost_bps": 10,
                "slippage_bps": 5,
                "stop_loss_percent": 5,
                "take_profit_percent": 15,
                "max_holding_sessions": 20,
                "benchmark_symbol": "^NSEI",
            },
        },
    }


@pytest.mark.asyncio
async def test_strategy_versions_and_repeated_backtests_are_reproducible(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_prices(db_session)
    headers = await _headers(client, "strategist@example.com")

    created = await client.post(
        "/api/v1/strategies", json=_strategy_payload(), headers=headers
    )
    assert created.status_code == 201
    strategy = created.json()["data"]
    assert strategy["latest_version"]["version"] == 1

    update_payload = _strategy_payload("EMA momentum v2")
    update_payload.pop("name")
    updated = await client.put(
        f"/api/v1/strategies/{strategy['id']}", json=update_payload, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["latest_version"]["version"] == 2
    assert await db_session.scalar(select(func.count()).select_from(StrategyVersion)) == 2

    request = {
        "start_date": START.isoformat(),
        "end_date": (START + timedelta(days=44)).isoformat(),
        "universe_code": "NIFTY100",
        "membership_mode": "current_universe",
    }
    first = await client.post(
        f"/api/v1/strategies/{strategy['id']}/backtests",
        json=request,
        headers=headers,
    )
    second = await client.post(
        f"/api/v1/strategies/{strategy['id']}/backtests",
        json=request,
        headers=headers,
    )

    assert first.status_code == second.status_code == 201
    first_data, second_data = first.json()["data"], second.json()["data"]
    assert first_data["result_hash"] == second_data["result_hash"]
    assert first_data["metrics"] == second_data["metrics"]
    assert first_data["trades"] == second_data["trades"]
    assert first_data["metrics"]["benchmark_return_percent"] is not None
    assert first_data["metrics"]["estimated_transaction_costs"] > 0
    assert "survivorship bias" in first_data["membership_disclaimer"]
    assert all(
        trade["entry_date"] > trade["entry_signal_date"] for trade in first_data["trades"]
    )
    assert all(
        trade["exit_signal_date"] is None
        or trade["exit_date"] > trade["exit_signal_date"]
        for trade in first_data["trades"]
    )
    assert await db_session.scalar(select(func.count()).select_from(BacktestRun)) == 2
    assert await db_session.scalar(select(func.count()).select_from(BacktestTrade)) > 0
    assert await db_session.scalar(select(func.count()).select_from(BacktestMetric)) == 32

    analysis = await client.post(
        f"/api/v1/backtests/{first_data['id']}/robustness", headers=headers
    )
    assert analysis.status_code == 200
    robustness = analysis.json()["data"]
    assert robustness["baseline_result_hash"] == first_data["result_hash"]
    assert robustness["chronological_split"]["test"] is not None
    assert len(robustness["parameter_sensitivity"]) == 3
    assert len(robustness["cost_sensitivity"]) == 3
    assert robustness["robustness"]["score"] <= 100
    stored = await client.get(
        f"/api/v1/backtests/{first_data['id']}", headers=headers
    )
    assert stored.json()["data"]["robustness_analysis"] == robustness


@pytest.mark.asyncio
async def test_strategy_and_backtest_ownership_is_hidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_prices(db_session)
    owner = await _headers(client, "owner-strategy@example.com")
    outsider = await _headers(client, "outsider-strategy@example.com")
    created = await client.post(
        "/api/v1/strategies", json=_strategy_payload(), headers=owner
    )
    strategy_id = created.json()["data"]["id"]

    response = await client.get(f"/api/v1/strategies/{strategy_id}", headers=outsider)

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "strategy_not_found"


@pytest.mark.asyncio
async def test_robustness_fails_closed_when_replay_inputs_drift(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_prices(db_session)
    headers = await _headers(client, "drift-strategy@example.com")
    created = await client.post(
        "/api/v1/strategies", json=_strategy_payload(), headers=headers
    )
    strategy_id = created.json()["data"]["id"]
    run = await client.post(
        f"/api/v1/strategies/{strategy_id}/backtests",
        json={
            "start_date": START.isoformat(),
            "end_date": (START + timedelta(days=44)).isoformat(),
            "universe_code": "NIFTY100",
            "membership_mode": "current_universe",
        },
        headers=headers,
    )
    run_id = run.json()["data"]["id"]
    equity = await db_session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
    assert equity is not None
    price = await db_session.scalar(
        select(DailyPrice).where(
            DailyPrice.stock_id == equity.id,
            DailyPrice.date == START + timedelta(days=1),
        )
    )
    assert price is not None
    price.open += 10
    price.high += 10
    await db_session.commit()

    response = await client.post(
        f"/api/v1/backtests/{run_id}/robustness", headers=headers
    )

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "backtest_replay_drift"


@pytest.mark.asyncio
async def test_historical_membership_fails_closed_before_recorded_coverage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_prices(db_session)
    headers = await _headers(client, "historical-strategy@example.com")
    created = await client.post(
        "/api/v1/strategies", json=_strategy_payload(), headers=headers
    )
    strategy_id = created.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/strategies/{strategy_id}/backtests",
        json={
            "start_date": (START - timedelta(days=1)).isoformat(),
            "end_date": (START + timedelta(days=30)).isoformat(),
            "universe_code": "NIFTY100",
            "membership_mode": "historical_membership",
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["type"] == "backtest_data_unavailable"


@pytest.mark.asyncio
async def test_news_is_assigned_to_first_close_after_publication(
    db_session: AsyncSession,
) -> None:
    await _seed_prices(db_session)
    equity = await db_session.scalar(select(Stock).where(Stock.symbol == "AAA.NS"))
    assert equity is not None
    ist = ZoneInfo("Asia/Kolkata")
    publication_day = START + timedelta(days=1)
    before = NewsArticle(
        source="test",
        url="https://example.test/before-close",
        fingerprint="before-close",
        title="Before close",
        summary="",
        published_at=datetime.combine(publication_day, time(14), tzinfo=ist).astimezone(
            timezone.utc
        ),
        sentiment_label="positive",
        sentiment_score=0.4,
        sentiment_positive=0.7,
        sentiment_negative=0.1,
        sentiment_neutral=0.2,
        sentiment_confidence=0.6,
        event_category="Other",
        event_confidence=0.2,
        driver="Coverage",
        evidence_excerpt="Before close",
    )
    after = NewsArticle(
        source="test",
        url="https://example.test/after-close",
        fingerprint="after-close",
        title="After close",
        summary="",
        published_at=datetime.combine(publication_day, time(16), tzinfo=ist).astimezone(
            timezone.utc
        ),
        sentiment_label="negative",
        sentiment_score=-0.6,
        sentiment_positive=0.1,
        sentiment_negative=0.8,
        sentiment_neutral=0.1,
        sentiment_confidence=0.7,
        event_category="Other",
        event_confidence=0.2,
        driver="Coverage",
        evidence_excerpt="After close",
    )
    db_session.add_all([before, after])
    await db_session.flush()
    db_session.add_all(
        [
            NewsArticleStock(article_id=before.id, stock_id=equity.id),
            NewsArticleStock(article_id=after.id, stock_id=equity.id),
        ]
    )
    await db_session.commit()

    data = await BacktestDataLoader(db_session).load(
        start_date=START,
        end_date=START + timedelta(days=4),
        universe_code="NIFTY100",
        membership_mode="current_universe",
        benchmark_symbol="^NSEI",
    )
    by_date = {bar.date: bar.news_sentiment for bar in data.bars}

    assert by_date[publication_day] == pytest.approx(0.4)
    assert by_date[publication_day + timedelta(days=1)] == pytest.approx(-0.6)
