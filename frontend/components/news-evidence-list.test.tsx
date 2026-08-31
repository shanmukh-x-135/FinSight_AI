import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NewsEvidenceList } from "@/components/news-evidence-list";

describe("NewsEvidenceList", () => {
  it("keeps missing coverage distinct from neutral", () => {
    render(<NewsEvidenceList evidence={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent("No relevant news found");
    expect(screen.getByRole("status")).toHaveTextContent("unavailable, not neutral");
  });

  it("shows traceable source, driver, excerpt, and confidences", () => {
    render(<NewsEvidenceList evidence={[{
      id: 7,
      headline: "Reliance profit rises",
      publisher: "Test Wire",
      published_at: "2026-08-27T10:00:00Z",
      source_url: "https://example.test/article",
      sentiment_class: "positive",
      sentiment_score: 0.68,
      sentiment_confidence: 0.82,
      event_category: "Earnings",
      event_confidence: 0.7,
      driver: "Reported financial performance",
      evidence_excerpt: "Quarterly profit rose on stronger refining margins.",
      matched_alias: "RELIANCE INDUSTRIES",
      entity_match_confidence: 0.95,
    }]} />);
    expect(screen.getByRole("link", { name: /open article/i })).toHaveAttribute("href", "https://example.test/article");
    expect(screen.getByText(/Reported financial performance/)).toBeVisible();
    fireEvent.click(screen.getByText("Review evidence"));
    expect(screen.getByText(/Quarterly profit rose/)).toBeVisible();
    expect(screen.getByText("95%")).toBeVisible();
  });
});
