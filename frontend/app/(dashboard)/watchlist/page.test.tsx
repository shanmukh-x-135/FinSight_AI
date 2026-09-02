import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { newsApi, watchlistApi } from "@/lib/api";

import WatchlistPage from "./page";

vi.mock("@/lib/api", () => ({
  ApiError: class ApiError extends Error {},
  newsApi: { latestSentiment: vi.fn() },
  watchlistApi: { list: vi.fn(), add: vi.fn(), update: vi.fn(), remove: vi.fn() },
}));

const rows = [
  { id: 1, symbol: "ZZZ.NS", name: "Zulu", sector: "Energy", current_price: 120, previous_close: 110, change: 10, change_percent: 9.09, pinned: false, sort_order: 0, rsi_14: 40, trend: "bullish" },
  { id: 2, symbol: "AAA.NS", name: "Alpha", sector: "Technology", current_price: 90, previous_close: 100, change: -10, change_percent: -10, pinned: false, sort_order: 1, rsi_14: 70, trend: "bearish" },
];

describe("WatchlistPage sorting", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(watchlistApi.list).mockResolvedValue(rows);
    vi.mocked(watchlistApi.update).mockResolvedValue({ id: 1 });
    vi.mocked(watchlistApi.remove).mockResolvedValue(null);
    vi.mocked(newsApi.latestSentiment).mockResolvedValue([{ symbol: "ZZZ.NS", latest_sentiment: -0.2, availability: "available", confidence: 0.7, article_count: 1 }, { symbol: "AAA.NS", latest_sentiment: 0.5, availability: "available", confidence: 0.8, article_count: 2 }]);
  });

  it("sorts the dense table while retaining pinned-first behavior", async () => {
    render(<WatchlistPage />);
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(3));
    expect(within(screen.getAllByRole("row")[1]).getByText("ZZZ.NS")).toBeVisible();

    fireEvent.change(screen.getByRole("combobox", { name: "Sort watchlist" }), { target: { value: "symbol" } });
    expect(within(screen.getAllByRole("row")[1]).getByText("AAA.NS")).toBeVisible();
  });

  it("pins immediately and rolls back when persistence fails", async () => {
    vi.mocked(watchlistApi.update).mockRejectedValueOnce(new Error("offline"));
    render(<WatchlistPage />);
    await screen.findByRole("button", { name: "Pin ZZZ.NS" });

    fireEvent.click(screen.getByRole("button", { name: "Pin ZZZ.NS" }));
    expect(screen.getByRole("button", { name: "Unpin ZZZ.NS" })).toBeDisabled();

    expect(await screen.findByRole("alert")).toHaveTextContent("previous watchlist was restored");
    expect(screen.getByRole("button", { name: "Pin ZZZ.NS" })).toBeEnabled();
  });

  it("removes immediately and restores the row when persistence fails", async () => {
    vi.mocked(watchlistApi.remove).mockRejectedValueOnce(new Error("offline"));
    render(<WatchlistPage />);
    await screen.findByRole("button", { name: "Remove ZZZ.NS" });

    fireEvent.click(screen.getByRole("button", { name: "Remove ZZZ.NS" }));
    expect(screen.queryByText("ZZZ.NS")).not.toBeInTheDocument();

    expect(await screen.findByRole("alert")).toHaveTextContent("previous watchlist was restored");
    expect(screen.getByText("ZZZ.NS")).toBeVisible();
  });
});
