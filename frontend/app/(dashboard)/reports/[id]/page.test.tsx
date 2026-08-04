import { render, screen } from "@testing-library/react";
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
    portfolio_summary: {
      total_value: 1000,
      total_return_percent: -3.5,
      health_score: 50,
      risk_level: "medium",
      number_of_holdings: 1,
    },
    historical_summary: {
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
    recommendations: [],
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
});
