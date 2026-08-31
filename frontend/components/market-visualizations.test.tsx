import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectorRotation } from "./sector-rotation";
import { StockHeatmap } from "./stock-heatmap";

describe("market universe visualizations", () => {
  it("groups heatmap stocks and exposes evidence availability", () => {
    render(<StockHeatmap stocks={[{ symbol: "AAA.NS", name: "Alpha", sector: "Technology", as_of: "2026-08-27", change_percent: 1.2, market_cap: 1000, sentiment: null, sentiment_availability: "no_relevant_news", rsi_14: 58, signal: "bullish" }]} />);

    expect(screen.getByRole("heading", { name: "Technology" })).toBeVisible();
    expect(screen.getByRole("link", { name: /AAA\.NS.*news unavailable/i })).toHaveAttribute("href", "/market/AAA.NS");
  });

  it("renders all sector rotation windows and regime", () => {
    render(<SectorRotation rows={[{ sector: "Financial Services", stock_count: 18, return_1d: 0.5, return_5d: 1.8, return_20d: 4.1, momentum_regime: "leader" }]} />);

    expect(screen.getByText("Financial Services")).toBeVisible();
    expect(screen.getByText("+4.10%")).toBeVisible();
    expect(screen.getByText("leader")).toBeVisible();
  });
});
