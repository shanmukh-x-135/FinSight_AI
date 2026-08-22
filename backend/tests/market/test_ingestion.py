"""Ingestion pipeline tests using a fake client (no network), plus the
yfinance client's retry and validation behavior."""

from __future__ import annotations

import time
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market import constants as market_constants
from app.market import service as market_service
from app.market.exceptions import UniverseNotInitializedError
from app.market.models import DailyPrice, Fundamentals, IndexMembership, Indicator, Stock
from app.market.repository import MarketRepository
from app.market.service import MarketIngestionService, compute_indicator_points
from app.shared.clients.market_data import (
    FundamentalsData,
    MarketDataError,
    PriceBar,
)


def _make_bars(n: int = 60, start: float = 100.0, step: float = 1.0) -> list[PriceBar]:
    """Rising series so all indicators (incl. EMA-50) are defined."""
    d0 = date(2024, 1, 1)
    bars = []
    for i in range(n):
        close = start + i * step
        bars.append(
            PriceBar(
                date=d0 + timedelta(days=i),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1000 + i,
            )
        )
    return bars


TARGET = _make_bars()[-1].date


class FakeClient:
    """Configurable in-memory MarketDataClient."""

    def __init__(self, bars_by_symbol=None, fail_symbols=None, fundamentals=None):
        self.bars_by_symbol = bars_by_symbol or {}
        self.fail_symbols = set(fail_symbols or [])
        self.fundamentals = fundamentals or FundamentalsData(
            name="Test Corp", sector="Technology", industry="Software", market_cap=1_000
        )

    def fetch_daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        if symbol in self.fail_symbols:
            raise MarketDataError(f"boom for {symbol}")
        return self.bars_by_symbol.get(symbol, _make_bars())

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        return self.fundamentals


async def _approve(
    db_session: AsyncSession,
    symbol: str,
    *,
    valid_to: date | None = None,
) -> Stock:
    stock = Stock(
        symbol=f"{symbol}.NS",
        exchange_symbol=symbol,
        exchange="NSE",
        is_active=valid_to is None,
    )
    db_session.add(stock)
    await db_session.flush()
    db_session.add(
        IndexMembership(
            stock_id=stock.id,
            index_code="NIFTY50",
            valid_from=TARGET - timedelta(days=30),
            valid_to=valid_to,
            source="test",
            source_snapshot_date=TARGET,
        )
    )
    await db_session.commit()
    return stock


# ----- Ingestion service ---------------------------------------------------
@pytest.mark.asyncio
async def test_ingest_stores_all_layers(db_session: AsyncSession) -> None:
    service = MarketIngestionService(db_session, FakeClient())
    result = await service.ingest(["GOOD.NS"], target_trading_date=TARGET)

    assert result.succeeded == ["GOOD.NS"]
    assert result.failed == []

    repo = MarketRepository(db_session)
    stock = await repo.get_stock_by_symbol("GOOD.NS")
    assert stock is not None
    assert stock.sector == "Technology"

    price_count = await db_session.scalar(
        select(func.count())
        .select_from(DailyPrice)
        .where(DailyPrice.stock_id == stock.id)
    )
    assert price_count == 60
    fundamentals = await db_session.scalar(
        select(Fundamentals).where(Fundamentals.stock_id == stock.id)
    )
    assert fundamentals is not None and fundamentals.market_cap == 1_000
    indicator_count = await db_session.scalar(
        select(func.count()).select_from(Indicator).where(Indicator.stock_id == stock.id)
    )
    assert indicator_count and indicator_count > 0


