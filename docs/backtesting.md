# Strategy Backtesting and Robustness

FinSight evaluates explicit, versioned end-of-day strategies. It is a research
replay, not a price predictor or execution system. Definitions are validated
JSON rule trees; they are never evaluated with `eval()` or translated into
user-supplied SQL.

## Definition and versioning

Rules support `AND`, `OR`, and unary `NOT` over price/EMA, RSI, MACD, prior
volume, sector momentum, breadth/regime, and point-in-time news sentiment.
Execution settings include capital, position limits, costs, slippage, optional
stop/take levels, maximum holding sessions, and a benchmark. Every edit creates
an immutable `strategy_versions` row, and each backtest persists its complete
version snapshot and canonical SHA-256 result hash.

## Point-in-time and execution rules

- Volume ratios and momentum use only preceding observations.
- Market and sector context uses the completed signal close.
- News published by 15:30 Asia/Kolkata is available at that session's close;
  later or non-session articles first become available at the next priced session.
- `current_universe` explicitly discloses possible survivorship bias.
- `historical_membership` fails closed if effective-dated coverage is incomplete.
- A close signal fills at the next eligible stock-session open, with adverse
  slippage and configured costs. It never fills on its signal bar.
- If stop and take levels both occur in one daily bar, the stop wins
  conservatively; gaps fill at the observed open.

Results include equity, benchmark and drawdown curves; signal/execution dates;
returns, Sharpe, Sortino, drawdown, win/loss, expectancy, turnover and cost
metrics; plus a complete trade audit.

## Robustness analysis

`POST /api/v1/backtests/{id}/robustness` reconstructs the exact replay and first
verifies its hash. Changed source data returns `409 backtest_replay_drift`
instead of mixing inconsistent evidence. The persisted `strategy_robustness_v1`
diagnostic includes:

- chronological 70% training / 30% out-of-sample comparison;
- outcomes by breadth, momentum, volatility, macro stress, sector, and
  input-only confidence bucket;
- ±10% numeric-parameter sensitivity;
- 0.5x, baseline, and 2x cost/slippage sensitivity; and
- every signal's close, next-session execution, confidence inputs, context and
  realized outcome.

The 0–100 robustness score is a disclosed sum: out-of-sample benchmark excess
(25), profitable parameter variants (25), breadth-regime consistency (20),
doubled-cost resilience (15), and drawdown control (15). It is diagnostic, not
an optimization target or forecast.

## API and UI

Authenticated, user-scoped endpoints cover strategy create/list/get/version/
archive, strategy backtest create/list, backtest detail, and robustness. The
`/strategies` workspace provides the rule builder, immutable versions, replay
history, responsive Plotly curves, robustness evidence, and accessible metric
and trade tables.

Tests cover recursive validation, fail-closed missing data, execution timing,
determinism, conservative fills, metrics, ownership, immutable versions,
membership coverage, point-in-time news, replay drift, sensitivity, score
arithmetic, persistence, and UI serialization/auditability.
