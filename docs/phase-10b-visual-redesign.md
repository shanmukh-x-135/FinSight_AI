# Phase 10B — Visual-First Research Workspace

Phase 10B converts the authenticated product into a dense, dark-first financial research workspace while preserving the Phase 0–9 data contracts and deterministic-analysis boundary.

## Design system

- Compact desktop rail and mobile bottom navigation cover Overview, Market, Portfolio, Watchlist, Research, Reports, AI, and Settings.
- The default dark theme uses finance-native slate surfaces, blue interaction accents, and semantic green/red/amber tokens. A session theme toggle provides a light alternative.
- Shared `PageHeader`, `SectionHeader`, `Panel`, `MetricCard`, `DataTable`, `StatusBadge`, `TrendValue`, loading skeletons, and explicit empty/error/unavailable states keep information hierarchy consistent.
- Positive and negative values include direction icons or text, not colour alone. Tables retain captions, keyboard-accessible actions, horizontal containment, and responsive layouts.

## Data visualization

- Plotly's finance distribution is loaded only on routes that render analytical charts and supports responsive candlestick, line, bar, and donut charts.
- Stock research uses persisted daily OHLCV and indicators for candlesticks, volume, EMA 20/50, technical readings, fundamentals, and news sentiment.
- Portfolio charts show real allocation and unrealized P&L contribution. FinSight does not store transaction timing, so Phase 10B deliberately does not fabricate an equity curve.
- Historical research visualizes actual analogue outcomes and confidence intervals. Copy explicitly frames this as context rather than prediction.

## API additions

- `GET /api/v1/market/stocks` returns one batched active-universe snapshot with quotes, RSI, EMAs, MACD histogram, and deterministic trend.
- `GET /api/v1/market/stocks/{symbol}/prices?limit=...` returns bounded daily OHLCV in chronological order.
- `GET /api/v1/news/sentiment` returns the latest sentiment for each active instrument.
- Watchlist rows now include RSI and deterministic trend from the existing batched market snapshot; no per-row queries were added.
- `GET /api/v1/dashboard/summary` remains the single Overview request and now composes sector performance, market-wide technical context, and latest universe sentiment alongside its existing data.

All additions use the standard response envelope. Static collection routes are declared before dynamic symbol routes.

## Screen coverage

- Overview: market participation, sector heatmap, sentiment distribution, KPI strip, intelligence brief, high-information watchlist, opportunities, and risk monitor.
- Market: searchable/filterable/sortable dense screener, watchlist actions, sector map, technical summary, economic events, and evidence-backed signals.
- Stock detail: OHLCV/EMA chart, volume, technicals, full stored fundamentals, annual range, sentiment, tagged news, watchlist action, AI interpretation, and an explicit capability state for unavailable stock-specific analogues.
- Portfolio: allocation, health, contribution, position intelligence, holdings, and existing CRUD. The equity-curve capability state explains why incomplete transaction history cannot support a truthful curve.
- Watchlist: searchable and sortable compact monitoring table with price, change, RSI, trend, sentiment, pinning, and removal.
- Research: historical outcome chart, direct current-vs-nearest feature comparison, current-state inputs, confidence interval, evidence, and analogue table.
- Reports add stored-data breadth, portfolio-health, analogue-outcome, and notable-news sentiment visuals.
- Reports, AI chat, and Settings adopt the shared workspace hierarchy without changing their existing workflows.

## Verification

- Backend API tests cover the batched screener, bounded chronological price history, latest sentiment, and watchlist signals.
- Frontend unit/component tests cover existing interactions and redesigned AI states.
- A Playwright visual smoke test renders all 10 major authenticated routes with deterministic fixtures at desktop (1440×1000), laptop (1180×900), and mobile (390×844) widths. All 30 combinations assert bounded document width and zero root horizontal scrolling, then capture full-page screenshots for inspection.
- The real-stack Playwright journeys cover dashboard evidence, grounded streaming chat with persistence/clear, and report generation/open/export. They run serially because the journeys intentionally mutate one shared account.
- Final Phase 10B verification: 357 backend tests passed (4 optional PostgreSQL integration tests skipped without `TEST_POSTGRES_URL`), Ruff passed, 55 frontend tests passed, ESLint passed, the Next.js production build passed, all 3 real-stack journeys passed against native PostgreSQL/FastAPI, and the 30-screen responsive visual sweep passed.
