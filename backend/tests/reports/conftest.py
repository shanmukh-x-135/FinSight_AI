"""Fixtures for the reports tests: a helper to insert reports directly.

Report generation is covered by the intelligence tests; here we seed reports
with controlled sections/types/timestamps to exercise listing, filtering,
pagination, and export.
"""

from __future__ import annotations

from datetime import datetime, timezone  # noqa: F401 (timezone used by callers)

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.models import Report


def sample_sections(*, long_text: bool = False, special: bool = False) -> dict:
    exec_summary = "Markets were mixed; one watch idea stands out."
    if long_text:
        exec_summary = ("A very long executive summary. " * 200).strip()
    if special:
        exec_summary = "Special chars — “curly”, ₹1,000, bullet •, arrow →, ellipsis…, CJK 中文."
    return {
        "executive_summary": exec_summary,
        "market_summary": {
            "narrative": "Breadth was positive.",
            "breadth": {"advancers": 3, "decliners": 1, "unchanged": 0, "total": 4,
                        "advance_decline_ratio": 3.0},
            "gainers": [{"symbol": "AAA.NS", "name": "Alpha", "close": 105.0,
                         "change_percent": 5.0}],
            "losers": [{"symbol": "BBB.NS", "name": "Beta", "close": 96.0,
                         "change_percent": -4.0}],
        },
        "portfolio_summary": {
            "narrative": "Concentrated but healthy.",
            "total_value": 19440.0, "total_return_percent": -3.5, "health_score": 46.9,
            "risk_level": "high", "diversification_score": 49.5, "number_of_holdings": 2,
            "sector_allocation": [],
        },
        "historical_summary": {
            "narrative": "Today resembles 5 past sessions.",
            "query_date": "2024-01-02",
            "statistics": {"k": 5, "sample_size": 5, "bullish_probability": 0.6,
                           "avg_next_day_return": 0.4},
            "similar_sessions": [],
        },
        "recommendations": [{
            "symbol": "AAA.NS", "name": "Alpha", "sector": "Technology", "action": "watch",
            "confidence": 62, "score": 0.14, "evidence": ["RSI at 60 (bullish momentum)"],
            "risks": ["Standard market risk applies"],
            "historical_context": {"bullish_probability": 0.6, "sample_size": 5},
            "explanation": "Watch AAA.NS — momentum is constructive.",
        }],
        "risk_alerts": [{
            "symbol": "BBB.NS", "name": "Beta", "sector": "Energy", "action": "avoid",
            "confidence": 40, "score": -0.2, "evidence": ["RSI at 35 (oversold)"],
            "risks": ["Negative news sentiment"],
            "historical_context": {"bullish_probability": None, "sample_size": None},
            "explanation": "Avoid BBB.NS for now.",
        }],
        "news": {"notable": [{"title": "Alpha wins deal", "sentiment_label": "positive",
                              "sentiment_score": 0.8, "tags": ["AAA.NS"]}]},
        "meta": {"prompt_version": "1.0", "llm_backend": "DeterministicNarrator",
                 "generated_at": "2024-01-02T10:00:00+00:00"},
    }


@pytest_asyncio.fixture
async def seed_reports(db_session: AsyncSession):
    """Insert reports for a given user_id; returns a callable factory."""

    async def _make(user_id: int, report_type: str = "daily", *,
                    created: datetime | None = None, **kwargs) -> Report:
        report = Report(user_id=user_id, report_type=report_type,
                        sections=sample_sections(**kwargs))
        if created is not None:
            report.created_at = created
        db_session.add(report)
        await db_session.flush()
        await db_session.commit()
        return report

    return _make


@pytest.fixture
def make_sections():
    """Expose the sections factory to tests without cross-module imports."""
    return sample_sections
