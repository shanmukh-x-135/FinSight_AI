"""Effective-membership-aware construction of market-regime sessions."""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.history.feature_engineering import (
    MacroDay,
    MembershipMode,
    SessionFeatureResult,
    StockDay,
    compute_session_feature,
)
from app.market.constants import MACRO_FEATURE_SYMBOLS


@dataclass(frozen=True)
class UniverseStock:
    stock_id: int
    sector: str | None


@dataclass(frozen=True)
class MembershipPeriod:
    stock_id: int
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True)
class EquityPriceRow:
    stock_id: int
    date: date
    close: float
    volume: int


@dataclass(frozen=True)
class EquityIndicatorRow:
    stock_id: int
    date: date
    rsi: float | None
    ema20: float | None
    ema50: float | None
    atr: float | None


@dataclass(frozen=True)
class EngineeredSession:
    date: date
    quality: SessionFeatureResult
    candidate_index: int


@dataclass(frozen=True)
class ReconstructionResult:
    sessions: tuple[EngineeredSession, ...]
    candidate_sessions: int
    rejected_sessions: int
    rejection_reasons: dict[str, int]


class MembershipResolver:
    """Use effective intervals where known and label earlier data honestly."""

    def __init__(
        self,
        tracked_stock_ids: set[int],
        memberships: list[MembershipPeriod],
    ) -> None:
        self.tracked_stock_ids = tracked_stock_ids
        self.memberships = memberships
        self.known_from = min(
            (membership.valid_from for membership in memberships), default=None
        )

    def for_date(self, session_date: date) -> tuple[set[int], MembershipMode]:
        if self.known_from is None or session_date < self.known_from:
            return set(self.tracked_stock_ids), MembershipMode.AVAILABLE_DATA_PROXY
        return (
            {
                membership.stock_id
                for membership in self.memberships
                if membership.valid_from <= session_date
                and (membership.valid_to is None or session_date < membership.valid_to)
            },
            MembershipMode.EFFECTIVE,
        )


@dataclass(frozen=True)
class _ComputedPrice:
    return_1d: float | None
    momentum_20: float | None
    realized_volatility_20: float | None
    relative_volume_20: float | None


def _price_metrics(
    rows: list[EquityPriceRow],
) -> dict[tuple[int, date], _ComputedPrice]:
    grouped: dict[int, list[EquityPriceRow]] = {}
    for row in rows:
        grouped.setdefault(row.stock_id, []).append(row)
    computed: dict[tuple[int, date], _ComputedPrice] = {}
    for stock_id, stock_rows in grouped.items():
        ordered = sorted(stock_rows, key=lambda item: item.date)
        closes: list[float] = []
        volumes: list[int] = []
        returns: list[float] = []
        for row in ordered:
            one_day = row.close / closes[-1] - 1.0 if closes and closes[-1] > 0 else None
            if one_day is not None:
                returns.append(one_day)
            momentum = (
                row.close / closes[-20] - 1.0
                if len(closes) >= 20 and closes[-20] > 0
                else None
            )
            recent_returns = returns[-20:]
            realized = (
                statistics.pstdev(recent_returns) if len(recent_returns) == 20 else None
            )
            previous_volumes = volumes[-20:]
            median_volume = (
                statistics.median(previous_volumes) if len(previous_volumes) == 20 else 0
            )
            relative_volume = row.volume / median_volume if median_volume > 0 else None
            computed[(stock_id, row.date)] = _ComputedPrice(
                return_1d=one_day,
                momentum_20=momentum,
                realized_volatility_20=realized,
                relative_volume_20=relative_volume,
            )
            closes.append(row.close)
            volumes.append(row.volume)
    return computed


def _macro_returns(
    rows: list[tuple[str, date, float]],
) -> dict[date, MacroDay]:
    feature_by_symbol = {
        symbol: feature for feature, symbol in MACRO_FEATURE_SYMBOLS.items()
    }
    values: dict[date, dict[str, float]] = {}
    previous: dict[str, float] = {}
    for symbol, session_date, close in sorted(rows, key=lambda row: (row[0], row[1])):
        prior = previous.get(symbol)
        if prior is not None and prior > 0 and close > 0:
            values.setdefault(session_date, {})[feature_by_symbol[symbol]] = (
                close / prior - 1.0
            )
        previous[symbol] = close
    return {
        session_date: MacroDay(**features)
        for session_date, features in values.items()
        if len(features) == len(MACRO_FEATURE_SYMBOLS)
    }


class RegimeSessionBuilder:
    def build(
        self,
        *,
        stocks: list[UniverseStock],
        memberships: list[MembershipPeriod],
        prices: list[EquityPriceRow],
        indicators: list[EquityIndicatorRow],
        macro_prices: list[tuple[str, date, float]],
    ) -> ReconstructionResult:
        stock_by_id = {stock.stock_id: stock for stock in stocks}
        resolver = MembershipResolver(set(stock_by_id), memberships)
        metrics = _price_metrics(prices)
        close_by = {(row.stock_id, row.date): row.close for row in prices}
        indicator_by = {(row.stock_id, row.date): row for row in indicators}
        macro_by_date = _macro_returns(macro_prices)
        dates = sorted({row.date for row in prices})
        accepted: list[EngineeredSession] = []
        rejected: Counter[str] = Counter()

        for candidate_index, session_date in enumerate(dates):
            expected_ids, membership_mode = resolver.for_date(session_date)
            stock_days: list[StockDay] = []
            for stock_id in sorted(expected_ids):
                stock = stock_by_id.get(stock_id)
                price = metrics.get((stock_id, session_date))
                indicator = indicator_by.get((stock_id, session_date))
                close = close_by.get((stock_id, session_date))
                stock_days.append(
                    StockDay(
                        stock_id=stock_id,
                        sector=stock.sector if stock else None,
                        return_1d=price.return_1d if price else None,
                        rsi=indicator.rsi if indicator else None,
                        above_ema20=(
                            close > indicator.ema20
                            if close is not None
                            and indicator is not None
                            and indicator.ema20 is not None
                            else None
                        ),
                        above_ema50=(
                            close > indicator.ema50
                            if close is not None
                            and indicator is not None
                            and indicator.ema50 is not None
                            else None
                        ),
                        momentum_20=price.momentum_20 if price else None,
                        atr_pct=(
                            indicator.atr / close
                            if close is not None
                            and close > 0
                            and indicator is not None
                            and indicator.atr is not None
                            else None
                        ),
                        realized_volatility_20=(
                            price.realized_volatility_20 if price else None
                        ),
                        relative_volume_20=(price.relative_volume_20 if price else None),
                    )
                )
            quality = compute_session_feature(
                stock_days,
                macro=macro_by_date.get(session_date),
                expected_constituent_count=len(expected_ids),
                membership_mode=membership_mode,
            )
            if quality.accepted:
                accepted.append(EngineeredSession(session_date, quality, candidate_index))
            else:
                assert quality.rejection_reason is not None
                rejected[quality.rejection_reason.value] += 1
        return ReconstructionResult(
            sessions=tuple(accepted),
            candidate_sessions=len(dates),
            rejected_sessions=sum(rejected.values()),
            rejection_reasons=dict(sorted(rejected.items())),
        )
