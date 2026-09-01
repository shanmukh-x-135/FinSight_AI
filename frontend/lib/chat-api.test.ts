import { beforeEach, describe, expect, it, vi } from "vitest";

import { chatApi, type ChatMessage } from "./api";

const userMessage: ChatMessage = {
  id: 1,
  role: "user",
  content: "How is the market?",
  created_at: "2026-08-04T10:00:00Z",
  evidence: [],
  confidence: null,
  sources: [],
  risks: [],
};

const assistantMessage: ChatMessage = {
  id: 2,
  role: "assistant",
  content: "Market breadth is balanced.",
  created_at: "2026-08-04T10:00:01Z",
  evidence: ["One advancer and one decliner."],
  confidence: 65,
  sources: [{ kind: "market", label: "Market breadth", reference: "/market" }],
  risks: ["End-of-day data may not reflect intraday moves."],
};

describe("chatApi.stream", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("parses SSE events split across arbitrary response chunks", async () => {
    const payload = [
      `event: meta\ndata: ${JSON.stringify({ user: userMessage })}\n\n`,
      'event: chunk\ndata: {"delta":"Market "}\n\n',
      'event: chunk\ndata: {"delta":"breadth is balanced."}\n\n',
      `event: complete\ndata: ${JSON.stringify({ assistant: assistantMessage })}\n\n`,
    ].join("");
    const encoded = new TextEncoder().encode(payload);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoded.slice(0, 37));
        controller.enqueue(encoded.slice(37, 111));
        controller.enqueue(encoded.slice(111));
        controller.close();
      },
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );
    const onUser = vi.fn();
    const onChunk = vi.fn();
    const onComplete = vi.fn();

    await chatApi.stream("How is the market?", { onUser, onChunk, onComplete });

    expect(onUser).toHaveBeenCalledWith(userMessage);
    expect(onChunk.mock.calls.flat()).toEqual(["Market ", "breadth is balanced."]);
    expect(onComplete).toHaveBeenCalledWith(assistantMessage);
    expect(fetch).toHaveBeenCalledWith(
      "/api-proxy/api/v1/chat?stream=true",
      expect.objectContaining({ method: "POST", cache: "no-store", credentials: "include" }),
    );
  });

  it("rejects a truncated stream instead of presenting a partial answer as complete", async () => {
    const body = `event: chunk\ndata: {"delta":"Partial"}\n\n`;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }),
    );

    await expect(
      chatApi.stream("Question", {
        onUser: vi.fn(),
        onChunk: vi.fn(),
        onComplete: vi.fn(),
      }),
    ).rejects.toThrow("Chat stream ended before completion.");
  });
});
