import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { WatchlistItem } from "@/lib/api";

import { DashboardWatchlist } from "./DashboardWatchlist";

const item = (id: number, overrides: Partial<WatchlistItem> = {}): WatchlistItem => ({
  id,
  symbol: `STOCK${id}.NS`,
  name: `Stock ${id}`,
  sector: "Technology",
  current_price: 100 + id,
  previous_close: 100,
  change: id,
  change_percent: id,
  pinned: false,
  sort_order: id,
  ...overrides,
});

describe("DashboardWatchlist", () => {
  it("renders live quote data, pin state, and management navigation", () => {
    render(
      <DashboardWatchlist
        items={[
          item(1, {
            symbol: "RELIANCE.NS",
            name: "Reliance Industries",
            current_price: 2910.5,
            change_percent: 1.25,
            pinned: true,
          }),
        ]}
      />,
    );

    expect(screen.getByText("RELIANCE.NS")).toBeInTheDocument();
    expect(screen.getByText("Reliance Industries")).toBeInTheDocument();
    expect(screen.getByText("₹2,910.5")).toBeInTheDocument();
    expect(screen.getByText("+1.25%")).toHaveClass("text-green-600");
    expect(screen.getByText("Pinned")).toHaveClass("sr-only");
    expect(screen.getByRole("link", { name: "Manage watchlist" })).toHaveAttribute(
      "href",
      "/watchlist",
    );
  });

  it("shows an actionable empty state", () => {
    render(<DashboardWatchlist items={[]} />);

    expect(screen.getByText("0 stocks tracked")).toBeInTheDocument();
    expect(screen.getByText(/Add stocks to keep/)).toBeInTheDocument();
  });

  it("limits dashboard rows while reporting the full count", () => {
    render(<DashboardWatchlist items={Array.from({ length: 7 }, (_, i) => item(i + 1))} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    expect(screen.getByText("Showing 5 of 7 tracked stocks.")).toBeInTheDocument();
  });
});
