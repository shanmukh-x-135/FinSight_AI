import { expect, test, type Page, type Route } from "@playwright/test";

const envelope = (data: unknown) => ({ success: true, message: "ok", data, timestamp: new Date().toISOString(), requestId: "visual-smoke" });
const quotes = [
  { symbol: "RELIANCE.NS", name: "Reliance Industries", sector: "Energy", date: "2026-08-21", close: 1428.5, previous_close: 1402.2, change: 26.3, change_percent: 1.88, volume: 8_220_000, rsi_14: 61.2, ema_20: 1401, ema_50: 1368, macd_histogram: 4.2, trend: "bullish" },
  { symbol: "TCS.NS", name: "Tata Consultancy Services", sector: "Technology", date: "2026-08-21", close: 3125.4, previous_close: 3160.1, change: -34.7, change_percent: -1.1, volume: 2_410_000, rsi_14: 42.8, ema_20: 3168, ema_50: 3210, macd_histogram: -8.1, trend: "bearish" },
  { symbol: "HDFCBANK.NS", name: "HDFC Bank", sector: "Financial Services", date: "2026-08-21", close: 1964.2, previous_close: 1951.6, change: 12.6, change_percent: .65, volume: 6_810_000, rsi_14: 55.4, ema_20: 1948, ema_50: 1912, macd_histogram: 2.1, trend: "bullish" },
];
const breadth = { advancers: 31, decliners: 18, unchanged: 1, total: 50, advance_decline_ratio: 1.72 };
const usage = { schema_version: 1, configured_backend: "deterministic", actual_backends: ["deterministic"], requested_models: [], model_versions: [], generation_count: 1, provider_attempt_count: 0, provider_response_count: 0, fallback_count: 0, usage: { prompt_tokens: null, candidate_tokens: null, total_tokens: null, cached_tokens: null, thoughts_tokens: null }, items: [] };
const rec = { symbol: "RELIANCE.NS", name: "Reliance Industries", sector: "Energy", action: "watch", confidence: 72, score: .64, evidence: ["RSI is 61.2", "Price is above its 20-day EMA", "Positive MACD histogram"], risks: ["Energy exposure is concentrated"], historical_context: { bullish_probability: .62, sample_size: 10 }, explanation: "Momentum and breadth evidence are constructive, while concentration remains the primary risk." };
const portfolio = { portfolio_id: 1, name: "Core Equity", total_value: 598210, total_cost: 560000, total_unrealized_pnl: 38210, total_return_percent: 6.82, daily_pnl: 4930, daily_pnl_percent: .83, number_of_holdings: 3, number_of_sectors: 3, top_holding_weight_percent: 42, concentration_hhi: .35, diversification_score: 74, volatility_percent: 1.18, health_score: 78, risk_level: "medium", valuation_complete: true, unpriced_symbols: [], sector_allocation: [{ sector: "Energy", value: 251248, weight_percent: 42 }, { sector: "Technology", value: 187524, weight_percent: 31.35 }, { sector: "Financial Services", value: 159438, weight_percent: 26.65 }], holdings: quotes.map((q, index) => ({ id: index + 1, symbol: q.symbol, name: q.name, sector: q.sector, quantity: index === 0 ? 176 : index === 1 ? 60 : 81, avg_buy_price: q.close * .94, current_price: q.close, previous_close: q.previous_close, market_value: [251216, 187524, 159100][index], cost_basis: [236200, 176271, 147529][index], unrealized_pnl: [15016, 11253, 11571][index], return_percent: [6.36, 6.38, 7.84][index], daily_pnl: [4628, -2082, 1021][index], weight_percent: [42, 31.35, 26.65][index] })) };
const historySummary = { date: "2026-08-21", avg_return: .006, pct_advancers: .62, advance_decline_ratio: 1.72, avg_rsi: 56.4, feature_version: "market_regime_v1", median_rsi: 56.1, median_atr_percent: 1.7, median_relative_volume: 1.08, coverage_ratio: .98, usable_constituents: 49, expected_constituents: 50, membership_mode: "available_data_proxy", quality_flags: ["historical_membership_unknown"], breadth_regime: "broad_positive", momentum_regime: "positive", volatility_regime: "normal" };
const factor = (name: string, score: number) => ({ factor: name, similarity_score: score, explanation: `${name[0].toUpperCase()}${name.slice(1)} features have ${(score * 100).toFixed(0)}% group similarity after robust normalization.` });
const history = { feature_version: "market_regime_v1", vector_dimension: 25, normalization_method: "median_iqr_clip8_v1", query_date: "2026-08-21", query_summary: historySummary, similar_sessions: Array.from({ length: 6 }, (_, index) => ({ ...historySummary, date: `2025-0${index + 1}-14`, avg_return: .004 - index * .001, pct_advancers: .58, advance_decline_ratio: 1.4, avg_rsi: 54, median_rsi: 54, similarity_score: .94 - index * .035, distance: .1 + index * .05, next_day_return: index === 4 ? -.007 : .006 + index * .001, outcome: index === 4 ? "bearish" : "bullish", next_session_breadth: .6, forward_5_session_return: .018 - index * .002, forward_5_session_drawdown: -.012, forward_5_session_upside: .025, matching_factors: [factor("breadth", .91), factor("momentum", .86), factor("sector", .81)], divergence_factors: [factor("macro", .52), factor("volume", .64)] })), statistics: { k: 10, sample_size: 6, bullish_count: 5, bearish_count: 1, neutral_count: 0, bullish_probability: .833, avg_next_day_return: .006, median_next_day_return: .007, std_next_day_return: .005, best_case_return: .011, worst_case_return: -.007, ci_low: .001, ci_high: .01 } };
const report = { id: 12, user_id: 1, report_type: "daily", created_at: "2026-08-21T16:00:00Z", sections: { executive_summary: "Market participation is constructive, led by energy and financial services, while technology remains under pressure.", market_summary: { narrative: "Breadth and momentum are positive but selective.", breadth, gainers: [quotes[0], quotes[2]], losers: [quotes[1]] }, portfolio_summary: { narrative: "The portfolio is profitable with moderate concentration risk.", total_value: portfolio.total_value, total_cost: portfolio.total_cost, total_return_percent: portfolio.total_return_percent, health_score: portfolio.health_score, risk_level: portfolio.risk_level, diversification_score: portfolio.diversification_score, number_of_holdings: portfolio.number_of_holdings, valuation_complete: true, unpriced_symbols: [] }, historical_summary: { narrative: "Five of six nearest sessions closed higher the next day.", statistics: history.statistics }, recommendations: [rec], risk_alerts: [], news: { notable: [{ title: "Reliance expands clean-energy investment", sentiment_label: "positive", tags: ["RELIANCE.NS"] }] }, meta: { prompt_version: "1.0", llm_backend: "deterministic", generated_at: "2026-08-21T16:00:00Z", generation: usage } } };

