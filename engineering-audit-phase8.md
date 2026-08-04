# FinSight AI Implementation Audit

## Remediation closure — 2026-08-05 (current state)

This section supersedes the original read-only snapshot retained below. Every
Phase 0–8 conclusion was re-evaluated from the implementation after remediation,
not inferred from tags or the roadmap progress table.

### 1. Repository Architecture

- **Backend:** FastAPI modular monolith with feature-owned routes, services,
  repositories, models, and schemas under `backend/app/`; shared envelopes,
  exceptions, request IDs, security, providers, and database lifecycle live in
  `app/shared/`. APScheduler executes the locked market → news → history
  post-close pipeline.
- **Database:** async SQLAlchemy 2/PostgreSQL with one Alembic chain through
  `0008_user_admin`. The history vectors and reports use JSON where their shape
  is intentionally versioned; FAISS artifacts live on the persisted data volume.
- **Frontend:** Next.js 16 App Router/React 19/Tailwind v4 with `(auth)` and
  `(dashboard)` route groups, a typed API client, auth context, reusable page
  templates, and responsive authenticated navigation.
- **Shared UI/design system:** Base UI/Shadcn primitives plus `MetricCard`,
  `StockCard`, `AIInsightCard`, mandatory `EvidencePanel`, `Heatmap`, reusable
  `DataTable`, SSR-safe Plotly allocation chart, and shared formatters/states.
- **API:** all product JSON routes are under `/api/v1` and use the standard
  envelope; authenticated file exports intentionally return raw Markdown/PDF.
  Expensive operations routes use the persisted administrator dependency.

### 2. Phase Audit

| Phase | Status | Definition of Done |
|---|---|---|
| 0 — Project Setup | COMPLETE | Satisfied |
| 1 — Authentication | COMPLETE | Satisfied |
| 2 — Market Data | COMPLETE | Satisfied |
| 3 — Portfolio | COMPLETE | Satisfied |
| 4 — Historical Intelligence | COMPLETE | Satisfied |
| 5 — News + Sentiment | COMPLETE | Satisfied |
| 6 — AI Intelligence | COMPLETE | Satisfied for the deterministic default and configured Gemini adapter |
| 7 — Dashboard UI | COMPLETE | Satisfied |
| 8 — Reports | COMPLETE | Satisfied |
| 9 — AI Chat | NOT STARTED | Not applicable yet |
| 10 — Deployment | NOT STARTED | Not applicable yet |
| 11 — Testing & Polish | NOT STARTED | Phase-specific deliverables remain future work |

#### Phase 0 — COMPLETE

Evidence: runnable Compose stack, FastAPI/Next.js applications, PostgreSQL,
health checks, structured request-ID logging, complete environment templates,
Alembic, tests, and current setup/architecture documentation. A clean image
rebuild and three-service startup passed. DoD: satisfied.

#### Phase 1 — COMPLETE

Evidence: Argon2 registration/login, JWT access and rotating refresh tokens,
revocable sessions, preferences, rate limiting, frontend auth/settings, and
ownership/security tests. DoD: satisfied. Process-local rate limiting and
browser token storage remain documented production-hardening choices, not
Phase 1 functional gaps.

#### Phase 2 — COMPLETE

Evidence: validated and retrying yfinance ingestion, externally enforced
provider deadlines, per-symbol isolation, deterministic indicators, scheduled
and admin-only manual operation, complete market read APIs, and batched snapshot
queries. Real NSE data remains populated in PostgreSQL. DoD: satisfied.

#### Phase 3 — COMPLETE

Evidence: user-scoped portfolio/holding/watchlist CRUD, deterministic analytics,
truthful incomplete-valuation semantics, constant-query snapshot assembly,
responsive UI, and an SSR-safe Plotly allocation visualization. DoD: satisfied;
missing quotes withhold dependent analytics instead of inventing a zero price.

#### Phase 4 — COMPLETE

