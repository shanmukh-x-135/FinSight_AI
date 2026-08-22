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

All additions use the standard response envelope. Static collection routes are declared before dynamic symbol routes.

## Screen coverage

- Overview: market participation, KPI strip, intelligence brief, watchlist, opportunities, and risk monitor.
- Market: searchable/filterable/sortable dense screener, sector map, technical summary, economic events, and evidence-backed signals.
- Stock detail: OHLCV/EMA chart, volume, technicals, annual range, sentiment, tagged news, watchlist action, and AI interpretation.
- Portfolio: allocation, health, contribution, position intelligence, holdings, and existing CRUD.
- Watchlist: compact monitoring table with price, change, RSI, trend, sentiment, pinning, and removal.
- Research: historical outcome chart, current-state inputs, confidence interval, evidence, and analogue table.
- Reports, AI chat, and Settings adopt the shared workspace hierarchy without changing their existing workflows.

## Verification

- Backend API tests cover the batched screener, bounded chronological price history, latest sentiment, and watchlist signals.
- Frontend unit/component tests cover existing interactions and redesigned AI states.
- A Playwright visual smoke test renders every major authenticated route with deterministic test fixtures, checks document-level horizontal overflow, and captures desktop screenshots. Overview is additionally checked at 390×844 and 768×1024.
- The native integration E2E suite remains the authoritative real-stack test and requires Docker Compose.
