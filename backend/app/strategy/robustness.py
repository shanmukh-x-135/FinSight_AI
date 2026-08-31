"""Deterministic Phase 11D validation for completed strategy replays."""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.strategy.engine import (
    BacktestEngine,
    BacktestResult,
    BenchmarkBar,
    SignalBar,
    _evaluate_rule,
)
from app.strategy.schemas import RuleCondition, RuleGroup, StrategyDefinition


@dataclass(frozen=True)
class RegimeContext:
    breadth: str
    momentum: str
    volatility: str
    macro_stress: str


def regime_contexts(
    bars: list[SignalBar], history_features: dict[date, dict[str, float]]
) -> dict[date, RegimeContext]:
    """Classify market_regime_v1 features with the published v1 thresholds."""
    by_date: dict[date, list[SignalBar]] = defaultdict(list)
    for bar in bars:
        by_date[bar.date].append(bar)
    contexts: dict[date, RegimeContext] = {}
    for session_date, session in by_date.items():
        features = history_features.get(session_date)
        breadth = session[0].market_regime or "unavailable"
        if features:
            rsi = features.get("median_rsi")
            momentum_value = features.get("median_momentum_20")
            volatility_value = max(
                features.get("median_atr_pct", 0.0),
                features.get("median_realized_volatility_20", 0.0),
            )
            momentum = (
                "positive"
                if rsi is not None and momentum_value is not None and rsi >= 55 and momentum_value > 0
                else "negative"
                if rsi is not None and momentum_value is not None and rsi <= 45 and momentum_value < 0
                else "neutral"
            )
            volatility = "high" if volatility_value >= 0.025 else "low" if volatility_value <= 0.012 else "normal"
            macro_values = [
                abs(features.get(name, 0.0))
                for name in ("usd_inr_return", "crude_oil_return", "gold_return", "us_10y_yield_return")
            ]
            macro = "high" if max(macro_values, default=0.0) >= 0.03 else "low" if max(macro_values, default=0.0) <= 0.01 else "normal"
        else:
            momentums = [bar.sector_momentum_20d for bar in session if bar.sector_momentum_20d is not None]
            median_momentum = statistics.median(momentums) if momentums else None
            momentum = "positive" if median_momentum is not None and median_momentum > 2 else "negative" if median_momentum is not None and median_momentum < -2 else "neutral" if median_momentum is not None else "unavailable"
            volatility = "unavailable"
            macro = "unavailable"
        contexts[session_date] = RegimeContext(breadth, momentum, volatility, macro)
    return contexts


def _leaf_results(rule: RuleCondition | RuleGroup, bar: SignalBar) -> list[bool | None]:
    if isinstance(rule, RuleCondition):
        return [_evaluate_rule(rule, bar)]
    values: list[bool | None] = []
    for child in rule.rules:
        values.extend(_leaf_results(child, bar))
    return values


def signal_confidence(rule: RuleGroup, bar: SignalBar) -> tuple[float, str]:
    """Input-only rule confirmation share; never uses future returns."""
    values = _leaf_results(rule, bar)
    score = sum(value is True for value in values) / len(values) if values else 0.0
    bucket = "high" if score >= 0.75 else "medium" if score >= 0.5 else "low"
    return score, bucket


