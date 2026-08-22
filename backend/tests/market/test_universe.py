"""Configured-universe validation and ticker-lifecycle regressions."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.market.universe import (
    SymbolHealthStatus,
    SymbolHistoryError,
    check_configured_universe,
    validate_symbol_history,
)
from app.shared.clients.market_data import (
    MarketDataError,
    MarketDataUnavailableError,
    PriceBar,
)

TARGET = date(2026, 8, 21)


def _bars(count: int = 60, *, latest: date = TARGET) -> list[PriceBar]:
    first = latest - timedelta(days=count - 1)
    return [
        PriceBar(
            date=first + timedelta(days=index),
            open=100.0 + index,
            high=102.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=1_000 + index,
        )
        for index in range(count)
    ]


@pytest.mark.parametrize(
    ("bars", "status"),
    [
        ([], SymbolHealthStatus.EMPTY_HISTORY),
        (_bars(49), SymbolHealthStatus.INSUFFICIENT_HISTORY),
        (
            _bars(60, latest=TARGET - timedelta(days=8)),
            SymbolHealthStatus.STALE_HISTORY,
        ),
    ],
)
def test_validate_symbol_history_rejects_unhealthy_history(
    bars: list[PriceBar], status: SymbolHealthStatus
) -> None:
    with pytest.raises(SymbolHistoryError) as raised:
        validate_symbol_history(
            "BAD.NS", bars, target_date=TARGET, minimum_bars=50
        )
    assert raised.value.status == status


def test_validate_symbol_history_rejects_corrupt_ohlcv() -> None:
    bars = _bars()
    bars[-1] = PriceBar(TARGET, 100, 99, 98, 101, 1_000)

    with pytest.raises(SymbolHistoryError) as raised:
        validate_symbol_history(
            "BAD.NS", bars, target_date=TARGET, minimum_bars=50
        )
    assert raised.value.status == SymbolHealthStatus.INVALID_OHLCV


class _HealthClient:
    def fetch_daily_prices(self, symbol, *, start_date=None, end_date=None):
        if symbol == "MISSING.NS":
            raise MarketDataUnavailableError("missing")
        if symbol == "OUTAGE.NS":
            raise MarketDataError("temporary")
        if symbol == "SHORT.NS":
            return _bars(10)
        return _bars()

    def fetch_fundamentals(self, symbol):  # pragma: no cover - not used here
        raise AssertionError(symbol)


@pytest.mark.asyncio
async def test_configured_universe_health_classifies_failure_types() -> None:
    results = await check_configured_universe(
        _HealthClient(),
        target_date=TARGET,
        equity_symbols=("GOOD.NS", "MISSING.NS", "OUTAGE.NS", "SHORT.NS"),
        macro_symbols=("MACRO",),
    )

    by_symbol = {result.symbol: result for result in results}
    assert by_symbol["GOOD.NS"].status == SymbolHealthStatus.HEALTHY
    assert by_symbol["MISSING.NS"].status == SymbolHealthStatus.SYMBOL_UNAVAILABLE
    assert by_symbol["OUTAGE.NS"].status == SymbolHealthStatus.PROVIDER_FAILURE
    assert by_symbol["SHORT.NS"].status == SymbolHealthStatus.INSUFFICIENT_HISTORY
    assert by_symbol["SHORT.NS"].bar_count == 10
    assert by_symbol["MACRO"].status == SymbolHealthStatus.HEALTHY
