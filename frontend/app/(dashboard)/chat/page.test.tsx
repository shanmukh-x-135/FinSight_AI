import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatApi, type ChatMessage } from "@/lib/api";

import ChatPage from "./page";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    chatApi: {
      history: vi.fn(),
      clear: vi.fn(),
      stream: vi.fn(),
    },
  };
});

const userMessage: ChatMessage = {
  id: 1,
  role: "user",
  content: "What does today's market breadth show?",
  created_at: "2026-08-04T10:00:00Z",
  evidence: [],
  confidence: null,
  sources: [],
  risks: [],
};

const assistantMessage: ChatMessage = {
  id: 2,
  role: "assistant",
  content: "Market breadth has one advancer and one decliner.",
  created_at: "2026-08-04T10:00:01Z",
  evidence: ["Market breadth has 1 advancer and 1 decliner."],
  confidence: 65,
  sources: [{ kind: "market", label: "Market breadth", reference: "/market" }],
  risks: ["End-of-day data may not reflect intraday moves."],
  generation: {
    configured_backend: "GeminiClient",
    backend: "gemini",
    requested_model: "gemini-3.6-flash",
    model_version: "gemini-3.6-flash-001",
    response_id: "response-1",
    finish_reason: "STOP",
    provider_created_at: "2026-08-04T10:00:01Z",
    attempt_count: 1,
    provider_response_count: 1,
    fallback_used: false,
    latency_ms: 20,
    usage: {
      prompt_tokens: 10,
      candidate_tokens: 4,
      total_tokens: 14,
      cached_tokens: null,
      thoughts_tokens: null,
    },
  },
};

describe("ChatPage", () => {
  beforeEach(() => {
    vi.mocked(chatApi.history).mockResolvedValue([]);
    vi.mocked(chatApi.clear).mockResolvedValue({ deleted: 2 });
    vi.mocked(chatApi.stream).mockImplementation(async (_question, handlers) => {
      handlers.onUser(userMessage);
      handlers.onChunk("Market breadth has ");
      handlers.onChunk("one advancer and one decliner.");
      handlers.onComplete(assistantMessage);
    });
    Object.defineProperty(Element.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("streams a suggested question and renders evidence, confidence, and sources", async () => {
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.click(
      await screen.findByRole("button", { name: "What does today's market breadth show?" }),
    );

    expect(await screen.findByText(assistantMessage.content)).toBeInTheDocument();
    expect(screen.getByText(/gemini-3.6-flash-001/)).toBeInTheDocument();
    expect(screen.getByText("65% confidence")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Market breadth" })).toHaveAttribute(
      "href",
      "/market",
    );
    await user.click(screen.getByRole("button", { name: "Show evidence" }));
    expect(screen.getByText("Market breadth has 1 advancer and 1 decliner.")).toBeInTheDocument();
    expect(screen.getByText("End-of-day data may not reflect intraday moves.")).toBeInTheDocument();
    expect(chatApi.stream).toHaveBeenCalledWith(
      "What does today's market breadth show?",
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it("loads private history and clears it after confirmation", async () => {
    vi.mocked(chatApi.history).mockResolvedValue([userMessage, assistantMessage]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    render(<ChatPage />);

    expect(await screen.findByText(assistantMessage.content)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Delete chat history" }));

    expect(chatApi.clear).toHaveBeenCalledOnce();
    expect(await screen.findByText("Ask about the evidence")).toBeInTheDocument();
  });
});
