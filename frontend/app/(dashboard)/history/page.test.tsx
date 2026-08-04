import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { historyApi, type SimilarityResult } from "@/lib/api";

import HistoryPage from "./page";

vi.mock("@/lib/api", () => ({
  historyApi: { similar: vi.fn() },
}));

const result: SimilarityResult = {
  query_date: "2024-01-02",
  query_summary: {
    date: "2024-01-02",
    avg_return: 0.01,
    pct_advancers: 0.6,
    advance_decline_ratio: 1.5,
    avg_rsi: 55,
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
  });
});
