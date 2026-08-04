import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AIInsightCard } from "./AIInsightCard";

describe("AIInsightCard", () => {
  it("renders the title, narrative, and action badge", () => {
    render(<AIInsightCard title="RELIANCE.NS" narrative="On the watchlist." action="watch" confidence={54} />);
    expect(screen.getByText("RELIANCE.NS")).toBeInTheDocument();
    expect(screen.getByText("On the watchlist.")).toBeInTheDocument();
    expect(screen.getByText("watch")).toBeInTheDocument();
    expect(screen.getByText("54% conf.")).toBeInTheDocument();
  });

  it("shows no evidence expander when no evidence is supplied", () => {
    render(<AIInsightCard title="Market" narrative="Mixed session." />);
    expect(screen.queryByRole("button", { name: /show evidence/i })).not.toBeInTheDocument();
  });

  it("wires the Show Evidence expander when evidence is supplied", async () => {
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
});
