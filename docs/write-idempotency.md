# Write Idempotency and Duplicate Prevention (P10.4)

P10.4 closes the domain-write crash window left by the durable EOD control
plane. If a process commits domain data and exits before its step checkpoint is
committed, a retry can safely execute the same work again. PostgreSQL uniqueness
constraints are the authority; pre-read checks are optimizations only.

## Atomic write contract

The shared `app/shared/upsert.py` selects SQLAlchemy's PostgreSQL or SQLite
`INSERT ... ON CONFLICT` construct. Production and tests therefore exercise the
same repository semantics:

- stocks are atomic by `symbol`;
- daily prices and indicators are atomic by `(stock_id, date)`;
- fundamentals are atomic by `stock_id`;
- historical sessions are atomic by `date`;
- historical embeddings and statistics are atomic by `session_id`;
- article tags and daily sentiment are atomic by their existing composite keys.

Repeated writes update deterministic values in place. Duplicate rows cannot be
created by two workers that both observe an initially absent row.

## News identity

Migration `0010_write_idempotency` adds a required, unique SHA-256 fingerprint
to `news_articles`. The input is the NFKC-normalized, case-folded, punctuation-
collapsed stored title plus its publication date. This catches a story republished
through a different feed URL while allowing a genuinely repeated headline on a
later date. URL uniqueness remains as an independent guard.

The migration backfills existing rows transactionally, merges duplicate tags,
deletes redundant articles, and rebuilds `sentiment_daily` so aggregate counts
cannot remain stale. Ingestion also collapses duplicate keys before scoring, but
the atomic insert decides the winner under concurrency.

## Report retries

`POST /api/v1/reports/generate` accepts an optional `Idempotency-Key` header
(1–200 characters). The production frontend sends a fresh UUID for each user
action and preserves it through the API client's authentication retry. Repeating
the request with the same key returns the original stored report rather than
generating or storing another one.

Keys are SHA-256 hashed with the user id and report type before storage. Raw
caller keys are never persisted, and two users may safely use the same opaque
key. Callers that intentionally omit the header retain the original behavior of
creating a new report on every request.

## Verification

- SQLite integration tests cover repeat ingestion across changed feed URLs,
  date scoping, normalization, aggregate correctness, report retry identity,
  raw-key non-persistence, and user scoping.
- Existing market/history idempotency suites run against atomic upserts.
- A PostgreSQL integration test launches independent concurrent sessions and
  proves one logical stock/date row, article fingerprint, and report key survive.
- Alembic upgrade/downgrade/upgrade verification covers the production schema
  transition and backfill path.

P10.4 changes persistence only. P10.5 builds bounded provider windows on these
atomic writes; see [Incremental Market Ingestion](incremental-market-ingestion.md).
