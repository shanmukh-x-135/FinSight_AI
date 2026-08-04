# Phase 6 AI regression benchmark — PASS

- Review date: 2026-08-04
- Benchmark version: 1.0
- Prompt version: 1.1
- Provider: `DeterministicNarrator`
- Scenarios reviewed: 12/12
- Mechanical gates: 12/12 passed
- Deterministic rank order: BULL.NS, VOL.NS, HOT.NS, REBOUND.NS,
  NEWSUP.NS, SECTOR.NS, HISTUP.NS, SPARSE.NS, FLAT.NS, HISTDN.NS,
  NEWSDN.NS, BEAR.NS

## Review result

Every narrative below was read in full. The review confirmed that actions and
rank order remain deterministic; confidence, evidence, and risks match the
scenario inputs; no output contains a price prediction; sparse inputs do not
invent unavailable indicators; and conflicting signals remain visible rather
than being flattened into an unsupported conclusion.

The first review run found that a zero MACD histogram was labelled “negative”
and a zero EMA distance was labelled “above.” Those evidence-label defects were
corrected before this passing snapshot and now have a focused regression test.

A Gemini run was not performed because no Gemini API key is configured in this
workspace. The same runner supports `--configured-provider`; its output must be
reviewed and recorded when provider credentials are available.

## Reviewed outputs

### broad_bullish_alignment — PASS

Action `watch`, confidence 79%, score 0.626000.

> Watch BULL.NS — confidence 79%. RSI at 68 (bullish momentum); Price above its
> 20-day EMA (+4.0%); MACD histogram positive; +3.0% today; Technology sector
> +2.0% today; News sentiment positive (+0.60); 70% of 20 similar historical
> sessions closed higher. Risks: Standard market risk applies.

### broad_bearish_alignment — PASS

Action `avoid`, confidence 19%, score -0.686000.

> Avoid BEAR.NS — confidence 19%. RSI at 32 (oversold); Price below its 20-day
> EMA (-4.0%); MACD histogram negative; -3.0% today; Energy sector -2.0% today;
> News sentiment negative (-0.60); 30% of 20 similar historical sessions closed
> higher. Risks: Negative news sentiment; Trading below its 50-day trend;
> Similar historical sessions favored downside.

### neutral_market — PASS

Action `hold`, confidence 49%, score -0.020000.

> Hold FLAT.NS — confidence 49%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.0% today; Utilities sector +0.0% today.
> Risks: Standard market risk applies.

### overbought_high_volatility — PASS

Action `watch`, confidence 59%, score 0.226000.

> Watch HOT.NS — confidence 59%. RSI at 78 (bullish momentum); Price above its
> 20-day EMA (+2.0%); MACD histogram positive; +1.2% today; Industrials sector
> +1.0% today; News sentiment positive (+0.20). Risks: Overbought (RSI 78);
> Elevated volatility (ATR 4.5%).

### oversold_rebound — PASS

Action `watch`, confidence 58%, score 0.198333.

> Watch REBOUND.NS — confidence 58%. RSI at 30 (oversold); Price above its
> 20-day EMA (+0.5%); MACD histogram positive; +2.0% today; Consumer sector
> +0.5% today; News sentiment positive (+0.30). Risks: Standard market risk
> applies.

### positive_news_only — PASS

Action `watch`, confidence 56%, score 0.160000.

> Watch NEWSUP.NS — confidence 56%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.0% today; Media sector +0.0% today; News
> sentiment positive (+0.90). Risks: Standard market risk applies.

### negative_news_only — PASS

Action `avoid`, confidence 42%, score -0.200000.

> Avoid NEWSDN.NS — confidence 42%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.0% today; Media sector +0.0% today; News
> sentiment negative (-0.90). Risks: Negative news sentiment.

### bullish_historical_context — PASS

Action `watch`, confidence 60%, score 0.110000.

> Watch HISTUP.NS — confidence 60%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.6% today; Finance sector +0.0% today; 80%
> of 25 similar historical sessions closed higher. Risks: Standard market risk
> applies.

### bearish_historical_context — PASS

Action `avoid`, confidence 40%, score -0.110000.

> Avoid HISTDN.NS — confidence 40%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.0% today; Finance sector +0.0% today; 20%
> of 25 similar historical sessions closed higher. Risks: Similar historical
> sessions favored downside.

### high_volatility_opportunity — PASS

Action `watch`, confidence 60%, score 0.253333.

> Watch VOL.NS — confidence 60%. RSI at 60 (bullish momentum); Price above its
> 20-day EMA (+2.0%); MACD histogram positive; +2.0% today; Metals sector +1.0%
> today; News sentiment positive (+0.30). Risks: Elevated volatility (ATR 6.0%).

### sector_leadership — PASS

Action `watch`, confidence 55%, score 0.130000.

> Watch SECTOR.NS — confidence 55%. RSI at 50 (neutral); Price at its 20-day EMA
> (+0.0%); MACD histogram neutral; +0.0% today; Healthcare sector +3.0% today.
> Risks: Standard market risk applies.

### sparse_data — PASS

Action `hold`, confidence 51%, score 0.033333.

> Hold SPARSE.NS — confidence 51%. +0.5% today. Risks: Standard market risk
> applies.

## Re-run

From `backend/`:

```bash
./.venv/bin/python -m pytest tests/intelligence/test_ai_regression_benchmark.py
./.venv/bin/python -m tests.ai_benchmark
./.venv/bin/python -m tests.ai_benchmark --configured-provider
```

The final command uses the configured provider and still falls back safely if
the SDK, credentials, network, timeout, or grounding checks fail. In that case,
the scenario's `provider_response` gate fails so fallback prose cannot be
misreported as a live-model pass. Confirm both `GeminiClient` and an overall
`PASS` before treating that run as a live-provider review.
