# Market Data Pipeline (Phase 2)

Deterministic ingestion of daily market data and computation of technical
indicators — the foundation every later intelligence module reads from. No AI
here (design doc's "analytics before AI").

## Data source

**yfinance** (Yahoo Finance), wrapped behind a provider-agnostic interface
(`app/shared/clients/market_data.py`) so it can be swapped. NSE listings use the
`.NS` suffix (e.g. `RELIANCE.NS`). The default universe is a spread of large-cap
NSE names across sectors (`app/market/constants.py`).

The default ingestion also fetches four global macro proxies (USD/INR, crude
oil, gold, and the US 10-year Treasury yield). They reuse `daily_prices` but are
stored with `is_active=false`; consequently they feed historical similarity
without appearing in equity APIs, breadth, sectors, watchlists, or portfolios.

The curated equity universe currently contains 15 approved symbols. Following
the Tata Motors commercial-vehicle demerger, NSE renamed the existing listed
`TATAMOTORS` security to `TMPV` effective 24 October 2025; `TMPV.NS` is therefore
the approved continuity symbol. `TMCV.NS` is the separately listed demerged
commercial-vehicle company and is not treated as an alias. When `TMPV.NS`
ingests successfully, any existing `TATAMOTORS.NS` stock row is deactivated
without renaming or deleting its historical prices.

The client (`app/shared/clients/yfinance_client.py`):
- **retries** transient failures (`market_fetch_max_attempts`, linear backoff);
- uses explicit inclusive `start` / exclusive `end` dates plus SDK and outer
  timeouts; yfinance's currently incompatible repair path is opt-in;
- **validates** — drops bars with NaN / non-finite / non-positive OHLC, or
  `high < low`. Yahoo returns a NaN close for the in-progress session, so the
  incomplete latest bar is discarded rather than stored as corrupt data;
- classifies Yahoo's missing-ticker response separately from retryable provider
  failures, avoiding pointless retries for renamed or delisted symbols.

The ingestion path additionally rejects malformed OHLCV relationships,
duplicate dates, materially stale history, and full-window histories too short
to compute the longest configured equity indicator. Operators can run the same
configured-universe checks without touching PostgreSQL:

```bash
cd backend
./.venv/bin/python -m app.market.universe --target-date YYYY-MM-DD
```

The command prints per-symbol bar counts and classified health status and exits
nonzero if any of the 15 equities or four macro proxies is unhealthy. It is an
explicit EOD/universe preflight tool; no network validation runs at API startup.

Before the external EOD runner enters the durable pipeline, the P10.3 preflight
uses maintained offline NSE session/holiday rules, waits for the configured
post-close buffer, and requires a validated `^NSEI` bar for the exact target
session. Non-trading dates are safe no-ops; premature, stale, timeout, and
provider-unavailable outcomes exit retryably without creating pipeline state.
See [Trading Calendar and Provider Readiness](trading-calendar-readiness.md).

Upcoming India macro events come from the optional **Trading Economics**
country/date calendar API through an async HTTPX adapter. Set
`TRADING_ECONOMICS_API_KEY` to enable it. Provider timeouts, HTTP errors, or
malformed payloads degrade to an explicit `unavailable` status; an absent key
returns `not_configured`. Neither path substitutes static or mocked events.

## Ingestion pipeline

`plan window → fetch → validate → atomic price upsert → canonical indicator
recompute → affected indicator upsert` per equity
(`app/market/service.py::MarketIngestionService`). Each symbol is **isolated**:
one bad symbol logs and is skipped (its transaction rolled back), never aborting
the batch. yfinance is blocking, so calls run off the event loop via
`asyncio.to_thread`; every price/fundamentals call is bounded by
`MARKET_FETCH_TIMEOUT_SECONDS` even where the provider SDK has no consistent
timeout parameter. The P10.5 planner bootstraps 370 calendar days, normally
fetches only a seven-day overlap from the latest stored bar, and performs a
full configured-window reconciliation every 30 days. See
[Incremental Market Ingestion](incremental-market-ingestion.md).
Macro proxies follow the same fetch/validation/deadline path but store only
prices because equity indicators and fundamentals do not apply to them.

Read-side composition uses `MarketRepository.get_market_snapshots`: stock
metadata, the latest two prices, and the latest indicator are assembled in at
most three queries regardless of universe size. Portfolio, watchlist, dashboard,
sector, and intelligence candidate paths share this batch primitive.

### Trigger

- **External runner** (normal path): a one-shot backend command invokes the
  durable EOD control plane independently of the FastAPI web process. The full
  market→news→history execution is date-scoped, resumable, independently
  checkpointed, and protected by a non-blocking PostgreSQL advisory lock. See
  [External EOD Runner](eod-runner.md) and
  [EOD Control Plane](eod-control-plane.md).
- **Manual** (administrator only): `POST /api/v1/admin/jobs/market-ingestion/run`
  (auth-protected), optional body `{"symbols": ["RELIANCE.NS", ...]}`. Runs
  synchronously and returns symbol results plus fetched-bar and window-mode
  counters.

## Indicators

Pure functions in `app/market/indicators.py` (no I/O — unit-tested against
hand-verified reference values, because indicator bugs are silent). Conventions
match standard charting tools:

| Indicator | Params (default) | Method |
|-----------|------------------|--------|
| RSI       | 14               | Wilder's smoothing (RMA) |
| EMA       | 20 and 50        | SMA seed, multiplier `2/(period+1)` |
| MACD      | 12 / 26 / 9      | EMA(fast) − EMA(slow); signal = EMA(MACD); histogram = MACD − signal |
| Bollinger | 20, 2σ           | SMA ± n × **population** std dev |
| ATR       | 14               | Wilder's smoothing of True Range |

Computed from full canonical stored history (`compute_indicator_points`), with
warm-up rows skipped and only the requested-window suffix rewritten. This keeps
incremental EMA/MACD mathematically identical to a full recomputation. Verified
end-to-end: an independent RSI-14 recomputation on 248 real RELIANCE bars matched
the stored value to 10 decimals.

## Data model (migrations `0003_market`, `0011_incremental_ingestion`)

- **stocks** — `symbol (unique), name, sector (indexed), industry, exchange,
  is_active, last_full_price_sync_at`;
  inactive rows identify cross-asset macro proxies.
- **daily_prices** — `stock_id, date, open/high/low/close, volume`; unique + index on `(stock_id, date)` (queried by date range constantly).
- **indicators** — `stock_id, date`, one column per indicator; unique on `(stock_id, date)`.
- **fundamentals** — 1:1 with stock: `market_cap, pe_ratio, eps, dividend_yield, week52_high/low`.

All logical keys use atomic PostgreSQL/SQLite `INSERT ... ON CONFLICT` upserts.
Retries and concurrent manual/EOD writers update the canonical row rather than
raising a uniqueness race or creating a duplicate. See
[Write Idempotency](write-idempotency.md).

## Read endpoints (`/api/v1/market`)

| Endpoint | Returns |
|----------|---------|
| `GET /gainers?limit=` | Top stocks by daily % change |
| `GET /losers?limit=`  | Bottom stocks by daily % change |
| `GET /breadth`        | Advancers / decliners / unchanged + A/D ratio |
| `GET /technical-summary` | Batched latest RSI/EMA/MACD/ATR market aggregates |
| `GET /economic-events?days=` | Upcoming India events with provider status and provenance |
| `GET /sectors` | Per-sector stock count and average daily change |
| `GET /sectors/{sector}` | Stocks in a sector + average % change |
| `GET /stocks/{symbol}` | Latest quote + fundamentals |
| `GET /stocks/{symbol}/indicators?limit=` | Indicator history (oldest→newest) |

Daily % change is computed from the two most recent `daily_prices` rows.

## Testing

`backend/tests/market/`:
- **Indicators** — reference-value goldens (hand-derived) + property checks.
- **Ingestion** — fake client: full-pipeline storage, inactive macro-proxy
  persistence, ticker retirement with history preservation, universe health,
  stale/invalid/insufficient-history classification, partial-failure isolation,
  idempotency, exact incremental/full
  windows, overlap correction, future-row rejection, rollback-safe watermarks,
  periodic reconciliation, and canonical indicators; yfinance retry
  (success-after-transient, exhaustion), window options, and invalid-bar dropping.
- **API** — seeded reads (gainers/losers/breadth/technical summary/sector/detail/
  indicators/economic events, 404s) and the administrator-gated trigger.
- **Economic calendar** — HTTPX mock transport verifies authenticated date-range
  requests, parsing, malformed-row isolation, ordering, and graceful provider
  failure/unconfigured behavior.
- **Runner/control plane** — one-shot process exit behavior, web-process
  isolation, PostgreSQL lock SQL, cross-worker contention, state transitions,
  heartbeat, stale recovery, sanitized failures, successful-step skipping, and
  retry/resume behavior.

~97% coverage across the market/scheduler/clients modules.

## Local development

```bash
# via the running stack (Docker): register a user, then trigger ingestion
TOKEN=... # from /api/v1/auth/login
curl -X POST localhost:8000/api/v1/admin/jobs/market-ingestion/run \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"symbols":["RELIANCE.NS","TCS.NS"]}'
curl localhost:8000/api/v1/market/stocks/RELIANCE.NS
```

## Known limitations

- yfinance/Yahoo is an unofficial source and can rate-limit or change; the client
  retries and isolates failures but ingestion quality depends on the provider.
- Yahoo backfills pre-rename history under `TMPV.NS` and retains the roughly 40%
  14 October 2025 demerger price step. That is a real corporate-action value
  transfer rather than an ordinary market loss. The old `TATAMOTORS.NS` rows are
  preserved separately and inactive; richer corporate-action normalization and
  effective-dated aliases remain Phase 10C/10D work.
- Fundamentals are best-effort (fields may be missing); a fundamentals failure
  does not sink the symbol's price/indicator ingestion.
- Economic events require a Trading Economics subscription/API key. The UI
  reports missing/unavailable provider state rather than showing invented data.
