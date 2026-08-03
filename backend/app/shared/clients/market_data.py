"""Provider-agnostic market-data contract.

The rest of the app depends on this interface, not on yfinance directly, so the
provider can be swapped and tests can inject a fake client with no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class PriceBar:
    """One validated daily OHLCV bar."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class FundamentalsData:
    """Company fundamentals. Every field is optional — providers vary."""

    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: int | None = None
    pe_ratio: float | None = None
    eps: float | None = None
    dividend_yield: float | None = None
    week52_high: float | None = None
    week52_low: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    """Everything fetched for one symbol in a single ingestion pass."""

    symbol: str
    bars: list[PriceBar] = field(default_factory=list)
    fundamentals: FundamentalsData = field(default_factory=FundamentalsData)


class MarketDataError(Exception):
    """Raised when a provider fails to return usable data after retries."""


class MarketDataClient(Protocol):
    """Synchronous provider interface (callers run it off the event loop)."""

    def fetch_daily_prices(self, symbol: str) -> list[PriceBar]:
        """Return validated daily bars (oldest→newest); may raise MarketDataError."""
        ...

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        """Return best-effort fundamentals; missing fields are None."""
        ...
