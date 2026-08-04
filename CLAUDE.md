# CLAUDE.md — FinSight AI

Project guide for Claude Code and contributors. Architecture is fixed by the
**Engineering Design Document v2.1**; build order by the **Implementation
Roadmap v1.0** (`~/Downloads/Roadmap.md`). Build one phase at a time; each phase
ends runnable end-to-end and is tagged.

## What this is

AI-powered **financial intelligence** platform (Indian markets first): turns
end-of-day market data into personalized, explainable investment intelligence.
A research assistant, **not** a price predictor. Core principle: **analytics
before AI** — indicators, portfolio metrics, sentiment, similarity, and
probabilities are computed deterministically; the LLM only *explains* them.

## Stack

- **Backend:** FastAPI · async SQLAlchemy 2 (asyncpg) · Alembic · pydantic-settings ·
  PostgreSQL · APScheduler · yfinance (market data) · FAISS (similarity) ·
  numpy · (Redis optional) · Gemini Flash + FinBERT (later). Python **3.12+**.
- **Frontend:** Next.js 16 · React 19 · TypeScript · Tailwind v4 · Shadcn UI (base-ui) ·
  Plotly (later). App Router, no `src/` dir (`app/` + `components/` at root).
- **Infra:** Docker Compose (db + backend + frontend); prod targets Vercel + Render.

## Layout

```
backend/app/{auth,market,portfolio,history,intelligence,reports,chat,scheduler,shared}/
backend/config/{settings,logging,constants,feature_flags,prompts}.py
backend/alembic/versions/          # migrations (0001 baseline, 0002 auth, …)
backend/tests/<feature>/           # pytest, feature-organized
frontend/app/(auth|dashboard)/…    # route groups
frontend/{components,lib}/         # shared components + api client / auth context
docker/  docs/  scripts/  infrastructure/
```

Naming is deliberate: `intelligence/` not `ai/`; `history/` not `similarity/`.
Each backend feature module uses the same internal layout
(`models/schemas/repository/service/routes/dependencies/constants/exceptions`).

## Conventions

- All API routes under `/api/v1`; every response uses the envelope
  `{success, message, data, timestamp, requestId}` (helper: `app/shared/response.py`).
  Errors go through the global handlers in `app/shared/exceptions.py`.
- Structured JSON logging with a request-ID (`config/logging.py` + middleware).
- Migrations via Alembic only (async env). Add new models' imports to
  `alembic/env.py` so autogenerate sees them.
- Tests: `pytest` from `backend/`; SQLite (aiosqlite) in-memory for speed.
  Coverage config sets `concurrency = ["thread","greenlet"]` (required for
  accurate async/SQLAlchemy coverage).
- Git: commits authored solely by Shanmukh — **no Claude co-author trailer**.
  Phase work on a `QA`-prefixed branch (e.g. `QA-phase-1-auth`), tagged on merge.

## Run / verify

```bash
docker compose up --build -d          # full stack: :3000 web, :8000 api, :5432 db
docker compose logs -f backend
curl localhost:8000/health            # + /health/db
cd backend && ./.venv/bin/python -m pytest      # tests (native venv, python3.13)
cd frontend && npm run build          # type-check + build
```

Native (no Docker) Postgres helper: `scripts/run_local_postgres.sh start`.

## Progress log

| Phase | Tag | Status | Notes |
|------|-----|--------|-------|
| 0 — Project Setup | `v0.1.0-skeleton` | ✅ done | Monorepo, FastAPI+health, Next.js landing, Docker Compose, logging, Alembic baseline. Verified in Docker. |
| 1 — Authentication | `v0.2.0-auth` | ✅ done | Register/login/refresh(+rotation), Argon2, JWT, `sessions` revocation, preferences (3 tables), login rate-limit, envelope. Frontend: login/register/dashboard/settings + auth context. Auth coverage ~99%. See `docs/auth.md`. |
| 2 — Market Data | `v0.3.0-market-data` | ✅ done | yfinance client (retry + NaN-drop), pure indicator engine (RSI/EMA/MACD/Bollinger/ATR, hand-verified), ingestion (per-symbol isolation), APScheduler cron + manual trigger, `stocks/daily_prices/indicators/fundamentals` (migration 0003), market read endpoints. ~97% coverage. Live-verified on real NSE data (independent RSI cross-check matched to 10 dp). See `docs/market-data.md`. |
| 3 — Portfolio | `v0.4.0-portfolio` | ✅ done | Portfolio + holdings + watchlist CRUD (migration 0004), all user-scoped with strict ownership (404 on not-owned). Pure analytics engine (value/P&L/allocation/diversification-HHI/concentration/volatility/health/risk), hand-verified. Frontend: `/portfolio` (Analytics template — metric cards, SVG allocation donut, health card, holdings add/edit/remove) + `/watchlist` (pin/sort/quotes). ~99% coverage. Live-verified on real RELIANCE+TCS portfolio. See `docs/portfolio.md`. Note: sector chart is a dependency-free SVG donut; Plotly deferred to Phase 7. |
| 4 — Historical Intelligence | `v0.5.0-historical-intelligence` | ✅ done | Core differentiator. Deterministic pipeline: daily market feature vectors (11-dim, sentiment placeholder) → shared persisted Normalizer (drift-proof) → FAISS IndexFlatL2 → Top-K similarity → statistics from real next-day outcomes. Split tables (migration 0005). `GET /history/similar` + admin rebuild (chained into scheduler). ~98% coverage; two-regime retrieval + determinism verified. Live: 199 real sessions, deterministic rebuild. FAISS index on persisted Docker volume. See `docs/historical-similarity.md`. |
| 5 — News + Sentiment | `v0.6.0-news-sentiment` | ⏳ next — wires real sentiment into Phase 4's placeholder | |
| 5 — News + Sentiment | `v0.6.0-news-sentiment` | | |
| 6 — AI Intelligence (RAG) | `v0.7.0-ai-intelligence` | | |
| 7 — Dashboard UI | `v0.8.0-dashboard` | | |
| 8 — Reports | `v0.9.0-reports` | | |
| 9 — AI Chat | `v0.10.0-ai-chat` | | |
| 10 — Deployment | `v1.0.0` | | |
| 11 — Testing & Polish | `v1.1.0-polish` | | |
