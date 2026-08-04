import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportsApi, type Report } from "@/lib/api";

import ReportDetailPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
}));

vi.mock("@/lib/api", () => ({
  reportsApi: { get: vi.fn() },
  downloadReport: vi.fn(),
}));

const report: Report = {
  id: 1,
  user_id: 1,
  report_type: "daily",
  created_at: "2024-01-02T10:00:00+00:00",
  sections: {
    executive_summary: "Markets were mixed.",
    market_summary: {
      narrative: "Breadth was positive.",
      breadth: {
        advancers: 3,
        decliners: 1,
        unchanged: 2,
        total: 6,
        advance_decline_ratio: 3,
      },
      gainers: [
        {
          symbol: "AAA.NS",
          name: "Alpha",
          sector: "Technology",
          date: "2024-01-02",
          close: 105,
          previous_close: 100,
          change: 5,
          change_percent: 5,
          volume: 1000,
        },
      ],
      losers: [],
    },
    portfolio_summary: {
      narrative: "Portfolio remains concentrated.",
      total_value: 1000,
      total_return_percent: -3.5,
      health_score: 50,
      risk_level: "medium",
      diversification_score: 49.5,
      number_of_holdings: 1,
    },
    historical_summary: {
      narrative: "Today resembles five past sessions.",
      statistics: {
        k: 5,
        sample_size: 5,
        bullish_count: 3,
        bearish_count: 2,
        neutral_count: 0,
        bullish_probability: 0.6,
        avg_next_day_return: 0.4,
        median_next_day_return: 0.3,
        std_next_day_return: 0.1,
        best_case_return: 0.8,
        worst_case_return: -0.2,
        ci_low: 0.1,
        ci_high: 0.7,
      },
    },
    recommendations: [
      {
        symbol: "AAA.NS",
        name: "Alpha",
        sector: "Technology",
        action: "watch",
        confidence: 62,
        score: 0.14,
        evidence: ["RSI at 60"],
        risks: ["Standard market risk applies"],
        historical_context: { bullish_probability: 0.6, sample_size: 5 },
        explanation: "Momentum is constructive.",
      },
    ],
    news: {
      notable: Array.from({ length: 6 }, (_, index) => ({
        title: `Story ${index + 1}`,
        sentiment_label: "neutral",
        tags: [],
      })),
    },
  },
};

describe("ReportDetailPage historical units", () => {
  beforeEach(() => {
    vi.mocked(reportsApi.get).mockResolvedValue(report);
  });

  it("scales historical ratios without changing portfolio percentages", async () => {
    render(<ReportDetailPage />);

    expect(await screen.findByText("+40.00%")).toBeInTheDocument();
    expect(screen.getByText("-3.50%")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("renders the same summary facts and limits as Markdown export", async () => {
    const user = userEvent.setup();
    render(<ReportDetailPage />);

    expect(
      await screen.findByRole("heading", { name: "FinSight AI — Daily Report" }),
    ).toBeVisible();
    expect(screen.getByText(/Report #1 · Generated/)).toBeVisible();
    expect(screen.getByText("Unchanged", { exact: true })).toBeVisible();
    expect(screen.getByText("Tracked", { exact: true })).toBeVisible();
    expect(screen.getByText("Diversification", { exact: true })).toBeVisible();
    expect(screen.getByText("50/100", { exact: true })).toBeVisible();
    expect(screen.getByText("top-5 nearest", { exact: true })).toBeVisible();
    expect(screen.getByText("Historical context, not a forecast.")).toBeVisible();
    expect(screen.getByText("Story 5")).toBeVisible();
    expect(screen.queryByText("Story 6")).not.toBeInTheDocument();

    const evidenceButtons = screen.getAllByRole("button", { name: "Show evidence" });
    await user.click(evidenceButtons.at(-1)!);
    expect(
      screen.getByText("60% of 5 similar historical sessions closed higher"),
    ).toBeVisible();
  });
});
