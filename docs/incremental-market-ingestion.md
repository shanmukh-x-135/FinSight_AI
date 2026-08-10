# Incremental Market Ingestion (P10.5)

P10.5 replaces the fixed one-year download on every run with explicit,
per-symbol provider windows. The durable EOD target date now reaches the market
step and is the inclusive upper trading date for every fetch. yfinance receives
the following day as its exclusive `end`, matching the provider API exactly.

## Window planner

`daily_prices` supplies the latest persisted date and `stocks` stores
`last_full_price_sync_at` (migration `0011_incremental_ingestion`). The planner
selects one of three modes:

| Mode | Condition | Start date |
|------|-----------|------------|
| `bootstrap` | No stock or no stored prices | Target minus `MARKET_BOOTSTRAP_LOOKBACK_DAYS` |
| `reconciliation` | Legacy/null watermark or full refresh is due | Same configured full window |
| `incremental` | Recent successful full synchronization | Earlier of latest stored/target minus `MARKET_INCREMENTAL_OVERLAP_DAYS` |

Defaults are 370 calendar days for bootstrap, seven days of overlap, and a
30-day full-window reconciliation cadence. The overlap repairs late/corrected
recent bars. Periodic reconciliation repairs older changes to Yahoo's adjusted
history after corporate actions without paying the full-window cost every day.
Existing installations deliberately have a null watermark after migration, so
their first P10.5 run reconciles before switching to incremental mode.

Backdated retries are bounded by their explicit target even if the database
already contains newer rows. Provider rows outside `[start, end)` and duplicate
dates are discarded defensively. An empty bounded result fails only that symbol,
rolls its transaction back, and does not advance the full-sync watermark. A
backdated reconciliation also cannot advance that watermark past newer stored
prices; the next current-date run must still perform its due reconciliation.

## Deterministic indicators and fundamentals

Incremental provider bars alone cannot warm EMA-50, MACD, Bollinger, RSI, or ATR.
After atomically upserting the bounded prices, ingestion reads canonical stored
history, recomputes the deterministic series, and writes only points affected by
the requested window. Thus the newest values equal a full-history computation
while network and database writes stay bounded.

Equity fundamentals refresh during bootstrap/reconciliation, not every daily
increment. Non-null fields merge into the existing row; a degraded empty
provider response cannot erase previously known market cap or ratios. Macro
proxies use the same price planner and watermark but never create fundamentals
or indicators.

## Provider behavior

The provider-neutral `MarketDataClient` accepts optional `start_date` and
exclusive `end_date`. The yfinance adapter uses explicit `start`/`end`, daily
intervals, adjusted OHLC, an SDK timeout, and raised provider errors so
retry/backoff actually runs. Provider repair is opt-in through
`MARKET_PROVIDER_REPAIR_ENABLED=false`: the pinned yfinance/pandas stack can
raise a mutability `ValueError` in that path. When explicitly enabled, the
adapter logs only the exception class and retries the same bounded request with
repair disabled. Periodic database reconciliation is the safe default
correction mechanism. The P10.3 readiness probe now requests only the exact
target session instead of a one-year index history.

## Observability and verification

Manual responses, structured logs, and durable market-step counters include
accepted price bars plus bootstrap/reconciliation/incremental symbol counts.
Exception messages and provider payloads are not logged.

Tests prove exact inclusive/exclusive windows, bootstrap and legacy migration
behavior, periodic reconciliation, overlap correction, future-row rejection,
empty-window rollback, backdated targets, metadata preservation, canonical
indicator equality, macro behavior, target propagation, and current yfinance
options. PostgreSQL migration and concurrency verification supplements the fast
SQLite suite.

Live verification against yfinance and PostgreSQL fetched 248 validated `^NSEI`
bars for a bootstrap window, then only six bars for an immediate incremental
rerun of the same target. Both runs succeeded, the target remained bounded, and
the temporary rows were removed afterward.
