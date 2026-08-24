# Phase 10E — Analytics and AI Validation

Status: deterministic production evaluation passed; live Gemini narration is blocked by an upstream provider request failure and Phase 10E is not signed off.

## Deterministic analytics audit

The audit traced market, indicator, portfolio, and `market_regime_v1` outputs back to their deterministic inputs. The LLM remains outside every formula, ranking, confidence score, and historical outcome.

Validated areas:

- market breadth, advance/decline ratio, signed movers, equal-weight sector performance, technical summary, and nullable sentiment;
- Wilder RSI/ATR, SMA-seeded EMA, MACD, and population-standard-deviation Bollinger Bands;
- portfolio value, cost, absolute/percentage return, daily P&L, weights, sector exposure, HHI concentration, diversification, volatility, health/risk, and holding contribution sums;
- the ordered 25-feature `market_regime_v1` vector, robust normalization, squared-L2 FAISS ranking, deterministic factor comparison, coverage flags, and forward wealth/drawdown/upside paths.

Three semantics defects were corrected:

1. Gainer and loser lists now exclude flat and opposite-direction stocks.
2. Portfolio volatility is `null` unless every valued holding also has valid ATR coverage; a partial subset is not presented as a portfolio-wide metric.
3. Historical outcomes require contiguous candidate trading sessions. A rejected intermediate date is never skipped and a later accepted date is never labelled “next day.”

Independent fixtures now cover flat indicators, overnight ATR gaps, zero and negative returns, single/multiple holdings, concentration extremes, missing price/ATR data, contribution identities, breadth edges, sector aggregation, normalized feature distances, deterministic divergent factors, and independently accumulated forward outcomes.

## Golden conversational evaluation

The fixed fixture at `backend/tests/fixtures/phase10e_golden_queries.json` contains the ten required production-style questions. `backend/tests/chat/test_phase10e_golden_queries.py` evaluates the same deterministic chat-draft path used before Gemini narration.

| Query | Required grounded slices |
|---|---|
| What moved the market today? | Breadth, signed movers, closes, session date |
| Analyse my portfolio. | User portfolio, holdings, return, health, concentration |
| What are the main risks in my portfolio? | Concentration, diversification, sector exposure, metric availability |
| Why is RELIANCE moving? | Exact ticker, close, move, session date, indicators, tagged-news limitations |
| Find historically similar market sessions. | Similarity statistics, query date, outcome limitation |
| Compare today with a similar historical regime. | Current market plus historical slice and scenario warning |
| Summarise the strongest bullish and bearish signals. | Deterministically ranked candidates, evidence, confidence, risks |
| Generate today’s EOD research brief. | Portfolio, watchlist, market, history, news, and signals |
| What evidence supports this conclusion? | Full topic continuity from the preceding EOD research brief |
| What data is unavailable or uncertain? | Explicit missing-slice and sparse-indicator inventory |

The harness asserts relevant source kinds, expected exact fixture prices and dates, ticker identifiers, risk language, bounded confidence, non-advice language, and absence of the untrusted question from the facts payload. Extra guards verify that an unknown ticker does not become company evidence, a news citation preserves its HTTP(S) URL and publication time, and an unsafe URL scheme falls back to the internal market page.

Chat retrieval now reuses `ContextBuilder.build_candidates()` and the existing deterministic recommendation engine. Gemini can narrate these selected facts but cannot create rankings or substitute question text for evidence. External news citations open separately with `noopener noreferrer`.

## Failure and fallback coverage

Automated coverage verifies:

- Gemini timeout, provider exception/quota-style failure, and empty response all terminate through the deterministic fallback;
- retries and the shared request deadline/provider-call budget are bounded;
- hallucinated price/advice prose is rejected by grounding validation;
- empty portfolio, partial valuation, no tagged news, and unavailable historical similarity produce explicit unavailable states;
- SSE streaming reconstructs the validated persisted response and rejects a truncated stream;
- assistant evidence, sources, risks, confidence, and generation metadata survive persistence;
- no raw provider exception or stack trace is returned through the chat API.

Historical probabilities are always described as analogue outcomes rather than forecasts or guarantees. The standard response risk also states that end-of-day data may not reflect intraday moves.

## Local verification

Run on 24 August 2026:

- backend Ruff lint: pass;
- backend pytest: 440 passed, with four PostgreSQL-only tests skipped locally because `TEST_POSTGRES_URL` was not set;
- frontend Vitest: 58 passed across 21 test files;
- frontend ESLint: pass;
- Next.js production compilation/type checking/static generation: pass using the documented `next build --webpack` fallback because local Turbopack was prohibited from binding its internal helper port by the execution sandbox.

PostgreSQL integration and production checks are separate gates.

## Production evaluation

The final application revision `764cf2c` passed GitHub Actions CI run
`32765606289`, including fresh PostgreSQL migrations, the full backend suite,
frontend lint/tests/build, and both container builds. Render and Vercel each
reported successful deployments for that exact revision.

An isolated production evaluator account was created without retaining or
printing its credentials. Its portfolio contains one RELIANCE and one TCS
holding whose cost bases were copied from their live production closes; its
watchlist contains RELIANCE. The account and chat history were intentionally
left intact because production user data must not be deleted.

All ten required questions returned HTTP 200 against the Render API on 24
August 2026. The evaluator confirmed:

- all 50 active stocks and a current market date of 24 August 2026;
- the expected retrieval source kinds for every question;
- non-empty evidence and risk metadata with confidence bounded to 85%;
- the exact live RELIANCE close and current-session date in company evidence;
- exactly the two evaluator holdings in portfolio evidence;
- an HTTP(S) news source URL;
- identical five-slice retrieval for the EOD brief and its evidence follow-up;
- explicit unavailable/uncertain-data language; and
- a streaming response with the correct event-stream content type, a terminal
  `complete` event, and no error event.

Observed full-response latency ranged from 996 ms to 12,561 ms, with a median
of 1,306.5 ms. No unsupported guarantee or price-target language was present.

## Remaining Phase 10E blocker

Every production query used the safe deterministic fallback. A separate
sanitized diagnostic request reported `GeminiClient` as configured with model
`gemini-3.6-flash`, two bounded attempts, zero provider responses, no token
usage/model version, and a deterministic fallback after 197 ms. This is an
upstream request failure, not a grounding rejection. Official Google Gen AI SDK
documentation confirms that `gemini-3.6-flash` is a valid model identifier.

The Render `GEMINI_API_KEY` and its Google project model access/quota must be
verified in their respective control planes without exposing the key. After the
external issue is corrected, at least one production request must return
`backend=gemini`, a provider response count of one or more, a model version, and
grounded prose before Phase 10E can be signed off. Phase 10F must not begin
before that gate passes.
