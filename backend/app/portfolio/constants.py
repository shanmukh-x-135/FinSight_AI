"""Portfolio-domain constants: analytics weights and thresholds.

Centralized and documented so the health/risk formulas are transparent and
reproducible (design doc's explainability principle) — see docs/portfolio.md.
"""

from __future__ import annotations

# Health score (0-100) is a weighted blend of three transparent components.
HEALTH_DIVERSIFICATION_WEIGHT = 0.4
HEALTH_CONCENTRATION_WEIGHT = 0.3
HEALTH_PERFORMANCE_WEIGHT = 0.3

# Risk level is derived from concentration (the largest single-holding weight).
CONCENTRATION_HIGH_PCT = 50.0   # >= this: high risk
CONCENTRATION_MEDIUM_PCT = 30.0  # >= this: medium risk

DEFAULT_PORTFOLIO_NAME = "My Portfolio"
