"""Deterministic execution, no-look-ahead, and metric golden tests."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.strategy.engine import (
    BacktestEngine,
    BenchmarkBar,
    EquityPoint,
    SignalBar,
    compute_metrics,
    evaluate_rule,
)
from app.strategy.schemas import (
    ExecutionConfig,
    RuleCondition,
    RuleGroup,
    StrategyDefinition,
)

D1 = date(2026, 1, 5)


def _bar(
    offset: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    ema50: float = 90,
    rsi: float = 50,
) -> SignalBar:
    return SignalBar(
        stock_id=1,
        symbol="AAA.NS",
        sector="Technology",
        date=D1 + timedelta(days=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1000,
        ema_50=ema50,
        rsi=rsi,
    )


def _definition(**execution: object) -> StrategyDefinition:
    return StrategyDefinition(
        entry=RuleGroup(
            operator="AND",
            rules=[RuleCondition(field="price_vs_ema50", operator="above")],
        ),
        exit=RuleGroup(
            operator="OR",
            rules=[RuleCondition(field="rsi", operator="gt", value=70)],
        ),
        execution=ExecutionConfig(
            initial_capital=100_000,
            max_positions=1,
            transaction_cost_bps=0,
            slippage_bps=0,
            **execution,
        ),
    )


def test_nested_rule_dsl_is_explicit_and_missing_values_fail_closed() -> None:
    rule = RuleGroup(
        operator="AND",
        rules=[
            RuleCondition(field="rsi", operator="between", value=45, upper_value=65),
            RuleGroup(
                operator="NOT",
                rules=[
                    RuleCondition(field="macd_histogram", operator="negative")
                ],
            ),
        ],
    )
    bar = _bar(0, open_=100, high=102, low=99, close=101, rsi=55)

    assert evaluate_rule(rule, bar) is False  # MACD is unavailable, NOT false.
    assert evaluate_rule(
        rule,
        SignalBar(**{**bar.__dict__, "macd_histogram": 0.2}),
    ) is True


@pytest.mark.parametrize(
    "payload",
    [
        {"field": "rsi", "operator": "between", "value": 60},
        {"field": "price_vs_ema20", "operator": "gt", "value": 20},
        {"field": "market_regime", "operator": "is", "value": "forecast"},
    ],
)
def test_invalid_rule_shapes_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RuleCondition.model_validate(payload)


def test_close_signal_executes_next_session_and_replay_is_identical() -> None:
    bars = [
        _bar(0, open_=50, high=210, low=40, close=200, ema50=100, rsi=50),
        _bar(1, open_=100, high=106, low=99, close=105, rsi=80),
        _bar(2, open_=110, high=112, low=109, close=111, rsi=50),
    ]
    benchmark = [
        BenchmarkBar(D1 + timedelta(days=index), 100 + index)
        for index in range(3)
    ]

    first = BacktestEngine().run(_definition(), bars, benchmark)
    second = BacktestEngine().run(_definition(), list(reversed(bars)), benchmark)

    assert first.result_hash == second.result_hash
    assert first.equity_curve == second.equity_curve
    assert first.trades == second.trades
    assert first.trades[0].entry_signal_date == D1
    assert first.trades[0].entry_date == D1 + timedelta(days=1)
    assert first.trades[0].entry_price == pytest.approx(100)
    assert first.trades[0].exit_signal_date == D1 + timedelta(days=1)
    assert first.trades[0].exit_date == D1 + timedelta(days=2)
    assert first.trades[0].exit_price == pytest.approx(110)
    assert first.metrics.total_return_percent == pytest.approx(10)
    assert first.metrics.benchmark_return_percent == pytest.approx(2)
    assert first.metrics.excess_return_percent == pytest.approx(8)


def test_ambiguous_intraday_stop_and_take_uses_conservative_stop() -> None:
    bars = [
        _bar(0, open_=100, high=102, low=99, close=101),
        _bar(1, open_=100, high=110, low=90, close=104),
    ]

    result = BacktestEngine().run(
        _definition(stop_loss_percent=5, take_profit_percent=5), bars, []
    )

    assert result.trades[0].entry_date == D1 + timedelta(days=1)
    assert result.trades[0].exit_date == D1 + timedelta(days=1)
    assert result.trades[0].exit_reason == "stop_loss"
    assert result.trades[0].exit_price == pytest.approx(95)
    assert result.metrics.total_return_percent == pytest.approx(-5)


def test_metrics_match_independent_control_fixture() -> None:
    curve = [
        EquityPoint(D1, 100.0, 100.0, 0.0),
        EquityPoint(D1 + timedelta(days=1), 110.0, 102.0, 0.0),
        EquityPoint(D1 + timedelta(days=2), 99.0, 101.0, -10.0),
    ]

    metrics = compute_metrics(curve, [], 100.0)

    assert metrics.total_return_percent == pytest.approx(-1)
    assert metrics.benchmark_return_percent == pytest.approx(1)
    assert metrics.excess_return_percent == pytest.approx(-2)
    assert metrics.max_drawdown_percent == pytest.approx(10)
    assert metrics.sharpe_ratio == pytest.approx(0)
    assert metrics.sortino_ratio == pytest.approx(0)
    assert metrics.cagr_percent is None
    assert metrics.total_trades == 0
