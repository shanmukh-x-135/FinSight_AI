import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PortfolioCounterfactual, PortfolioRisk } from "@/lib/api";

import { PortfolioRiskView } from "./portfolio-risk";

const risk: PortfolioRisk = {
  portfolio_id: 1, as_of: "2026-08-21", methodology: "Static current-quantity/current-value weights applied to aligned historical close returns; not actual portfolio performance.", benchmark_symbol: "^NSEI", observations: 200, minimum_observations: 30, data_complete: true, missing_symbols: [], annualized_volatility_percent: 18, beta: .9, sharpe_ratio: 1.1, max_drawdown_percent: 8, concentration_hhi: .52, momentum_exposure_percent: 4,
  correlation: [{ symbol_x: "AAA.NS", symbol_y: "AAA.NS", correlation: 1, observations: 200 }],
  holding_contributions: [{ symbol: "AAA.NS", weight_percent: 100, return_contribution_percent: 10, risk_contribution_percent: 100, momentum_20d_percent: 4 }],
  sector_deviation: [{ sector: "Technology", portfolio_weight_percent: 100, benchmark_weight_percent: 20, deviation_percent: 80 }], sector_benchmark_methodology: "NIFTY 100 current constituent market-cap weights.",
  regime_sensitivity: [{ regime: "mixed", sessions: 100, average_daily_return_percent: .05, positive_session_percent: 55 }],
  stress_scenarios: [{ code: "nifty_down_5", label: "Broad market sell-off", shock: "NIFTY -5%", estimated_impact_percent: -4.5, estimated_value_change: -4500, methodology: "Portfolio beta × -5%.", is_prediction: false }],
};

describe("PortfolioRiskView", () => {
  it("shows diagnostics, correlation, and scenario labels", () => {
    render(<PortfolioRiskView risk={risk} onCounterfactual={vi.fn()} />);
    expect(screen.getByRole("region", { name: "Advanced portfolio risk" })).toBeVisible();
    expect(screen.getByText("0.90")).toBeVisible();
    expect(screen.getByText("Broad market sell-off")).toBeVisible();
    expect(screen.getByText(/not predictions/i)).toBeVisible();
    expect(screen.getByRole("table", { name: "Holding return correlation heatmap" })).toBeVisible();
  });

  it("submits a non-mutating before/after counterfactual", async () => {
    const scenario: PortfolioCounterfactual = { label: "Scenario estimate, not a prediction", changes: [{ symbol: "AAA.NS", quantity_delta: -2 }, { symbol: "BBB.NS", quantity_delta: 1 }], before: risk, after: { ...risk, concentration_hhi: .4 }, deltas: { concentration_hhi: -.12 } };
    const analyze = vi.fn().mockResolvedValue(scenario);
    render(<PortfolioRiskView risk={risk} onCounterfactual={analyze} />);
    fireEvent.change(screen.getByLabelText("Reduce symbol"), { target: { value: "aaa.ns" } });
    fireEvent.change(screen.getByLabelText("Reduce quantity"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Add symbol"), { target: { value: "bbb.ns" } });
    fireEvent.change(screen.getByLabelText("Add quantity"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare scenario" }));
    await waitFor(() => expect(analyze).toHaveBeenCalledWith([{ symbol: "AAA.NS", quantity_delta: -2 }, { symbol: "BBB.NS", quantity_delta: 1 }]));
    expect(await screen.findByText("Scenario estimate, not a prediction")).toBeVisible();
    expect(screen.getByText("-0.120")).toBeVisible();
  });

  it("withholds advanced metrics for short histories", () => {
    render(<PortfolioRiskView risk={{ ...risk, data_complete: false, observations: 10, missing_symbols: ["AAA.NS"] }} onCounterfactual={vi.fn()} />);
    expect(screen.getByText("Risk history is incomplete")).toBeVisible();
    expect(screen.getByText(/At least 30 aligned sessions/)).toBeVisible();
  });
});
