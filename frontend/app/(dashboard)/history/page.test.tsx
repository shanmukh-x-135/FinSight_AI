import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { historyApi, type SimilarityResult } from "@/lib/api";

import HistoryPage from "./page";

vi.mock("@/lib/api", () => ({
  historyApi: { similar: vi.fn() },
}));

vi.mock("@/components/finance-charts", () => ({
  HistoryOutcomeChart: () => <div data-testid="history-outcome-chart" />,
}));

const result: SimilarityResult = {
  feature_version: "market_regime_v1",
  vector_dimension: 25,
  normalization_method: "median_iqr_clip8_v1",
  query_date: "2024-01-02",
  query_summary: {
    date: "2024-01-02",
    avg_return: 0.01,
    pct_advancers: 0.6,
    advance_decline_ratio: 1.5,
    avg_rsi: 55,
    median_rsi: 54.5,
    median_relative_volume: 1.1,
    coverage_ratio: 0.98,
    usable_constituents: 49,
    expected_constituents: 50,
    membership_mode: "available_data_proxy",
    quality_flags: ["historical_membership_unknown"],
    breadth_regime: "broad_positive",
    momentum_regime: "positive",
    volatility_regime: "normal",
  },
  similar_sessions: [
    {
      date: "2023-12-20",
      avg_return: -0.025,
      pct_advancers: 0.4,
      advance_decline_ratio: 0.67,
      avg_rsi: 48,
      similarity_score: 0.9,
      distance: 0.1,
      next_day_return: 0.02,
      outcome: "bullish",
      forward_5_session_return: 0.035,
      matching_factors: [{ factor: "breadth", similarity_score: 0.88, explanation: "Breadth participation is closely aligned." }],
      divergence_factors: [{ factor: "macro", similarity_score: 0.45, explanation: "Macro cross-asset returns differ most." }],
    },
  ],
  statistics: {
    k: 1,
    sample_size: 1,
    bullish_count: 1,
    bearish_count: 0,
    neutral_count: 0,
    bullish_probability: 1,
    avg_next_day_return: 0.02,
    median_next_day_return: 0.02,
    std_next_day_return: 0,
    best_case_return: 0.02,
    worst_case_return: 0.02,
    ci_low: 0.02,
    ci_high: 0.02,
  },
};

describe("HistoryPage historical units", () => {
  beforeEach(() => {
    vi.mocked(historyApi.similar).mockResolvedValue(result);
  });

  it("renders return ratios and breadth as correctly scaled percentages", async () => {
    render(<HistoryPage />);

    expect(await screen.findByText("+1.00%")).toBeInTheDocument();
    expect(screen.getByText("60.0%")).toBeInTheDocument();
    expect(screen.getByText("-2.50%")).toBeInTheDocument();
    expect(screen.getAllByText("+2.00%").length).toBeGreaterThan(0);
    expect(screen.getByText("market_regime_v1")).toBeInTheDocument();
    expect(screen.getByText("98% constituent coverage")).toBeInTheDocument();
    expect(screen.getByText("Breadth participation is closely aligned.")).toBeInTheDocument();
  });
});
