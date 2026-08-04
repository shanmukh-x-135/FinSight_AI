import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { intelligenceApi, marketApi } from "@/lib/api";

import MarketPage from "./page";

vi.mock("@/lib/api", () => ({
  marketApi: {
    breadth: vi.fn(),
    gainers: vi.fn(),
    losers: vi.fn(),
    sectors: vi.fn(),
    technicalSummary: vi.fn(),
    economicEvents: vi.fn(),
  },
  intelligenceApi: { recommendations: vi.fn() },
}));

describe("MarketPage AI analysis states", () => {
  beforeEach(() => {
    vi.mocked(marketApi.breadth).mockResolvedValue({
      advancers: 8,
      decliners: 4,
      unchanged: 1,
      total: 13,
      advance_decline_ratio: 2,
    });
    vi.mocked(marketApi.gainers).mockResolvedValue([]);
    vi.mocked(marketApi.losers).mockResolvedValue([]);
    vi.mocked(marketApi.sectors).mockResolvedValue([]);
    vi.mocked(marketApi.technicalSummary).mockResolvedValue({
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
    });
    vi.mocked(marketApi.economicEvents).mockResolvedValue({
      status: "not_configured",
      provider: "Trading Economics",
      events: [],
    });
  });

  it("shows a truthful empty state when no recommendations meet thresholds", async () => {
    vi.mocked(intelligenceApi.recommendations).mockResolvedValue({
      watchlist: [],
      risk_alerts: [],
    });
    render(<MarketPage />);

    expect(await screen.findByRole("heading", { name: "Market Intelligence" })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "No watch or avoid signals met the recommendation thresholds",
    );
    expect(screen.queryByText(/later phase/i)).not.toBeInTheDocument();
  });

  it("keeps real market data visible when AI analysis is unavailable", async () => {
    vi.mocked(intelligenceApi.recommendations).mockRejectedValue(new Error("offline"));
    render(<MarketPage />);

    expect(await screen.findByText("8", { exact: true })).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent(
      "AI analysis is temporarily unavailable. The market data above is still current.",
    );
  });
});
