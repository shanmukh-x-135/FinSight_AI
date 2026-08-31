"""Configured-universe health checks shared by ingestion and smoke tests."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from app.market import constants as C
from app.market import indicators as ind
from app.shared.clients.market_data import (
    MarketDataClient,
    MarketDataError,
    MarketDataUnavailableError,
    PriceBar,
)
from config.settings import settings

MINIMUM_EQUITY_HISTORY_BARS = C.EMA_LONG_PERIOD
MINIMUM_MACRO_HISTORY_BARS = C.EMA_LONG_PERIOD
MAX_HISTORY_STALENESS_DAYS = 7


class SymbolHealthStatus(StrEnum):
    HEALTHY = "healthy"
    SYMBOL_UNAVAILABLE = "symbol_unavailable"
    PROVIDER_FAILURE = "provider_failure"
    EMPTY_HISTORY = "empty_history"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INVALID_OHLCV = "invalid_ohlcv"
    STALE_HISTORY = "stale_history"
    INDICATOR_INCOMPATIBLE = "indicator_incompatible"


class SymbolHistoryError(MarketDataError):
    """A deterministic validation failure for returned price history."""

    def __init__(self, symbol: str, status: SymbolHealthStatus) -> None:
        self.symbol = symbol
        self.status = status
        super().__init__(f"{status.value} for {symbol}")


@dataclass(frozen=True)
class SymbolHealthResult:
    symbol: str
    asset_type: str
    status: SymbolHealthStatus
    bar_count: int = 0
    first_date: date | None = None
    latest_date: date | None = None

    @property
    def healthy(self) -> bool:
        return self.status == SymbolHealthStatus.HEALTHY


def validate_symbol_history(
    symbol: str,
    bars: list[PriceBar],
    *,
    target_date: date,
    minimum_bars: int,
    max_staleness_days: int = MAX_HISTORY_STALENESS_DAYS,
) -> None:
    """Reject empty, malformed, too-short, or materially stale history."""
    if not bars:
        raise SymbolHistoryError(symbol, SymbolHealthStatus.EMPTY_HISTORY)

    seen_dates: set[date] = set()
    for bar in bars:
        prices = (bar.open, bar.high, bar.low, bar.close)
        invalid_prices = any(
            not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
            for value in prices
        )
        # Yahoo's rounded FX candles can miss open/close by a few basis points.
        # A 0.1% tolerance preserves those bars while rejecting material errors.
        range_tolerance = 0.0 if invalid_prices else max(prices) * 0.001
        if (
            invalid_prices
            or bar.high < bar.low
            or bar.high + range_tolerance < max(bar.open, bar.close)
            or bar.low - range_tolerance > min(bar.open, bar.close)
            or bar.volume < 0
            or bar.date in seen_dates
        ):
            raise SymbolHistoryError(symbol, SymbolHealthStatus.INVALID_OHLCV)
        seen_dates.add(bar.date)

    if len(bars) < minimum_bars:
        raise SymbolHistoryError(symbol, SymbolHealthStatus.INSUFFICIENT_HISTORY)

    latest_date = max(seen_dates)
    if latest_date < target_date - timedelta(days=max_staleness_days):
        raise SymbolHistoryError(symbol, SymbolHealthStatus.STALE_HISTORY)

    # Incremental ingestion validates a deliberately short overlap window and
    # computes indicators from canonical stored history after upsert. Candidate
    # and full-window checks reach this gate with at least the longest period.
    if len(bars) < C.EMA_LONG_PERIOD:
        return

    ordered = sorted(bars, key=lambda bar: bar.date)
    closes = [bar.close for bar in ordered]
    highs = [bar.high for bar in ordered]
    lows = [bar.low for bar in ordered]
    macd_line, macd_signal, macd_histogram = ind.macd(
        closes, C.MACD_FAST, C.MACD_SLOW, C.MACD_SIGNAL
    )
    bb_upper, bb_middle, bb_lower = ind.bollinger_bands(closes, C.BB_PERIOD, C.BB_NUM_STD)
    latest_indicators = (
        ind.rsi(closes, C.RSI_PERIOD)[-1],
        ind.ema(closes, C.EMA_SHORT_PERIOD)[-1],
        ind.ema(closes, C.EMA_LONG_PERIOD)[-1],
        macd_line[-1],
        macd_signal[-1],
        macd_histogram[-1],
        bb_upper[-1],
        bb_middle[-1],
        bb_lower[-1],
        ind.atr(highs, lows, closes, C.ATR_PERIOD)[-1],
    )
    if any(value is None or not math.isfinite(value) for value in latest_indicators):
        raise SymbolHistoryError(symbol, SymbolHealthStatus.INDICATOR_INCOMPATIBLE)


async def check_configured_universe(
    client: MarketDataClient,
    *,
    target_date: date,
    equity_symbols: tuple[str, ...],
    macro_symbols: tuple[str, ...] | None = None,
    max_concurrency: int = 5,
) -> list[SymbolHealthResult]:
    """Fetch and validate the approved universe without touching the database."""
    if macro_symbols is None:
        macro_symbols = tuple(C.MACRO_PROXIES)
    start_date = target_date - timedelta(days=settings.market_bootstrap_lookback_days)
    end_date = target_date + timedelta(days=1)
    configured = [
        *((symbol, "equity", MINIMUM_EQUITY_HISTORY_BARS) for symbol in equity_symbols),
        *((symbol, "macro", MINIMUM_MACRO_HISTORY_BARS) for symbol in macro_symbols),
    ]
    semaphore = asyncio.Semaphore(max_concurrency)

    async def check_one(
        symbol: str, asset_type: str, minimum_bars: int
    ) -> SymbolHealthResult:
        bars: list[PriceBar] = []
        try:
            async with semaphore:
                bars = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.fetch_daily_prices,
                        symbol,
                        start_date=start_date,
                        end_date=end_date,
                    ),
                    timeout=settings.market_fetch_timeout_seconds,
                )
            validate_symbol_history(
                symbol,
                bars,
                target_date=target_date,
                minimum_bars=minimum_bars,
            )
        except MarketDataUnavailableError:
            status = SymbolHealthStatus.SYMBOL_UNAVAILABLE
            bars = []
        except SymbolHistoryError as exc:
            status = exc.status
        except (MarketDataError, TimeoutError):
            status = SymbolHealthStatus.PROVIDER_FAILURE
            bars = []
        else:
            status = SymbolHealthStatus.HEALTHY
        return SymbolHealthResult(
            symbol=symbol,
            asset_type=asset_type,
            status=status,
            bar_count=len(bars),
            first_date=min((bar.date for bar in bars), default=None),
            latest_date=max((bar.date for bar in bars), default=None),
        )

    return list(
        await asyncio.gather(
            *(
                check_one(symbol, asset_type, minimum_bars)
                for symbol, asset_type, minimum_bars in configured
            )
        )
    )


def _target_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be YYYY-MM-DD") from exc


async def _run_health_check(target_date: date) -> int:
    from app.market.repository import MarketRepository
    from app.shared.clients.yfinance_client import build_default_client
    from app.shared.database import SessionFactory
    from config.settings import settings

    async with SessionFactory() as db:
        approved = await MarketRepository(db).list_approved_equities(
            settings.research_universe
        )
    if not approved:
        print(
            json.dumps(
                {
                    "target_date": target_date.isoformat(),
                    "error": (
                        f"{settings.research_universe} universe is empty; run "
                        "app.market.universe_sync first"
                    ),
                },
                indent=2,
            )
        )
        return 2
    results = await check_configured_universe(
        build_default_client(),
        target_date=target_date,
        equity_symbols=tuple(stock.symbol for stock in approved),
    )
    payload = {
        "target_date": target_date.isoformat(),
        "equities_tested": sum(row.asset_type == "equity" for row in results),
        "macro_symbols_tested": sum(row.asset_type == "macro" for row in results),
        "successful": sum(row.healthy for row in results),
        "failed": sum(not row.healthy for row in results),
        "symbols": [
            {
                "symbol": row.symbol,
                "asset_type": row.asset_type,
                "status": row.status.value,
                "bar_count": row.bar_count,
                "first_date": row.first_date.isoformat() if row.first_date else None,
                "latest_date": row.latest_date.isoformat() if row.latest_date else None,
            }
            for row in results
        ],
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["failed"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the DB-approved market universe through its provider."
    )
    parser.add_argument(
        "--target-date", type=_target_date, default=date.today(), help="YYYY-MM-DD"
    )
    args = parser.parse_args()
    return asyncio.run(_run_health_check(args.target_date))


if __name__ == "__main__":
    raise SystemExit(main())
