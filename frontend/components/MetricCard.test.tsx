import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetricCard, toneOf } from "./MetricCard";

describe("toneOf", () => {
  it("maps sign to tone, null → default", () => {
    expect(toneOf(1)).toBe("positive");
    expect(toneOf(-1)).toBe("negative");
    expect(toneOf(0)).toBe("neutral");
    expect(toneOf(null)).toBe("default");
    expect(toneOf(undefined)).toBe("default");
  });
});

describe("MetricCard", () => {
  it("renders label, value, and sub", () => {
    render(<MetricCard label="Total Value" value="₹1,000" sub="+5.00%" />);
    expect(screen.getByText("Total Value")).toBeInTheDocument();
    expect(screen.getByText("₹1,000")).toBeInTheDocument();
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
  });

  it("applies the positive tone colour to the value", () => {
    render(<MetricCard label="P&L" value="+₹500" tone="positive" />);
    expect(screen.getByText("+₹500")).toHaveClass("text-positive");
  });

  it("omits the sub line when not provided", () => {
    const { container } = render(<MetricCard label="X" value="1" />);
    // label + value paragraphs only.
    expect(container.querySelectorAll("p")).toHaveLength(2);
  });
});