@pytest.mark.asyncio
async def test_default_ingest_persists_macro_as_inactive(
    db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(
        market_constants,
        "MACRO_PROXIES",
        {"INR=X": ("USD/INR", "Currency")},
    )
    await _approve(db_session, "GOOD")

    result = await MarketIngestionService(db_session, FakeClient()).ingest(
        target_trading_date=TARGET
    )

    assert result.succeeded == ["GOOD.NS", "INR=X"]
    macro = await db_session.scalar(select(Stock).where(Stock.symbol == "INR=X"))
    assert macro is not None
    assert macro.is_active is False
    assert macro.sector == "Macro"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DailyPrice)
            .where(DailyPrice.stock_id == macro.id)
        )
        == 60
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Indicator)
            .where(Indicator.stock_id == macro.id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_default_ingest_requires_initialized_database_universe(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(UniverseNotInitializedError):
        await MarketIngestionService(db_session, FakeClient()).ingest(
            target_trading_date=TARGET
        )


@pytest.mark.asyncio
async def test_default_ingest_excludes_removed_membership_and_keeps_macros(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        market_constants,
        "MACRO_PROXIES",
        {"INR=X": ("USD/INR", "Currency")},
    )
    await _approve(db_session, "GOOD")
    await _approve(db_session, "REMOVED", valid_to=TARGET)

    result = await MarketIngestionService(
        db_session, FakeClient(fail_symbols=["REMOVED.NS"])
    ).ingest(target_trading_date=TARGET)

    assert result.requested == 2
    assert result.succeeded == ["GOOD.NS", "INR=X"]
    assert result.failed == []


@pytest.mark.asyncio
async def test_approved_equity_failure_remains_strictly_visible(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(market_constants, "MACRO_PROXIES", {})
    await _approve(db_session, "BAD")

    result = await MarketIngestionService(
        db_session, FakeClient(fail_symbols=["BAD.NS"])
    ).ingest(target_trading_date=TARGET)

    assert result.requested == 1
    assert result.succeeded == []
    assert result.failed == ["BAD.NS"]


@pytest.mark.asyncio
async def test_ingest_isolates_failures(db_session: AsyncSession) -> None:
    service = MarketIngestionService(db_session, FakeClient(fail_symbols=["BAD.NS"]))
    result = await service.ingest(
        ["GOOD.NS", "BAD.NS", "ALSOGOOD.NS"], target_trading_date=TARGET
    )

    assert set(result.succeeded) == {"GOOD.NS", "ALSOGOOD.NS"}
    assert result.failed == ["BAD.NS"]
    # The good symbols persisted despite the bad one in the middle.
    assert await MarketRepository(db_session).get_stock_by_symbol("GOOD.NS") is not None
    assert await MarketRepository(db_session).get_stock_by_symbol("BAD.NS") is None


@pytest.mark.asyncio
async def test_indicator_failure_rolls_back_the_symbol_and_is_safe_to_retry(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = market_service.compute_indicator_points

    def fail_indicators(_bars: list[PriceBar]) -> list[dict]:
        raise RuntimeError("simulated indicator failure")

    monkeypatch.setattr(market_service, "compute_indicator_points", fail_indicators)
    failed = await MarketIngestionService(db_session, FakeClient()).ingest(
        ["RETRY.NS"], target_trading_date=TARGET
    )
    assert failed.failed == ["RETRY.NS"]
    assert await MarketRepository(db_session).get_stock_by_symbol("RETRY.NS") is None

    monkeypatch.setattr(market_service, "compute_indicator_points", original)
    recovered = await MarketIngestionService(db_session, FakeClient()).ingest(
        ["RETRY.NS"], target_trading_date=TARGET
    )
    assert recovered.succeeded == ["RETRY.NS"]
    stock = await MarketRepository(db_session).get_stock_by_symbol("RETRY.NS")
    assert stock is not None
    assert await db_session.scalar(
        select(func.count(DailyPrice.id)).where(DailyPrice.stock_id == stock.id)
    ) == len(_make_bars())


@pytest.mark.asyncio
async def test_replacement_ingestion_retires_old_symbol_without_rewriting_history(
    db_session: AsyncSession,
) -> None:
    old_stock = Stock(symbol="TATAMOTORS.NS", name="Historical Tata Motors")
    db_session.add(old_stock)
    await db_session.flush()
    old_bar = _make_bars(1)[0]
    await MarketRepository(db_session).upsert_daily_prices(old_stock.id, [old_bar])
    await db_session.commit()

    result = await MarketIngestionService(db_session, FakeClient()).ingest(
        ["TMPV.NS"], target_trading_date=TARGET
    )

    assert result.failed == []
    await db_session.refresh(old_stock)
    assert old_stock.is_active is False
    assert old_stock.symbol == "TATAMOTORS.NS"
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DailyPrice)
            .where(DailyPrice.stock_id == old_stock.id)
        )
        == 1
    )
    replacement = await MarketRepository(db_session).get_stock_by_symbol("TMPV.NS")
    assert replacement is not None and replacement.is_active is True


@pytest.mark.asyncio
async def test_failed_replacement_does_not_retire_old_symbol(
    db_session: AsyncSession,
) -> None:
    old_stock = Stock(symbol="TATAMOTORS.NS", name="Historical Tata Motors")
    db_session.add(old_stock)
    await db_session.commit()

    result = await MarketIngestionService(
        db_session, FakeClient(fail_symbols=["TMPV.NS"])
    ).ingest(["TMPV.NS"], target_trading_date=TARGET)

    assert result.failed == ["TMPV.NS"]
    await db_session.refresh(old_stock)
    assert old_stock.is_active is True


@pytest.mark.asyncio
async def test_ingest_enforces_provider_deadline(
    db_session: AsyncSession, monkeypatch
) -> None:
    from config.settings import settings

    class SlowClient(FakeClient):
        def fetch_daily_prices(
            self,
            symbol: str,
            *,
            start_date: date | None = None,
            end_date: date | None = None,
        ) -> list[PriceBar]:
            time.sleep(0.05)
            return _make_bars()

    monkeypatch.setattr(settings, "market_fetch_timeout_seconds", 0.001)
    result = await MarketIngestionService(db_session, SlowClient()).ingest(
        ["SLOW.NS"], target_trading_date=TARGET
    )

    assert result.succeeded == []
    assert result.failed == ["SLOW.NS"]


@pytest.mark.asyncio
async def test_ingest_is_idempotent(db_session: AsyncSession) -> None:
    service = MarketIngestionService(db_session, FakeClient())
    await service.ingest(["GOOD.NS"], target_trading_date=TARGET)
    await service.ingest(
        ["GOOD.NS"], target_trading_date=TARGET
    )  # second run must not duplicate rows

    stock = await MarketRepository(db_session).get_stock_by_symbol("GOOD.NS")
    count = await db_session.scalar(
        select(func.count())
        .select_from(DailyPrice)
        .where(DailyPrice.stock_id == stock.id)
    )
    assert count == 60


def test_compute_indicator_points_skips_warmup() -> None:
    bars = _make_bars(60)
    points = compute_indicator_points(bars)
    assert points, "expected some indicator rows"
    # Every emitted row has at least one defined indicator.
    for p in points:
        assert any(v is not None for k, v in p.items() if k != "date")
    # The latest row should have all long-window indicators defined.
    last = points[-1]
    for key in ("rsi_14", "ema_20", "ema_50", "macd", "bb_upper", "atr_14"):
        assert last[key] is not None


# ----- yfinance client behavior (retry + validation) -----------------------
def test_yfinance_retry_succeeds_after_transient_failures() -> None:
    from app.shared.clients.yfinance_client import YFinanceClient

    client = YFinanceClient(max_attempts=3, base_delay=0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    assert client._retry("thing", "SYM", flaky) == "ok"
    assert calls["n"] == 3


def test_yfinance_retry_raises_after_exhaustion() -> None:
    from app.shared.clients.yfinance_client import YFinanceClient

    client = YFinanceClient(max_attempts=2, base_delay=0)

    def always_fail():
        raise RuntimeError("down")

    with pytest.raises(MarketDataError):
        client._retry("thing", "SYM", always_fail)


def test_yfinance_classifies_missing_symbol_without_retry(monkeypatch) -> None:
    from yfinance.exceptions import YFTzMissingError

    from app.shared.clients import yfinance_client as mod
    from app.shared.clients.market_data import MarketDataUnavailableError

    calls = 0

    class FakeTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            nonlocal calls
            calls += 1
            raise YFTzMissingError("STALE.NS")

    monkeypatch.setattr(mod.yf, "Ticker", FakeTicker)

    with pytest.raises(MarketDataUnavailableError):
        mod.YFinanceClient(max_attempts=3, base_delay=0).fetch_daily_prices("STALE.NS")
    assert calls == 1


def test_yfinance_drops_nan_and_invalid_bars(monkeypatch) -> None:
    import pandas as pd

    from app.shared.clients import yfinance_client as mod

    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame(
        {
            "Open": [10.0, 11.0, float("nan"), 12.0],
            "High": [11.0, 12.0, 13.0, 5.0],  # last row: High < Low → invalid
            "Low": [9.0, 10.0, 12.0, 9.0],
            "Close": [10.5, 11.5, float("nan"), 12.5],  # row 3: NaN close → dropped
            "Volume": [100, 200, 300, 400],
        },
        index=idx,
    )

    class FakeTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **_kwargs):
            return frame

    monkeypatch.setattr(mod.yf, "Ticker", FakeTicker)

    client = mod.YFinanceClient()
    bars = client.fetch_daily_prices("SYM")
    # Only the first two rows are valid.
    assert [b.date.isoformat() for b in bars] == ["2024-01-01", "2024-01-02"]


def test_yfinance_uses_explicit_exclusive_window_and_repair_options(monkeypatch) -> None:
    import pandas as pd

    from app.shared.clients import yfinance_client as mod

    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
    frame = pd.DataFrame(
        {
            "Open": [10.0] * 4,
            "High": [11.0] * 4,
            "Low": [9.0] * 4,
            "Close": [10.0, 11.0, 12.0, 13.0],
            "Volume": [100] * 4,
        },
        index=idx,
    )
    options: dict[str, object] = {}

    class FakeTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **kwargs):
            options.update(kwargs)
            return frame

    monkeypatch.setattr(mod.yf, "Ticker", FakeTicker)
    client = mod.YFinanceClient(timeout_seconds=9)
    bars = client.fetch_daily_prices(
        "SYM", start_date=date(2024, 1, 2), end_date=date(2024, 1, 4)
    )

    assert [bar.date for bar in bars] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert options == {
        "interval": "1d",
        "auto_adjust": True,
        "actions": False,
        "repair": False,
        "raise_errors": True,
        "timeout": 9,
        "start": "2024-01-02",
        "end": "2024-01-04",
    }


