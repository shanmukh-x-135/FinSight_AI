import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { discoveryApi, type ScreenerResult } from "@/lib/api";

import DiscoverPage from "./page";

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  discoveryApi: { list: vi.fn(), screen: vi.fn(), save: vi.fn(), run: vi.fn(), remove: vi.fn() },
}));

const result: ScreenerResult = {
  query: "NIFTY 100 profitable stocks above EMA50",
  ast: { version: "screener_ast_v1", universe: "NIFTY100", conditions: [
    { field: "price_vs_ema50", operator: "above", value: null, upper_value: null },
    { field: "eps", operator: "positive", value: null, upper_value: null },
  ] },
  explanation: ["Price vs EMA 50: above", "EPS: positive"],
  rows: [{ symbol: "AAA.NS", name: "Alpha", sector: "Technology", as_of: "2026-08-21", close: 110, price_change_percent: 2, rsi_14: 55, ema_20: 105, ema_50: 100, macd_histogram: 1, volume_ratio: 1.5, pe_ratio: 20, eps: 12, news_sentiment: .3, signal_state: "bullish", regime_fit: "aligned" }],
  result_hash: "a".repeat(64),
};

describe("DiscoverPage", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(discoveryApi.list).mockResolvedValue([]); });

  it("renders the validated AST explanation and deterministic results", async () => {
    vi.mocked(discoveryApi.screen).mockResolvedValue(result);
    render(<DiscoverPage />);
    fireEvent.change(screen.getByLabelText("Describe your screen"), { target: { value: result.query } });
    fireEvent.click(screen.getByRole("button", { name: "Run deterministic screen" }));
    expect(await screen.findByText("AAA.NS")).toBeVisible();
    expect(screen.getByText("Price vs EMA 50: above")).toBeVisible();
    expect(screen.getByText(/reproducibility hash aaaaaaaaaaaa/)).toBeVisible();
    expect(discoveryApi.screen).toHaveBeenCalledWith(result.query);
  });

  it("saves the server-validated filter tree and can replay it", async () => {
    vi.mocked(discoveryApi.screen).mockResolvedValue(result);
    vi.mocked(discoveryApi.save).mockResolvedValue({ id: 7, name: "Quality", query_text: result.query, filter_ast: result.ast, created_at: "2026-08-28T00:00:00Z", updated_at: "2026-08-28T00:00:00Z" });
    vi.mocked(discoveryApi.run).mockResolvedValue(result);
    render(<DiscoverPage />);
    fireEvent.click(screen.getByRole("button", { name: "Run deterministic screen" }));
    await screen.findByText("AAA.NS");
    fireEvent.change(screen.getByLabelText("Saved screen name"), { target: { value: "Quality" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Quality")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /^Run$/ }));
    await waitFor(() => expect(discoveryApi.run).toHaveBeenCalledWith(7));
    expect(discoveryApi.save).toHaveBeenCalledWith({ name: "Quality", query_text: result.query, filter_ast: result.ast });
  });
});
