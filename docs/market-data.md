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

The client (`app/shared/clients/yfinance_client.py`):
- **retries** transient failures (`market_fetch_max_attempts`, linear backoff);
- **validates** — drops bars with NaN / non-finite / non-positive OHLC, or
  `high < low`. Yahoo returns a NaN close for the in-progress session, so the
incomplete latest bar is discarded rather than stored as corrupt data.

Upcoming India macro events come from the optional **Trading Economics**
country/date calendar API through an async HTTPX adapter. Set
`TRADING_ECONOMICS_API_KEY` to enable it. Provider timeouts, HTTP errors, or
malformed payloads degrade to an explicit `unavailable` status; an absent key
returns `not_configured`. Neither path substitutes static or mocked events.

## Ingestion pipeline

`fetch → validate → store prices → compute indicators → store` per equity
(`app/market/service.py::MarketIngestionService`). Each symbol is **isolated**:
one bad symbol logs and is skipped (its transaction rolled back), never aborting
the batch. yfinance is blocking, so calls run off the event loop via
`asyncio.to_thread`; every price/fundamentals call is bounded by
`MARKET_FETCH_TIMEOUT_SECONDS` even where the provider SDK has no consistent
timeout parameter.
Macro proxies follow the same fetch/validation/deadline path but store only
prices because equity indicators and fundamentals do not apply to them.

Read-side composition uses `MarketRepository.get_market_snapshots`: stock
metadata, the latest two prices, and the latest indicator are assembled in at
most three queries regardless of universe size. Portfolio, watchlist, dashboard,
sector, and intelligence candidate paths share this batch primitive.

### Trigger

- **Scheduled** (normal path): APScheduler cron job, weekdays at
  `MARKET_INGESTION_HOUR:MINUTE` in `MARKET_TIMEZONE` (default 18:30 IST, after
  NSE close/settlement). Registered in `app/scheduler/scheduler.py`. The full
  market→news→history pipeline holds a non-blocking PostgreSQL advisory lock, so
  only one application worker runs it at a time.
- **Manual** (administrator only): `POST /api/v1/admin/jobs/market-ingestion/run`
  (auth-protected), optional body `{"symbols": ["RELIANCE.NS", ...]}`. Runs
  synchronously and returns `{requested, succeeded, failed}`.

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

Computed for the full stored history (`compute_indicator_points`), warm-up rows
skipped. Verified end-to-end: an independent RSI-14 recomputation on 248 real
RELIANCE bars matched the stored value to 10 decimals.

## Data model (migration `0003_market`)

- **stocks** — `symbol (unique), name, sector (indexed), industry, exchange, is_active`;
  inactive rows identify cross-asset macro proxies.
- **daily_prices** — `stock_id, date, open/high/low/close, volume`; unique + index on `(stock_id, date)` (queried by date range constantly).
- **indicators** — `stock_id, date`, one column per indicator; unique on `(stock_id, date)`.
- **fundamentals** — 1:1 with stock: `market_cap, pe_ratio, eps, dividend_yield, week52_high/low`.

Upserts load a stock's existing rows once and update/insert in memory (portable
across Postgres/SQLite, no dialect-specific `ON CONFLICT`) — fine for a modest
universe run once per day.

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
  persistence, partial-failure isolation, idempotency; yfinance retry
  (success-after-transient, exhaustion) and NaN/invalid bar dropping.
- **API** — seeded reads (gainers/losers/breadth/technical summary/sector/detail/
  indicators/economic events, 404s) and the administrator-gated trigger.
- **Economic calendar** — HTTPX mock transport verifies authenticated date-range
  requests, parsing, malformed-row isolation, ordering, and graceful provider
  failure/unconfigured behavior.
- **Scheduler** — start/stop + job registration, disabled-flag, job body.

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
- Fundamentals are best-effort (fields may be missing); a fundamentals failure
  does not sink the symbol's price/indicator ingestion.
- Economic events require a Trading Economics subscription/API key. The UI
  reports missing/unavailable provider state rather than showing invented data.
