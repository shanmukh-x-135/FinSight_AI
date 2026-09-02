# Frontend components and research workspaces

Phase 11C adds the `/strategies` research workspace. `StrategyRuleBuilder`
serializes explicit AND/OR/NOT trees, while `BacktestChart` renders responsive
strategy, benchmark, drawdown, entry, and exit traces from persisted replay
results. The page reuses the existing workspace panels, tables, badges, and
trend values; chart evidence is also represented in text metrics and the trade
audit table. See [Strategy Backtesting](backtesting.md).

Phase 11D adds `RobustnessAnalysisView` beneath a completed replay. It adapts
the existing dense analytics-card pattern into a decomposable score, accessible
progress indicators, chronological train/test cards, sensitivity comparisons,
and reusable regime-performance tables. See
[Strategy Backtesting](backtesting.md).

Phase 11E adds `PortfolioRiskView`: compact risk KPI cards, an accessible CSS
correlation heatmap, contribution and sector-deviation tables, regime rows,
clearly labeled stress estimates, and a non-mutating before/after form. The
layout follows the existing financial-stat card hierarchy and contains wide
matrices within local horizontal scrollers. See [Portfolio](portfolio.md).

Phase 7 turns the API into an application. The rule the roadmap insists on:
**build the shared component library first, screens second** — the Analytics
template only pays off if the components underneath are genuinely reused, not
copy-pasted per screen. Every screen below is composed from the same small set
of components, and every AI insight uses the same evidence expander.

## Design system

- **Semantic colour:** green = up/positive, red = down/negative, blue = AI /
  interactive, amber = risk/warning, with explicit delayed, stale, selected,
  and confidence tokens. Icons and text accompany state colour. Helpers
  `signClass` / `toneOf` in `lib/utils.ts` keep signed values consistent.
- **Icons:** Lucide (`lucide-react`).
- **Hierarchy:** primary surfaces use visual weight, spacing, and typography;
  supporting evidence uses quieter surfaces and dividers rather than another
  grid of equally bordered cards.
- **Typography:** display, page heading, section heading, label, metadata, and
  financial-number roles are explicit. Prices, ratios, percentages, and tables
  use tabular numerals; dense research values can use the mono numeric role.
- **Layout:** a compact collapsible desktop rail, restrained contextual topbar,
  five-destination mobile dock, and complete mobile drawer preserve every route
  without a horizontally scrolling navigation strip.
- **Surfaces:** `surface-primary` and `surface-subtle` define the small elevation
  vocabulary; `Panel` no longer applies a visible border to every section.
- **Formatting:** `money` / `pct` / `signClass` (`lib/utils.ts`) — one source of
  truth for ₹ and % rendering across screens.

The global command palette opens with `⌘K` / `Ctrl+K`, supports arrow/Enter/Esc
keyboard operation, searches NIFTY 100 instruments, and provides deterministic
navigation to market, portfolio, watchlist, research, strategies, movers,
reports, and the AI workspace. Basic navigation never depends on an LLM.

## Shared component library (`frontend/components/`)

| Component | Props (summary) | Purpose |
|-----------|-----------------|---------|
| `MetricCard` | `label, value, sub?, tone?, icon?` | A single KPI tile. `tone` (`positive`/`negative`/`neutral`/`default`) colours the value; `toneOf(n)` derives it from a signed number. |
| `StockCard` | `symbol, name?, sector?, price?, changePercent?` | Compact quote tile for movers/opportunities; colours the change by sign. |
| `DashboardWatchlist` | `items, maxItems?` | Compact user-watchlist card with real quotes, pin emphasis, empty/truncated states, and management navigation. |
| `TechnicalSummaryCard` | `summary` | Market-wide latest RSI, EMA, MACD, and ATR aggregates computed by the backend. |
| `EconomicEventsCard` | `calendar` | Horizontally scrollable, provider-attributed India event cards with explicit unavailable/unconfigured states. |
| `AIInsightCard` | `title, narrative, evidence, action?, confidence?` | Standard container for any AI-written insight. Evidence is required at compile time, so every narrative mounts the same disclosure. Never computes anything. |
| `AIAnalysisState` | `status, message` | Shared honest empty/unavailable state for Analytics-template AI slots; prevents service failures from looking like unfinished features. |
| `EvidencePanel` | `evidence[], risks?, confidence?, historicalContext?, extra?` | **Research Mode "Show Evidence"** disclosure. The one reusable expander behind every AI insight — reveals the real indicators, historical analogs, risks, and confidence bar. |
| `Heatmap` | `cells: {label, value, sub?}[]` | Sector heatmap — a grid of tiles coloured green/red by signed value, intensity by magnitude. Dependency-free (no chart lib). |
| `StockHeatmap` | `stocks: HeatmapStock[]` | Compact, sector-grouped, keyboard-accessible research map for up to 100 membership-scoped stocks with return, RSI, and news availability. |
| `SectorRotation` | `rows: SectorRotation[]` | Responsive 1D/5D/20D sector-return table with deterministic leader/improving/weakening/laggard regimes. |
| `DataTable<T>` | `columns, rows, rowKey, loading?, loadingMessage?, emptyMessage?` | Generic responsive table with shared loading/empty states; used for gainers/losers/holdings/watchlist/similar-sessions instead of bespoke `<table>` markup. |

