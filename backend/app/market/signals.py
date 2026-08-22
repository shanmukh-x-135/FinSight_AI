"""Small deterministic display signals derived from persisted indicators."""

from __future__ import annotations


def trend_signal(
    close: float | None,
    ema_20: float | None,
    macd_histogram: float | None,
) -> str | None:
    if close is None or ema_20 is None or macd_histogram is None:
        return None
    if close > ema_20 and macd_histogram > 0:
        return "bullish"
    if close < ema_20 and macd_histogram < 0:
        return "bearish"
    return "mixed"
