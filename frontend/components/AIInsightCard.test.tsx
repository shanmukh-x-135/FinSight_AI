import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AIInsightCard } from "./AIInsightCard";

describe("AIInsightCard", () => {
  it("renders the title, narrative, and action badge", () => {
    render(
      <AIInsightCard
        title="RELIANCE.NS"
        narrative="On the watchlist."
        action="watch"
        confidence={54}
        evidence={{ evidence: ["RSI supports momentum"] }}
      />,
    );
    expect(screen.getByText("RELIANCE.NS")).toBeInTheDocument();
    expect(screen.getByText("On the watchlist.")).toBeInTheDocument();
    expect(screen.getByText("watch")).toBeInTheDocument();
    expect(screen.getByText("54% conf.")).toBeInTheDocument();
  });

  it("always wires the required Show Evidence expander", async () => {
    const user = userEvent.setup();
    render(
      <AIInsightCard
        title="AAA.NS"
        narrative="Strong momentum."
        confidence={70}
        evidence={{ evidence: ["MACD histogram positive"], risks: ["Standard market risk applies"] }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /show evidence/i }));
    expect(screen.getByText("MACD histogram positive")).toBeInTheDocument();
    // Card confidence flows through to the evidence panel bar.
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  it("keeps disclosure available when a grounded narrative has no indicators", async () => {
    const user = userEvent.setup();
    render(
      <AIInsightCard
        title="Sparse context"
        narrative="No comparable sessions were found."
        evidence={{ evidence: [] }}
      />,
    );
    await user.click(screen.getByRole("button", { name: /show evidence/i }));
    expect(screen.getByText("No supporting indicators.")).toBeInTheDocument();
  });
});
