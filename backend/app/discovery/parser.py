"""Strict natural-language-to-AST parser; it never emits SQL."""

from __future__ import annotations

import re

from app.discovery.exceptions import UnsupportedScreenerQueryError
from app.discovery.schemas import ScreenerAST, ScreenerCondition

_UNSUPPORTED = {
    "roe": "ROE",
    "roce": "ROCE",
    "debt": "debt",
    "revenue": "revenue",
    "promoter": "promoter holding",
    "cash flow": "cash flow",
    "ebitda": "EBITDA",
    "book value": "book value",
    "dividend": "dividend yield",
}


def _number(value: str) -> float:
    return float(value.replace(",", ""))


def parse_screener_query(query: str) -> ScreenerAST:
    text = " ".join(query.lower().strip().split())
    unsupported = [label for token, label in _UNSUPPORTED.items() if token in text]
    if unsupported:
        raise UnsupportedScreenerQueryError(unsupported)

    universe = "NIFTY100"
    if re.search(r"nifty\s*(?:next\s*)?50", text):
        universe = "NIFTYNEXT50" if "next" in text else "NIFTY50"
    elif re.search(r"nifty\s*100", text):
        universe = "NIFTY100"

    conditions: list[ScreenerCondition] = []
    sector = re.search(
        r"(?:in|from)\s+(?:the\s+)?([a-z][a-z &-]{1,40}?)\s+sector\b", text
    )
    if sector:
        conditions.append(
            ScreenerCondition(
                field="sector", operator="eq", value=sector.group(1).strip()
            )
        )

    rsi_between = re.search(
        r"rsi(?:\s*14)?\s+(?:between\s+)?(\d+(?:\.\d+)?)\s*(?:-|to|and)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if rsi_between:
        conditions.append(
            ScreenerCondition(
                field="rsi_14",
                operator="between",
                value=_number(rsi_between.group(1)),
                upper_value=_number(rsi_between.group(2)),
            )
        )
    else:
        rsi = re.search(
            r"rsi(?:\s*14)?\s*(?:is\s*)?(above|over|greater than|below|under|less than)\s*(\d+(?:\.\d+)?)",
            text,
        )
        if rsi:
            conditions.append(
                ScreenerCondition(
                    field="rsi_14",
                    operator="gt"
                    if rsi.group(1) in {"above", "over", "greater than"}
                    else "lt",
                    value=_number(rsi.group(2)),
                )
            )

    for period in (20, 50):
        match = re.search(
            rf"(above|below)\s+(?:the\s+)?ema\s*{period}\b|ema\s*{period}\s+(above|below)",
            text,
        )
        if match:
            direction = match.group(1) or match.group(2)
            conditions.append(
                ScreenerCondition(field=f"price_vs_ema{period}", operator=direction)
            )  # type: ignore[arg-type]

    macd = re.search(r"macd(?:\s+histogram)?\s+(positive|negative)", text)
    if macd:
        conditions.append(
            ScreenerCondition(field="macd_histogram", operator=macd.group(1))
        )  # type: ignore[arg-type]

    volume = re.search(
        r"(?:relative\s+)?volume\s*(?:above|over|greater than|>)\s*(\d+(?:\.\d+)?)\s*x?",
        text,
    )
    if volume:
        conditions.append(
            ScreenerCondition(
                field="volume_ratio", operator="gt", value=_number(volume.group(1))
            )
        )

    pe = re.search(
        r"(?:p/e|pe)(?:\s+ratio)?\s*(?:is\s*)?(above|over|greater than|below|under|less than)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if pe:
        conditions.append(
            ScreenerCondition(
                field="pe_ratio",
                operator="gt"
                if pe.group(1) in {"above", "over", "greater than"}
                else "lt",
                value=_number(pe.group(2)),
            )
        )
    if "profitable" in text or "positive eps" in text:
        conditions.append(ScreenerCondition(field="eps", operator="positive"))

    sentiment = re.search(
        r"(?:recent\s+)?(?:news\s+)?sentiment\s+(non[- ]negative|positive|negative)", text
    )
    if sentiment is None:
        sentiment = re.search(
            r"(non[- ]negative|positive|negative)\s+(?:recent\s+)?(?:news\s+)?sentiment",
            text,
        )
    if sentiment:
        operator = (
            "non_negative" if sentiment.group(1).startswith("non") else sentiment.group(1)
        )
        conditions.append(ScreenerCondition(field="news_sentiment", operator=operator))  # type: ignore[arg-type]

    change = re.search(
        r"(?:price\s+)?change\s*(?:is\s*)?(above|over|greater than|below|under|less than)\s*([+-]?\d+(?:\.\d+)?)\s*%",
        text,
    )
    if change:
        conditions.append(
            ScreenerCondition(
                field="price_change_percent",
                operator="gt"
                if change.group(1) in {"above", "over", "greater than"}
                else "lt",
                value=_number(change.group(2)),
            )
        )
    elif "gainers" in text or "gaining" in text:
        conditions.append(
            ScreenerCondition(field="price_change_percent", operator="positive")
        )
    elif "losers" in text or "falling" in text:
        conditions.append(
            ScreenerCondition(field="price_change_percent", operator="negative")
        )

    signal = re.search(
        r"(?:signal(?:\s+state)?|signals?)\s+(bullish|bearish|neutral)", text
    )
    if signal:
        conditions.append(
            ScreenerCondition(field="signal_state", operator="eq", value=signal.group(1))
        )
    if re.search(
        r"(?:current\s+)?regime(?:\s+fit)?\s+(?:is\s+)?(?:aligned|matching)|fits?\s+(?:the\s+)?(?:current\s+)?regime",
        text,
    ):
        conditions.append(
            ScreenerCondition(field="regime_fit", operator="eq", value="aligned")
        )

    if not conditions:
        raise UnsupportedScreenerQueryError([])
    return ScreenerAST(universe=universe, conditions=conditions)
