# Trading Calendar and Provider Readiness (P10.3)

The external EOD runner performs a read-only preflight before creating or
resuming pipeline execution state. This prevents holiday runs, premature runs,
and runs against a market provider that has not published the target session.

## Trading calendar

`pandas-market-calendars` supplies packaged NSE session and holiday rules. The
default calendar is `NSE`, with `MARKET_TIMEZONE=Asia/Kolkata`. Calendar rules
are offline and versioned with the application, so the runner does not depend on
a calendar network service. Dependency updates remain necessary as exchanges
publish or correct future holiday schedules.

For an explicit target date:

- weekends and NSE holidays exit successfully without creating a pipeline run;
- trading sessions expose their authoritative open and close timestamps;
- provider probing begins only after the session close plus
  `MARKET_CLOSE_GRACE_MINUTES`.

When no target is supplied, the runner walks backward through the NSE calendar
from the current market-local date, skips weekends and holidays before provider
checks, and selects the latest session confirmed ready.

## Provider readiness

After the close buffer, the runner fetches validated daily bars for
`MARKET_READINESS_SYMBOL` (default `^NSEI`) through the existing yfinance
adapter. Readiness requires an actual bar whose date exactly matches the target
session. A newer bar alone does not substitute for a missing target bar.

Stable outcomes are:

| Status | Runner behavior |
|--------|-----------------|
| `ready` | Continue into the durable EOD control plane. |
| `non_trading_day` | Exit `0`; no pipeline state is created. |
| `too_early` | Exit `1` so automation can retry after the close buffer. |
| `data_not_ready` | Exit `1`; the provider has not published the target bar. |
| `provider_unavailable` | Exit `1`; timeout/provider failures remain retryable. |

Only safe status codes, timestamps, dates, and exception class names are logged.
Provider payloads and exception messages are not persisted. A previously
completed logical run bypasses provider probing and remains a successful no-op,
preserving the P10.1 retry contract.

## Configuration

- `MARKET_CALENDAR=NSE`
- `MARKET_TIMEZONE=Asia/Kolkata`
- `MARKET_READINESS_SYMBOL=^NSEI`
- `MARKET_CLOSE_GRACE_MINUTES=60`
- `MARKET_FETCH_TIMEOUT_SECONDS=30`

P10.3 is the pipeline-level readiness gate. P10.4 adds write-level idempotency,
and P10.5 bounds both this probe and per-symbol ingestion to explicit provider
windows. See [Incremental Market Ingestion](incremental-market-ingestion.md).
