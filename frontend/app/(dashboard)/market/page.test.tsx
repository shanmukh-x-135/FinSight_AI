import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { intelligenceApi, marketApi, watchlistApi, type MarketWorkspace } from "@/lib/api";

import MarketPage from "./page";

vi.mock("@/lib/api", () => ({
  marketApi: {
    universes: vi.fn(),
    workspace: vi.fn(),
    stocks: vi.fn(),
    breadth: vi.fn(),
    gainers: vi.fn(),
    losers: vi.fn(),
    sectors: vi.fn(),
    technicalSummary: vi.fn(),
    heatmap: vi.fn(),
    sectorRotation: vi.fn(),
    economicEvents: vi.fn(),
  },
  intelligenceApi: { recommendations: vi.fn() },
  watchlistApi: { list: vi.fn(), add: vi.fn(), remove: vi.fn() },
}));

const emptyWorkspace: MarketWorkspace = {
  universe: "NIFTY100",
  stocks: [],
  breadth: { advancers: 8, decliners: 4, unchanged: 1, total: 13, advance_decline_ratio: 2 },
  sectors: [],
  technical: { as_of: null, stocks_with_indicators: 0, average_rsi: null, bullish_rsi_count: 0, overbought_count: 0, oversold_count: 0, above_ema20_count: 0, above_ema50_count: 0, positive_macd_count: 0, average_atr_percent: null },
  heatmap: [],
  sector_rotation: [],
  economic_events: { status: "not_configured", provider: "Trading Economics", events: [] },
  sentiment: [],
};

describe("MarketPage AI analysis states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(marketApi.universes).mockResolvedValue([
      { code: "NIFTY50", label: "NIFTY 50", expected_constituents: 50, active_constituents: 50, initialized: true, preferred: false, source_url: "https://example.test/50.csv" },
      { code: "NIFTY100", label: "NIFTY 100", expected_constituents: 100, active_constituents: 100, initialized: true, preferred: true, source_url: "https://example.test/100.csv" },
    ]);
    vi.mocked(marketApi.workspace).mockResolvedValue(emptyWorkspace);
    vi.mocked(marketApi.stocks).mockResolvedValue([]);
    vi.mocked(marketApi.heatmap).mockResolvedValue([]);
    vi.mocked(marketApi.sectorRotation).mockResolvedValue([]);
    vi.mocked(watchlistApi.list).mockResolvedValue([]);
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
      generation: {
        schema_version: 1,
        configured_backend: "DeterministicNarrator",
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
    });
    render(<MarketPage />);

    expect(await screen.findByRole("heading", { name: "Market Intelligence" })).toBeVisible();
    expect(screen.getByText(/No watch or avoid signals met the recommendation thresholds/)).toBeVisible();
    expect(screen.queryByText(/later phase/i)).not.toBeInTheDocument();
  });

  it("keeps real market data visible when AI analysis is unavailable", async () => {
    vi.mocked(intelligenceApi.recommendations).mockRejectedValue(new Error("offline"));
    render(<MarketPage />);

    expect(await screen.findByText("8", { exact: true })).toBeVisible();
    expect(screen.getByText("AI analysis is temporarily unavailable. The market data above is still current.")).toBeVisible();
  });

  it("adds a screener row to the authenticated watchlist", async () => {
    vi.mocked(marketApi.workspace).mockResolvedValue({ ...emptyWorkspace, stocks: [{ symbol: "AAA.NS", name: "Alpha", sector: "Technology", date: "2026-08-21", close: 110, previous_close: 100, change: 10, change_percent: 10, volume: 1000, rsi_14: 62, ema_20: 105, ema_50: 101, macd_histogram: 2, trend: "bullish" }] });
    vi.mocked(watchlistApi.add).mockResolvedValue({ id: 9 });
    vi.mocked(watchlistApi.list).mockResolvedValueOnce([]).mockResolvedValue([{ id: 9, symbol: "AAA.NS", name: "Alpha", sector: "Technology", current_price: 110, previous_close: 100, change: 10, change_percent: 10, pinned: false, sort_order: 0, rsi_14: 62, trend: "bullish" }]);
    vi.mocked(intelligenceApi.recommendations).mockResolvedValue({ watchlist: [], risk_alerts: [], generation: { schema_version: 1, configured_backend: "deterministic", actual_backends: ["deterministic"], requested_models: [], model_versions: [], generation_count: 0, provider_attempt_count: 0, provider_response_count: 0, fallback_count: 0, usage: { prompt_tokens: null, candidate_tokens: null, total_tokens: null, cached_tokens: null, thoughts_tokens: null }, items: [] } });
    render(<MarketPage />);

    fireEvent.click(await screen.findByRole("button", { name: "Add AAA.NS to watchlist" }));
    await waitFor(() => expect(watchlistApi.add).toHaveBeenCalledWith("AAA.NS"));
    expect(await screen.findByRole("button", { name: "Remove AAA.NS from watchlist" })).toBeVisible();
  });

  it("refetches membership-scoped market views when the universe changes", async () => {
    vi.mocked(intelligenceApi.recommendations).mockResolvedValue({ watchlist: [], risk_alerts: [], generation: { schema_version: 1, configured_backend: "deterministic", actual_backends: ["deterministic"], requested_models: [], model_versions: [], generation_count: 0, provider_attempt_count: 0, provider_response_count: 0, fallback_count: 0, usage: { prompt_tokens: null, candidate_tokens: null, total_tokens: null, cached_tokens: null, thoughts_tokens: null }, items: [] } });
    render(<MarketPage />);

    fireEvent.change(await screen.findByRole("combobox", { name: "Research universe" }), { target: { value: "NIFTY50" } });

    await waitFor(() => expect(marketApi.workspace).toHaveBeenCalledWith("NIFTY50"));
  });
});