def _group_performance(
    outcomes: list[dict[str, Any]], dimension: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for outcome in outcomes:
        grouped[str(outcome[dimension])].append(outcome)
    rows = []
    for label in sorted(grouped):
        items = grouped[label]
        returns = [float(item["return_percent"]) for item in items]
        rows.append(
            {
                "label": label,
                "trades": len(items),
                "average_return_percent": statistics.fmean(returns),
                "win_rate_percent": sum(value > 0 for value in returns)
                / len(returns)
                * 100,
                "net_pnl": sum(float(item["net_pnl"]) for item in items),
            }
        )
    return rows


def _metric_slice(result: BacktestResult) -> dict[str, Any]:
    metric = result.metrics
    return {
        "total_return_percent": metric.total_return_percent,
        "benchmark_return_percent": metric.benchmark_return_percent,
        "excess_return_percent": metric.excess_return_percent,
        "max_drawdown_percent": metric.max_drawdown_percent,
        "sharpe_ratio": metric.sharpe_ratio,
        "total_trades": metric.total_trades,
    }


def _scaled_condition(rule: RuleCondition, scale: float) -> RuleCondition:
    payload = rule.model_dump()
    if isinstance(payload.get("value"), (int, float)):
        payload["value"] = float(payload["value"]) * scale
    if isinstance(payload.get("upper_value"), (int, float)):
        payload["upper_value"] = float(payload["upper_value"]) * scale
    return RuleCondition.model_validate(payload)


def _perturb(rule: RuleCondition | RuleGroup, scale: float) -> RuleCondition | RuleGroup:
    if isinstance(rule, RuleCondition):
        return _scaled_condition(rule, scale)
    return RuleGroup(
        operator=rule.operator,
        rules=[_perturb(child, scale) for child in rule.rules],
    )


def _run(
    definition: StrategyDefinition,
    bars: list[SignalBar],
    benchmark: list[BenchmarkBar],
) -> BacktestResult | None:
    return BacktestEngine().run(definition, bars, benchmark) if bars else None


def _score(
    baseline: BacktestResult,
    test_result: BacktestResult | None,
    perturbations: list[dict[str, Any]],
    costs: list[dict[str, Any]],
    breadth_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    test_excess = test_result.metrics.excess_return_percent if test_result else None
    oos = 25.0 if test_excess is not None and test_excess > 0 else 12.5 if test_result else 0.0
    positive_variants = sum(row["total_return_percent"] > 0 for row in perturbations)
    parameter = 25.0 * positive_variants / len(perturbations) if perturbations else 0.0
    regime_returns = [row["average_return_percent"] for row in breadth_rows if row["trades"]]
    dispersion = statistics.pstdev(regime_returns) if len(regime_returns) >= 2 else 0.0
    regime = max(0.0, 20.0 - min(20.0, dispersion * 4)) if regime_returns else 0.0
    high_cost = next((row for row in costs if row["label"] == "2x costs"), None)
    degradation = max(0.0, baseline.metrics.total_return_percent - high_cost["total_return_percent"]) if high_cost else 0.0
    cost = max(0.0, 15.0 - min(15.0, degradation * 3))
    drawdown = max(0.0, 15.0 - min(15.0, baseline.metrics.max_drawdown_percent * 0.75))
    components = {
        "out_of_sample": round(oos, 2),
        "parameter_stability": round(parameter, 2),
        "regime_independence": round(regime, 2),
        "cost_resilience": round(cost, 2),
        "drawdown_control": round(drawdown, 2),
    }
    return {
        "score": round(sum(components.values()), 2),
        "components": components,
        "explanation": [
            "Out-of-sample rewards positive benchmark excess in the chronological test segment.",
            "Parameter stability measures how many ±10% threshold variants remain profitable.",
            "Regime independence penalizes dispersion in trade returns across breadth regimes.",
            "Cost resilience measures return degradation when modeled costs double.",
            "Drawdown control applies a transparent penalty to maximum drawdown.",
        ],
    }


def analyze_robustness(
    definition: StrategyDefinition,
    bars: list[SignalBar],
    benchmark: list[BenchmarkBar],
    baseline: BacktestResult,
    regimes: dict[date, RegimeContext],
) -> dict[str, Any]:
    """Build reproducible regime, signal, OOS, and sensitivity evidence."""
    bar_by_key = {(bar.symbol, bar.date): bar for bar in bars}
    stock_sector = {bar.symbol: bar.sector or "Unclassified" for bar in bars}
    outcomes: list[dict[str, Any]] = []
    for trade in baseline.trades:
        signal_bar = bar_by_key.get((trade.symbol, trade.entry_signal_date))
        if signal_bar is None:
            continue
        confidence, bucket = signal_confidence(definition.entry, signal_bar)
        context = regimes.get(
            trade.entry_signal_date,
            RegimeContext(
                breadth=signal_bar.market_regime or "unavailable",
                momentum="unavailable",
                volatility="unavailable",
                macro_stress="unavailable",
            ),
        )
        outcomes.append(
            {
                "symbol": trade.symbol,
                "signal_date": trade.entry_signal_date.isoformat(),
                "execution_date": trade.entry_date.isoformat(),
                "confidence": confidence,
                "confidence_bucket": bucket,
                "positive_outcome": trade.net_pnl > 0,
                "return_percent": trade.return_percent,
                "net_pnl": trade.net_pnl,
                "breadth_regime": context.breadth,
                "momentum_regime": context.momentum,
                "volatility_regime": context.volatility,
                "macro_stress": context.macro_stress,
                "sector": stock_sector.get(trade.symbol, "Unclassified"),
            }
        )

    dates = sorted({bar.date for bar in bars})
    split_index = max(1, min(len(dates) - 1, int(len(dates) * 0.7))) if len(dates) > 1 else 0
    split_date = dates[split_index] if dates else None
    train_bars = [bar for bar in bars if split_date is not None and bar.date < split_date]
    test_bars = [bar for bar in bars if split_date is not None and bar.date >= split_date]
    train_benchmark = [row for row in benchmark if split_date is not None and row.date < split_date]
    test_benchmark = [row for row in benchmark if split_date is not None and row.date >= split_date]
    train = _run(definition, train_bars, train_benchmark)
    test = _run(definition, test_bars, test_benchmark)

    perturbations = []
    for label, scale in (("parameters -10%", 0.9), ("baseline", 1.0), ("parameters +10%", 1.1)):
        candidate = definition if scale == 1 else definition.model_copy(
            update={
                "entry": _perturb(definition.entry, scale),
                "exit": _perturb(definition.exit, scale),
                "execution": definition.execution.model_copy(
                    update={
                        "stop_loss_percent": (
                            definition.execution.stop_loss_percent * scale
                            if definition.execution.stop_loss_percent is not None
                            else None
                        ),
                        "take_profit_percent": (
                            definition.execution.take_profit_percent * scale
                            if definition.execution.take_profit_percent is not None
                            else None
                        ),
                        "max_holding_sessions": (
                            max(
                                1,
                                round(
                                    definition.execution.max_holding_sessions * scale
                                ),
                            )
                            if definition.execution.max_holding_sessions is not None
                            else None
                        ),
                    }
                ),
            }
        )
        replay = baseline if scale == 1 else BacktestEngine().run(candidate, bars, benchmark)
        perturbations.append({"label": label, **_metric_slice(replay)})

    cost_sensitivity = []
    for label, scale in (("0.5x costs", 0.5), ("baseline", 1.0), ("2x costs", 2.0)):
        candidate = definition if scale == 1 else definition.model_copy(
            update={"execution": definition.execution.model_copy(update={"transaction_cost_bps": min(500.0, definition.execution.transaction_cost_bps * scale), "slippage_bps": min(500.0, definition.execution.slippage_bps * scale)})}
        )
        replay = baseline if scale == 1 else BacktestEngine().run(candidate, bars, benchmark)
        cost_sensitivity.append({"label": label, "transaction_cost_bps": candidate.execution.transaction_cost_bps, "slippage_bps": candidate.execution.slippage_bps, **_metric_slice(replay)})

    breakdowns = {
        dimension: _group_performance(outcomes, dimension)
        for dimension in ("breadth_regime", "momentum_regime", "volatility_regime", "macro_stress", "sector", "confidence_bucket")
    }
    return {
        "analysis_version": "strategy_robustness_v1",
        "baseline_result_hash": baseline.result_hash,
        "chronological_split": {
            "train_percent": 70,
            "test_percent": 30,
            "split_date": split_date.isoformat() if split_date else None,
            "training": _metric_slice(train) if train else None,
            "test": _metric_slice(test) if test else None,
            "note": "No parameter fitting occurs; this is a chronological evaluation split.",
        },
        "signal_outcomes": outcomes,
        "breakdowns": breakdowns,
        "parameter_sensitivity": perturbations,
        "cost_sensitivity": cost_sensitivity,
        "robustness": _score(baseline, test, perturbations, cost_sensitivity, breakdowns["breadth_regime"]),
    }
