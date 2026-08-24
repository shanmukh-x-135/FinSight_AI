# Portfolio Management (Phase 3)

Authenticated users hold portfolios and a watchlist; the system computes
valuation, P&L, allocation, diversification, concentration, volatility, a health
score, and a risk level — deterministically, from Phase 2's market data. No AI.

## Ownership (security)

Every portfolio/holding/watchlist query is scoped to the authenticated
`user_id` (directly, or via a pre-verified parent portfolio). Not-found and
not-owned both return **404** — a user can never read or mutate another user's
data, and existence isn't leaked. This is covered by explicit cross-user tests.

## Data model (migration `0004_portfolio`)

- **portfolios** — `user_id (FK, cascade), name`.
- **portfolio_items** — `portfolio_id (FK, cascade), stock_id (FK stocks),
  quantity, avg_buy_price`; unique on `(portfolio_id, stock_id)`.
- **watchlist_items** — `user_id (FK, cascade), stock_id (FK stocks), pinned,
  sort_order`; unique on `(user_id, stock_id)`.

Holdings reference `stocks` (Phase 2), so adding a holding requires a **tracked**
stock (else `404 stock_not_tracked`) — analytics need its price history.

## Endpoints (`/api/v1`, all auth-protected)

| Endpoint | Purpose |
|----------|---------|
| `POST/GET /portfolios` | Create / list portfolios |
| `GET/PUT/DELETE /portfolios/{id}` | Detail (holdings) / rename / delete |
| `GET /portfolios/{id}/analytics` | Full analytics (below) |
| `POST /portfolios/{id}/items` | Add holding `{symbol, quantity, avg_buy_price}` |
| `PUT/DELETE /portfolios/{id}/items/{item_id}` | Update / remove holding |
| `GET/POST /watchlist` | List (with quotes) / add `{symbol}` |
| `PATCH/DELETE /watchlist/{item_id}` | Pin/sort / remove |

## Analytics — how each metric is computed

Computed by pure functions (`app/portfolio/analytics.py`), unit-tested against a
hand-built portfolio. For each holding with quantity `q`, average buy price `a`,
current price `c` (latest close), previous close `p`:

- **market_value** = `q·c` · **cost_basis** = `q·a`
- **unrealized_pnl** = `market_value − cost_basis`
- **return_percent** = `unrealized_pnl / cost_basis × 100`
- **daily_pnl** = `q·(c − p)`
- **weight** = `market_value / total_value`

Portfolio-level:

- **total_value / total_cost / total_unrealized_pnl / total_return_percent** — sums and the aggregate return.
- **daily_pnl_percent** = `daily_pnl / (total_value − daily_pnl) × 100` (vs yesterday's value).
- **concentration (HHI)** = `Σ weightᵢ²` (0–1; higher = more concentrated).
- **diversification_score** = `(1 − HHI) × 100` (0–100; higher = more diversified).
- **top_holding_weight_percent** = the largest single-holding weight.
- **sector_allocation** = market value grouped by `stock.sector` (sorted desc).
- **volatility_percent** = market-value-weighted `ATR / price × 100` across holdings (uses Phase 2's ATR-14; `null` unless every holding has both price and ATR, so partial coverage is never presented as a complete portfolio metric).
- **health_score** (0–100) = a transparent weighted blend:
  `0.4 × diversification_score + 0.3 × (100 − top_holding_weight) + 0.3 × clamp(50 + total_return_percent, 0, 100)`.
- **risk_level** — from concentration: `high` if top weight ≥ 50%, `medium` if ≥ 30%, else `low`.

Price availability is explicit: if any holding has no current close,
`valuation_complete` is false, `unpriced_symbols` identifies it, and valuation,
return, allocation, health, and risk metrics are `null`/`unknown` rather than
reporting a false zero value or total loss. The known cost basis remains
available. If only a previous close is missing, valuation remains valid while
daily P&L is withheld.

Weights/thresholds live in `app/portfolio/constants.py`.

### Worked example (from the unit tests)

Two holdings — H1: 10 @ 100 (price 110, prev 108, Tech); H2: 5 @ 200 (price 180,
prev 185, Energy):

- values 1100 / 900 → weights 55% / 45% → HHI 0.505 → diversification **49.5**
- total return **0%**, daily P&L **−5** (**−0.2494%**), volatility **5.0%**
- health = `0.4·49.5 + 0.3·45 + 0.3·50` = **48.3**, risk **high**

Verified live too: a real RELIANCE+TCS portfolio produced hand-checkable returns
(+8.98% / −21.15%), diversification 49.87, health 46.87.

## Frontend

- **Portfolio page** (`/portfolio`) — first use of the **Analytics page template**
  with a responsive, client-only Plotly sector-allocation donut. Its compact
  external legend remains readable without hover, while Plotly supplies precise
  interactive percentages; browser-only loading is isolated behind
  `next/dynamic` so App Router prerendering remains safe.
  (Summary Cards → Charts → AI Analysis → Details): metric cards, a sector
  **allocation donut**, a health card, and the holdings table with add/edit/remove.
- **Watchlist page** (`/watchlist`) — add/remove/pin with live quotes.

## Testing

`backend/tests/portfolio/`: pure analytics goldens + edge cases; portfolio CRUD,
holdings, analytics-on-real-prices, duplicate/untracked errors, and cross-user
ownership; watchlist CRUD, quotes, pin/sort, dedupe, and ownership. ~99% coverage.
