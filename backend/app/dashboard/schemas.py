"""Schema for the combined dashboard-summary endpoint (Phase 7).

The dashboard batches everything the home screen needs into one round trip
(design doc §7.3): market breadth/movers, the deterministic AI market summary,
the user's portfolio snapshot, today's opportunities (evidence-backed
recommendations), risk alerts, and the historical-similarity context. Nested
payloads are already-serialized JSON dicts reused verbatim from the market,
portfolio, history, and recommendation layers — so this endpoint composes them
rather than redefining their shapes.
"""

from __future__ import annotations

from pydantic import BaseModel


class DashboardSummaryOut(BaseModel):
    market: dict
    ai_market_summary: str
    portfolio: dict | None
    opportunities: list[dict]
    risk_alerts: list[dict]
    history: dict | None
