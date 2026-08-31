import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { operationsApi, type EODStatus } from "@/lib/api";

import OperationsPage from "./page";

vi.mock("@/lib/api", () => ({ operationsApi: { eodStatus: vi.fn() } }));

const status: EODStatus = {
  pipeline_name: "eod_market_intelligence", requested_trading_date: null,
  rerun_recommended: true, health: "attention",
  operator_explanation: "The EOD workflow is partial; a safe resumable rerun is recommended. Failed step(s): history.",
  freshness: [
    { dataset: "market", state: "Fresh", observed_date: "2026-08-27", observed_at: null, expected_trading_date: "2026-08-27", explanation: "Market is current." },
    { dataset: "news", state: "Delayed", observed_date: "2026-08-25", observed_at: "2026-08-25T12:00:00Z", expected_trading_date: "2026-08-27", explanation: "News is delayed." },
    { dataset: "universe", state: "Fresh", observed_date: "2026-08-24", observed_at: "2026-08-24T12:00:00Z", expected_trading_date: null, explanation: "Universe is current." },
    { dataset: "historical_corpus", state: "Delayed", observed_date: "2026-08-26", observed_at: "2026-08-26T17:00:00Z", expected_trading_date: "2026-08-27", explanation: "History is delayed." },
  ],
  run: { id: 9, pipeline_name: "eod_market_intelligence", target_trading_date: "2026-08-27", correlation_id: "cid-9", status: "partial", attempt_count: 2, counters: {}, last_error_summary: "history failed (RuntimeError)", started_at: "2026-08-27T12:00:00Z", heartbeat_at: "2026-08-27T12:05:00Z", completed_at: null, created_at: "2026-08-27T12:00:00Z", updated_at: "2026-08-27T12:05:00Z", steps: [
    { step_name: "market", sequence: 0, status: "completed", attempt_count: 1, counters: { requested: 100, succeeded: 100 }, last_error_summary: null, started_at: "2026-08-27T12:00:00Z", heartbeat_at: null, completed_at: "2026-08-27T12:02:00Z" },
    { step_name: "history", sequence: 2, status: "failed", attempt_count: 2, counters: {}, last_error_summary: "history failed (RuntimeError)", started_at: "2026-08-27T12:04:00Z", heartbeat_at: null, completed_at: null },
  ] },
};

describe("OperationsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("makes pipeline progress, freshness, and failure guidance understandable", async () => {
    vi.mocked(operationsApi.eodStatus).mockResolvedValue(status);
    render(<OperationsPage />);
    expect(await screen.findByRole("heading", { name: "EOD Operations" })).toBeVisible();
    expect(screen.getByText(/safe resumable rerun/)).toBeVisible();
    expect(screen.getAllByText("history failed (RuntimeError)", { selector: "p" })).toHaveLength(2);
    expect(screen.getByRole("region", { name: "Data freshness" })).toHaveTextContent("NewsDelayed");
    expect(screen.getAllByText("100", { selector: "strong" })).toHaveLength(2);
  });
});
