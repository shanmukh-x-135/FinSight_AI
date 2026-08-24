import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { dashboardApi, type DashboardSummary } from "@/lib/api";

import DashboardPage from "./page";

vi.mock("@/lib/api", () => ({
  dashboardApi: { summary: vi.fn() },
}));

const summary: DashboardSummary = {
  market: {
    breadth: { advancers: 0, decliners: 0, unchanged: 0, total: 0, advance_decline_ratio: null },
    gainers: [],
    losers: [],
  },
  ai_market_summary: "Market data is currently unavailable.",
  portfolio: null,
  watchlist: [],
  sectors: [],
  technical: {
    as_of: null,
    stocks_with_indicators: 0,
    average_rsi: null,
    bullish_rsi_count: 0,
    overbought_count: 0,
    oversold_count: 0,
    above_ema20_count: 0,
    above_ema50_count: 0,
    positive_macd_count: 0,
    average_atr_percent: null,
  },
  sentiment: [],
  opportunities: [],
  risk_alerts: [],
  history: null,
  generation: {
    schema_version: 1,
    configured_backend: "deterministic",
    actual_backends: ["deterministic"],
    requested_models: [],
    model_versions: [],
    generation_count: 0,
    provider_attempt_count: 0,
    provider_response_count: 0,
    fallback_count: 0,
    usage: {
      prompt_tokens: null,
      candidate_tokens: null,
      total_tokens: null,
      cached_tokens: null,
      thoughts_tokens: null,
    },
    items: [],
  },
};

describe("Dashboard news sentiment", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows missing coverage as unavailable instead of neutral", async () => {
    vi.mocked(dashboardApi.summary).mockResolvedValue({
      ...summary,
      sentiment: Array.from({ length: 50 }, (_, index) => ({
        symbol: `STOCK${index}.NS`,
        latest_sentiment: null,
      })),
    });
    render(<DashboardPage />);

    const title = await screen.findByText("No recent sentiment data");
    const state = title.closest('[role="status"]');
    expect(state).not.toBeNull();
    expect(state).toHaveTextContent("No recent sentiment data");
    expect(state).toHaveTextContent("50 active stocks");
    expect(state).toHaveTextContent("Missing coverage is not classified as neutral");
  });

  it("counts only observed zero scores as neutral", async () => {
    vi.mocked(dashboardApi.summary).mockResolvedValue({
      ...summary,
      sentiment: [
        { symbol: "POS.NS", latest_sentiment: 0.4 },
        { symbol: "FLAT.NS", latest_sentiment: 0 },
        { symbol: "NEG.NS", latest_sentiment: -0.3 },
        { symbol: "NONE.NS", latest_sentiment: null },
      ],
    });
    render(<DashboardPage />);

    const chart = await screen.findByRole("img", {
      name: "1 positive, 1 neutral, 1 negative sentiment readings; 1 unavailable",
    });
    expect(chart).toBeVisible();
    expect(screen.getByText("1 stocks have no recent tagged coverage.")).toBeVisible();
  });
});
