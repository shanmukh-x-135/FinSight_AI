import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { strategiesApi, type Backtest, type RobustnessAnalysis, type Strategy } from "@/lib/api";

import StrategiesPage from "./page";

vi.mock("@/components/backtest-chart", () => ({ BacktestChart: () => <div data-testid="backtest-chart">Chart</div> }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, strategiesApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), archive: vi.fn(), run: vi.fn(), runs: vi.fn(), backtest: vi.fn(), analyze: vi.fn() } };
});

const definition: Strategy["latest_version"]["definition"] = {
  entry: { kind: "group", operator: "AND", rules: [{ kind: "condition", field: "price_vs_ema50", operator: "above", value: null }] },
  exit: { kind: "group", operator: "OR", rules: [{ kind: "condition", field: "rsi", operator: "gt", value: 75 }] },
  execution: { initial_capital: 100000, max_positions: 10, transaction_cost_bps: 10, slippage_bps: 5, stop_loss_percent: 3, take_profit_percent: 8, max_holding_sessions: 20, benchmark_symbol: "^NSEI" },
};
const strategy: Strategy = { id: 7, name: "EMA momentum", description: "Test", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z", latest_version: { id: 8, version: 1, definition, created_at: "2026-01-01T00:00:00Z" } };
const result: Backtest = {
  id: 9, strategy_id: 7, strategy_version_id: 8, strategy_version: 1, status: "completed", start_date: "2024-01-01", end_date: "2025-01-01", universe_code: "NIFTY100", membership_mode: "current_universe", membership_disclaimer: "Uses today's active constituents and may contain survivorship bias.", benchmark_symbol: "^NSEI", result_hash: "abcdef1234567890", created_at: "2026-01-01T00:00:00Z", completed_at: "2026-01-01T00:00:01Z", robustness_analysis: null,
  metrics: { total_return_percent: 12, benchmark_return_percent: 8, excess_return_percent: 4, cagr_percent: 11.9, sharpe_ratio: 1.2, sortino_ratio: 1.6, max_drawdown_percent: -5, win_rate_percent: 60, profit_factor: 1.8, average_winner_percent: 4, average_loser_percent: -2, expectancy_percent: 1.6, total_trades: 1, average_holding_sessions: 4, turnover_percent: 30, estimated_transaction_costs: 42 },
  equity_curve: [{ date: "2024-01-02", equity: 100000, benchmark_equity: 100000, drawdown_percent: 0 }, { date: "2024-01-03", equity: 101000, benchmark_equity: 100500, drawdown_percent: 0 }],
  trades: [{ symbol: "AAA.NS", entry_signal_date: "2024-01-01", entry_date: "2024-01-02", entry_price: 100, exit_signal_date: "2024-01-02", exit_date: "2024-01-03", exit_price: 104, quantity: 10, gross_pnl: 40, net_pnl: 38, return_percent: 3.8, holding_sessions: 1, exit_reason: "rule_exit", transaction_cost: 2 }],
};
const metricSlice = { total_return_percent: 8, benchmark_return_percent: 5, excess_return_percent: 3, max_drawdown_percent: 4, sharpe_ratio: 1, total_trades: 3 };
const breakdown = [{ label: "positive", trades: 3, average_return_percent: 2, win_rate_percent: 66.7, net_pnl: 600 }];
const robustness: RobustnessAnalysis = { analysis_version: "strategy_robustness_v1", baseline_result_hash: "abcdef1234567890", chronological_split: { train_percent: 70, test_percent: 30, split_date: "2024-09-01", training: metricSlice, test: metricSlice, note: "No parameter fitting occurs." }, signal_outcomes: [], breakdowns: { breadth_regime: breakdown, momentum_regime: breakdown, volatility_regime: breakdown, macro_stress: breakdown, sector: breakdown, confidence_bucket: breakdown }, parameter_sensitivity: [{ label: "baseline", ...metricSlice }], cost_sensitivity: [{ label: "baseline", transaction_cost_bps: 10, slippage_bps: 5, ...metricSlice }], robustness: { score: 72, components: { out_of_sample: 20, parameter_stability: 18, regime_independence: 14, cost_resilience: 10, drawdown_control: 10 }, explanation: ["Deterministic component evidence."] } };

describe("StrategiesPage", () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(strategiesApi.list).mockResolvedValue([strategy]); vi.mocked(strategiesApi.runs).mockResolvedValue([]); vi.mocked(strategiesApi.run).mockResolvedValue(result); });

  it("shows deterministic timing and survivorship disclosures with complete results", async () => {
    render(<StrategiesPage />);
    expect(await screen.findByRole("heading", { name: "Strategy Lab" })).toBeVisible();
    expect(screen.getByText(/earliest fill is the next eligible session/i)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /EMA momentum/i }));
    fireEvent.click(screen.getByRole("button", { name: "Run backtest" }));

    await waitFor(() => expect(strategiesApi.run).toHaveBeenCalledWith(7, expect.objectContaining({ universe_code: "NIFTY100", membership_mode: "current_universe" })));
    expect((await screen.findAllByText(/survivorship bias/i)).at(-1)).toBeVisible();
    expect(screen.getAllByText("+4.00%")).toHaveLength(2);
    expect(screen.getByText("2024-01-01 → 2024-01-02")).toBeVisible();
    expect(screen.getByTestId("backtest-chart")).toBeVisible();
  });

  it("creates a strategy before its first replay", async () => {
    vi.mocked(strategiesApi.list).mockResolvedValue([]);
    vi.mocked(strategiesApi.create).mockResolvedValue(strategy);
    render(<StrategiesPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Run backtest" }));
    await waitFor(() => expect(strategiesApi.create).toHaveBeenCalledWith(expect.objectContaining({ definition: expect.objectContaining({ entry: expect.objectContaining({ operator: "AND" }) }) })));
    expect(strategiesApi.run).toHaveBeenCalledWith(7, expect.anything());
  });

  it("renders explainable out-of-sample and sensitivity evidence", async () => {
    vi.mocked(strategiesApi.analyze).mockResolvedValue(robustness);
    render(<StrategiesPage />);
    fireEvent.click(await screen.findByRole("button", { name: /EMA momentum/i }));
    fireEvent.click(screen.getByRole("button", { name: "Run backtest" }));
    fireEvent.click(await screen.findByRole("button", { name: "Analyze robustness" }));

    expect(await screen.findByRole("region", { name: "Strategy robustness analysis" })).toBeVisible();
    expect(screen.getByText("72")).toBeVisible();
    expect(screen.getByText("Out-of-sample segment")).toBeVisible();
    expect(screen.getByText("Parameters")).toBeVisible();
    expect(screen.getByRole("progressbar", { name: "Parameter stability" })).toHaveAttribute("aria-valuenow", "18");
  });
});
