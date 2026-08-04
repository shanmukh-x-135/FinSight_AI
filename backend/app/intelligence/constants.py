"""Intelligence-domain constants: ranking weights, thresholds, prompt constraints.

Centralized so the (deterministic) recommendation scoring is transparent and
reproducible — see docs/ai-intelligence.md.
"""

from __future__ import annotations

# Recommendation ranking weights (applied to components each roughly in [-1, 1]).
W_TECHNICAL = 0.30
W_MOMENTUM = 0.20
W_SECTOR = 0.15
W_SENTIMENT = 0.20
W_HISTORICAL = 0.15
W_VOLATILITY_PENALTY = 0.10   # subtracted (higher volatility → lower score)

# Action thresholds on the composite score.
WATCH_THRESHOLD = 0.10        # >= → "watch" (a recommendation)
AVOID_THRESHOLD = -0.10       # <= → "avoid" (a risk alert)

# Interpretation thresholds.
RSI_OVERBOUGHT = 70.0
RSI_BULLISH = 55.0
RSI_OVERSOLD = 35.0
HIGH_VOLATILITY_PCT = 3.5     # ATR% above this is flagged as a risk

# Report/LLM constraints (design doc §5.9) — enforced in the prompt.
PROMPT_CONSTRAINTS = (
    "Never predict exact future prices.",
    "Only use the facts provided; do not invent numbers or events.",
    "Cite the supporting evidence for every claim.",
    "Surface uncertainty and risks; do not overstate confidence.",
    "Be concise and professional.",
)