Evidence: the fixed vector is now 15-dimensional: market, technical, real news
sentiment, and real daily returns for USD/INR, crude oil, gold, and the US
10-year yield. Macro proxies reuse validated price ingestion as inactive rows,
so they cannot contaminate equity views. Sessions require all four macro inputs;
no zero imputation is used. Persisted normalization, exact FAISS retrieval,
self-exclusion, actual next-day outcomes, statistics, and deterministic rebuild
tests remain intact. Stale pre-upgrade artifacts now fail safely with a rebuild
contract rather than a 500. Live acceptance indexed 194 macro-complete sessions
at dimension 15 and returned five ranked analogues with five actual outcomes.
DoD: satisfied. FII/DII is a documented provider-source extension, not a fake
placeholder.

#### Phase 5 — COMPLETE

Evidence: RSS ingestion/deduplication, precise company tagging, batched lexicon
or optional FinBERT inference, successful FinBERT-path regression, stock/day
aggregation, article-weighted sector/day aggregation and API, scheduler wiring,
and direct history-vector consumption. DoD: satisfied; the deterministic lexicon
remains the install-light default while FinBERT is explicitly selectable.

#### Phase 6 — COMPLETE

Evidence: scoped RAG context, deterministic ranking and evidence/confidence/risk,
versioned prompts, async Gemini adapter with transport/per-attempt deadlines,
strict prose grounding/rejection/retry, deterministic fallback, structured
reports, and a manually reviewed 12-scenario benchmark. DoD: satisfied in the
repository's supported default configuration. A live Gemini benchmark remains
credential-dependent and is recorded as external verification, not silently
claimed.

#### Phase 7 — COMPLETE

Evidence: reusable components were built and used across dashboard, market,
portfolio, history, and reports; dashboard summary is batched; watchlist,
technical summary, economic-event provider states, evidence disclosures, and
responsive navigation are real-data wired. Unit tests and Chromium Compose E2E
cover login → dashboard → evidence. DoD: satisfied.

#### Phase 8 — COMPLETE

Evidence: owned filterable/paginated report browse/detail APIs, generation,
Markdown single source of truth, Unicode-safe PDF conversion, authenticated
blob downloads, content/provenance parity across screen/Markdown/PDF, report
templates, evidence disclosures, exhaustive export tests, and real-stack
generate/open/export E2E. Report persistence has one repository owner. DoD:
satisfied.

### 3. Remaining Technical Debt

- Phase 9 chat, Phase 10 production infrastructure, and Phase 11 accessibility,
  performance/load, clean-clone, and full multi-page journey work have not been
  pulled forward and should not be represented as Phase 0–8 defects.
- A live Gemini benchmark needs a user-supplied API key; deterministic benchmark,
  adapter, timeout, retry, rejection, and fallback coverage are complete.
- FII/DII historical flows need a trustworthy licensed/provider source before
  joining the macro vector. The current implementation deliberately does not
  fabricate them.
- Authentication still uses browser storage and login throttling is process
  local; production deployment should move these to hardened cookie/distributed
  controls if its threat and scale model requires them.
- Broader accessibility and performance measurement belongs to Phase 11.

Resolved debt includes report-repository duplication, per-holding N+1 reads,
fake zero-price valuation, missing job authorization, scheduler races, blocking
provider calls, stale feature flags/dependencies/assets, duplicated frontend
formatters/tables/metrics, missing Plotly, ungrounded AI prose, report parity,
historical percentage units, sector sentiment, and missing macro features.

### 4. Current Project State

Verified current evidence:

- Backend: **233 tests pass**; Ruff passes.
- Frontend: **37 tests pass**; lint and the Next.js webpack production build pass.
- Browser: **2 Chromium E2E flows pass** against the rebuilt real Compose stack.
- Database: one Alembic head at `0008_user_admin`.
- Live macro ingestion: all four proxies succeeded, each with 252–260 real bars.
- Live history rebuild: 194 sessions, 15 dimensions, latest date 2026-08-04;
  Top-5 query returned five stored next-day outcomes.