async function mockWorkspace(page: Page) {
  await page.addInitScript(() => localStorage.setItem("finsight_access", "visual-token"));
  await page.route("**/api/v1/**", async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let data: unknown = null;
    if (path === "/api/v1/user/me") data = { id: 1, email: "researcher@finsight.ai", is_active: true, created_at: "2026-01-01", preferences: { risk_tolerance: "moderate", investment_horizon: "long_term", preferred_market: "NSE", preferred_sectors: ["Technology", "Energy"] } };
    else if (path === "/api/v1/user/preferences") data = { risk_tolerance: "moderate", investment_horizon: "long_term", preferred_market: "NSE", preferred_sectors: ["Technology", "Energy"] };
    else if (path === "/api/v1/dashboard/summary") data = { market: { breadth, gainers: [quotes[0], quotes[2]], losers: [quotes[1]] }, ai_market_summary: "Participation is constructive with advancers leading decliners. Momentum remains selective rather than universal.", portfolio, watchlist: quotes.map((q, index) => ({ id: index + 1, ...q, current_price: q.close, pinned: index === 0, sort_order: index })), sectors: [{ sector: "Energy", stock_count: 12, average_change_percent: 1.4 }, { sector: "Technology", stock_count: 14, average_change_percent: -.8 }, { sector: "Financial Services", stock_count: 16, average_change_percent: .6 }], technical: { as_of: "2026-08-21", stocks_with_indicators: 50, average_rsi: 56.4, bullish_rsi_count: 30, overbought_count: 3, oversold_count: 2, above_ema20_count: 31, above_ema50_count: 28, positive_macd_count: 29, average_atr_percent: 1.6 }, sentiment: quotes.map((q, index) => ({ symbol: q.symbol, latest_sentiment: [.42, -.18, .12][index] })), opportunities: [rec], risk_alerts: [], history, generation: usage };
    else if (path === "/api/v1/market/stocks") data = quotes;
    else if (path === "/api/v1/market/breadth") data = breadth;
    else if (path === "/api/v1/market/sectors") data = [{ sector: "Energy", stock_count: 12, average_change_percent: 1.4 }, { sector: "Technology", stock_count: 14, average_change_percent: -.8 }, { sector: "Financial Services", stock_count: 16, average_change_percent: .6 }];
    else if (path === "/api/v1/market/technical-summary") data = { as_of: "2026-08-21", stocks_with_indicators: 50, average_rsi: 56.4, bullish_rsi_count: 30, overbought_count: 3, oversold_count: 2, above_ema20_count: 31, above_ema50_count: 28, positive_macd_count: 29, average_atr_percent: 1.6 };
    else if (path === "/api/v1/market/economic-events") data = { provider: "Trading Economics", status: "ok", events: [{ event_id: "rbi", date: "2026-08-25T10:00:00Z", country: "India", category: "Interest Rate", name: "RBI policy minutes", importance: 3, reference: null, source: "RBI", source_url: null, actual: null, forecast: null, previous: null }] };
    else if (path === "/api/v1/news/sentiment") data = quotes.map((q, index) => ({ symbol: q.symbol, latest_sentiment: [.42, -.18, .12][index] }));
    else if (path === "/api/v1/recommendations") data = { watchlist: [rec], risk_alerts: [], generation: usage };
    else if (/\/market\/stocks\/[^/]+\/prices$/.test(path)) data = Array.from({ length: 90 }, (_, index) => { const close = 1320 + index * 1.2 + Math.sin(index / 5) * 18; return { date: new Date(Date.UTC(2026, 4, index + 1)).toISOString().slice(0, 10), open: close - 4, high: close + 10, low: close - 9, close, volume: 5_000_000 + index * 22000 }; });
    else if (/\/market\/stocks\/[^/]+\/indicators$/.test(path)) data = Array.from({ length: 90 }, (_, index) => ({ date: new Date(Date.UTC(2026, 4, index + 1)).toISOString().slice(0, 10), rsi_14: 48 + Math.sin(index / 7) * 14, ema_20: 1315 + index * 1.15, ema_50: 1300 + index, macd: 5, macd_signal: 3, macd_histogram: 2, bb_upper: 1450, bb_middle: 1400, bb_lower: 1350, atr_14: 19 }));
    else if (/\/market\/stocks\/[^/]+$/.test(path)) data = { ...quotes[0], industry: "Integrated Energy", exchange: "NSE", fundamentals: { market_cap: 19000000000000, pe_ratio: 24.8, eps: 57.6, dividend_yield: .7, week52_high: 1608, week52_low: 1115 } };
    else if (/\/news\/sentiment\//.test(path)) data = { symbol: "RELIANCE.NS", name: "Reliance Industries", latest_sentiment: .42, series: Array.from({ length: 14 }, (_, index) => ({ date: `2026-08-${String(index + 1).padStart(2, "0")}`, avg_sentiment: Math.sin(index / 3) * .5, article_count: 3 + index % 4, positive_count: 2, negative_count: 1, neutral_count: 1 })) };
    else if (path === "/api/v1/news") data = [{ id: 1, source: "Reuters", url: "https://example.com", title: "Reliance expands clean-energy investment", summary: "", published_at: "2026-08-21T08:00:00Z", sentiment_label: "positive", sentiment_score: .48, tags: ["RELIANCE.NS"] }];
    else if (path === "/api/v1/portfolios") data = [{ id: 1, name: "Core Equity", created_at: "2026-01-01", holding_count: 3 }];
    else if (path === "/api/v1/portfolios/1/analytics") data = portfolio;
    else if (path === "/api/v1/portfolios/1") data = { id: 1, name: "Core Equity", created_at: "2026-01-01", holdings: portfolio.holdings.map((holding) => ({ id: holding.id, symbol: holding.symbol, name: holding.name, sector: holding.sector, quantity: holding.quantity, avg_buy_price: holding.avg_buy_price })) };
    else if (path === "/api/v1/watchlist") data = quotes.map((q, index) => ({ id: index + 1, ...q, current_price: q.close, pinned: index === 0, sort_order: index }));
    else if (path === "/api/v1/history/similar") data = history;
    else if (path === "/api/v1/reports") data = [{ id: 12, report_type: "daily", created_at: "2026-08-21T16:00:00Z" }, { id: 11, report_type: "weekly", created_at: "2026-08-18T16:00:00Z" }];
    else if (path === "/api/v1/reports/12") data = report;
    else if (path === "/api/v1/chat/history") data = [];
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(envelope(data)) });
  });
}

