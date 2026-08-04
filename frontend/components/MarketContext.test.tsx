import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EconomicEventsCard, TechnicalSummaryCard } from "./MarketContext";

describe("Market context cards", () => {
  it("renders deterministic technical aggregates", () => {
    render(
      <TechnicalSummaryCard
        summary={{
          as_of: "2026-08-04",
          stocks_with_indicators: 20,
          average_rsi: 58.25,
          bullish_rsi_count: 12,
          overbought_count: 2,
          oversold_count: 1,
          above_ema20_count: 14,
          above_ema50_count: 11,
          positive_macd_count: 13,
          average_atr_percent: 2.345,
        }}
      />,
    );
    expect(screen.getByText("58.3")).toBeInTheDocument();
    expect(screen.getByText("14")).toBeInTheDocument();
    expect(screen.getByText("2.35%")).toBeInTheDocument();
    expect(screen.getByText(/2 overbought · 1 oversold/)).toBeInTheDocument();
  });

  it("renders live event values and impact", () => {
    render(
      <EconomicEventsCard
        calendar={{
          provider: "Trading Economics",
          status: "ok",
          events: [
            {
              event_id: "1",
              date: "2026-08-07T06:30:00Z",
              country: "India",
              category: "Interest Rate",
              name: "RBI Interest Rate Decision",
              importance: 3,
              reference: null,
              source: "RBI",
              source_url: null,
              actual: null,
              forecast: "5.25%",
              previous: "5.50%",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("RBI Interest Rate Decision")).toBeInTheDocument();
    expect(screen.getByText("High impact")).toBeInTheDocument();
    expect(screen.getByText("5.25%")).toBeInTheDocument();
  });

  it("never substitutes mock events when the provider is not configured", () => {
    render(
      <EconomicEventsCard
        calendar={{ provider: "Trading Economics", status: "not_configured", events: [] }}
      />,
    );
    expect(screen.getByText(/not configured/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});
