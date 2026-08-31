"""Pure, deterministic, close-signal/next-session backtesting engine."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date

from app.strategy.schemas import RuleCondition, RuleGroup, StrategyDefinition


@dataclass(frozen=True)
class SignalBar:
    stock_id: int
    symbol: str
    sector: str | None
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    ema_20: float | None = None
    ema_50: float | None = None
    rsi: float | None = None
    macd_histogram: float | None = None
    volume_ratio: float | None = None
    sector_momentum_20d: float | None = None
    market_breadth: float | None = None
    market_regime: str | None = None
    news_sentiment: float | None = None


@dataclass(frozen=True)
class BenchmarkBar:
    date: date
    close: float


@dataclass(frozen=True)
class EquityPoint:
    date: date
    equity: float
    benchmark_equity: float | None
    drawdown_percent: float


@dataclass(frozen=True)
class TradeResult:
    stock_id: int
    symbol: str
    entry_signal_date: date
    entry_date: date
    entry_price: float
    exit_signal_date: date | None
    exit_date: date
    exit_price: float
    quantity: int
    gross_pnl: float
    net_pnl: float
    return_percent: float
    holding_sessions: int
    exit_reason: str
    transaction_cost: float
    entry_notional: float
    exit_notional: float


@dataclass(frozen=True)
class BacktestMetrics:
    total_return_percent: float
    benchmark_return_percent: float | None
    excess_return_percent: float | None
    cagr_percent: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown_percent: float
    win_rate_percent: float | None
    profit_factor: float | None
    average_winner_percent: float | None
    average_loser_percent: float | None
    expectancy_percent: float | None
    total_trades: int
    average_holding_sessions: float | None
    turnover_percent: float
    estimated_transaction_costs: float


@dataclass(frozen=True)
class BacktestResult:
    metrics: BacktestMetrics
    equity_curve: tuple[EquityPoint, ...]
    trades: tuple[TradeResult, ...]
    result_hash: str


@dataclass
class _Position:
    stock_id: int
    symbol: str
    entry_signal_date: date
    entry_date: date
    entry_price: float
    quantity: int
    entry_fee: float
    entry_notional: float
    holding_sessions: int = 0


def evaluate_rule(rule: RuleCondition | RuleGroup, bar: SignalBar) -> bool:
    """Evaluate the validated DSL explicitly; arbitrary code is impossible."""
    return _evaluate_rule(rule, bar) is True


def _evaluate_rule(rule: RuleCondition | RuleGroup, bar: SignalBar) -> bool | None:
    if isinstance(rule, RuleGroup):
        values = [_evaluate_rule(child, bar) for child in rule.rules]
        if rule.operator == "AND":
            return False if False in values else None if None in values else True
        if rule.operator == "OR":
            return True if True in values else None if None in values else False
        return None if values[0] is None else not values[0]

    if rule.field == "price_vs_ema20":
        return _compare_optional(bar.close, bar.ema_20, rule.operator)
    if rule.field == "price_vs_ema50":
        return _compare_optional(bar.close, bar.ema_50, rule.operator)
    if rule.field == "market_regime":
        if bar.market_regime is None:
            return None
        return (
            bar.market_regime == rule.value
            if rule.operator == "is"
            else bar.market_regime != rule.value
        )
    value = {
        "rsi": bar.rsi,
        "macd_histogram": bar.macd_histogram,
        "volume_ratio": bar.volume_ratio,
        "sector_momentum_20d": bar.sector_momentum_20d,
        "market_breadth": bar.market_breadth,
        "news_sentiment": bar.news_sentiment,
    }[rule.field]
    if value is None:
        return None
    if rule.operator == "positive":
        return value > 0
    if rule.operator == "negative":
        return value < 0
    threshold = float(rule.value)  # validated by RuleCondition
    if rule.operator == "gt":
        return value > threshold
    if rule.operator == "gte":
        return value >= threshold
    if rule.operator == "lt":
        return value < threshold
    if rule.operator == "lte":
        return value <= threshold
    if rule.operator == "between":
        assert rule.upper_value is not None
        return threshold <= value <= rule.upper_value
    return False


def _compare_optional(left: float, right: float | None, operator: str) -> bool | None:
    if right is None:
        return None
    return left > right if operator == "above" else left < right


class BacktestEngine:
    """Replay a membership-filtered multi-stock data set deterministically."""

    def run(
        self,
        definition: StrategyDefinition,
        bars: list[SignalBar],
        benchmark: list[BenchmarkBar],
    ) -> BacktestResult:
        if not bars:
            raise ValueError("Backtest requires at least one market bar")
        self._validate_bars(bars)
        ordered = sorted(bars, key=lambda item: (item.date, item.symbol))
        dates = sorted({bar.date for bar in ordered})
        bars_by_date: dict[date, dict[str, SignalBar]] = {}
        for bar in ordered:
            bars_by_date.setdefault(bar.date, {})[bar.symbol] = bar

        cfg = definition.execution
        cash = cfg.initial_capital
        slot_budget = cfg.initial_capital / cfg.max_positions
        cost_rate = cfg.transaction_cost_bps / 10_000
        slip_rate = cfg.slippage_bps / 10_000
        positions: dict[str, _Position] = {}
        pending_entries: dict[str, date] = {}
        pending_exits: dict[str, tuple[date, str]] = {}
        last_bar: dict[str, SignalBar] = {}
        trades: list[TradeResult] = []
        raw_equity: list[tuple[date, float]] = []

        for session_date in dates:
            today = bars_by_date[session_date]
            for symbol in sorted(today):
                last_bar[symbol] = today[symbol]

            for symbol in sorted(set(pending_exits) & set(today)):
                position = positions.get(symbol)
                if position is None:
                    pending_exits.pop(symbol, None)
                    continue
                signal_date, reason = pending_exits.pop(symbol)
                cash += self._close_position(
                    position,
                    today[symbol].open,
                    session_date,
                    signal_date,
                    reason,
                    slip_rate,
                    cost_rate,
                    trades,
                )
                del positions[symbol]

            available_slots = cfg.max_positions - len(positions)
            for symbol in sorted(set(pending_entries) & set(today)):
                if available_slots <= 0:
                    break
                signal_date = pending_entries.pop(symbol)
                if symbol in positions or session_date <= signal_date:
                    continue
                fill = today[symbol].open * (1 + slip_rate)
                budget = min(slot_budget, cash)
                quantity = math.floor(budget / (fill * (1 + cost_rate)))
                if quantity <= 0:
                    continue
                notional = quantity * fill
                fee = notional * cost_rate
                cash -= notional + fee
                positions[symbol] = _Position(
                    stock_id=today[symbol].stock_id,
                    symbol=symbol,
                    entry_signal_date=signal_date,
                    entry_date=session_date,
                    entry_price=fill,
                    quantity=quantity,
                    entry_fee=fee,
                    entry_notional=notional,
                )
                available_slots -= 1

            for symbol in sorted(set(positions) & set(today)):
                position = positions[symbol]
                risk = self._risk_exit(position, today[symbol], definition)
                if risk is None:
                    continue
                raw_fill, reason = risk
                cash += self._close_position(
                    position,
                    raw_fill,
                    session_date,
                    None,
                    reason,
                    slip_rate,
                    cost_rate,
                    trades,
                )
                del positions[symbol]
                pending_exits.pop(symbol, None)

            for symbol in sorted(set(positions) & set(today)):
                position = positions[symbol]
                position.holding_sessions += 1
                if evaluate_rule(definition.exit, today[symbol]):
                    pending_exits.setdefault(symbol, (session_date, "rule"))
                elif (
                    cfg.max_holding_sessions is not None
                    and position.holding_sessions >= cfg.max_holding_sessions
                ):
                    pending_exits.setdefault(
                        symbol, (session_date, "maximum_holding_period")
                    )

            for symbol in sorted(today):
                if symbol in positions or symbol in pending_entries:
                    continue
                if evaluate_rule(definition.entry, today[symbol]):
                    pending_entries[symbol] = session_date

            marked = cash + sum(
                position.quantity * last_bar[symbol].close
                for symbol, position in positions.items()
            )
            raw_equity.append((session_date, marked))

        final_date = dates[-1]
        for symbol in sorted(positions):
            position = positions[symbol]
            bar = last_bar[symbol]
            cash += self._close_position(
                position,
                bar.close,
                bar.date,
                None,
                "end_of_test",
                slip_rate,
                cost_rate,
                trades,
            )
        raw_equity[-1] = (final_date, cash)

        equity_curve = _build_equity_curve(raw_equity, benchmark, cfg.initial_capital)
        metrics = compute_metrics(
            equity_curve,
            trades,
            cfg.initial_capital,
        )
        result_hash = _result_hash(definition, equity_curve, trades, metrics)
        return BacktestResult(metrics, tuple(equity_curve), tuple(trades), result_hash)

    @staticmethod
    def _validate_bars(bars: list[SignalBar]) -> None:
        seen: set[tuple[str, date]] = set()
        for bar in bars:
            key = (bar.symbol, bar.date)
            if key in seen:
                raise ValueError(f"Duplicate bar for {bar.symbol} on {bar.date}")
            seen.add(key)
            if min(bar.open, bar.high, bar.low, bar.close) <= 0:
                raise ValueError("OHLC values must be positive")
            if bar.high < max(bar.open, bar.close, bar.low):
                raise ValueError("Bar high is inconsistent")
            if bar.low > min(bar.open, bar.close, bar.high):
                raise ValueError("Bar low is inconsistent")

    @staticmethod
    def _risk_exit(
        position: _Position,
        bar: SignalBar,
        definition: StrategyDefinition,
    ) -> tuple[float, str] | None:
        cfg = definition.execution
        stop = (
            position.entry_price * (1 - cfg.stop_loss_percent / 100)
            if cfg.stop_loss_percent is not None
            else None
        )
        take = (
            position.entry_price * (1 + cfg.take_profit_percent / 100)
            if cfg.take_profit_percent is not None
            else None
        )
        if stop is not None and bar.open <= stop:
            return bar.open, "stop_loss"
        if take is not None and bar.open >= take:
            return bar.open, "take_profit"
        # If both thresholds occur inside one daily bar, choose the adverse
        # stop first because intraday ordering is unknowable from OHLC alone.
        if stop is not None and bar.low <= stop:
            return stop, "stop_loss"
        if take is not None and bar.high >= take:
            return take, "take_profit"
        return None

    @staticmethod
    def _close_position(
        position: _Position,
        raw_fill: float,
        exit_date: date,
        exit_signal_date: date | None,
        reason: str,
        slip_rate: float,
        cost_rate: float,
        trades: list[TradeResult],
    ) -> float:
        fill = raw_fill * (1 - slip_rate)
        exit_notional = position.quantity * fill
        exit_fee = exit_notional * cost_rate
        gross_pnl = exit_notional - position.entry_notional
        net_pnl = gross_pnl - position.entry_fee - exit_fee
        invested = position.entry_notional + position.entry_fee
        trades.append(
            TradeResult(
                stock_id=position.stock_id,
                symbol=position.symbol,
                entry_signal_date=position.entry_signal_date,
                entry_date=position.entry_date,
                entry_price=position.entry_price,
                exit_signal_date=exit_signal_date,
                exit_date=exit_date,
                exit_price=fill,
                quantity=position.quantity,
                gross_pnl=gross_pnl,
                net_pnl=net_pnl,
                return_percent=net_pnl / invested * 100 if invested else 0.0,
                holding_sessions=position.holding_sessions,
                exit_reason=reason,
                transaction_cost=position.entry_fee + exit_fee,
                entry_notional=position.entry_notional,
                exit_notional=exit_notional,
            )
        )
        return exit_notional - exit_fee


def _build_equity_curve(
    raw_equity: list[tuple[date, float]],
    benchmark: list[BenchmarkBar],
    initial_capital: float,
) -> list[EquityPoint]:
    benchmark_by_date = {row.date: row.close for row in benchmark if row.close > 0}
    benchmark_start = next(
        (benchmark_by_date[day] for day, _ in raw_equity if day in benchmark_by_date),
        None,
    )
    peak = initial_capital
    points = []
    latest_benchmark: float | None = None
    for session_date, equity in raw_equity:
        latest_benchmark = benchmark_by_date.get(session_date, latest_benchmark)
        peak = max(peak, equity)
        points.append(
            EquityPoint(
                date=session_date,
                equity=equity,
                benchmark_equity=(
                    initial_capital * latest_benchmark / benchmark_start
                    if latest_benchmark is not None and benchmark_start is not None
                    else None
                ),
                drawdown_percent=(equity / peak - 1) * 100 if peak else 0.0,
            )
        )
    return points


def compute_metrics(
    equity_curve: list[EquityPoint],
    trades: list[TradeResult],
    initial_capital: float,
) -> BacktestMetrics:
    final_equity = equity_curve[-1].equity if equity_curve else initial_capital
    total_return = (final_equity / initial_capital - 1) * 100
    benchmark_values = [
        point.benchmark_equity
        for point in equity_curve
        if point.benchmark_equity is not None
    ]
    benchmark_return = (
        (benchmark_values[-1] / benchmark_values[0] - 1) * 100
        if len(benchmark_values) >= 2 and benchmark_values[0]
        else None
    )
    days = (equity_curve[-1].date - equity_curve[0].date).days if equity_curve else 0
    cagr = (
        ((final_equity / initial_capital) ** (365.25 / days) - 1) * 100
        if days >= 30 and final_equity > 0
        else None
    )
    daily_returns = [
        equity_curve[index].equity / equity_curve[index - 1].equity - 1
        for index in range(1, len(equity_curve))
        if equity_curve[index - 1].equity > 0
    ]
    mean_return = statistics.fmean(daily_returns) if daily_returns else None
    volatility = statistics.stdev(daily_returns) if len(daily_returns) >= 2 else None
    sharpe = (
        mean_return / volatility * math.sqrt(252)
        if mean_return is not None and volatility not in (None, 0)
        else None
    )
    downside = (
        math.sqrt(statistics.fmean(min(value, 0.0) ** 2 for value in daily_returns))
        if daily_returns
        else None
    )
    sortino = (
        mean_return / downside * math.sqrt(252)
        if mean_return is not None and downside not in (None, 0)
        else None
    )
    winners = [trade for trade in trades if trade.net_pnl > 0]
    losers = [trade for trade in trades if trade.net_pnl < 0]
    returns = [trade.return_percent for trade in trades]
    average_equity = (
        statistics.fmean(point.equity for point in equity_curve)
        if equity_curve
        else initial_capital
    )
    turnover_notional = sum(
        trade.entry_notional + trade.exit_notional for trade in trades
    )
    return BacktestMetrics(
        total_return_percent=total_return,
        benchmark_return_percent=benchmark_return,
        excess_return_percent=(
            total_return - benchmark_return if benchmark_return is not None else None
        ),
        cagr_percent=cagr,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown_percent=max(
            (-point.drawdown_percent for point in equity_curve), default=0.0
        ),
        win_rate_percent=len(winners) / len(trades) * 100 if trades else None,
        profit_factor=(
            sum(trade.net_pnl for trade in winners)
            / abs(sum(trade.net_pnl for trade in losers))
            if losers
            else None
        ),
        average_winner_percent=(
            statistics.fmean(trade.return_percent for trade in winners)
            if winners
            else None
        ),
        average_loser_percent=(
            statistics.fmean(trade.return_percent for trade in losers) if losers else None
        ),
        expectancy_percent=statistics.fmean(returns) if returns else None,
        total_trades=len(trades),
        average_holding_sessions=(
            statistics.fmean(trade.holding_sessions for trade in trades)
            if trades
            else None
        ),
        turnover_percent=(
            turnover_notional / average_equity * 100 if average_equity else 0.0
        ),
        estimated_transaction_costs=sum(trade.transaction_cost for trade in trades),
    )


def _result_hash(
    definition: StrategyDefinition,
    equity_curve: list[EquityPoint],
    trades: list[TradeResult],
    metrics: BacktestMetrics,
) -> str:
    def rounded(value):
        if isinstance(value, float):
            return round(value, 10)
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {key: rounded(item) for key, item in sorted(value.items())}
        if isinstance(value, (list, tuple)):
            return [rounded(item) for item in value]
        return value

    payload = {
        "definition": definition.model_dump(mode="json"),
        "equity_curve": [asdict(point) for point in equity_curve],
        "trades": [asdict(trade) for trade in trades],
        "metrics": asdict(metrics),
    }
    encoded = json.dumps(rounded(payload), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
