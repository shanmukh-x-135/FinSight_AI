# Expanded NIFTY50 Bootstrap (Phase 10D)

`app.market.expanded_bootstrap` is the operator entry point for the initial or
repair bootstrap of the database-approved NIFTY50 universe, prices, indicators,
macro histories, versioned historical sessions, and FAISS cache. It composes
the existing sync, ingestion, and history services; it does not introduce a
second ingestion implementation.

The workflow is resumable and upsert-only:

```text
schema preflight
  → official NIFTY50 sync + validate all 50
  → require exactly 50 active and zero validation failures
  → ingest 50 approved equities + 4 macro proxies
  → require zero symbol failures and exactly 54 requested symbols
  → reconstruct market_regime_v1 sessions
  → commit PostgreSQL index identity
  → publish reconstructable FAISS cache
  → report before/after counts and timing
```

It never deletes users, portfolios, reports, market prices, or indicators.
Per-symbol market commits make a provider interruption safely resumable; the
history corpus is not rebuilt unless every requested symbol succeeded.

## Local or staging procedure

Use an environment whose `DATABASE_URL` is known to be non-production:

```bash
cd backend
./.venv/bin/alembic upgrade head

# Read-only: verifies revision 0015 and prints starting counts.
./.venv/bin/python -m app.market.expanded_bootstrap \
  --target-date YYYY-MM-DD

# Writes only after the preflight has been reviewed.
./.venv/bin/python -m app.market.expanded_bootstrap \
  --execute --target-date YYYY-MM-DD
```

The command exits `0` for a completed preflight/bootstrap and `2` for a blocked
safety condition. A failed universe or ingestion run prints the exact cause;
fix the provider/data issue and rerun the same command. Upserts and incremental
windows prevent duplicate rows.

Normal EOD news ingestion remains separate. `market_regime_v1` intentionally
does not use historical sentiment because a complete comparable backfill does
not exist.

## Production procedure

Production execution is intentionally not automatic. First deploy the exact
Phase 10D commit, back up PostgreSQL according to the hosting provider, and run
the command without `--execute`. Confirm all of the following:

1. `environment` is `production` and `database_revision` is
   `0015_market_regime_history`.
2. The database host/name identifies the intended production database.
3. Provider validation can tolerate a roughly one-to-two-minute run and the
   configured market-data limits.
4. No EOD pipeline or other universe sync is running.
5. The before counts and maintenance window are recorded.

Only then run:

```bash
APP_ENV=production ./.venv/bin/python -m app.market.expanded_bootstrap \
  --execute \
  --target-date YYYY-MM-DD \
  --confirm-production RUN_PRODUCTION_PHASE_10D_BOOTSTRAP
```

Both `--execute` and the exact confirmation token are required. Stop and rerun
after any blocked result; do not bypass a validation failure with a partial
symbol list. After completion, retain the JSON output and verify:

- 50 active constituents and 50 equities with price history;
- four macro proxies with price history;
- zero ingestion failures;
- a nonzero `market_regime_v1` session count and dimension 25; and
- `GET /api/v1/history/similar?k=5` returns version, coverage/membership flags,
  deterministic factor explanations, and real outcomes.

To test ephemeral-disk recovery, move—not delete—the active
`DATA_DIR/faiss/generations/<corpus-hash>` directory to a backup location and
issue the query again. PostgreSQL should reconstruct it. Restore the backup only
if the query fails, then investigate logs before another rebuild.

## Observability

Bootstrap JSON and structured logs include universe counts/fallback status,
symbol success/failure and ingestion modes, bars fetched, candidate/accepted/
rejected session counts and rejection reasons, feature version/dimension,
normalization method, build duration, approximate index bytes, and full
before/after database counts.

The isolated live migration test also verified the upgrade path on populated
data: downgrade 0015→0014 followed by upgrade to head preserved stocks, prices,
indicators, and user tables; it retired only incompatible history index state.
The next guarded run used incremental windows and restored the v1 corpus.
