import { describe, expect, it } from "vitest";

import type { Breadth, HistoryStatistics, Quote, ReportSections } from "@/lib/api";
import {
  executiveNarrativeEvidence,
  historicalNarrativeEvidence,
  marketNarrativeEvidence,
  portfolioNarrativeEvidence,
} from "@/lib/evidence";

const breadth: Breadth = {
  advancers: 12,
  decliners: 8,
  unchanged: 2,
  total: 22,
  advance_decline_ratio: 1.5,
};

const quote = (symbol: string, change: number): Quote => ({
  symbol,
  name: null,
  sector: null,
  date: "2026-08-04",
  close: 100,
  previous_close: 95,
  change: 5,
  change_percent: change,
  volume: 1000,
});

const statistics: HistoryStatistics = {
  k: 5,
  sample_size: 5,
  bullish_count: 3,
  bearish_count: 2,
  neutral_count: 0,
  bullish_probability: 0.6,
  avg_next_day_return: 0.004,
  median_next_day_return: 0.003,
  std_next_day_return: 0.01,
  best_case_return: 0.02,
  worst_case_return: -0.01,
  ci_low: -0.005,
  ci_high: 0.013,
};

describe("narrative evidence builders", () => {
  it("formats market facts and movers", () => {
    expect(
      marketNarrativeEvidence({
        breadth,
        gainers: [quote("AAA.NS", 2.5)],
        losers: [quote("BBB.NS", -1.25)],
      }),
    ).toEqual([
      "Breadth: 12 advancers, 8 decliners, and 2 unchanged across 22 tracked stocks",
      "Advance/decline ratio: 1.50",
      "Top gainer: AAA.NS at +2.50%",
      "Top decliner: BBB.NS at -1.25%",
    ]);
  });

  it("keeps percentage units correct for portfolio and historical facts", () => {
    expect(
      portfolioNarrativeEvidence({ total_value: 1000, total_return_percent: -3.5 }),
    ).toEqual(["Portfolio value: ₹1,000", "Total return: -3.50%"]);
    expect(historicalNarrativeEvidence(statistics)).toContain(
      "Average next-day return: +0.40%",
    );
  });

  it("builds executive evidence only from stored deterministic sections", () => {
    const sections: ReportSections = {
      market_summary: { breadth },
      historical_summary: { statistics },
      recommendations: [
        {
          symbol: "AAA.NS",
          name: null,
          sector: null,
          action: "watch",
          confidence: 64,
          score: 1,
          evidence: [],
          risks: [],
          historical_context: { bullish_probability: null, sample_size: null },
          explanation: "Watch AAA.NS.",
        },
      ],
    };

    expect(executiveNarrativeEvidence(sections)).toContain(
      "Watch-rated: AAA.NS (64% confidence)",
    );
  });
});
