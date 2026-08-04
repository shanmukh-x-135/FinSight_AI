# AI Intelligence — RAG (Phase 6)

Turns everything computed in Phases 2–5 (market analytics, portfolio metrics,
historical statistics, sentiment) into explainable, evidence-backed output —
**without letting the LLM compute anything**. The LLM writes prose only; every
number, ranking, evidence item, confidence, and risk is deterministic.

## The hard rule

> Analytics decide; the AI explains.

- **Rankings, evidence, confidence, risks** — computed by the recommendation
  engine from the analytics. Provably deterministic (verified: identical order
  and scores across runs).
- **Prose** (section narratives, recommendation explanations) — the only LLM
  output, and it may only use the facts provided.

This makes the whole pipeline reproducible and grounded by construction.

## LLM backend

Provider-agnostic (`app/intelligence/llm_client.py`):

| Backend | When | Notes |
|---------|------|-------|
| **Gemini Flash** (`google-genai`) | `GEMINI_API_KEY` set | Design doc's model. Native async calls, retry + per-attempt timeout; **degrades to the fallback on any failure — never raises**. Needs the AI extra (`requirements-ai.txt`). |
| **DeterministicNarrator** | default | Renders the prose directly from the structured facts. No API key, no cost, reproducible, offline-testable. The prompt builder always supplies a grounded fallback narrative, so output is always valid. |

Same trade-off as FinBERT/Plotly in earlier phases: the design-doc model is
integrated and selectable, but the default keeps the system reproducible and
cost-free. The evidence/rankings are identical either way.

Gemini generation uses `client.aio.models.generate_content`, so provider I/O
does not block FastAPI's event loop. `LLM_TIMEOUT_SECONDS` is applied both to
the SDK transport (milliseconds) and as an `asyncio` deadline around each
attempt. Timeouts, quota errors, empty responses, and exhausted retries all
return the deterministic grounded fallback.

## Pipeline

```
context builder (RAG) → prompt builder → LLM (prose) → explainability validation → report
recommendation engine (deterministic filter → rank → evidence/risks/confidence)
```

### Context builder (`context_builder.py`)

Assembles ONLY the relevant slice per request (RAG — never the whole DB): market
breadth/gainers/losers, the user's portfolio analytics, historical similarity
statistics, news sentiment, and per-stock candidate facts. Pure data gathering,
no LLM.

### Recommendation engine (`recommendation_engine.py`)

Deterministic, LLM-free:
1. **Score** each candidate — a weighted blend (weights in `constants.py`) of
   technical strength, momentum, sector momentum, sentiment, and historical
   analog probability, minus a volatility penalty.
2. **Rank** — score descending, then symbol (stable tie-break) → the same inputs
   always yield the same order.
3. **Evidence / risks / confidence** — factual strings and a 0–100 confidence
   derived directly from the data (e.g. "RSI at 53 (neutral)", "40% of 5 similar
   historical sessions closed higher"; risks like "Elevated volatility").

`watch` (positive score) → recommendations; `avoid` (negative) → risk alerts.

### Prompt strategy (`config/prompts.py`, `prompt_builder.py`)

Structured, versioned prompts (mirrored in `docs/prompts/`): a system instruction
fixing the persona and **hard constraints** — never predict exact prices, only
use provided facts, cite evidence, surface uncertainty — then per-section
instructions with the facts injected as JSON. Each section also has a
deterministic grounded fallback narrative.

### Explainability validation (`explainability.py`)

Before a report is stored: every recommendation must have evidence, confidence,
risks, and an explanation; the report must have a market summary,
recommendations, and an executive summary. Missing anything → rejected. (Because
the fields are deterministic, well-formed output passes; the guard catches
regressions and empty LLM prose.)

### Report (`report_generator.py`)

Structured **JSONB sections** (design doc §6.2): `executive_summary`,
`market_summary`, `historical_summary` (if the index is built),
`portfolio_summary` (if the user has a portfolio), `recommendations`,
`risk_alerts`, `news`, `meta`. Markdown/PDF are rendered on demand in Phase 8.

## Data model (migration `0007_reports`)

- **reports** — `user_id` (nullable → global market report), `report_type`,
  `sections` (JSONB), `created_at`. Ownership: a user-scoped report is 404 to
  others.
- **chat_history** — created now, used by Phase 9.

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/reports/generate` | Generate + store an evidence-backed report |
| `GET /api/v1/reports` · `GET /api/v1/reports/{id}` | List / fetch (ownership-scoped) |
| `GET /api/v1/recommendations` | Current watchlist + risk alerts (evidence-backed) |

## Verification (the design doc's AI evaluation dimensions)

- **Retrieval** — context builder returns the expected slice per request.
- **Grounding** — narratives contain the real facts; recommendation explanations
  contain their own evidence (grounded by construction with the narrator).
- **Consistency / regression** — the test suite is the regression benchmark:
  bullish/bearish/neutral scenarios, with/without portfolio and history,
  determinism, and reproducibility. Live: identical rankings + reproducible
  reports across runs.
- **No price prediction** — enforced by prompt constraints; the historical
  section is explicitly framed as context, "not a forecast".
- **Provider reliability** — tests cover native async generation, event-loop
  progress during an in-flight request, configured transport timeout, retries,
  timeout fallback, empty output, and provider exceptions.

~97% coverage across the intelligence modules. Live: a real report cited RELIANCE
with RSI/EMA/MACD/sector/historical evidence and real risks, confidence 54%, and
no price forecast.
