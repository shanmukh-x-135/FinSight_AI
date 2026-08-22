"""yfinance-backed market data client.

Wraps yfinance with:
* **retry + backoff** on transient failures,
* **validation** — drops NaN / non-finite / non-positive bars (yfinance returns a
  NaN close for the in-progress session), and bars where ``high < low``,
* isolation — pandas/yfinance types never leak past this module.

yfinance is blocking; callers invoke these methods via ``asyncio.to_thread``.
"""

from __future__ import annotations

import math
import time
from datetime import date
from typing import Any, Callable, TypeVar

import yfinance as yf
from yfinance.exceptions import YFTickerMissingError

from app.shared.clients.market_data import (
    FundamentalsData,
    MarketDataError,
    MarketDataInvalidError,
    MarketDataUnavailableError,
    PriceBar,
)
from config.logging import get_logger
from config.settings import settings

logger = get_logger(__name__)

T = TypeVar("T")


def _finite_positive(*values: Any) -> bool:
    return all(
        isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values
    )


def _clean_float(value: Any) -> float | None:
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def _clean_int(value: Any) -> int | None:
    f = _clean_float(value)
    return int(f) if f is not None else None


class YFinanceClient:
    def __init__(
        self,
        period: str | None = None,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        timeout_seconds: float | None = None,
        provider_repair: bool | None = None,
    ) -> None:
        from app.market.constants import HISTORY_PERIOD

        self.period = period or HISTORY_PERIOD
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.timeout_seconds = timeout_seconds or settings.market_fetch_timeout_seconds
        self.provider_repair = (
            settings.market_provider_repair_enabled
            if provider_repair is None
            else provider_repair
        )

    def _retry(self, what: str, symbol: str, fn: Callable[[], T]) -> T:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn()
            except MarketDataUnavailableError:
                # Missing/renamed tickers are permanent for this provider
                # symbol; retrying the exact request cannot repair them.
                raise
            except Exception as exc:  # noqa: BLE001 — provider raises many types
                last_exc = exc
                logger.warning(
                    "market_data_retry",
                    extra={
                        "what": what,
                        "symbol": symbol,
                        "attempt": attempt,
                        "error": type(exc).__name__,
                    },
                )
                if attempt < self.max_attempts:
                    time.sleep(self.base_delay * attempt)  # linear backoff
        raise MarketDataError(f"{what} failed for {symbol}: {last_exc}") from last_exc

    def fetch_daily_prices(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PriceBar]:
        if start_date is not None and end_date is not None and start_date >= end_date:
            raise ValueError("start_date must be earlier than exclusive end_date")

        def _do() -> list[PriceBar]:
            history_options: dict[str, object] = {
                "interval": "1d",
                "auto_adjust": True,
                "actions": False,
                "repair": self.provider_repair,
                "raise_errors": True,
                "timeout": self.timeout_seconds,
            }
            if start_date is None and end_date is None:
                history_options["period"] = self.period
            else:
                if start_date is not None:
                    history_options["start"] = start_date.isoformat()
                if end_date is not None:
                    history_options["end"] = end_date.isoformat()
            ticker = yf.Ticker(symbol)
            try:
                frame = ticker.history(**history_options)
            except YFTickerMissingError as exc:
                raise MarketDataUnavailableError(
                    f"Symbol unavailable from market-data provider: {symbol}"
                ) from exc
            except ValueError:
                if not self.provider_repair:
                    raise
                # yfinance repair can be incompatible with a newly released
                # pandas/NumPy array mutability change. Preserve the bounded
                # fetch instead of failing the symbol; periodic reconciliation
                # still repairs stored adjusted history at the database layer.
                logger.warning(
                    "market_data_repair_fallback",
                    extra={"symbol": symbol, "error": "ValueError"},
                )
                fallback_options = {**history_options, "repair": False}
                frame = ticker.history(**fallback_options)
            bars: list[PriceBar] = []
            for index, row in frame.iterrows():
                o, h, low, c = row.get("Open"), row.get("High"), row.get("Low"), row.get("Close")
                if not _finite_positive(o, h, low, c) or h < low:
                    continue  # drop incomplete/invalid bar
                bar_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
                if start_date is not None and bar_date < start_date:
                    continue
                if end_date is not None and bar_date >= end_date:
                    continue
                bars.append(
                    PriceBar(
                        date=bar_date,
                        open=float(o),
                        high=float(h),
                        low=float(low),
                        close=float(c),
                        volume=_clean_int(row.get("Volume")) or 0,
                    )
                )
            bars.sort(key=lambda b: b.date)
            return bars

        bars = self._retry("fetch_daily_prices", symbol, _do)
        if not bars:
            raise MarketDataInvalidError(
                f"No valid price bars returned for {symbol}"
            )
        return bars

    def fetch_fundamentals(self, symbol: str) -> FundamentalsData:
        # Fundamentals are best-effort: a failure here must not sink the symbol,
        # so we degrade to empty rather than raise.
        try:
            info: dict[str, Any] = self._retry(
                "fetch_fundamentals", symbol, lambda: dict(yf.Ticker(symbol).info)
            )
        except MarketDataError:
            logger.warning("fundamentals_unavailable", extra={"symbol": symbol})
            return FundamentalsData()

        return FundamentalsData(
            name=info.get("shortName") or info.get("longName"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            market_cap=_clean_int(info.get("marketCap")),
            pe_ratio=_clean_float(info.get("trailingPE")),
            eps=_clean_float(info.get("trailingEps")),
            dividend_yield=_clean_float(info.get("dividendYield")),
            week52_high=_clean_float(info.get("fiftyTwoWeekHigh")),
            week52_low=_clean_float(info.get("fiftyTwoWeekLow")),
        )


def build_default_client() -> YFinanceClient:
    """Factory used by the ingestion service / scheduler."""
    return YFinanceClient(
        max_attempts=settings.market_fetch_max_attempts,
        timeout_seconds=settings.market_fetch_timeout_seconds,
        provider_repair=settings.market_provider_repair_enabled,
    )
