# Historical Market-Regime Similarity (Phase 10D)

Historical similarity compares the current aggregate market regime with past
trading sessions and reports what actually happened afterward. It is research
context, not a price forecast. Every feature, outcome, distance, factor
explanation, and statistic is deterministic; an LLM never computes or ranks it.

## Reconstruction contract

`market_regime_v1` replaces the legacy 15-feature representation with a fixed,
ticker-order-independent 25-feature vector:

| Group | Features |
|---|---|
| Direction | equal-weight return, median return |
| Breadth | advancing/declining/unchanged shares, capped A/D ratio, shares above EMA20 and EMA50 |
| Momentum | median/IQR RSI, overbought/oversold shares, median/IQR 20-session momentum |
| Volatility | median ATR/close, return IQR, median 20-session realized volatility |
| Volume | median 20-session relative volume, elevated-volume share |
| Sector | dispersion of sector returns, leader/laggard spread |
| Macro | USD/INR, crude, gold, and US 10-year daily returns |

Inputs with naturally dangerous tails are winsorized before aggregation. All
rolling values use only the current or earlier observations: 20-session
momentum, realized volatility, and relative volume cannot see future data.
Sentiment is deliberately excluded because reliable full-window per-company
history is unavailable; missing historical news is not silently treated as
neutral evidence.

A candidate date is accepted only when it has at least three usable expected
constituents, at least 80% constituent coverage, at least 60% sector-metadata
coverage, and all four macro returns. Rejected dates are counted by reason and
reported by rebuild/bootstrap telemetry. Accepted sessions persist usable and
expected counts, coverage ratios, membership mode, and quality flags.

## Effective membership without invented history

Membership intervals use `[valid_from, valid_to)`. On and after the first known
NIFTY50 membership snapshot, reconstruction uses the exact effective members for
the session date, including retired constituents whose stored history remains.

The database cannot truthfully infer membership before its first snapshot. For
those dates, the builder uses the available tracked historical equities as a
proxy and labels every session `available_data_proxy` with
`historical_membership_unknown`. It never presents current membership as known
past membership. Migration `0014`'s `history_eligible` values remain useful to
discover legacy tracked stocks, but are no longer the permanent reconstruction
definition.

## Normalization, indexing, and versioning

The feature order, `market_regime_v1`, and
`median_iqr_clip8_v1` normalization method form one persisted contract.
Normalization uses corpus medians and IQRs; zero-IQR dimensions become zero and
normalized values are clipped to ±8. This is more resistant to market outliers
than the legacy mean/std scaler.

The normalized vector is indexed by an exact
`IndexIDMap(IndexFlatL2)`. FAISS returns squared L2; the API converts this to
root-mean-square normalized feature distance, then reports
`similarity = 1 / (1 + distance)`. Exact L2 remains appropriate because robust
normalization makes dimensions comparable and the corpus is small enough that
approximate search would add complexity without benefit.

Migration `0015_market_regime_history` marks legacy sessions with a distinct
version and clears their embeddings/statistics/index state. Legacy rows remain
inspectable until the first successful rebuild atomically replaces stale dates.
Queries refuse schema, feature-version, dimension, normalization, corpus-hash,
row-count, or ID mismatches instead of interpreting incompatible vectors.

PostgreSQL owns raw vectors, embedding membership, and the committed singleton
index state. `DATA_DIR/faiss/generations/<corpus-hash>/` is only a
generation-addressed cache. Missing or corrupt files are reconstructed from the
committed database snapshot, checksummed, and atomically published. Database
commit precedes cache publication, so a publication failure cannot expose an
uncommitted corpus.

## Outcomes and explanations

Each historical session stores separately from its input vector:

- next-session equal-weight return and breadth;
- compounded return over the next five accepted trading sessions;
- realized peak drawdown and upside over that five-session path; and
- bullish/bearish/neutral next-session label.

The last session and sessions without a complete five-session horizon retain
honest `null` outcomes. Outcome fields never enter FAISS. API statistics use
only known next-session outcomes from retrieved neighbours.

Each analogue also exposes its three closest and two most divergent feature
groups. Group similarity and its explanation are calculated from the same
robust-normalized dimensions, with no generated prose and no raw-vector leak.

## API and UI

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/history/similar?date=&k=` | Version metadata, query quality/regimes, analogues, factor explanations, forward outcomes, statistics |
| `POST /api/v1/admin/jobs/history-rebuild/run` | Reconstruct sessions and atomically rebuild PostgreSQL/FAISS state (admin) |

The `/history` workspace displays model/dimension/membership/coverage badges,
current breadth/momentum/volatility regimes, deterministic closest/divergent
factors, next-session and five-session outcomes, and the existing evidence card.
The `available_data_proxy` badge keeps unknown historical membership visible.

## Verification

- Feature tests cover exact order/dimension, clipping, sparse coverage, missing
  macro/sector data, sentiment exclusion, robust normalization, and finite
  output.
- Reconstruction tests cover effective additions/removals, unknown-history
  proxy labels, input-order determinism, warmup rejection, and future-data
  leakage.
- Service/index tests cover same-regime retrieval, outcome dates, idempotent
  rebuilds, incompatible versions, empty corpora, FAISS construction failure,
  commit/publication boundaries, checksums, concurrent publishers, and missing
  or corrupt cache recovery.
- On 22 August 2026, an isolated local PostgreSQL staging database completed a
  live 50-equity + four-macro bootstrap: 12,693 equity price rows, 12,043
  indicator rows, 254 candidate dates, 198 accepted sessions, 56 explicitly
  rejected dates, dimension 25, and a 21,384-byte approximate FAISS footprint.
  A repeat kept all row/session counts stable and used incremental ingestion;
  moving the active cache generation aside was followed by a successful
  PostgreSQL-backed query and automatic reconstruction.

Production was not mutated. See [Expanded Production Bootstrap](expanded-bootstrap.md).
