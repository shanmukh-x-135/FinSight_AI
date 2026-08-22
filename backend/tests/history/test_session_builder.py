"""Membership-aware session reconstruction and past-only metric tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.history.feature_engineering import MembershipMode
from app.history.service import HistoryService
from app.history.session_builder import (
    EquityIndicatorRow,
    EquityPriceRow,
    MembershipPeriod,
    MembershipResolver,
    RegimeSessionBuilder,
    UniverseStock,
)
from app.market.constants import MACRO_PROXIES


def _dates(count: int = 30) -> list[date]:
    start = date(2024, 1, 1)
    return [start + timedelta(days=index) for index in range(count)]


def _inputs():
    dates = _dates()
    stocks = [
        UniverseStock(1, "Technology"),
        UniverseStock(2, "Financial Services"),
        UniverseStock(3, "Technology"),
    ]
    prices: list[EquityPriceRow] = []
    indicators: list[EquityIndicatorRow] = []
    for stock in stocks:
        for index, session_date in enumerate(dates):
            close = 100 + stock.stock_id * 10 + index
            prices.append(
                EquityPriceRow(stock.stock_id, session_date, close, 1000 + index * 10)
            )
            indicators.append(
                EquityIndicatorRow(
                    stock.stock_id,
                    session_date,
                    55 + stock.stock_id,
                    close * 0.99,
                    close * 0.98,
                    close * 0.02,
                )
            )
    macro_prices: list[tuple[str, date, float]] = []
    for symbol_index, symbol in enumerate(MACRO_PROXIES):
        for index, session_date in enumerate(dates):
            macro_prices.append(
                (symbol, session_date, 70 + symbol_index * 20 + index * 0.1)
            )
    return dates, stocks, prices, indicators, macro_prices


def test_membership_resolver_distinguishes_unknown_and_effective_history() -> None:
    resolver = MembershipResolver(
        {1, 2, 3},
        [
            MembershipPeriod(1, date(2024, 1, 10), None),
            MembershipPeriod(2, date(2024, 1, 10), date(2024, 1, 20)),
            MembershipPeriod(3, date(2024, 1, 20), None),
        ],
    )

    assert resolver.for_date(date(2024, 1, 5)) == (
        {1, 2, 3},
        MembershipMode.AVAILABLE_DATA_PROXY,
    )
    assert resolver.for_date(date(2024, 1, 15)) == (
        {1, 2},
        MembershipMode.EFFECTIVE,
    )
    assert resolver.for_date(date(2024, 1, 20)) == (
        {1, 3},
        MembershipMode.EFFECTIVE,
    )


def test_builder_records_unknown_history_mode_and_warmup_rejections() -> None:
    dates, stocks, prices, indicators, macro_prices = _inputs()
    result = RegimeSessionBuilder().build(
        stocks=stocks,
        memberships=[],
        prices=prices,
        indicators=indicators,
        macro_prices=macro_prices,
    )

    assert result.candidate_sessions == 30
    assert len(result.sessions) == 10
    assert result.rejected_sessions == 20
    assert result.sessions[0].date == dates[20]
    assert all(
        item.quality.membership_mode == MembershipMode.AVAILABLE_DATA_PROXY
        for item in result.sessions
    )
    assert all(
        "historical_membership_unknown" in item.quality.quality_flags
        for item in result.sessions
    )


def test_builder_switches_to_effective_membership_on_known_date() -> None:
    dates, stocks, prices, indicators, macro_prices = _inputs()
    memberships = [MembershipPeriod(stock.stock_id, dates[25], None) for stock in stocks]

    result = RegimeSessionBuilder().build(
        stocks=stocks,
        memberships=memberships,
        prices=prices,
        indicators=indicators,
        macro_prices=macro_prices,
    )

    by_date = {item.date: item for item in result.sessions}
    assert (
        by_date[dates[24]].quality.membership_mode == MembershipMode.AVAILABLE_DATA_PROXY
    )
    assert by_date[dates[25]].quality.membership_mode == MembershipMode.EFFECTIVE
    assert by_date[dates[25]].quality.expected_constituent_count == 3


def test_builder_is_deterministic_under_input_reordering() -> None:
    _dates_value, stocks, prices, indicators, macro_prices = _inputs()
    builder = RegimeSessionBuilder()
    first = builder.build(
        stocks=stocks,
        memberships=[],
        prices=prices,
        indicators=indicators,
        macro_prices=macro_prices,
    )
    second = builder.build(
        stocks=list(reversed(stocks)),
        memberships=[],
        prices=list(reversed(prices)),
        indicators=list(reversed(indicators)),
        macro_prices=list(reversed(macro_prices)),
    )
    assert [item.quality.features for item in first.sessions] == [
        item.quality.features for item in second.sessions
    ]


def test_future_market_data_cannot_change_an_earlier_feature_vector() -> None:
    dates, stocks, prices, indicators, macro_prices = _inputs()
    builder = RegimeSessionBuilder()
    baseline = builder.build(
        stocks=stocks,
        memberships=[],
        prices=prices,
        indicators=indicators,
        macro_prices=macro_prices,
    )
    changed_future = [
        EquityPriceRow(row.stock_id, row.date, row.close * 4, row.volume * 20)
        if row.date == dates[-1]
        else row
        for row in prices
    ]
    changed = builder.build(
        stocks=stocks,
        memberships=[],
        prices=changed_future,
        indicators=indicators,
        macro_prices=macro_prices,
    )

    baseline_by_date = {item.date: item.quality.features for item in baseline.sessions}
    changed_by_date = {item.date: item.quality.features for item in changed.sessions}
    assert baseline_by_date[dates[-2]] == changed_by_date[dates[-2]]


def test_forward_outcomes_use_only_subsequent_sessions() -> None:
    _dates_value, stocks, prices, indicators, macro_prices = _inputs()
    sessions = list(
        RegimeSessionBuilder()
        .build(
            stocks=stocks,
            memberships=[],
            prices=prices,
            indicators=indicators,
            macro_prices=macro_prices,
        )
        .sessions
    )

    outcome = HistoryService._forward_outcome(sessions, 0)
    expected_next = sessions[1].quality.features
    assert expected_next is not None
    assert outcome[0] == expected_next["equal_weight_return"]
    assert outcome[1] == expected_next["advancing_share"]
    expected_wealth = 1.0
    for item in sessions[1:6]:
        assert item.quality.features is not None
        expected_wealth *= 1 + item.quality.features["equal_weight_return"]
    assert outcome[2] == pytest.approx(expected_wealth - 1)
    assert HistoryService._forward_outcome(sessions, len(sessions) - 1) == (
        None,
        None,
        None,
        None,
        None,
    )