- Dependency audit: zero npm vulnerabilities at the last verification.

The Phase 8 backlog is closed. The codebase is at the boundary between completed
Reports and unstarted AI Chat.

### 5. Recommended Next Phase

Resume at **Phase 9 — AI Chat**. Start with the roadmap's conversation model,
user-scoped chat history, grounded context retrieval, streaming/error contract,
and chat UI; keep recommendation computation in deterministic services and let
the LLM explain only supplied facts. Phase 10 and Phase 11 should remain separate
after Chat is runnable end-to-end.

---

## Original read-only audit snapshot (historical; superseded above)

  I reviewed the complete roadmap, repository structure, backend and frontend implementation, migrations, tests, configuration, documentation, phase tags, and outstanding placeholders. No source files were modified.

  The repository is substantial and functional, but the progress table overstates completion. Under a strict roadmap-based definition, only Phase 1 is fully complete. Phases 0 and 2–8 have material gaps; Phases 9–11
  have not started.

  ## 1. Repository Architecture

  ### Backend

  The backend is a FastAPI modular monolith:

  - Application composition and lifecycle: backend/app/main.py:36
  - Central configuration: backend/config/settings.py:25
  - Shared database, response envelope, exception handling, request IDs, logging, security clients, and ML adapters under backend/app/shared/
  - Feature modules:
      - auth
      - market
      - portfolio
      - history
      - news
      - intelligence
      - dashboard
      - reports
      - chat
      - scheduler

  - Most mature modules follow routes → service → repository → models/schemas.
  - All product routes are mounted under /api/v1; health endpoints are intentionally unversioned.
  - APScheduler runs the post-close market → news → history pipeline from backend/app/scheduler/jobs.py:18.

  ### Database

  Alembic has one valid migration chain and one head:

  1. Baseline
  2. Auth
  3. Market
  4. Portfolio
  5. Historical intelligence
  6. News/sentiment
  7. Reports/chat history

  All model modules are imported into Alembic metadata in backend/alembic/env.py:21.

  ### Frontend

  The frontend is Next.js 16 App Router with React 19 and Tailwind v4:

  - Route groups: (auth) and (dashboard)
  - Authenticated shell and navigation: frontend/app/(dashboard)/layout.tsx:1
  - Central typed client and API contracts: frontend/lib/api.ts:1
  - Client-side JWT/auth state: frontend/lib/auth-context.tsx:1
  - Pages exist for dashboard, market, history, portfolio, watchlist, reports, report detail, settings, login, and registration.
  - There is no chat route.

  Most pages are client components that fetch after hydration. There are no Server Actions or backend-for-frontend routes.

  ### Shared utilities and design system

  Reusable components include:

  - MetricCard
  - StockCard
  - AIInsightCard
  - EvidencePanel
  - Heatmap
  - DataTable
  - AnalyticsPageTemplate
  - ReportPageTemplate
  - Shadcn/Base UI primitives for cards, buttons, fields, and selects

  The design system is card-based with green/red/blue/amber semantic colors. Reuse is only partial: portfolio and watchlist still duplicate formatters, metric cards, and raw table markup despite shared equivalents.

  ### API organization

  Major route families are:

  - /auth, /user
  - /market, /admin/jobs/*
  - /portfolios, /watchlist
  - /history
  - /news
  - /recommendations
  - /dashboard
  - /reports

  Success responses use the standard envelope. File exports correctly return raw document responses instead.

  One authorization concern: the routes named “admin” only require an ordinary authenticated user. Any registered user can trigger market ingestion, news ingestion, or a FAISS rebuild.

  ## 2. Phase Audit

   Phase                          Status         Definition of Done
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   0 — Project Setup              PARTIAL        Not fully satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   1 — Authentication             COMPLETE       Satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   2 — Market Data                PARTIAL        Mostly satisfied; live-data criterion not independently verified
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   3 — Portfolio                  PARTIAL        Satisfied for seeded/fully priced portfolios
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   4 — Historical Intelligence    PARTIAL        Determinism satisfied; completeness/quality only partially established
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   5 — News + Sentiment           PARTIAL        Not fully satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   6 — AI Intelligence            PARTIAL        Not fully satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   7 — Dashboard UI               PARTIAL        Not satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   8 — Reports                    PARTIAL        Not satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   9 — AI Chat                    NOT STARTED    Not satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   10 — Deployment                NOT STARTED    Not satisfied
  ─────────────────────────────  ─────────────  ────────────────────────────────────────────────────────────────────────
   11 — Testing & Polish          NOT STARTED    Not satisfied

  ### Phase 0 — Project Setup: PARTIAL

  Evidence:

  - FastAPI factory, health endpoints, structured logging, request IDs, database session, Alembic, Docker Compose, frontend health page, tests, and repository scaffolding exist.
  - Phase 0 smoke tests pass.
  - Docker Compose defines all three required services.

  Missing:

  - .env.example is no longer complete. It omits approximately 15 settings, including scheduler, history, sentiment, login-rate-limit, and LLM settings. Compare backend/config/settings.py:59 with
    backend/.env.example:1.

  - README and architecture documentation still say the project is at Phase 0 and feature modules are empty: README.md:10, docs/architecture.md:49.
  - Docker was not started during this read-only audit, so clean-start runtime behavior was not independently retested.

  ### Phase 1 — Authentication: COMPLETE

  Evidence:

  - Registration, login, refresh rotation, /user/me, and preferences are implemented.
  - Argon2, JWT validation, expiry handling, refresh-session revocation, ownership, and login rate limiting are tested.
  - Frontend login/register, auth provider, route protection, and settings are wired.
  - Auth coverage is above 95%.

  DoD is satisfied in the current testable implementation.

  Remaining hardening items, but not Phase 1 blockers:

  - Tokens are stored in localStorage, with the XSS trade-off documented.
  - Rate limiting is process-local and unsuitable for multi-instance deployment.

  ### Phase 2 — Market Data: PARTIAL

  Evidence:

  - Four market tables and indexes exist.
  - Pure RSI, EMA, MACD, Bollinger, and ATR calculations are implemented and tested.
  - Ingestion isolates per-symbol failures.
  - Scheduler and manual trigger exist.
  - Market reads include breadth, movers, sectors, stock detail, fundamentals, and indicators: backend/app/market/routes.py:31.

  Missing:

  - The roadmap requires provider timeout handling. The yfinance wrapper retries but passes no timeout and has no external deadline: backend/app/shared/clients/yfinance_client.py:51.
  - Real-provider ingestion is mocked in automated tests. The documented live verification cannot be proven solely from the current repository.
  - “Admin” ingestion can be triggered by any authenticated user.

  ### Phase 3 — Portfolio: PARTIAL

  Evidence:

  - Portfolio, holdings, and watchlist CRUD exist.
  - Queries enforce ownership.
  - Analytics are pure and extensively tested.
  - Portfolio and watchlist pages are functional.

  Missing/deviations:

  - The roadmap explicitly names Plotly for allocation; the implementation uses a custom SVG donut.
  - Missing market prices are valued as zero, creating a fictitious full loss and distorted allocation/health metrics: backend/app/portfolio/analytics.py:82.
  - Portfolio analytics and watchlist assembly perform several queries per holding, creating N+1 scaling problems: backend/app/portfolio/service.py:147.

  The DoD works for portfolios whose holdings all have current prices, but not reliably for partially ingested data.

  ### Phase 4 — Historical Intelligence: PARTIAL

  Evidence:

  - Fixed feature vectors, persisted normalization, FAISS IndexFlatL2, self-exclusion, Top-K retrieval, actual next-day outcomes, statistics, migration, scheduler integration, and deterministic rebuild tests exist.
  - Synthetic two-regime tests establish meaningful nearest-neighbor behavior.

  Missing:

  - The roadmap requires macro features; the 11-dimensional vector contains only market, technical, and sentiment inputs: backend/app/history/feature_engineering.py:23.
  - The documentation explicitly acknowledges macro inputs are not implemented: docs/historical-similarity.md:103.
  - “Genuinely similar” is verified with synthetic regimes, not a committed real-market quality benchmark.
  - Only the latest session’s statistics row is cached, rather than statistics for the historical corpus.

  ### Phase 5 — News + Sentiment: PARTIAL

  Evidence:

  - RSS ingestion, URL/title dedupe, tagging, batched scorer interface, article sentiment, stock/day aggregation, scheduler integration, and history-feature wiring exist.
  - FinBERT is implemented as an optional backend: backend/app/shared/ml/sentiment.py:94.

  Missing:

  - The roadmap requests per-stock and per-sector aggregation; only per-stock/day aggregates exist: backend/app/news/service.py:114.
  - Default behavior is lexicon scoring, not FinBERT.
  - Automated tests verify lexicon behavior and FinBERT fallback, not successful real FinBERT inference: backend/tests/news/test_sentiment.py:1.
  - The historical documentation still describes sentiment as a placeholder even though it has been wired.

  ### Phase 6 — AI Intelligence: PARTIAL

  Evidence:

  - Context builder, structured prompts, deterministic ranking, Gemini adapter, narrator fallback, recommendations, explainability structure, reports, and chat-history migration exist.
  - Ranking is deterministic and well tested.
  - Reports include structured evidence, confidence, and risks.

  Material gaps:

  - **Resolved 2026-08-04:** A dedicated, versioned 12-scenario benchmark now covers aligned/conflicting signals, neutral conditions, volatility, sentiment, historical context, sector leadership, and sparse data. It checks action, confidence, evidence, risks, grounding, rank determinism, and reproducibility; all deterministic outputs were read and recorded in docs/benchmarks/phase6-v1.1-deterministic.md.
  - Tests primarily use the deterministic narrator, not real-model responses: backend/tests/intelligence/test_report_generation.py:1.
  - **Resolved 2026-08-04:** Gemini generation now uses the SDK's native async client, configures its transport timeout from llm_timeout_seconds, and enforces the same deadline around every retry attempt.
  - **Resolved 2026-08-04:** Every narration path now validates provider prose against its prompt facts. Unsupported numbers, price predictions/advice, and missing section anchors are rejected; recommendation prose must include its symbol, confidence, supplied evidence, and supplied risk. Gemini retries rejected output and all adapters have a post-generation fallback guard.

  The deterministic fallback path is strong; the actual generative-AI quality gate required by the roadmap is incomplete.

  ### Phase 7 — Dashboard UI: COMPLETE

  Evidence:

  - Shared component library and primary pages exist.
  - Dashboard has a batched endpoint.
  - Recommendations expose real evidence.
  - Responsive grids and mobile navigation exist.
  - Twenty-one shared-component tests pass.

  Closure evidence:

  - **Resolved 2026-08-04:** The batched dashboard response now includes the authenticated user's quote-enriched watchlist, and the page renders it with a tested responsive card using real prices, changes, pin state, empty state, truncation, and management navigation.
  - **Resolved 2026-08-04:** Market Intelligence now includes a batched deterministic RSI/EMA/MACD/ATR summary and upcoming India economic events from an optional Trading Economics adapter. Provider configuration/failure is explicit and never replaced with mock events; backend and responsive component states are tested.
  - **Resolved 2026-08-04:** Every `AIInsightCard` now requires evidence at compile time. Dashboard market prose and report executive/market/portfolio/history narratives expose shared deterministic fact-to-evidence disclosures; recommendation and historical cards retain their existing real evidence. Tests cover market, portfolio, historical, executive, percentage-unit, and sparse-evidence paths.
  - **Resolved 2026-08-05:** A Playwright Chromium E2E test now rebuilds and waits for the real Compose stack, idempotently provisions an account through the backend, logs in through the UI, verifies every dashboard summary card plus watchlist/AI content, and expands `Show Evidence` to assert real breadth facts. The external-stack URL and credentials are configurable; traces/screenshots are retained on failure.
  - **Resolved 2026-08-04:** Historical percentage display was wrong by 100×:
      - avg_return and next-day returns are decimal fractions, but pct() appends % without multiplying.
      - pct_advancers is also a fraction but is displayed directly as a percent.
      - See frontend/app/(dashboard)/history/page.tsx:69 and frontend/lib/utils.ts:12.

  - **Resolved 2026-08-05:** Portfolio and Watchlist now use the shared `DataTable`; Portfolio uses `MetricCard`; StockCard, Heatmap, Portfolio, and Watchlist use the shared money/percentage/sign formatters. `DataTable` gained accessible, tested loading/empty/action states without adding a second grid abstraction.
  - **Resolved 2026-08-05:** Market and Portfolio distinguish successful no-signal results from recommendation-service failures using the shared `AIAnalysisState`; no Analytics screen claims implemented AI belongs to a later phase.

  The Definition of Done is satisfied: Dashboard, Market Intelligence, and Historical Similarity use real APIs; every AI insight requires real evidence; the Phase 7 browser acceptance flow passes against the rebuilt stack; and responsive grids/navigation remain intact.

  ### Phase 8 — Reports: PARTIAL

  The backend portion is close to complete:

  - Filtered/paginated listing
  - Ownership-scoped detail
  - Markdown and PDF exports
  - Markdown as the rendering source
  - Long-text, Unicode, missing-section, and ownership tests
  - Frontend list/detail/export workflow

  Why the DoD still fails:

  - **Resolved 2026-08-04:** Historical returns were exported/displayed with the same 100× units error: backend/app/reports/exporters/markdown.py:126, frontend/app/(dashboard)/reports/[id]/page.tsx:171.
  - **Resolved 2026-08-05:** Screen, Markdown, and therefore PDF expose the same report provenance, complete breadth facts, mover details, portfolio metrics (including diversification), top-K historical statistics/disclaimer, recommendation historical context, and five-item news limit. Shared historical evidence is deduplicated. Backend and frontend parity regressions cover every corrected field.

  - **Resolved 2026-08-04:** Report executive, market, portfolio, historical, recommendation, and risk narratives all use the required shared evidence disclosure.
  - **Resolved 2026-08-05:** Report-detail unit tests cover units and all parity fields. A real-stack Chromium flow logs in, generates a report, opens the returned ID, expands evidence, downloads both formats, validates filenames/Markdown provenance, and checks valid non-trivial PDF bytes.
  - **Resolved 2026-08-04:** Frontend lint failed in the reports page and auth context due react-hooks/set-state-in-effect: frontend/app/(dashboard)/reports/page.tsx:73, frontend/lib/auth-context.tsx:56.

  Therefore, the v0.9.0-reports tag exists, but Phase 8 is not genuinely complete.

  ### Phase 9 — AI Chat: NOT STARTED

  Only these prerequisites exist:

  - Empty backend/app/chat/__init__.py
  - chat_history table from migration 0007

  Missing everything else:

  - Chat service/repository/routes
  - Chat prompt
  - RAG reuse
  - Streaming
  - History APIs
  - Ownership tests
  - Chat page
  - Documentation

  ### Phase 10 — Deployment: NOT STARTED

  Evidence:

  - infrastructure/ contains only .gitkeep.
  - No .github/workflows.
  - No deployment documentation.
  - Dockerfiles explicitly describe themselves as development-oriented and Phase-10 pending: docker/Dockerfile.frontend:1, docker/Dockerfile.backend:1.
  - No Render/Vercel production configuration or smoke-test script.

  ### Phase 11 — Testing & Polish: NOT STARTED

  Some groundwork is already strong, especially backend coverage, but the phase deliverables are absent:

  - No full user-journey E2E suite
  - No accessibility audit
  - No performance/load measurements
  - No AI benchmark review
  - No production-readiness checklist evidence
  - No walkthrough script
  - Documentation is materially stale
  - app/shared/ml/sentiment.py is below 80% coverage, and feature flags have 0% coverage

  ## 3. Technical Debt

  ### Correctness and security

  - **Resolved 2026-08-04:** Historical percentages understated by 100× in UI and export.
  - **Resolved 2026-08-05:** Missing current prices are represented as unavailable, not zero; total valuation, return, allocation, health, and risk are withheld with explicit unpriced symbols until coverage is complete. Missing previous closes likewise withhold daily P&L.
  - **Resolved 2026-08-04:** Gemini timeout is enforced at both the SDK transport and coroutine levels, and provider inference no longer blocks async workers.
  - **Resolved 2026-08-04:** Deterministic grounding validation now checks model prose against supplied JSON facts before it reaches reports, recommendations, or dashboard responses.
  - **Resolved 2026-08-05:** Expensive manual jobs require a persisted administrator capability through one reusable dependency; unauthenticated callers receive 401 and authenticated non-admins receive 403 across market, news, and history jobs.
  - **Resolved 2026-08-05:** The scheduled market→news→history pipeline uses a non-blocking PostgreSQL advisory lock held on a dedicated connection; concurrent workers skip while the owner runs. SQLite tests/local runs use matching in-process semantics, with a concurrent-worker regression test.

  ### Duplication and missing abstractions

  - **Resolved 2026-08-05:** `ReportRepository` is the single report persistence owner; intelligence delegates creation to it, while reports exclusively owns reads and ownership enforcement.
  - **Resolved 2026-08-05:** Money/percentage/sign formatting is centralized in frontend/lib/utils.ts across StockCard, Heatmap, Portfolio, and Watchlist.
  - **Resolved 2026-08-05:** Portfolio reuses `MetricCard` for all summary metrics.
  - **Resolved 2026-08-05:** Portfolio and Watchlist reuse the responsive `DataTable`, including shared loading and empty states.
  - **Resolved 2026-08-05:** `MarketRepository.get_market_snapshots` batches stock metadata, latest-two prices, and latest indicators in at most three queries using window functions. Market overview, sectors, portfolio/detail/watchlist, dashboard, and intelligence candidates reuse it; a query-count regression test proves cardinality does not scale with stock count.

  ### Placeholder or unused surfaces

  - `chat/` and `infrastructure/` remain intentional Phase 9/10 scaffolding and are not Phase 0–8 backlog. `tests/fixtures` now holds the exercised 12-scenario AI benchmark; obsolete empty integration/E2E placeholders are absent.
  - **Resolved 2026-08-05:** Removed the unused feature-flag placeholder, unimplemented Redis/News API settings, and unreferenced create-next-app public SVGs.

  ### Dependency hygiene

  - **Resolved 2026-08-05:** NumPy is declared directly, Ruff is a declared executable dev/test dependency matching `pyproject.toml`, and the shadcn scaffolding CLI is a frontend devDependency.
  - **Resolved 2026-08-05:** Portfolio allocation now uses a responsive, browser-only Plotly donut with an accessible external legend and SSR-safe loading shell; component tests and the production App Router build pass.

  ### UI consistency

  - **Resolved 2026-08-04:** Every AI narrative card requires and renders evidence.
  - **Resolved 2026-08-05:** Shared formatting, metric-card, and table conventions are consistently applied across Phase 7 screens.
  - **Resolved 2026-08-05:** Market/Portfolio AI failures and legitimate empty results have distinct shared states; the stale future-phase placeholder was removed.
  - **Resolved 2026-08-05:** Reports uses the shared controlled Base UI Select for report type; its accessible label and filter request are covered by a user-interaction test.

  ### Missing tests

  - **Resolved for the Phase 7 acceptance flow on 2026-08-05:** Chromium covers real-stack login → dashboard data → evidence disclosure. The broader Phase 11 multi-page journey remains future work.
  - Focused history/reports page unit regressions now exist; frontend API integration coverage is still missing.
  - **Resolved 2026-08-05:** A successful FinBERT-path regression verifies model construction, batched/truncated inference, case-normalized three-class probabilities, labels, compound scores, and empty-batch behavior without downloading the optional model.
  - Automated grounding/rejection/retry tests and a manually reviewed 12-scenario deterministic benchmark now exist. The configured-provider runner is ready, but a Gemini run remains unverified because no API key is configured in this workspace.
  - **Resolved 2026-08-04:** Regression tests now cover historical percentage units in shared formatting, the history page, report detail, and Markdown export.
  - **Resolved 2026-08-05:** A pypdf regression reads the generated PDF from memory and verifies every non-empty, sanitized Markdown line is extractable from the PDF text. The test also exposed and fixed leaked single-asterisk emphasis markers.
  - **Resolved 2026-08-05:** Scheduler contention and PostgreSQL advisory-lock SQL are tested; admin job routes have explicit 401/403/allow coverage.
  - No accessibility or performance tests.

  ### Documentation gaps

  - Root README and architecture document still describe Phase 0.
  - Historical docs still say sentiment is a placeholder.
  - **Resolved 2026-08-04:** AI documentation now matches the implemented async retry and per-attempt timeout behavior.
  - Frontend docs claim every insight has evidence and formatters/tables are single-source, which the code contradicts.
  - No AI chat, deployment, accessibility, performance, or walkthrough documentation.

  ## 4. Current Project State

  This is not merely “around Phase 8.” It has a strong, tested backend foundation and a mostly implemented Reports workflow, but Phase 8 sits on unresolved Phase 4–7 gaps.

  Verification results:

  - Backend: 219 passed
  - Backend coverage: 97% overall
  - Frontend unit tests: 36 passed
  - Frontend Playwright E2E: 2 passed against the rebuilt Docker Compose stack
  - Alembic: single head at 0007_reports
  - Frontend production build: passed using webpack
  - Default Turbopack build could not be verified because this execution environment prohibited its internal port binding
  - Frontend lint: passed
  - Ruff: configured but unavailable
  - Docker/live-provider flows: not started during this read-only audit

  The next logical task is a phase-completion and correctness pass—not Phase 9.

  ## 5. Recommended Next Phase

  Resume at Phase 8 closure, while treating inherited Phase 4–7 defects as prerequisites.

  Recommended order:

  1. **Completed 2026-08-04:** Correct historical units across the history UI, report detail, Markdown, and PDF; add regression tests.
  2. Close Phase 6 AI guarantees:
      - **Completed 2026-08-04:** enforce timeout/non-blocking Gemini calls;
      - **Completed 2026-08-04:** validate model output against supplied evidence;
      - **Completed 2026-08-04:** add and manually review the required 12-scenario benchmark (deterministic provider; live Gemini remains credential-dependent).

  3. Close Phase 7:
      - **Completed 2026-08-04:** dashboard watchlist;
      - **Completed 2026-08-04:** market technical summary and economic events;
      - **Completed 2026-08-04:** evidence on every AI narrative;
      - **Completed 2026-08-05:** browser E2E coverage for the Phase 7 acceptance flow.

  4. Close Phase 8:
      - **Completed 2026-08-05:** exact screen/Markdown/PDF content parity;
      - **Completed 2026-08-05:** report-page integration and real-stack export E2E tests;
      - **completed 2026-08-04:** fix frontend lint.

  5. Refresh environment templates and documentation.
  6. Only then start Phase 9 AI Chat.

  No files were changed. The pre-existing dirty worktree entries (CLAUDE.md deletion plus untracked .mcp.json and AGENTS.md) were left untouched.
