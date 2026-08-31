"""Controlled tests for Phase 11D validation and explainable scoring."""

from __future__ import annotations

from datetime import date, timedelta

from app.strategy.engine import BacktestEngine, BenchmarkBar, SignalBar
from app.strategy.robustness import (
    RegimeContext,
    analyze_robustness,
    regime_contexts,
    signal_confidence,
)
from app.strategy.schemas import (
    ExecutionConfig,
    RuleCondition,
    RuleGroup,
    StrategyDefinition,
)

START = date(2025, 1, 1)


def _definition() -> StrategyDefinition:
    return StrategyDefinition(
        entry=RuleGroup(
            operator="OR",
            rules=[
                RuleCondition(field="price_vs_ema50", operator="above"),
                RuleCondition(field="rsi", operator="gt", value=55),
            ],
        ),
        exit=RuleGroup(
            operator="OR",
            rules=[RuleCondition(field="rsi", operator="gt", value=75)],
        ),
        execution=ExecutionConfig(
            initial_capital=10_000,
            max_positions=1,
            transaction_cost_bps=10,
            slippage_bps=5,
            max_holding_sessions=4,
        ),
    )


def _data() -> tuple[list[SignalBar], list[BenchmarkBar]]:
    bars = []
    benchmark = []
    for index in range(30):
        close = 100 + index * 1.5
        bars.append(
            SignalBar(
                stock_id=1,
                symbol="AAA.NS",
                sector="Technology",
                date=START + timedelta(days=index),
                open=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000,
                ema_50=close - 2,
                rsi=60 if index % 6 else 80,
                market_regime="broad_positive" if index < 15 else "mixed",
            )
        )
        benchmark.append(BenchmarkBar(START + timedelta(days=index), 200 + index))
    return bars, benchmark


def test_signal_confidence_uses_signal_inputs_not_future_outcome() -> None:
    definition = _definition()
    bar = _data()[0][1]

    score, bucket = signal_confidence(definition.entry, bar)

    assert score == 1
    assert bucket == "high"


def test_robustness_analysis_is_deterministic_populated_and_decomposable() -> None:
    definition = _definition()
    bars, benchmark = _data()
    baseline = BacktestEngine().run(definition, bars, benchmark)
    regimes = {
        bar.date: RegimeContext(
            breadth=bar.market_regime or "unavailable",
            momentum="positive",
            volatility="normal",
            macro_stress="low",
        )
        for bar in bars
    }

    first = analyze_robustness(definition, bars, benchmark, baseline, regimes)
    second = analyze_robustness(
        definition, list(reversed(bars)), benchmark, baseline, regimes
    )

    assert first == second
    assert first["analysis_version"] == "strategy_robustness_v1"
    assert first["chronological_split"]["training"] is not None
    assert first["chronological_split"]["test"] is not None
    assert len(first["parameter_sensitivity"]) == 3
    assert len(first["cost_sensitivity"]) == 3
    assert first["signal_outcomes"]
    assert first["breakdowns"]["breadth_regime"]
    assert first["breakdowns"]["sector"]
    assert first["breakdowns"]["confidence_bucket"]
    components = first["robustness"]["components"]
    assert first["robustness"]["score"] == round(sum(components.values()), 2)
    assert 0 <= first["robustness"]["score"] <= 100


def test_market_regime_v1_context_classification_is_explicit() -> None:
    bars, _ = _data()
    features = {
        bars[0].date: {
            "median_rsi": 60,
            "median_momentum_20": 0.05,
            "median_atr_pct": 0.03,
            "median_realized_volatility_20": 0.02,
            "usd_inr_return": 0.005,
            "crude_oil_return": 0.04,
            "gold_return": 0.002,
            "us_10y_yield_return": 0.001,
        }
    }

    context = regime_contexts([bars[0]], features)[bars[0].date]

    assert context.breadth == "broad_positive"
    assert context.momentum == "positive"
    assert context.volatility == "high"
    assert context.macro_stress == "high"
