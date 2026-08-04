import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { EvidencePanel } from "./EvidencePanel";

const props = {
  evidence: ["RSI at 65 (bullish momentum)", "Price above its 20-day EMA (+4.8%)"],
  risks: ["Elevated volatility (ATR 2.2%)"],
  confidence: 62,
  historicalContext: { bullish_probability: 0.6, sample_size: 5 },
};

describe("EvidencePanel", () => {
  it("hides evidence until expanded", () => {
    render(<EvidencePanel {...props} />);
    expect(screen.getByRole("button", { name: /show evidence/i })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    expect(screen.queryByText(/RSI at 65/)).not.toBeInTheDocument();
  });

  it("reveals real evidence, risks, confidence, and historical analog on click", async () => {
    const user = userEvent.setup();
    render(<EvidencePanel {...props} />);
    await user.click(screen.getByRole("button", { name: /show evidence/i }));

    expect(screen.getByText(/RSI at 65 \(bullish momentum\)/)).toBeInTheDocument();
    expect(screen.getByText(/Price above its 20-day EMA/)).toBeInTheDocument();
    expect(screen.getByText(/Elevated volatility/)).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(
      screen.getByText(/60% of 5 similar historical sessions closed higher/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide evidence/i })).toBeInTheDocument();
  });

  it("handles an empty evidence list gracefully", async () => {
    const user = userEvent.setup();
    render(<EvidencePanel evidence={[]} />);
    await user.click(screen.getByRole("button", { name: /show evidence/i }));
    expect(screen.getByText(/No supporting indicators/)).toBeInTheDocument();
  });
});