test("major research screens remain responsive and visually inspectable", async ({ page }, testInfo) => {
  await mockWorkspace(page);
  const routes: { route: string; heading: string | RegExp }[] = [
    { route: "dashboard", heading: "Overview" },
    { route: "market", heading: "Market Intelligence" },
    { route: "market/RELIANCE.NS", heading: /RELIANCE\.NS/ },
    { route: "portfolio", heading: "Core Equity" },
    { route: "watchlist", heading: "Watchlist" },
    { route: "history", heading: "Historical Similarity" },
    { route: "reports", heading: "Reports" },
    { route: "reports/12", heading: /FinSight AI.*Daily Report/ },
    { route: "chat", heading: "AI Research Assistant" },
    { route: "settings", heading: "Settings" },
  ];
  const viewports = [
    { width: 1440, height: 1000, name: "desktop" },
    { width: 1180, height: 900, name: "laptop" },
    { width: 390, height: 844, name: "mobile" },
  ];
  for (const viewport of viewports) {
    for (const { route, heading } of routes) {
      await page.setViewportSize(viewport);
      await page.goto(`/${route}`);
      await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
      await page.waitForTimeout(150);
      const overflow = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: document.documentElement.clientWidth,
        offenders: Array.from(document.querySelectorAll("body *"))
          .filter((element) => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
          .slice(0, 5)
          .map((element) => {
            const parents: { tag: string; className: string; width: number; overflowX: string }[] = [];
            let parent = element.parentElement;
            while (parent && parents.length < 4) {
              parents.push({ tag: parent.tagName, className: parent.className, width: Math.round(parent.getBoundingClientRect().width), overflowX: getComputedStyle(parent).overflowX });
              parent = parent.parentElement;
            }
            return { tag: element.tagName, className: element.className, right: Math.round(element.getBoundingClientRect().right), parents };
          }),
      }));
      const rootScroll = await page.evaluate(() => {
        window.scrollTo({ left: 10_000, top: 0 });
        const value = window.scrollX;
        window.scrollTo({ left: 0, top: 0 });
        return value;
      });
      expect(overflow.documentWidth, `${route} at ${viewport.name} expands document width (${overflow.documentWidth}/${overflow.viewportWidth}): ${JSON.stringify(overflow.offenders)}`).toBeLessThanOrEqual(overflow.viewportWidth);
      expect(rootScroll, `${route} at ${viewport.name} root scrolls horizontally (${overflow.documentWidth}/${overflow.viewportWidth}): ${JSON.stringify(overflow.offenders)}`).toBe(0);
      await page.screenshot({ path: testInfo.outputPath(`${route.replaceAll("/", "-")}-${viewport.name}.png`), fullPage: true });
    }
  }
});

test("historical regime evidence is visible across responsive layouts", async ({ page }) => {
  await mockWorkspace(page);
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/history");
    await expect(page.getByText("market_regime_v1", { exact: true })).toBeVisible();
    await expect(page.getByText("25 regime features", { exact: true })).toBeVisible();
    await expect(page.getByText("98% constituent coverage", { exact: true })).toBeVisible();
    await expect(page.getByText(/Breadth features have 91% group similarity/)).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "Next 5 sessions" })).toBeVisible();
  }
});
