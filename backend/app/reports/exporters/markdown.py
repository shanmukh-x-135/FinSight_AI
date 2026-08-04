"""Render a stored structured report to Markdown.

This is the **single source of truth** for report export: the PDF exporter
renders from this Markdown, so the two formats can never drift. Pure and
deterministic — it reads the JSONB ``sections`` produced in Phase 6 and lays
them out; it computes nothing and calls no LLM. Optional sections (portfolio,
historical, risk alerts, news) are simply skipped when absent.
"""

from __future__ import annotations

from typing import Any

from app.intelligence.models import Report


def _pct(n: Any) -> str:
    if n is None:
        return "—"
    return f"{n:+.2f}%" if isinstance(n, (int, float)) else str(n)


def _ratio_pct(n: Any) -> str:
    """Format a decimal ratio (0.01 = 1%) as a display percentage."""
    if n is None:
        return "—"
    return f"{n * 100:+.2f}%" if isinstance(n, (int, float)) else str(n)


def _num(n: Any, digits: int = 2) -> str:
    if n is None:
        return "—"
    return f"{n:,.{digits}f}" if isinstance(n, (int, float)) else str(n)


def _money(n: Any) -> str:
    return "—" if n is None else f"₹{_num(n)}"


def _lines(*parts: str) -> str:
    return "\n".join(parts)


def _quote_md(quote: dict) -> str:
    symbol = quote.get("symbol", "?")
    identity = f"{symbol} — {quote['name']}" if quote.get("name") else symbol
    return f"{identity} ({_money(quote.get('close'))}; {_pct(quote.get('change_percent'))})"


def _recommendation_md(rec: dict) -> list[str]:
    header = f"### {rec.get('symbol', '?')}"
    if rec.get("name"):
        header += f" — {rec['name']}"
    action = rec.get("action", "")
    conf = rec.get("confidence")
    meta = " · ".join(
        p for p in [action, f"confidence {conf}%" if conf is not None else ""] if p
    )
    out = [header]
    if meta:
        out.append(f"*{meta}*")
    if rec.get("explanation"):
        out.append("")
        out.append(rec["explanation"])
    evidence = list(rec.get("evidence") or [])
    historical = rec.get("historical_context") or {}
    probability = historical.get("bullish_probability")
    sample_size = historical.get("sample_size")
    if probability is not None and sample_size:
        historical_line = (
            f"{round(probability * 100)}% of {sample_size} similar historical "
            "sessions closed higher"
        )
        if historical_line not in evidence:
            evidence.append(historical_line)
    if evidence:
        out.append("")
        out.append("**Evidence:**")
        out.extend(f"- {item}" for item in evidence)
    if rec.get("risks"):
        out.append("")
        out.append("**Risks:**")
        out.extend(f"- {r}" for r in rec["risks"])
    out.append("")
    return out


def render_markdown(report: Report) -> str:
    s: dict = report.sections or {}
    meta: dict = s.get("meta", {})
    out: list[str] = []

    # Title + provenance
    title = f"FinSight AI — {report.report_type.capitalize()} Report"
    out.append(f"# {title}")
    generated = meta.get("generated_at", report.created_at.isoformat() if report.created_at else "")
    provenance = " · ".join(
        p for p in [
            f"Report #{report.id}",
            f"generated {generated}" if generated else "",
            f"prompt v{meta['prompt_version']}" if meta.get("prompt_version") else "",
            f"backend {meta['llm_backend']}" if meta.get("llm_backend") else "",
        ] if p
    )
    if provenance:
        out.append(f"_{provenance}_")
    out.append("")

    # Executive summary
    if s.get("executive_summary"):
        out.append("## Executive Summary")
        out.append(s["executive_summary"])
        out.append("")

    # Market summary
    market = s.get("market_summary")
    if market:
        out.append("## Market Summary")
        if market.get("narrative"):
            out.append(market["narrative"])
            out.append("")
        b = market.get("breadth") or {}
        if b:
            out.append(
                f"- **Breadth:** {b.get('advancers', '—')} advancers / "
                f"{b.get('decliners', '—')} decliners / "
                f"{b.get('unchanged', '—')} unchanged "
                f"({b.get('total', '—')} tracked; A/D ratio "
                f"{_num(b.get('advance_decline_ratio'))})"
            )
        gainers = market.get("gainers") or []
        if gainers:
            g = ", ".join(_quote_md(quote) for quote in gainers[:5])
            out.append(f"- **Top gainers:** {g}")
        losers = market.get("losers") or []
        if losers:
            lo = ", ".join(_quote_md(quote) for quote in losers[:5])
            out.append(f"- **Top losers:** {lo}")
        out.append("")

    # Portfolio summary (optional)
    portfolio = s.get("portfolio_summary")
    if portfolio:
        out.append("## Portfolio Summary")
        if portfolio.get("narrative"):
            out.append(portfolio["narrative"])
            out.append("")
        out.append(f"- **Total value:** {_money(portfolio.get('total_value'))}")
        out.append(f"- **Total return:** {_pct(portfolio.get('total_return_percent'))}")
        out.append(f"- **Health score:** {_num(portfolio.get('health_score'), 0)} "
                   f"(risk: {portfolio.get('risk_level', '—')})")
        out.append(f"- **Diversification:** {_num(portfolio.get('diversification_score'), 0)}/100")
        out.append(f"- **Holdings:** {portfolio.get('number_of_holdings', '—')}")
        out.append("")

    # Historical context (optional)
    hist = s.get("historical_summary")
    if hist:
        out.append("## Historical Context")
        if hist.get("narrative"):
            out.append(hist["narrative"])
            out.append("")
        st = hist.get("statistics") or {}
        prob = st.get("bullish_probability")
        out.append(f"- **Similar sessions:** {st.get('sample_size', '—')} "
                   f"(top-{st.get('k', '—')} nearest)")
        if prob is not None:
            out.append(f"- **Closed higher next day:** {round(prob * 100)}% of them, historically")
        out.append(f"- **Avg next-day return:** {_ratio_pct(st.get('avg_next_day_return'))}")
        out.append("- _Historical context, not a forecast._")
        out.append("")

    # Recommendations
    recs = s.get("recommendations") or []
    out.append("## Recommendations")
    if recs:
        for rec in recs:
            out.extend(_recommendation_md(rec))
    else:
        out.append("_No watch-rated opportunities in this report._")
        out.append("")

    # Risk alerts (optional)
    alerts = s.get("risk_alerts") or []
    if alerts:
        out.append("## Risk Alerts")
        for rec in alerts:
            out.extend(_recommendation_md(rec))

    # News (optional)
    news = (s.get("news") or {}).get("notable") or []
    if news:
        out.append("## Notable News")
        for a in news[:5]:
            label = a.get("sentiment_label")
            tags = ", ".join(a.get("tags") or [])
            suffix = " · ".join(p for p in [label, tags] if p)
            out.append(f"- {a.get('title', '')}" + (f" _({suffix})_" if suffix else ""))
        out.append("")

    return _lines(*out).rstrip() + "\n"
