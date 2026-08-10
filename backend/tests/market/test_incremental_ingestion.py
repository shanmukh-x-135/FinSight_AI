"""P10.5 incremental window, repair, and canonical-indicator regressions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import DailyPrice, Fundamentals, Indicator, Stock
from app.market.repository import MarketRepository, PriceIngestionState
from app.market.service import (
    IngestionMode,
    MarketIngestionService,
    compute_indicator_points,
    plan_price_fetch,
)
from app.shared.clients.market_data import FundamentalsData, PriceBar
from config.settings import settings

START = date(2024, 1, 1)
INITIAL_TARGET = START + timedelta(days=59)
NEXT_TARGET = INITIAL_TARGET + timedelta(days=1)
SYNC_TIME = datetime(2024, 3, 1, 12, tzinfo=timezone.utc)


def _bar(day: date, close: float) -> PriceBar:
    return PriceBar(day, close - 0.5, close + 1, close - 1, close, 1000)


def _series(count: int = 60) -> list[PriceBar]:
    return [_bar(START + timedelta(days=i), 100 + i) for i in range(count)]


class RecordingClient:
    def __init__(self, bars: list[PriceBar]) -> None:
        self.bars = bars
        self.fundamentals = FundamentalsData(
            name="Incremental Corp",
            sector="Technology",
            industry="Software",
            market_cap=1_000,
        )
        self.price_calls: list[tuple[str, date | None, date | None]] = []
        self.fundamental_calls: list[str] = []

    def fetch_daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        self.price_calls.append((symbol, start_date, end_date))
        # Deliberately return unbounded provider data. The service must enforce
        # the requested range even if an adapter/provider violates its contract.
        return self.bars

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        self.fundamental_calls.append(symbol)
        return self.fundamentals


def test_fetch_plan_bootstraps_reconciles_and_handles_backdated_targets(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "market_bootstrap_lookback_days", 100)
    monkeypatch.setattr(settings, "market_incremental_overlap_days", 5)
    monkeypatch.setattr(settings, "market_full_reconciliation_days", 30)

    bootstrap = plan_price_fetch(None, NEXT_TARGET, now=SYNC_TIME)
    assert bootstrap.mode == IngestionMode.BOOTSTRAP
    assert bootstrap.start_date == NEXT_TARGET - timedelta(days=100)
    assert bootstrap.end_date == NEXT_TARGET + timedelta(days=1)

    legacy = PriceIngestionState(1, INITIAL_TARGET, None)
    assert plan_price_fetch(legacy, NEXT_TARGET, now=SYNC_TIME).mode == (
        IngestionMode.RECONCILIATION
    )

    recent = PriceIngestionState(1, NEXT_TARGET + timedelta(days=10), SYNC_TIME)
    backdated = plan_price_fetch(
        recent, NEXT_TARGET, now=SYNC_TIME + timedelta(days=1)
    )
    assert backdated.mode == IngestionMode.INCREMENTAL
    assert backdated.start_date == NEXT_TARGET - timedelta(days=5)

    due = plan_price_fetch(
        recent, NEXT_TARGET, now=SYNC_TIME + timedelta(days=30)
    )
    assert due.mode == IngestionMode.RECONCILIATION


@pytest.mark.asyncio
async def test_incremental_fetch_repairs_overlap_and_uses_canonical_indicator_history(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "market_incremental_overlap_days", 7)
    client = RecordingClient(_series())
    service = MarketIngestionService(db_session, client)

    first = await service.ingest(
        ["WINDOW.NS"], target_trading_date=INITIAL_TARGET, now=SYNC_TIME
    )
    assert first.bootstrap_symbols == 1
    assert first.price_bars_fetched == 60
    assert client.price_calls[0] == (
        "WINDOW.NS",
        INITIAL_TARGET - timedelta(days=settings.market_bootstrap_lookback_days),
        INITIAL_TARGET + timedelta(days=1),
    )

    corrected_day = INITIAL_TARGET - timedelta(days=3)
    correction = _bar(corrected_day, 250)
    new_bar = _bar(NEXT_TARGET, 175)
    future_bar = _bar(NEXT_TARGET + timedelta(days=1), 999)
    client.bars = [correction, new_bar, future_bar]
    second = await service.ingest(
        ["WINDOW.NS"],
        target_trading_date=NEXT_TARGET,
        now=SYNC_TIME + timedelta(days=1),
    )

    assert second.incremental_symbols == 1
    assert second.price_bars_fetched == 2
    assert client.price_calls[-1] == (
        "WINDOW.NS",
        INITIAL_TARGET - timedelta(days=7),
        NEXT_TARGET + timedelta(days=1),
    )
    assert client.fundamental_calls == ["WINDOW.NS"]

    stock = await MarketRepository(db_session).get_stock_by_symbol("WINDOW.NS")
    assert stock is not None
    stored = await MarketRepository(db_session).get_price_history(stock.id)
    assert len(stored) == 61
    assert next(row for row in stored if row.date == corrected_day).close == 250
    assert max(row.date for row in stored) == NEXT_TARGET

    canonical = [
        PriceBar(row.date, row.open, row.high, row.low, row.close, row.volume)
        for row in stored
    ]
    expected = compute_indicator_points(canonical)[-1]
    latest = await db_session.scalar(
        select(Indicator).where(
            Indicator.stock_id == stock.id, Indicator.date == NEXT_TARGET
        )
    )
    assert latest is not None
    assert latest.ema_50 == pytest.approx(expected["ema_50"])
    assert latest.macd == pytest.approx(expected["macd"])


@pytest.mark.asyncio
async def test_periodic_reconciliation_refreshes_full_window_and_fundamentals(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "market_full_reconciliation_days", 30)
    client = RecordingClient(_series())
    service = MarketIngestionService(db_session, client)
    await service.ingest(
        ["RECON.NS"], target_trading_date=INITIAL_TARGET, now=SYNC_TIME
    )
    client.fundamentals = FundamentalsData(
        name="Reconciled Corp", sector="Financials", market_cap=2_000
    )

    result = await service.ingest(
        ["RECON.NS"],
        target_trading_date=INITIAL_TARGET,
        now=SYNC_TIME + timedelta(days=30),
    )

    assert result.reconciliation_symbols == 1
    assert client.price_calls[-1][1] == (
        INITIAL_TARGET - timedelta(days=settings.market_bootstrap_lookback_days)
    )
    assert client.fundamental_calls == ["RECON.NS", "RECON.NS"]
    stock = await MarketRepository(db_session).get_stock_by_symbol("RECON.NS")
    assert stock is not None
    assert stock.name == "Reconciled Corp"
    assert stock.sector == "Financials"
    assert stock.fundamentals is not None
    assert stock.fundamentals.market_cap == 2_000


@pytest.mark.asyncio
async def test_empty_incremental_window_rolls_back_without_advancing_watermark(
    db_session: AsyncSession,
) -> None:
    client = RecordingClient(_series())
    service = MarketIngestionService(db_session, client)
    await service.ingest(
        ["EMPTY.NS"], target_trading_date=INITIAL_TARGET, now=SYNC_TIME
    )
    stock = await MarketRepository(db_session).get_stock_by_symbol("EMPTY.NS")
    assert stock is not None
    original_watermark = stock.last_full_price_sync_at

    client.bars = [_bar(NEXT_TARGET + timedelta(days=1), 999)]
    failed = await service.ingest(
        ["EMPTY.NS"],
        target_trading_date=NEXT_TARGET,
        now=SYNC_TIME + timedelta(days=1),
    )

    assert failed.failed == ["EMPTY.NS"]
    assert failed.incremental_symbols == 0
    await db_session.refresh(stock)
    assert stock.last_full_price_sync_at == original_watermark
    assert await db_session.scalar(
        select(func.count(DailyPrice.id)).where(DailyPrice.stock_id == stock.id)
    ) == 60


@pytest.mark.asyncio
async def test_backdated_reconciliation_does_not_advance_full_watermark(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "market_full_reconciliation_days", 30)
    client = RecordingClient(_series())
    service = MarketIngestionService(db_session, client)
    await service.ingest(
        ["BACKDATE.NS"], target_trading_date=INITIAL_TARGET, now=SYNC_TIME
    )
    stock = await MarketRepository(db_session).get_stock_by_symbol("BACKDATE.NS")
    assert stock is not None
    await MarketRepository(db_session).upsert_daily_prices(
        stock.id, [_bar(INITIAL_TARGET + timedelta(days=10), 300)]
    )
    await db_session.commit()

    result = await service.ingest(
        ["BACKDATE.NS"],
        target_trading_date=INITIAL_TARGET,
        now=SYNC_TIME + timedelta(days=30),
    )

    assert result.reconciliation_symbols == 1
    await db_session.refresh(stock)
    stored_watermark = stock.last_full_price_sync_at
    assert stored_watermark is not None
    if stored_watermark.tzinfo is None:  # SQLite drops timezone metadata.
        stored_watermark = stored_watermark.replace(tzinfo=timezone.utc)
    assert stored_watermark == SYNC_TIME


@pytest.mark.asyncio
async def test_empty_fundamentals_do_not_erase_previous_values(
    db_session: AsyncSession,
) -> None:
    repo = MarketRepository(db_session)
    stock = Stock(symbol="META.NS", name="Metadata")
    db_session.add(stock)
    await db_session.flush()
    await repo.upsert_fundamentals(
        stock.id, FundamentalsData(market_cap=10_000, pe_ratio=20)
    )
    await repo.upsert_fundamentals(stock.id, FundamentalsData())
    await db_session.commit()

    stored = await db_session.scalar(
        select(Fundamentals).where(Fundamentals.stock_id == stock.id)
    )
    assert stored is not None
    assert stored.market_cap == 10_000
    assert stored.pe_ratio == 20


@pytest.mark.asyncio
async def test_provider_exception_details_are_not_logged(
    db_session: AsyncSession, caplog
) -> None:
    class FailingClient(RecordingClient):
        def fetch_daily_prices(
            self,
            symbol: str,
            *,
            start_date: date | None = None,
            end_date: date | None = None,
        ) -> list[PriceBar]:
            raise RuntimeError("provider payload secret-token")

    result = await MarketIngestionService(
        db_session, FailingClient([])
    ).ingest(["SAFE.NS"], target_trading_date=INITIAL_TARGET, now=SYNC_TIME)

    assert result.failed == ["SAFE.NS"]
    assert "secret-token" not in caplog.text
