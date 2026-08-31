# Operations and Recovery

FinSight's EOD pipeline is a durable, database-backed control plane. The
canonical sequence is market ingestion, news ingestion, then historical-corpus
rebuild. Run/step state, attempts, counters, correlation IDs, heartbeats and
sanitized failures survive process restarts. See [EOD control
plane](eod-control-plane.md) for state transitions and
[trading-calendar readiness](trading-calendar-readiness.md) for session rules.

## Selecting the default session

An explicit `--target-trading-date` is authoritative. Without one, the runner
walks backward over up to ten market-local dates, skips non-sessions using the
NSE calendar, and checks provider readiness until it finds the newest session
with an available bar. This handles after-midnight delayed jobs, weekends, and
exchange holidays without processing an unready session. A completed logical
run exits successfully before another provider check; no ready session exits
incomplete without creating misleading state.

## Operator surface

Administrators use `/operations`, backed by
`GET /api/v1/admin/jobs/eod/status`. It shows overall health, target date,
attempts, timestamps, correlation ID, step states and counters, sanitized error
summaries, rerun guidance, and market/news/universe/historical freshness. A
specific trading date can be inspected. Non-admin users cannot see the route in
navigation or access the endpoint.

The status API derives `health` and `operator_explanation` from persisted state;
it never exposes raw exceptions or provider secrets. Normal reruns resume
failed or stale work and preserve completed-step idempotency. Use the dedicated
news-only operation when refreshing news after an already-completed EOD run.

## Recovery checklist

1. Inspect `/operations` and the correlation ID before rerunning.
2. Confirm universe initialization and provider readiness.
3. Rerun the same logical target; do not edit control-plane rows manually.
4. If news alone is stale after a completed run, use the news-only runner.
5. Rebuild historical artifacts from PostgreSQL if the local FAISS generation
   is lost; database state remains authoritative.

Tests cover midnight rollover, weekends/holidays, explicit dates, completion
no-ops, readiness failure, stale-run recovery, safe failures, counters,
freshness, admin authorization, and responsive operations UI.
