# Dynamic NIFTY 50 Universe (Phase 10C)

Phase 10C replaces the hardcoded equity list with an effective-dated,
database-backed NIFTY 50 universe. It changes universe management only: it does
not load the expanded production price corpus or rebuild historical similarity.

## Architecture and sources of truth

```text
official NSE Indices CSV
  → NseNifty50Provider
  → defensive CSV normalization (exactly 50 unique rows)
  → YahooNseSymbolResolver
  → yfinance history validation
  → transactional membership update
  → PostgreSQL-approved active universe
  → strict EOD ingestion + separately configured macro proxies
```

- The official machine-readable source is
  `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`.
- The external source determines discovery. A successfully persisted
  `universe_snapshots` row is the last-known-good discovery payload.
- Open `index_memberships` rows (`valid_to IS NULL`) are the operational source
  of truth for approved equities. `stocks.symbol` remains the Yahoo ticker;
  `stocks.exchange_symbol` is the canonical NSE symbol.
- PostgreSQL remains authoritative for market data. The four macro proxies stay
  in static configuration and are not NIFTY constituents.

The provider is behind the `UniverseProvider` protocol. The NSE implementation
requires the expected columns, valid symbols and company names, exactly 50
unique constituents, a non-empty body, and a successful HTTP response. It does
not scrape HTML.

## Synchronization lifecycle

Each run acquires the existing non-blocking job lock using a stable key for
`NIFTY50`, then persists a `universe_sync_runs` audit record.

1. Fetch and validate the official snapshot.
2. If the source is unavailable or malformed, explicitly load the latest
   persisted snapshot. `fallback_used=true` and the provider error remain on the
   run; without a cached snapshot, the run fails.
3. Normalize NSE symbols and resolve Yahoo tickers.
4. Diff canonical symbols against open database memberships.
5. Validate new candidates using the Phase 10A health checks: provider
   availability, non-empty and sufficient daily history, recency, OHLCV sanity,
   and enough bars for the longest indicator.
6. In one membership transaction, refresh unchanged metadata, activate valid
   additions, and close removed memberships. The transaction rolls back as a
   unit on a persistence failure.
7. Persist per-symbol run items and structured counts.

Unchanged approved symbols are not revalidated on every weekly run. Use
`--validate-all` for a full live smoke test. A revalidation failure is reported
but does not automatically evict an already approved constituent due to a
temporary Yahoo outage. A new invalid candidate is stored as a quarantined sync
item and remains inactive; a later healthy run can activate it.

Membership intervals use `[valid_from, valid_to)`. Removal closes membership and
sets the stock inactive only when it has no other open index membership. It
never deletes the stock, OHLCV, indicators, or fundamentals.

## Symbol mapping and Tata Motors

The default Yahoo rule is `<NSE_SYMBOL>.NS`. Explicit overrides take precedence
and are injectable into `YahooNseSymbolResolver`.

The historical `TATAMOTORS` identifier resolves explicitly to canonical `TMPV`
and provider ticker `TMPV.NS`. Sync records a `replacement` row in
`stock_symbol_aliases`, links the retired stock row when present, and deactivates
that old row without moving or rewriting its historical prices. `TMCV` is a
separate listed company and is not an alias.

## Operator procedure and first run

Apply migrations, synchronize membership, inspect the result, and only then run
normal EOD ingestion:

```bash
cd backend
./.venv/bin/alembic upgrade head
./.venv/bin/python -m app.market.universe_sync
./.venv/bin/python -m app.market.universe --target-date YYYY-MM-DD
```

Useful sync modes:

```bash
# Fetch, diff, and validate without changing snapshots or membership
./.venv/bin/python -m app.market.universe_sync --dry-run

# Validate every current candidate (the Phase 10C live smoke path)
./.venv/bin/python -m app.market.universe_sync --dry-run --validate-all
```

The command exits `0` when all required validations pass, `1` when candidates
are quarantined, and `2` when synchronization itself cannot run. JSON output
includes fetched, normalized, added, removed, unchanged, failed, active, and
fallback counts plus every failed exchange/provider symbol and classification.

An empty deployment does not let EOD guess or silently use a Python fallback.
Default ingestion raises `market_universe_not_initialized` until the operator
runs universe sync. This avoids the circular dependency between EOD and initial
membership. Universe sync is intended to run weekly (and before a first
bootstrap), independently of the daily EOD job; Phase 10C adds no always-on
scheduler or infrastructure.

The administrator ingestion endpoint may still accept explicit symbols for
targeted repair. With no explicit list, it reads deterministic, duplicate-free
provider tickers from open NIFTY50 memberships and then appends `INR=X`, `CL=F`,
`GC=F`, and `^TNX`. Once approved, any equity ingestion failure remains visible
in the result and therefore fails the scheduler's market step.

## Data model

Migrations `0013_dynamic_universe` and `0014_freeze_history_universe` add:

- `stocks.exchange_symbol` and `stocks.data_provider`, while preserving
  `stocks.symbol` as the existing provider-ticker key;
- `index_memberships` for effective-dated, historical index membership;
- `universe_snapshots` for checksum-idempotent last-known-good payloads;
- `universe_sync_runs` and `universe_sync_items` for run and quarantine audit;
- `stock_symbol_aliases` for explicit alias/replacement relationships; and
- `stocks.history_eligible`, a frozen compatibility boundary described below.

## Historical-similarity boundary

The 15 historical features are aggregate market measures, not one dimension per
stock. Their dimension therefore remains unchanged. However, rebuilding old
dates from only today's active members would create survivorship bias.

Migration `0014` captures the pre-Phase-10C active equity set in
`history_eligible`. Universe synchronization does not add new candidates to or
remove retired candidates from that frozen reconstruction set. This prevents a
normal EOD history rebuild from silently changing the legacy corpus. Phase 10D
must replace this temporary boundary with effective-date-aware reconstruction,
perform the deliberate 50-stock production bootstrap, and then rebuild the
historical sessions/FAISS corpus.

## Deferred to Phase 10D

- production 50-stock price and indicator bootstrap;
- effective-membership-aware historical session reconstruction;
- historical regime-feature and FAISS corpus redesign/rebuild; and
- richer corporate-action normalization.

## Phase 10C live verification

On 22 August 2026, the complete provider → resolver → validation → sync path was
run against the official NSE CSV and live Yahoo history using an isolated
in-memory database:

- fetched: 50; normalized/resolved: 50; validated: 50; failed: 0;
- initial sync: 50 added, 0 removed, 0 unchanged, 50 active;
- immediate repeat: 0 added, 0 removed, 50 unchanged, 50 active; and
- quarantined symbols/provider anomalies: none.

The yfinance dependency emitted its upstream pandas deprecation warning during
fetches, but returned valid data for every constituent. The production database
was not modified and no price bootstrap or historical/FAISS rebuild was run.
