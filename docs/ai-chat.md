# AI Chat (Phase 9)

FinSight's conversational assistant explains the deterministic intelligence
already produced by the platform. It does not create a parallel RAG path and it
does not calculate recommendations or predict prices.

## Reused intelligence pipeline

`ChatService` imports and reuses:

1. `ContextBuilder.build_chat_context()` for authenticated market, portfolio,
   watchlist, historical-similarity, and tagged-news slices;
2. `prompt_builder.chat_response()` and the shared versioned system prompt;
3. the configured `LLMClient` (`DeterministicNarrator` by default, Gemini when
   configured);
4. `generate_grounded()` and `validate_grounded_narrative()` for the same
   numeric, prediction/advice, evidence, source, confidence-consistency, and
   risk guards used by reports.

The conversational template is versioned separately. `chat-v1.1` makes
confidence application-owned metadata rather than required generated prose,
without invalidating the reviewed Phase 6 report benchmark.

Gemini receives compact deterministic facts and produces only the narrative.
Generation reserves 2,048 total output tokens while capping hidden thinking at
256 tokens. Only a normal `STOP` completion proceeds to grounding validation;
`MAX_TOKENS` and other incomplete/blocked finish reasons are retried and then
use the deterministic fallback. This completion gate does not relax any numeric,
date, citation, evidence, source, or risk validation.

Question text and recent questions are marked as untrusted and kept outside the
facts JSON. They help resolve conversational follow-ups but cannot establish a
numeric fact.

## Response contract

Every assistant message contains:

- `content` — validated explanation;
- `evidence[]` — deterministic facts used by the answer;
- `confidence` — deterministic 0–100 context-coverage score;
- `sources[]` — typed labels and routes back to the supporting screen;
- `risks[]` — uncertainty and data-timing limitations.
- `generation` — actual backend/model, response/finish identity when supplied,
  retry/fallback outcome, latency, and optional token usage.

The frontend renders these through the same `EvidencePanel` used elsewhere,
plus direct source links. Suggested questions are conveniences only; they do not
change the grounding path.

## Streaming

`POST /api/v1/chat?stream=true` returns `text/event-stream` with:

| Event | Data |
|---|---|
| `meta` | Persisted user message |
| `chunk` | `{ "delta": "..." }` validated answer fragment |
| `complete` | Complete persisted structured assistant message |

The server first generates and validates the complete answer, then atomically
persists the user/assistant pair, and only then emits chunks. This preserves the
Phase 6 safety guarantee: no unsupported provider token is exposed before
validation. It also means a browser disconnect cannot leave half an assistant
message in history. `Cache-Control: no-cache` and `X-Accel-Buffering: no`
prevent intermediary buffering; the client rejects a stream without a terminal
`complete` event.

## Persistence and ownership

Phase 9 reuses the `chat_history` table created in migration `0007_reports`.
User rows store plain question text. Assistant rows store the structured answer
as JSON in the existing text column, avoiding a schema migration while retaining
evidence/source metadata after reload. Legacy plain assistant rows remain
readable.

P10.7 adds generation provenance to that same structured payload, so a Gemini
failure cannot be reloaded or displayed later as if Gemini supplied the answer.
Legacy structured answers without provenance remain valid and return `null`.

Every repository read and delete includes `user_id`. There is no endpoint that
accepts another user's ID, and two-account API tests prove isolation.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/chat` | Grounded JSON request/response |
| `POST /api/v1/chat?stream=true` | Same response over validated SSE |
| `GET /api/v1/chat/history?limit=` | Current user's chronological history |
| `DELETE /api/v1/chat/history` | Delete only the current user's history |

All endpoints require a valid access token. JSON responses use the standard
envelope; SSE uses its documented event contract.

## Verification

- Backend API tests cover authentication, input validation, portfolio/watchlist
  grounding, valid Gemini prose without repeated confidence, contradictory
  confidence fallback, unsupported advice rejection, successful-Gemini SSE
  reconstruction, persistence, generation provenance, empty portfolios,
  two-user ownership, and isolated deletion.
- Frontend tests cover arbitrary network chunk boundaries, truncated streams,
  suggested prompts, history, clearing, evidence, confidence, sources, and
  risks.
- Chromium exercises login → Assistant → streamed response → evidence → reload
  persistence → history deletion against the real Compose stack.
