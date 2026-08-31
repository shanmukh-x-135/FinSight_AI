# Repository and Codebase Consolidation

Phase 12 followed the feature freeze. Its purpose was to reduce maintenance
surface without changing analytical behavior. The worktree already contained
the Phase 11 feature set, so no historical commit represented the exact
feature-freeze snapshot; metrics that were not captured at the opening audit
are marked unavailable rather than reconstructed inaccurately.

## Inventory and decisions

- No generated build, cache, coverage, Playwright, FAISS, log, screenshot, or
  real environment file is tracked. Alembic migrations `0001`–`0019` remain.
- Root and frontend ignore rules cover real `.env*` files while preserving
  examples, Python/Node caches, build output, test output, FAISS, logs,
  screenshots, editor/OS files, TypeScript build state, and local PostgreSQL.
- All 18 backend and 10 frontend runtime declarations have active imports or
  operational entry points. No runtime dependency was removed merely to lower a
  count. Backend dev dependencies (7), frontend dev dependencies (17), and the
  three optional AI/ML declarations remain separated from runtime.
- The unused `AnalyticsPageTemplate` was deleted. Routes compose the shared
  workspace primitives directly; the used report template remains.
- The unconsumed strategy rule-options endpoint was removed. The standalone
  dashboard freshness endpoint was also removed because the same typed data is
  already included in dashboard summary and administrator EOD status.
- Fourteen local UTC normalization/clock helpers were replaced by
  `app.shared.time`. The scheduler keeps only its explicit naive-datetime
  compatibility branch.
- Seven temporary Phase 11 notes were merged into permanent backtesting,
  discovery, operations, universe, news, portfolio, frontend, README, and
  architecture documentation.
- Tests were retained unless their public surface was deliberately removed. One
  duplicate freshness endpoint test disappeared with that route; behavior
  remains exercised through dashboard and operations contracts. A stale chat
  E2E source-label assertion was aligned with the real `Market analytics` label.

## API consolidation

`GET /api/v1/market/workspace` is the typed non-personalized Market-page
contract. One universe snapshot now supplies stocks, breadth, sectors and
heatmap; technical, rotation, recent sentiment and economic-calendar context
are composed server-side. The browser performs one membership-scoped workspace
request per selection instead of eight independent requests. Existing focused
market endpoints remain for stock detail and compatible external consumers.

The OpenAPI surface changed from 73 to 72 operations: one aggregate endpoint
was added and two unconsumed duplicate endpoints were removed.

## Quality metrics

| Metric | Feature-freeze / audit baseline | Consolidated result |
|---|---:|---:|
| Market workspace HTTP requests per universe | 8 | 1 |
| Local UTC helper implementations | 14 | 0 |
| Obvious dead components | 1 | 0 |
| Redundant public endpoints | 2 | 0 |
| API operations | 73 | 72 |
| Temporary Phase 11 notes | 7 | 0 |
| Permanent Markdown documents | 26 | 30 |
| Production dependencies | 28 | 28, all retained with evidence |
| Backend + frontend source modules | 238 | 237 |
| Backend tests collected | 494 | 493 (one redundant endpoint test removed) |
| Frontend tests | 78 | 78 |
| Source LOC | not captured at feature freeze | 27,499 |
| Python functions / average size | not captured at feature freeze | 711 / 17.5 lines |
| Ruff C901 hotspots | 14 audited | 14 retained; no release-risk rewrites |
| Production static JavaScript | not captured at feature freeze | 2.6 MB |
| Backend image size | unavailable: Docker daemon absent | not fabricated |

The 14 complexity findings are concentrated in the chat draft assembler,
grounding validator, strict screener parser, strategy engine/data loader,
universe sync, report renderer, yfinance adapter, and feature engineering.
They are explicit future refactor candidates; their tests are comprehensive,
and splitting them during release consolidation would have increased regression
risk without removing duplication.

## Verification snapshot

- Backend: 489 fast tests passed, 4 PostgreSQL tests skipped by default, 23.94 s.
- PostgreSQL: all 4 opt-in integration tests passed against PostgreSQL 16 after
  migration to `0019_saved_screens`, 1.59 s.
- Frontend: 78 tests passed in 4.63 s; ESLint and TypeScript passed.
- Production build: Next.js 16 Webpack build passed in 8.47 s. Webpack is the
  configured build path because Turbopack cannot allocate its internal port in
  the current host environment.
- Browser: 2 responsive visual tests passed across desktop/laptop/mobile and 14
  routes; 3 real-stack dashboard/report/chat journeys passed. The populated
  staging-only Phase 10D journey remains opt-in by design.
- Secret-pattern scan returned no matches. Generated/local files were confirmed
  ignored. Alembic reports one head at `0019_saved_screens`.
