# External EOD Runner (P10.2)

The EOD pipeline runs as a one-shot backend process, independently of the
FastAPI web server. A deployment scheduler can invoke the same command after the
Indian market closes without keeping an in-process scheduler in every web
worker.

## Command

From `backend/`:

```bash
./.venv/bin/python -m app.scheduler.runner \
  --target-trading-date 2026-08-05
```

`--target-trading-date` accepts an ISO `YYYY-MM-DD` date. If it is omitted, the
runner resolves the current calendar date in `MARKET_TIMEZONE` (default
`Asia/Kolkata`). The P10.3 preflight validates that the target is an NSE session,
the close buffer has elapsed, and yfinance exposes a real target-session bar.
See [Trading Calendar and Provider Readiness](trading-calendar-readiness.md).

The process uses the P10.1 control plane, so duplicate invocations are safe at
the orchestration level and retries resume the same logical run. P10.5 forwards
that target date into every bounded per-symbol market fetch; see
[Incremental Market Ingestion](incremental-market-ingestion.md).

After market and news checkpoints complete, the Phase 10D history checkpoint
reconstructs accepted regime sessions and the exact-L2 FAISS generation from
PostgreSQL. It reports candidate, rejected, and indexed-session counts plus
feature dimension, normalization method, build time, and approximate index
bytes. Local FAISS files remain disposable: a later web query reconstructs a
missing generation from the committed database state. Initial 50-stock setup is
an explicit operator workflow, not an EOD responsibility; see
[Expanded NIFTY50 Bootstrap](expanded-bootstrap.md).

## Exit behavior

| Code | Meaning |
|------|---------|
| `0` | The run is complete, the target is not a trading day, or another worker owns the lock. |
| `1` | Readiness is retryable/incomplete, the run is incomplete, or the runner encountered an exception. |
| `2` | Command-line usage or target-date validation failed. |

The runner logs the resolved target date, run ID, correlation ID, status, and
safe exception class where applicable. It always disposes its SQLAlchemy engine
before exiting.

## Runtime topology

The web process now handles HTTP traffic only. Its FastAPI lifespan performs
web-resource cleanup but starts no scheduler and executes no EOD work. The base
backend dependency set no longer includes APScheduler.

P10.2 provides the portable process entrypoint only. Managed-cron provider
configuration and production deployment resources remain part of the later
deployment work; no provider accounts or cloud resources are created here.
