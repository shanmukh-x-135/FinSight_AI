import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { newsApi } from "@/lib/api";

import NewsPage from "./page";

vi.mock("@/lib/api", () => ({ newsApi: { recent: vi.fn() } }));

describe("NewsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not turn an empty news window into neutral sentiment", async () => {
    vi.mocked(newsApi.recent).mockResolvedValue([]);
    render(<NewsPage />);
    expect(await screen.findByText("No recent news found")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("unavailable, not neutral");
  });

  it("shows article and stock-match evidence", async () => {
    vi.mocked(newsApi.recent).mockResolvedValue([{
      id: 1,
      source: "Test Wire",
      url: "https://example.test/story",
      title: "Reliance reports profit growth",
      summary: "",
      published_at: "2026-08-27T10:00:00Z",
      sentiment_label: "positive",
      sentiment_score: 0.7,
      sentiment_confidence: 0.85,
      event_category: "Earnings",
      event_confidence: 0.78,
      driver: "Reported financial performance",
      evidence_excerpt: "Profit grew during the quarter.",
      tags: ["RELIANCE.NS"],
      associations: [{ symbol: "RELIANCE.NS", matched_alias: "RELIANCE INDUSTRIES", entity_match_confidence: 0.95 }],
    }]);
    render(<NewsPage />);
    expect(await screen.findByText("Reliance reports profit growth")).toBeVisible();
    expect(screen.getByRole("link", { name: /open article/i })).toHaveAttribute("href", "https://example.test/story");
    expect(screen.getByRole("link", { name: /RELIANCE.NS/i })).toHaveTextContent("match 95%");
  });
});
