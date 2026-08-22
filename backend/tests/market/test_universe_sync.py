"""Dynamic universe lifecycle, quarantine, fallback, and locking tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market.models import (
    DailyPrice,
    IndexMembership,
    Stock,
    StockSymbolAlias,
    UniverseSnapshot,
    UniverseSyncItem,
    UniverseSyncRun,
)
from app.market.universe_provider import (
    NIFTY50_INDEX_CODE,
    UniverseConstituent,
    UniverseProviderSnapshot,
    UniverseProviderUnavailableError,
)
from app.market.universe_sync import (
    UniverseSyncError,
    UniverseSyncInProgressError,
    UniverseSyncService,
)
from app.scheduler.locks import pipeline_run_lock, pipeline_run_lock_id
from app.shared.clients.market_data import MarketDataError, PriceBar

TARGET = date(2026, 8, 21)


def _constituent(symbol: str) -> UniverseConstituent:
    return UniverseConstituent(
        index_code=NIFTY50_INDEX_CODE,
        exchange_symbol=symbol,
        company_name=f"{symbol} Limited",
        industry="Test Sector",
        series="EQ",
        isin=f"INE{symbol}",
    )


def _snapshot(*symbols: str) -> UniverseProviderSnapshot:
    return UniverseProviderSnapshot(
        index_code=NIFTY50_INDEX_CODE,
        source="test-provider",
        source_url="https://example.test/universe.csv",
        snapshot_date=TARGET,
        fetched_at=datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
        constituents=tuple(_constituent(symbol) for symbol in symbols),
    )


class _Provider:
    source = "test-provider"

    def __init__(self, snapshots: list[UniverseProviderSnapshot]) -> None:
        self.snapshots = snapshots
        self.calls = 0

    async def get_constituents(self, index_code: str) -> UniverseProviderSnapshot:
        assert index_code == NIFTY50_INDEX_CODE
        snapshot = self.snapshots[min(self.calls, len(self.snapshots) - 1)]
        self.calls += 1
        return snapshot


class _UnavailableProvider:
    source = "test-provider"

    async def get_constituents(self, index_code: str) -> UniverseProviderSnapshot:
        raise UniverseProviderUnavailableError(f"offline: {index_code}")


def _bars() -> list[PriceBar]:
    start = TARGET - timedelta(days=59)
    return [
        PriceBar(
            date=start + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1_000 + index,
        )
        for index in range(60)
    ]


class _MarketClient:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    def fetch_daily_prices(self, symbol: str, **_kwargs: object) -> list[PriceBar]:
        self.calls.append(symbol)
        if symbol in self.failures:
            raise MarketDataError("temporary outage")
        return _bars()

    def fetch_fundamentals(self, symbol: str):  # pragma: no cover - unused
        raise AssertionError(symbol)


@pytest.mark.asyncio
async def test_initial_population_and_repeated_sync_are_idempotent(
    db_session: AsyncSession,
) -> None:
    provider = _Provider([_snapshot("ALPHA", "BETA")])
    market = _MarketClient()
    service = UniverseSyncService(db_session, provider=provider, market_client=market)

    first = await service.sync(target_date=TARGET)
    second = await service.sync(target_date=TARGET)

    assert first.added_count == 2
    assert first.active_count == 2
    assert second.added_count == 0
    assert second.unchanged_count == 2
    assert second.active_count == 2
    assert market.calls == ["ALPHA.NS", "BETA.NS"]
    assert await db_session.scalar(select(func.count()).select_from(Stock)) == 2
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(Stock)
            .where(Stock.history_eligible.is_(True))
        )
        == 0
    )
    assert await db_session.scalar(select(func.count()).select_from(IndexMembership)) == 2
    assert (
        await db_session.scalar(select(func.count()).select_from(UniverseSnapshot)) == 1
    )
    assert await db_session.scalar(select(func.count()).select_from(UniverseSyncRun)) == 2


@pytest.mark.asyncio
async def test_preflight_validates_every_candidate_without_persisting(
    db_session: AsyncSession,
) -> None:
    provider = _Provider([_snapshot("ALPHA", "BETA")])
    market = _MarketClient()
    service = UniverseSyncService(db_session, provider=provider, market_client=market)

    result = await service.preflight(target_date=TARGET)

    assert result.status == "ready"
    assert result.fetched_count == result.normalized_count == 2
    assert result.validated_count == 2
    assert result.failed_validation_count == 0
    assert result.active_count == 2
    assert result.dry_run is True
    assert market.calls == ["ALPHA.NS", "BETA.NS"]
    assert await db_session.scalar(select(func.count()).select_from(Stock)) == 0
    assert await db_session.scalar(select(func.count()).select_from(UniverseSyncRun)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(UniverseSyncItem)) == 0
    )


@pytest.mark.asyncio
async def test_preflight_requires_live_official_source_without_cached_fallback(
    db_session: AsyncSession,
) -> None:
    service = UniverseSyncService(
        db_session,
        provider=_UnavailableProvider(),
        market_client=_MarketClient(),
    )

    with pytest.raises(UniverseSyncError, match="must be available for preflight"):
        await service.preflight(target_date=TARGET)

    assert await db_session.scalar(select(func.count()).select_from(UniverseSyncRun)) == 0


@pytest.mark.asyncio
async def test_new_and_removed_constituents_preserve_membership_and_price_history(
    db_session: AsyncSession,
) -> None:
    provider = _Provider([_snapshot("ALPHA", "BETA"), _snapshot("BETA", "GAMMA")])
    service = UniverseSyncService(
        db_session, provider=provider, market_client=_MarketClient()
    )
    await service.sync(target_date=TARGET)
    alpha = await db_session.scalar(select(Stock).where(Stock.exchange_symbol == "ALPHA"))
    assert alpha is not None
    db_session.add(DailyPrice(stock_id=alpha.id, **_bars()[0].__dict__))
    await db_session.commit()

    result = await service.sync(target_date=TARGET)

    assert result.added_count == 1
    assert result.removed_count == 1
    assert result.unchanged_count == 1
    await db_session.refresh(alpha)
    assert alpha.is_active is False
    membership = await db_session.scalar(
        select(IndexMembership).where(IndexMembership.stock_id == alpha.id)
    )
    assert membership is not None and membership.valid_to == TARGET
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DailyPrice)
            .where(DailyPrice.stock_id == alpha.id)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_failed_candidate_is_quarantined_then_can_activate(
    db_session: AsyncSession,
) -> None:
    provider = _Provider([_snapshot("ALPHA"), _snapshot("ALPHA")])
    market = _MarketClient({"ALPHA.NS"})
    service = UniverseSyncService(db_session, provider=provider, market_client=market)

    failed = await service.sync(target_date=TARGET)
    assert failed.added_count == 0
    assert failed.failed_validation_count == 1
    assert failed.active_count == 0
    item = await db_session.scalar(select(UniverseSyncItem))
    assert item is not None
    assert item.status == "quarantined"
    assert item.validation_status == "provider_failure"

    market.failures.clear()
    recovered = await service.sync(target_date=TARGET)
    assert recovered.added_count == 1
    assert recovered.failed_validation_count == 0
    assert recovered.active_count == 1


@pytest.mark.asyncio
async def test_provider_failure_uses_explicit_last_known_good_fallback(
    db_session: AsyncSession,
) -> None:
    initial = UniverseSyncService(
        db_session,
        provider=_Provider([_snapshot("ALPHA")]),
        market_client=_MarketClient(),
    )
    await initial.sync(target_date=TARGET)

    result = await UniverseSyncService(
        db_session,
        provider=_UnavailableProvider(),
        market_client=_MarketClient(),
    ).sync(target_date=TARGET)

    assert result.fallback_used is True
    assert result.unchanged_count == 1
    run = await db_session.get(UniverseSyncRun, result.run_id)
    assert run is not None and run.fallback_used is True
    assert run.error_summary and "offline" in run.error_summary


@pytest.mark.asyncio
async def test_provider_failure_without_cache_is_recorded(
    db_session: AsyncSession,
) -> None:
    service = UniverseSyncService(
        db_session,
        provider=_UnavailableProvider(),
        market_client=_MarketClient(),
    )
    with pytest.raises(UniverseSyncError, match="no last-known-good"):
        await service.sync(target_date=TARGET)

    run = await db_session.scalar(select(UniverseSyncRun))
    assert run is not None and run.status == "failed"
    assert run.error_summary and "no cached snapshot" in run.error_summary


@pytest.mark.asyncio
async def test_membership_transaction_rolls_back_and_run_records_failure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = UniverseSyncService(
        db_session,
        provider=_Provider([_snapshot("ALPHA", "BETA")]),
        market_client=_MarketClient(),
    )
    original = service.repo.activate
    calls = 0

    async def fail_second(**kwargs: object) -> Stock:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("database write failed")
        return await original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service.repo, "activate", fail_second)
    with pytest.raises(RuntimeError, match="database write failed"):
        await service.sync(target_date=TARGET)

    assert await db_session.scalar(select(func.count()).select_from(Stock)) == 0
    assert await db_session.scalar(select(func.count()).select_from(IndexMembership)) == 0
    run = await db_session.scalar(select(UniverseSyncRun))
    assert run is not None and run.status == "failed"


@pytest.mark.asyncio
async def test_dry_run_does_not_change_snapshot_or_membership(
    db_session: AsyncSession,
) -> None:
    result = await UniverseSyncService(
        db_session,
        provider=_Provider([_snapshot("ALPHA")]),
        market_client=_MarketClient(),
    ).sync(dry_run=True, target_date=TARGET)

    assert result.dry_run is True
    assert result.added_count == 1
    assert result.active_count == 0
    assert await db_session.scalar(select(func.count()).select_from(Stock)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(UniverseSnapshot)) == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(UniverseSyncItem)) == 1
    )


@pytest.mark.asyncio
async def test_tata_replacement_alias_preserves_retired_stock(
    db_session: AsyncSession,
) -> None:
    retired = Stock(
        symbol="TATAMOTORS.NS",
        exchange_symbol="TATAMOTORS",
        exchange="NSE",
        name="Historical Tata Motors",
        history_eligible=True,
    )
    db_session.add(retired)
    await db_session.commit()

    result = await UniverseSyncService(
        db_session,
        provider=_Provider([_snapshot("TATAMOTORS")]),
        market_client=_MarketClient(),
    ).sync(target_date=TARGET)

    assert result.added_count == 1
    replacement = await db_session.scalar(select(Stock).where(Stock.symbol == "TMPV.NS"))
    alias = await db_session.scalar(select(StockSymbolAlias))
    await db_session.refresh(retired)
    assert replacement is not None and replacement.exchange_symbol == "TMPV"
    assert replacement.history_eligible is False
    assert retired.is_active is False
    assert retired.history_eligible is True
    assert alias is not None
    assert alias.stock_id == replacement.id
    assert alias.retired_stock_id == retired.id
    assert alias.alias_type == "replacement"


@pytest.mark.asyncio
async def test_concurrent_sync_is_rejected_by_existing_lock_pattern(
    db_session: AsyncSession,
) -> None:
    lock_id = pipeline_run_lock_id(f"universe-sync:{NIFTY50_INDEX_CODE}", date.min)
    service = UniverseSyncService(
        db_session,
        provider=_Provider([_snapshot("ALPHA")]),
        market_client=_MarketClient(),
    )
    async with pipeline_run_lock(db_session, lock_id) as acquired:
        assert acquired is True
        with pytest.raises(UniverseSyncInProgressError):
            await service.sync(target_date=TARGET)
