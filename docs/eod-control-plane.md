# EOD Control Plane (P10.1)

P10.1 adds durable orchestration around the existing market → news → history
pipeline. It does not redesign the domain jobs themselves. PostgreSQL remains the
source of truth for execution state, while APScheduler temporarily remains a thin
caller until P10.2.

## Execution contract

Every invocation identifies a `pipeline_name` and an explicit
`target_trading_date`. The database enforces one logical `pipeline_runs` row for
that pair. The current APScheduler caller supplies the market-local calendar date
when it invokes the control plane; exchange-holiday and provider-readiness checks
are intentionally deferred to P10.3.

The logical run has a stable UUID correlation ID and an attempt counter. Retrying
a failed or partial execution resumes that row and increments the attempt counter;
it does not create a second logical run.

## State model

Run states are `pending`, `running`, `partial`, `completed`, and `failed`.

- `partial` means at least one upstream step completed before a later step failed.
- `failed` means the execution failed before any step completed.
- Both `partial` and `failed` are retryable by a later invocation.

Step states are `pending`, `running`, `completed`, `failed`, and `skipped`. Each
step stores its own attempt count, timestamps, heartbeat, numeric counters, and a
bounded sanitized error summary. Completed and intentionally skipped steps are
terminal checkpoints and are not executed again when a run resumes.

## Locking and transactions

A stable signed 64-bit key derived from `(pipeline_name, target_trading_date)`
identifies a non-blocking PostgreSQL session advisory lock. The lock is held on a
dedicated connection for the whole orchestration attempt. A competing worker
returns without running any step. SQLite uses a process-local lock only for tests
and local development; production exclusion depends on PostgreSQL.

Control-plane transitions use short, independently committed sessions. Each
domain step also receives its own session and retains its existing commit
behavior. Therefore the pipeline is never wrapped in one large transaction:
market data committed before a news failure remains committed, and the market
checkpoint remains `completed`.

## Resume, retry, and recovery

Steps execute in dependency order. The first failure stops the attempt, so
downstream steps stay pending. A retry skips completed upstream steps, retries the
failed step, then continues downstream only after it succeeds.

The active run and step heartbeat before execution and periodically while a step
is running. On a later invocation, a `running` row older than
`PIPELINE_STALE_AFTER_SECONDS` is recovered: running steps become failed with a
sanitized recovery summary, the logical run becomes failed or partial, and the
same invocation resumes it. A recent heartbeat is not stolen.

Unexpected exceptions persist only their class in a generic bounded summary.
Tracebacks, exception messages, provider payloads, symbols returned in failure
lists, credentials, and secrets are not written to control-plane error fields.

## Configuration

- `PIPELINE_HEARTBEAT_INTERVAL_SECONDS` (default `30`)
- `PIPELINE_STALE_AFTER_SECONDS` (default `900`)

## Deliberate later-phase boundaries

P10.2 replaces in-process APScheduler startup with an external EOD runner. P10.3
adds the real Indian-market trading calendar and provider-readiness checks. This
phase also does not add incremental ingestion, stronger write idempotency/news
fingerprints, report dedupe, PostgreSQL-backed FAISS reconstruction, Gemini
generation metadata, deployment resources, or provider accounts.

There is necessarily a small crash window between a domain service committing
its data and the control plane committing the step checkpoint. A retry in that
window may call the domain service again; closing all write-level duplicate gaps
is P10.4.
