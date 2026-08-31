# Architecture

The authoritative architecture, data model, and technology decisions live in the
**FinSight AI — Engineering Design Document v2.1**. This file is a lightweight
pointer plus notes on what exists *right now*; it intentionally does not
duplicate the design document.

## Source of truth

- **Engineering Design Document v2.1** — system, AI, data, and UI architecture.
- **Implementation Roadmap v1.0** — the day-to-day, phase-by-phase build plan.

## Style

Modular monolith: a single FastAPI application organized into independent,
feature-owned modules communicating through shared services rather than network
calls (design doc §4.1). Five principles: modularity by feature, event-driven
processing, deterministic analytics before AI reasoning, RAG, and explainability
by default.

## High-level topology

```
User → Next.js (frontend) → REST API → FastAPI (backend)
                                          │
              ┌───────────────────┬────────┼────────────────────┐
          PostgreSQL       FAISS cache   External EOD Runner    Providers
                                          │                    (market/RSS,
                                 market → news → history       Gemini optional)
```

The frontend talks **only** to the backend; nothing calls the database or vector
store directly.

## Backend modules (`backend/app/`)

| Module          | Responsibility                                                        | First built |
|-----------------|----------------------------------------------------------------------|-------------|
| `shared`        | DB engine/session, exceptions, middleware, security, utils           | Phase 0     |
| `auth`          | Registration, login, JWT, preferences, risk profile                  | Phase 1     |
| `market`        | Market data ingestion, technical indicators, sectors, fundamentals   | Phase 2     |
| `portfolio`     | Portfolio/watchlist CRUD, diversification, exposure, risk             | Phase 3     |
| `history`       | Feature engineering, embeddings, FAISS similarity, statistics        | Phase 4     |
| `news`          | RSS ingestion, company tagging, sentiment, daily aggregation           | Phase 5     |
| `intelligence`  | RAG, context/prompt builders, recommendations, report composition    | Phase 6     |
| `reports`       | Report listing/detail, Markdown/PDF export                           | Phase 8     |
| `chat`          | Conversational assistant reusing the RAG pipeline                    | Phase 9     |
| `dashboard`     | Batched home-screen composition and cross-domain freshness           | Phase 7     |
| `strategy`      | Versioned rules, deterministic replay, robustness analysis           | Phase 11C   |
| `discovery`     | Validated natural-language screening and saved screens               | Phase 11F   |
| `scheduler`     | Durable control plane and one-shot external EOD runner                 | Phase 2+    |

## Implemented through Phase 12

- FastAPI app factory with request IDs, structured JSON logging, global envelope
  errors, health probes, and async SQLAlchemy/Alembic (`0001`–`0019`).
- JWT/Argon2 auth with refresh rotation, preferences, rate limiting, persisted
  administrator capability, and ownership-scoped resources.
- Deterministic market indicators, batched market snapshots, portfolio/risk
  analytics, RSS sentiment, FAISS analogues, recommendations, and grounded prose.
- A date-scoped, cross-worker-locked, durable and resumable
  market→news→history EOD control plane invoked by a one-shot external process;
  FastAPI web workers run no background scheduler.
- Maintained offline NSE session/holiday rules plus a post-close yfinance
  target-bar preflight gate execution before durable pipeline state is created.
- Database-enforced atomic domain upserts, cross-feed news fingerprints, and
  scoped report idempotency keys make process and HTTP retries duplicate-safe.
- Target-bounded, per-symbol market windows use persisted watermarks for daily
  overlap repair and periodic adjusted-history reconciliation.
- PostgreSQL-owned historical vectors and corpus identity reconstruct missing or
  corrupt generation-addressed FAISS caches after restarts or interrupted writes.
- Next.js App Router screens for auth, dashboard, market, history, portfolio,
  watchlist, settings, and reports; shared evidence disclosures and Plotly
  allocation visualization.
- Stored structured reports rendered on demand from one Markdown source into
  Markdown or PDF, with browser and extracted-PDF parity tests.
- A grounded conversational assistant that reuses the Phase 6 context, prompt,
  validation, and narration pipeline; responses stream over SSE only after
  validation and persist in user-scoped history.
- Provider-neutral generation provenance records the actual backend, model
  version, finish reason, attempts, latency, token usage, and fallback state for
  reports, chat, dashboard summaries, and recommendations without logging prompts
  or generated financial content.
- Next.js Assistant UI with incremental rendering, recent-question history,
  confidence, sources, risks, and the shared evidence disclosure.
- Effective-dated NIFTY 50/Next 50/100 membership, a batched Market workspace,
  evidence-backed movement attribution, advanced portfolio risk, deterministic
  strategy replay/robustness, validated research discovery, and administrator
  operations status.
- Zero-cost Vercel Hobby + Render Free + Neon Free topology, timezone-aware
  GitHub Actions EOD attempts, non-root health-checked production images,
  CI-gated deploys, fail-closed settings, and a non-mutating smoke verifier.
- Docker Compose for the real stack, 493 backend tests, 78 frontend tests, and
  responsive plus real-stack Playwright Chromium journeys.

See [Production Deployment](deployment.md) for the P10.8 operator contract.

## Configuration

- `config/settings.py` — Pydantic `BaseSettings`, validated once at startup.
- `config/logging.py` — JSON logging + request-ID context.
- `config/constants.py`, `config/prompts.py`
  (prompts populated from Phase 6).
