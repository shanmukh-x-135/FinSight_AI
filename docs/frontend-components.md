# Frontend components & page templates (Phases 7–9)

Phase 7 turns the API into an application. The rule the roadmap insists on:
**build the shared component library first, screens second** — the Analytics
template only pays off if the components underneath are genuinely reused, not
copy-pasted per screen. Every screen below is composed from the same small set
of components, and every AI insight uses the same evidence expander.

## Design system

- **Semantic colour:** green = up/positive, red = down/negative, blue = AI /
  interactive, amber = risk/warning. Helpers `signClass` / `toneOf` in
  `lib/utils.ts` map a signed number to the right class so colour is consistent.
- **Icons:** Lucide (`lucide-react`).
- **Layout:** card-based (Shadcn `Card`), `Analytics` page template for the
  analytical screens.
- **Formatting:** `money` / `pct` / `signClass` (`lib/utils.ts`) — one source of
  truth for ₹ and % rendering across screens.

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
| `DataTable<T>` | `columns, rows, rowKey, loading?, loadingMessage?, emptyMessage?` | Generic responsive table with shared loading/empty states; used for gainers/losers/holdings/watchlist/similar-sessions instead of bespoke `<table>` markup. |

`EvidencePanel` and `AIInsightCard` are client components (`"use client"`) — the
expander holds toggle state. The rest are pure/presentational, so they render in
any context and are unit-tested directly.

## Page templates

The design doc defines three templates; Phase 7 uses two:

| Template | Shape | Screens |
|----------|-------|---------|
| **Analytics** (`components/templates/AnalyticsPageTemplate.tsx`) | Header → Summary Cards → Charts → AI Analysis → Details/Tables | Market Intelligence, Historical Similarity, Portfolio |
| **Management** (composed inline) | Header → Table/Form → Actions | Watchlist |

The Dashboard is a bespoke composition (its own summary → AI summary →
watchlist → opportunities → risk alerts → movers), assembled from the same
shared components.

## Screens → components → data

| Screen | Template | Key components | Backend data |
|--------|----------|----------------|--------------|
| **Dashboard** (`/dashboard`) | bespoke | `MetricCard`, `DashboardWatchlist`, `AIInsightCard` + `EvidencePanel`, `StockCard` | `GET /dashboard/summary` (one batched call) |
| **Market Intelligence** (`/market`) | Analytics | `MetricCard`, `Heatmap`, `TechnicalSummaryCard`, `EconomicEventsCard`, `DataTable`, `AIInsightCard` + `EvidencePanel` | `GET /market/{breadth,gainers,losers,sectors,technical-summary,economic-events}` + `GET /recommendations` |
| **Historical Similarity** (`/history`) | Analytics | `MetricCard`, `DataTable`, `AIInsightCard` + `EvidencePanel` | `GET /history/similar` |
| **Portfolio** (`/portfolio`) | Analytics | `MetricCard`, `DonutChart`, `AIInsightCard` + `EvidencePanel`, `DataTable` | `GET /portfolios/{id}/analytics` + `GET /recommendations` (filtered to holdings) |
| **Watchlist** (`/watchlist`) | Management | `DataTable` + form | `GET/POST/PATCH/DELETE /watchlist` |
| **AI Assistant** (`/chat`) | Conversation | message stream, recent-question history, `EvidencePanel` | `POST /chat?stream=true`, `GET/DELETE /chat/history` |

The Assistant uses the same restrained card, type, colour, and evidence language
as the analytical screens. Its desktop history rail moves below the conversation
on narrow screens. Server-sent events progressively render validated prose; the
completed response exposes confidence, sources, risks, and the shared evidence
panel. Suggested questions are only input shortcuts and never mocked answers.

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

- Desktop: full top nav (Dashboard · Market · History · Portfolio · Watchlist ·
  Reports · Assistant · Settings).
- Mobile: the top nav collapses to a horizontally scrollable strip of the
  prioritized screens; summary grids collapse to one/two columns; wide tables
  scroll inside their own container. Advanced analytics remain desktop-first.

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
