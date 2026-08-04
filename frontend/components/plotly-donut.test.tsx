import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlotlyDonut } from "@/components/plotly-donut";

vi.mock("react-plotly.js", () => ({
  default: () => <div data-testid="plotly-chart" />,
}));

describe("PlotlyDonut", () => {
  it("renders an accessible chart and exact allocation legend", () => {
    render(
      <PlotlyDonut
        size={180}
        slices={[
          { label: "Technology", value: 600, percent: 60 },
          { label: "Financials", value: 400, percent: 40 },
        ]}
      />,
    );

    expect(screen.getByRole("img", { name: "Sector allocation donut chart" })).toBeVisible();
    expect(screen.getByTestId("plotly-chart")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeVisible();
    expect(screen.getByText("60.0%")).toBeVisible();
    expect(screen.getByText("Financials")).toBeVisible();
    expect(screen.getByText("40.0%")).toBeVisible();
  });
});
