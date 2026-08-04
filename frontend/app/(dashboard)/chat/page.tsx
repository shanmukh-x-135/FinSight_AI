"use client";

import {
  Clock3,
  MessageSquareText,
  Send,
  Sparkles,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

import { EvidencePanel } from "@/components/EvidencePanel";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ApiError, chatApi, type ChatMessage } from "@/lib/api";

const SUGGESTED_QUESTIONS = [
  "How are my portfolio and watchlist doing?",
  "What does today's market breadth show?",
  "What happened after similar historical sessions?",
  "Summarize the latest tagged news sentiment.",
];

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <article className="ml-auto max-w-2xl" aria-label="Your message">
      <div className="rounded-2xl rounded-br-md bg-foreground px-4 py-3 text-sm leading-relaxed text-background">
        {message.content}
      </div>
      <p className="mt-1 text-right text-xs text-muted-foreground">
        {formatTime(message.created_at)}
      </p>
    </article>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  return (
    <article className="max-w-3xl" aria-label="FinSight AI response">
      <Card className="gap-0 border-blue-100 py-0 shadow-sm">
        <div className="flex items-center gap-2 border-b bg-blue-50/50 px-4 py-3">
          <Sparkles className="h-4 w-4 text-blue-600" aria-hidden />
          <span className="text-sm font-semibold">FinSight AI</span>
          {message.confidence != null && (
            <span className="ml-auto text-xs text-muted-foreground">
              {message.confidence}% confidence
            </span>
          )}
        </div>
        <div className="px-4 py-4">
          <p className="text-sm leading-7 text-foreground/90">{message.content}</p>
          <EvidencePanel
            evidence={message.evidence}
            confidence={message.confidence ?? undefined}
            risks={message.risks}
          />
          {message.sources.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Sources
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {message.sources.map((source) => (
                  <Link
                    key={`${source.kind}-${source.label}`}
                    href={source.reference}
                    className="rounded-full border bg-background px-2.5 py-1 text-xs font-medium hover:bg-muted"
                  >
                    {source.label}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>
      <p className="mt-1 text-xs text-muted-foreground">{formatTime(message.created_at)}</p>
    </article>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [streamedText, setStreamedText] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const requestRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let active = true;
    chatApi
      .history()
      .then((history) => {
        if (active) setMessages(history);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load chat history.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      requestRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: sending ? "smooth" : "auto" });
  }, [messages, streamedText, sending]);

  async function send(value: string) {
    const clean = value.trim();
    if (!clean || sending) return;
    setQuestion("");
    setError("");
    setStreamedText("");
    setSending(true);
    const controller = new AbortController();
    requestRef.current = controller;
    try {
      await chatApi.stream(
        clean,
        {
          onUser: (message) => setMessages((current) => [...current, message]),
          onChunk: (delta) => setStreamedText((current) => current + delta),
          onComplete: (message) => {
            setMessages((current) => [...current, message]);
            setStreamedText("");
          },
        },
        controller.signal,
      );
    } catch (reason) {
      if (reason instanceof DOMException && reason.name === "AbortError") return;
      setError(
        reason instanceof ApiError || reason instanceof Error
          ? reason.message
          : "The assistant could not answer. Please try again.",
      );
    } finally {
      requestRef.current = null;
      setSending(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(question);
  }

  function onQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send(question);
    }
  }

  async function clearHistory() {
    if (messages.length === 0 || !window.confirm("Delete your complete chat history?")) return;
    setError("");
    try {
      await chatApi.clear();
      setMessages([]);
      setStreamedText("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete chat history.");
    }
  }

  const userPrompts = messages.filter((message) => message.role === "user").slice().reverse();

  return (
    <div className="mx-auto grid min-h-[calc(100vh-9rem)] max-w-7xl gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="order-2 rounded-xl border bg-muted/20 p-4 lg:order-1" aria-label="Chat history">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Clock3 className="h-4 w-4 text-muted-foreground" aria-hidden />
            <h2 className="text-sm font-semibold">Recent questions</h2>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void clearHistory()}
            disabled={messages.length === 0 || sending}
            aria-label="Delete chat history"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
          </Button>
        </div>
        <div className="mt-3 max-h-52 space-y-1 overflow-y-auto lg:max-h-[calc(100vh-14rem)]">
          {userPrompts.length === 0 ? (
            <p className="py-3 text-xs leading-relaxed text-muted-foreground">
              Your questions will appear here and remain private to your account.
            </p>
          ) : (
            userPrompts.map((message) => (
              <button
                key={message.id}
                type="button"
                onClick={() => setQuestion(message.content)}
                className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-muted"
              >
                <span className="line-clamp-2">{message.content}</span>
                <span className="mt-1 block text-xs text-muted-foreground">
                  {formatTime(message.created_at)}
                </span>
              </button>
            ))
          )}
        </div>
      </aside>

      <section className="order-1 flex min-h-[38rem] min-w-0 flex-col overflow-hidden rounded-xl border bg-background lg:order-2">
        <header className="border-b px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
              <MessageSquareText className="h-5 w-5" aria-hidden />
            </div>
            <div>
              <h1 className="font-semibold">AI Research Assistant</h1>
              <p className="text-xs text-muted-foreground">
                Grounded in your portfolio, watchlist, market data, and historical evidence
              </p>
            </div>
          </div>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-4 sm:p-6" aria-label="Conversation">
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading conversation…</p>
          ) : messages.length === 0 && !sending ? (
            <div className="mx-auto flex max-w-2xl flex-col items-center py-12 text-center">
              <div className="rounded-2xl bg-blue-50 p-4 text-blue-600">
                <Sparkles className="h-7 w-7" aria-hidden />
              </div>
              <h2 className="mt-4 text-lg font-semibold">Ask about the evidence</h2>
              <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted-foreground">
                Answers use deterministic analytics already computed by FinSight. The assistant explains them; it does not predict prices.
              </p>
              <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
                {SUGGESTED_QUESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => void send(suggestion)}
                    className="rounded-xl border p-3 text-left text-sm hover:border-blue-200 hover:bg-blue-50/40"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) =>
              message.role === "user" ? (
                <UserMessage key={message.id} message={message} />
              ) : (
                <AssistantMessage key={message.id} message={message} />
              ),
            )
          )}
          {sending && (
            <article className="max-w-3xl" aria-label="FinSight AI is responding">
              <Card className="gap-0 border-blue-100 p-4 shadow-sm">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <Sparkles className="h-4 w-4 text-blue-600" aria-hidden />
                  FinSight AI
                </div>
                <p className="mt-3 text-sm leading-7" aria-live="polite">
                  {streamedText || "Reviewing your evidence…"}
                  <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-blue-600 align-middle" aria-hidden />
                </p>
              </Card>
            </article>
          )}
          <div ref={endRef} />
        </div>

        <div className="border-t bg-muted/10 p-3 sm:p-4">
          {error && <p className="mb-2 text-sm text-destructive" role="alert">{error}</p>}
          <form onSubmit={submit} className="flex items-end gap-2">
            <label htmlFor="chat-question" className="sr-only">Ask FinSight AI</label>
            <textarea
              id="chat-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={onQuestionKeyDown}
              maxLength={2000}
              rows={2}
              placeholder="Ask about your portfolio, watchlist, market, history, or news…"
              className="min-h-12 flex-1 resize-none rounded-xl border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              disabled={sending}
            />
            <Button type="submit" size="icon" disabled={sending || !question.trim()} aria-label="Send question">
              <Send className="h-4 w-4" aria-hidden />
            </Button>
          </form>
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            Research context only—not investment advice or a price prediction.
          </p>
        </div>
      </section>
    </div>
  );
}
