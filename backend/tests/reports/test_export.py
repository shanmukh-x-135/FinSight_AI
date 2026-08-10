"""Export tests: Markdown is the source of truth; PDF renders from it.

Covers the happy path plus the roadmap's edge cases — an unusually long section,
a missing optional section, and special/Unicode characters in generated text.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pytest
from httpx import AsyncClient
from pypdf import PdfReader

from app.intelligence.models import Report
from app.reports.exporters import render_markdown, render_pdf
from app.reports.exporters.pdf import _latin1, _strip_inline

PW = "S3curePass!"


def _report(sections: dict) -> Report:
    r = Report(user_id=1, report_type="daily", sections=sections)
    r.id = 1
    r.created_at = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
    return r


# ----- Markdown (single source of truth) -----------------------------------
def test_markdown_contains_all_sections(make_sections) -> None:
    md = render_markdown(_report(make_sections()))
    for heading in [
        "# FinSight AI — Daily Report",
        "## Executive Summary",
        "## Market Summary",
        "## Portfolio Summary",
        "## Historical Context",
        "## Recommendations",
        "## Risk Alerts",
        "## Notable News",
    ]:
        assert heading in md
    assert "AAA.NS" in md and "RSI at 60 (bullish momentum)" in md
    assert "not a forecast" in md


def test_markdown_includes_actual_model_fallback_and_token_provenance(
    make_sections,
) -> None:
    sections = make_sections()
    sections["meta"]["llm_backend"] = "Gemini + deterministic fallback"
    sections["meta"]["generation"] = {
        "model_versions": ["gemini-3.6-flash-001"],
        "requested_models": ["gemini-3.6-flash"],
        "fallback_count": 1,
        "usage": {"total_tokens": 42},
    }

    markdown = render_markdown(_report(sections))

    assert "backend Gemini + deterministic fallback" in markdown
    assert "model gemini-3.6-flash-001" in markdown
    assert "1 deterministic fallback(s)" in markdown
    assert "42 tokens" in markdown


def test_markdown_scales_historical_return_ratio(make_sections) -> None:
    md = render_markdown(_report(make_sections()))
    # Historical returns use decimal ratios, unlike already-scaled market and
    # portfolio percentages. 0.4 must therefore render as 40%, not 0.4%.
    assert "**Avg next-day return:** +40.00%" in md
    assert "AAA.NS — Alpha (₹105.00; +5.00%)" in md
    assert "**Total return:** -3.50%" in md


def test_markdown_contains_all_screen_summary_facts(make_sections) -> None:
    md = render_markdown(_report(make_sections()))

    assert (
        "**Breadth:** 3 advancers / 1 decliners / 0 unchanged (4 tracked; A/D ratio 3.00)"
    ) in md
    assert "BBB.NS — Beta (₹96.00; -4.00%)" in md
    assert "**Diversification:** 50/100" in md
    assert "**Similar sessions:** 5 (top-5 nearest)" in md
    assert "60% of 5 similar historical sessions closed higher" in md


def test_markdown_deduplicates_structured_historical_evidence(make_sections) -> None:
    sections = make_sections()
    historical_line = "60% of 5 similar historical sessions closed higher"
    sections["recommendations"][0]["evidence"].append(historical_line)
    md = render_markdown(_report(sections))

    assert md.count(historical_line) == 1


def test_markdown_and_screen_share_five_item_news_limit(make_sections) -> None:
    sections = make_sections()
    sections["news"]["notable"] = [
        {"title": f"Story {index}", "sentiment_label": "neutral", "tags": []}
        for index in range(1, 7)
    ]
    md = render_markdown(_report(sections))

    assert "Story 5" in md
    assert "Story 6" not in md


def test_markdown_skips_missing_optional_sections(make_sections) -> None:
    sections = make_sections()
    del sections["portfolio_summary"]
    del sections["historical_summary"]
    del sections["risk_alerts"]
    md = render_markdown(_report(sections))
    assert "## Portfolio Summary" not in md
    assert "## Historical Context" not in md
    assert "## Risk Alerts" not in md
    # Required sections still present.
    assert "## Market Summary" in md and "## Recommendations" in md


def test_markdown_handles_empty_recommendations(make_sections) -> None:
    sections = make_sections()
    sections["recommendations"] = []
    md = render_markdown(_report(sections))
    assert "## Recommendations" in md
    assert "No watch-rated opportunities" in md


# ----- PDF (rendered from the Markdown) ------------------------------------
def test_pdf_renders_happy_path(make_sections) -> None:
    pdf = render_pdf(render_markdown(_report(make_sections())))
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_pdf_text_contains_every_markdown_line(make_sections) -> None:
    markdown = render_markdown(_report(make_sections()))
    pdf = render_pdf(markdown)
    reader = PdfReader(BytesIO(pdf))
    extracted = " ".join((page.extract_text() or "") for page in reader.pages)
    extracted = " ".join(extracted.split())

    for line in markdown.splitlines():
        if not line:
            continue
        expected = _latin1(_strip_inline(line))
        if expected.startswith("### "):
            expected = expected[4:]
        elif expected.startswith("## "):
            expected = expected[3:]
        elif expected.startswith("# "):
            expected = expected[2:]
        expected = " ".join(expected.split())
        assert expected in extracted, f"PDF omitted Markdown line: {line}"


def test_pdf_handles_long_text(make_sections) -> None:
    pdf = render_pdf(render_markdown(_report(make_sections(long_text=True))))
    assert pdf[:4] == b"%PDF"


def test_pdf_handles_special_characters(make_sections) -> None:
    # Em dashes, curly quotes, ₹, arrows, ellipsis, CJK — must not crash.
    pdf = render_pdf(render_markdown(_report(make_sections(special=True))))
    assert pdf[:4] == b"%PDF"


def test_pdf_handles_missing_sections(make_sections) -> None:
    sections = make_sections()
    del sections["portfolio_summary"]
    del sections["news"]
    pdf = render_pdf(render_markdown(_report(sections)))
    assert pdf[:4] == b"%PDF"


# ----- Export endpoint ------------------------------------------------------
async def _token(client: AsyncClient, email: str) -> tuple[str, int]:
    r = await client.post("/api/v1/auth/register", json={"email": email, "password": PW})
    uid = r.json()["data"]["id"]
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PW})
    return login.json()["data"]["access_token"], uid


@pytest.mark.asyncio
async def test_export_markdown_endpoint(client: AsyncClient, seed_reports) -> None:
    token, uid = await _token(client, "exp-md@example.com")
    h = {"Authorization": f"Bearer {token}"}
    report = await seed_reports(uid, "daily")
    resp = await client.get(
        f"/api/v1/reports/{report.id}/export?format=markdown", headers=h
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "attachment" in resp.headers["content-disposition"]
    assert ".md" in resp.headers["content-disposition"]
    assert "## Executive Summary" in resp.text


@pytest.mark.asyncio
async def test_export_pdf_endpoint(client: AsyncClient, seed_reports) -> None:
    token, uid = await _token(client, "exp-pdf@example.com")
    h = {"Authorization": f"Bearer {token}"}
    report = await seed_reports(uid, "daily")
    resp = await client.get(f"/api/v1/reports/{report.id}/export?format=pdf", headers=h)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:4] == b"%PDF"


@pytest.mark.asyncio
async def test_export_rejects_unknown_format(client: AsyncClient, seed_reports) -> None:
    token, uid = await _token(client, "exp-bad@example.com")
    h = {"Authorization": f"Bearer {token}"}
    report = await seed_reports(uid, "daily")
    resp = await client.get(f"/api/v1/reports/{report.id}/export?format=docx", headers=h)
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "unsupported_export_format"
