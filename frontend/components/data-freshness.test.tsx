import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataFreshnessStrip } from "@/components/data-freshness";

describe("DataFreshnessStrip", () => {
  it("renders explicit fresh, delayed, and unavailable states", () => {
    render(<DataFreshnessStrip items={[
      { dataset: "market", state: "Fresh", observed_date: "2026-08-27", observed_at: null, expected_trading_date: "2026-08-27", explanation: "Market current" },
      { dataset: "news", state: "Delayed", observed_date: "2026-08-25", observed_at: null, expected_trading_date: "2026-08-27", explanation: "News delayed" },
      { dataset: "historical_corpus", state: "Unavailable", observed_date: null, observed_at: null, expected_trading_date: "2026-08-27", explanation: "History unavailable" },
    ]} />);
    const region = screen.getByRole("region", { name: "Data freshness" });
    expect(region).toHaveTextContent("MarketFresh");
    expect(region).toHaveTextContent("NewsDelayed");
    expect(region).toHaveTextContent("HistoryUnavailable");
  });
});