def test_yfinance_rejects_an_empty_or_reversed_window() -> None:
    from app.shared.clients.yfinance_client import YFinanceClient

    with pytest.raises(ValueError, match="exclusive end_date"):
        YFinanceClient().fetch_daily_prices(
            "SYM", start_date=date(2024, 1, 2), end_date=date(2024, 1, 2)
        )


def test_yfinance_falls_back_when_provider_repair_is_incompatible(
    monkeypatch, caplog
) -> None:
    import pandas as pd

    from app.shared.clients import yfinance_client as mod

    frame = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.5],
            "Volume": [100],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    repair_values: list[bool] = []

    class FakeTicker:
        def __init__(self, *_args, **_kwargs):
            pass

        def history(self, **kwargs):
            repair_values.append(kwargs["repair"])
            if kwargs["repair"]:
                raise ValueError("provider internal secret detail")
            return frame

    monkeypatch.setattr(mod.yf, "Ticker", FakeTicker)
    bars = mod.YFinanceClient(max_attempts=1, provider_repair=True).fetch_daily_prices(
        "SYM", start_date=date(2024, 1, 2), end_date=date(2024, 1, 3)
    )

    assert [bar.date for bar in bars] == [date(2024, 1, 2)]
    assert repair_values == [True, False]
    assert "secret detail" not in caplog.text