`EvidencePanel` and `AIInsightCard` are client components (`"use client"`) — the
expander holds toggle state. The rest are pure/presentational, so they render in
any context and are unit-tested directly.

## Page composition

Analytical and management routes compose `PageHeader`, `Panel`, `SectionHeader`,
`DataState`, metric cards and domain components directly. This keeps route data
flow visible while preserving one shared visual system. The Dashboard remains a
bespoke summary composition assembled from those same components.

## Screens → components → data

| Screen | Template | Key components | Backend data |
|--------|----------|----------------|--------------|
| **Dashboard** (`/dashboard`) | bespoke | `MetricCard`, `DashboardWatchlist`, `AIInsightCard` + `EvidencePanel`, `StockCard` | `GET /dashboard/summary` (one batched call) |
| **Market Intelligence** (`/market`) | Analytics | universe selector, `MetricCard`, `StockHeatmap`, `SectorRotation`, `TechnicalSummaryCard`, `EconomicEventsCard`, `DataTable`, `AIInsightCard` + `EvidencePanel` | `GET /market/universes`, batched `GET /market/workspace`, and `GET /recommendations` |
| **Historical Similarity** (`/history`) | Analytics | `MetricCard`, model/coverage badges, deterministic factor cards, `DataTable`, `AIInsightCard` + `EvidencePanel` | `GET /history/similar` |
| **Portfolio** (`/portfolio`) | Analytics | `MetricCard`, `DonutChart`, `AIInsightCard` + `EvidencePanel`, `DataTable` | `GET /portfolios/{id}/analytics` + `GET /recommendations` (filtered to holdings) |
| **Watchlist** (`/watchlist`) | Management | `DataTable` + form | `GET/POST/PATCH/DELETE /watchlist` |
| **AI Assistant** (`/chat`) | Conversation | message stream, recent-question history, `EvidencePanel` | `POST /chat?stream=true`, `GET/DELETE /chat/history` |
| **Discover** (`/discover`) | Research workflow | validated filter chips, `DataTable`, saved-screen cards | `POST /discovery/screen`, saved-screen CRUD/replay |
| **EOD Operations** (`/operations`, administrator only) | Operational status | freshness strip, run summary, step status cards, failure guidance | `GET /admin/jobs/eod/status` |

The Assistant uses the same restrained card, type, colour, and evidence language
as the analytical screens. Its desktop history rail moves below the conversation
on narrow screens. Server-sent events progressively render validated prose; the
completed response exposes confidence, sources, risks, and the shared evidence
panel. Suggested questions are only input shortcuts and never mocked answers.
Stock, portfolio, and news contextual actions use the same mechanism: they open
the Assistant with a visible prefilled question while its evidence pipeline
remains authoritative.

### The batched dashboard endpoint

To avoid the per-card round trips the roadmap warns against, the dashboard is
backed by a single **`GET /api/v1/dashboard/summary`** (`app/dashboard/`). It
composes — it generates nothing new: market slice, deterministic AI market
summary, portfolio snapshot (or `null`), the authenticated user's quote-enriched
watchlist, evidence-backed opportunities, risk alerts, and the
historical-similarity slice. Rankings and evidence remain deterministic (Phase
6); the endpoint is reproducible for identical data.

## Research Mode — "Show Evidence" everywhere

The same `EvidencePanel` is required by `AIInsightCard` on the Dashboard, Market,
History, Portfolio, and Report screens, so evidence looks and behaves identically
on every AI insight. Shared evidence builders render the *real* deterministic
market, portfolio, historical, recommendation, and executive-summary inputs,
never a static mock.

## Responsive behaviour

- Desktop: compact collapsible sidebar with full route coverage, visible active
  state, command search, account context, theme, and session controls.
- Mobile: five primary destinations remain one tap away; the drawer exposes the
  complete product map and account/session actions. Summary grids collapse to
  one/two columns and wide tables scroll inside their own container.

## Tests

- **Component tests** (`components/*.test.tsx`, Vitest + Testing Library):
  `MetricCard`, `DataTable`, `AIAnalysisState`, `EvidencePanel`,
  `AIInsightCard`, and `DashboardWatchlist` — including table
  loading/empty/actions, explicit AI empty/unavailable outcomes, evidence
  disclosure, and populated, pinned, empty, and truncated watchlist states.
  Run with `npm test`.
- **Assistant tests:** stream parsing across arbitrary network chunks, truncated
  stream rejection, suggested questions, private-history load/delete, and
  evidence/confidence/source/risk rendering.
- **Type/build:** `npm run build` type-checks every screen against the API
  client types in `lib/api.ts`.
- **Browser E2E:** `npm run test:e2e` rebuilds and waits for the real Docker
  Compose stack, idempotently provisions the test account, logs in through the
  UI, checks all four summary cards plus the watchlist and AI summary, then
  expands `Show Evidence` and verifies real breadth content. Install the local
  browser once with `npx playwright install chromium`. Use
  `E2E_BASE_URL`, `E2E_API_URL`, `E2E_EMAIL`, and `E2E_PASSWORD` with
  `npm run test:e2e:external` when testing an already-running remote stack.
  Set `E2E_PHASE10D_LIVE=1` for the populated-staging journey, which verifies
  the real 50-stock market table, stock price chart, regime model/version and
  coverage disclosures, deterministic factor explanations, and forward-outcome
  table. The mocked visual workspace separately checks those additions at
  desktop and mobile widths.
