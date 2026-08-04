import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AIAnalysisState } from "./AIAnalysisState";

describe("AIAnalysisState", () => {
  it("renders a neutral empty state", () => {
    render(<AIAnalysisState status="empty" message="No signals today." />);
    expect(screen.getByRole("status")).toHaveTextContent("No signals today.");
    expect(screen.getByRole("status")).not.toHaveClass("text-foreground");
  });

  it("renders a distinct unavailable state without hiding other page content", () => {
    render(<AIAnalysisState status="unavailable" message="Analysis is unavailable." />);
    expect(screen.getByRole("status")).toHaveTextContent("Analysis is unavailable.");
    expect(screen.getByRole("status")).toHaveClass("text-foreground");
  });
});
