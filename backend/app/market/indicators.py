"""Technical indicators — pure functions, no I/O.

Every function takes plain Python sequences of floats and returns a list of the
same length, with ``None`` for the warm-up positions where the indicator is not
yet defined. Keeping these pure (no DB, no network, no pandas) makes them
deterministic and unit-testable against hand-verified reference values — which
matters here because indicator bugs are silent (wrong numbers, no crash).

Conventions (to match standard charting tools):
* EMA seeds on the SMA of the first ``period`` values, multiplier ``2/(period+1)``.
* RSI and ATR use **Wilder's** smoothing (RMA), seeded on a simple average.
* Bollinger Bands use the **population** standard deviation (divide by N).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

Number = float
OptFloat = float | None


def sma(values: Sequence[Number], period: int) -> list[OptFloat]:
    """Simple moving average. ``result[i]`` = mean of the trailing ``period`` values."""
    n = len(values)
    out: list[OptFloat] = [None] * n
    if period <= 0 or n < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, n):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: Sequence[Number], period: int) -> list[OptFloat]:
    """Exponential moving average, seeded on the SMA of the first ``period`` values."""
    n = len(values)
    out: list[OptFloat] = [None] * n
    if period <= 0 or n < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period  # SMA seed
    out[period - 1] = prev
    for i in range(period, n):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def wilder_rma(values: Sequence[Number], period: int) -> list[OptFloat]:
    """Wilder's smoothed moving average (RMA), seeded on a simple average.

    ``rma[i] = (rma[i-1] * (period - 1) + values[i]) / period``.
    """
    n = len(values)
    out: list[OptFloat] = [None] * n
    if period <= 0 or n < period:
        return out
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def rsi(closes: Sequence[Number], period: int = 14) -> list[OptFloat]:
    """Relative Strength Index (Wilder). Values in [0, 100]."""
    n = len(closes)
    out: list[OptFloat] = [None] * n
    if n <= period:
        return out

    gains = [0.0] * (n - 1)
    losses = [0.0] * (n - 1)
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains[i - 1] = change if change > 0 else 0.0
        losses[i - 1] = -change if change < 0 else 0.0

    avg_gain = wilder_rma(gains, period)
    avg_loss = wilder_rma(losses, period)

    # avg_gain/avg_loss are aligned to the `changes` array (index j -> close j+1).
    for j in range(len(gains)):
        g, loss = avg_gain[j], avg_loss[j]
        if g is None or loss is None:
            continue
        if g == 0 and loss == 0:
            value = 50.0
        elif loss == 0:
            value = 100.0
        elif g == 0:
            value = 0.0
        else:
            rs = g / loss
            value = 100.0 - 100.0 / (1.0 + rs)
        out[j + 1] = value
    return out


def macd(
    closes: Sequence[Number],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[OptFloat], list[OptFloat], list[OptFloat]]:
    """MACD line, signal line, histogram.

    * MACD line   = EMA(fast) - EMA(slow)
    * signal line = EMA(MACD line, signal)
    * histogram   = MACD line - signal line
    """
    n = len(closes)
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    macd_line: list[OptFloat] = [None] * n
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal = EMA over the defined tail of the MACD line, realigned to full length.
    defined = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[OptFloat] = [None] * n
    histogram: list[OptFloat] = [None] * n
    if defined:
        values = [v for _, v in defined]
        sig = ema(values, signal)
        for (idx, _), s in zip(defined, sig, strict=True):
            if s is not None:
                signal_line[idx] = s
                histogram[idx] = macd_line[idx] - s
    return macd_line, signal_line, histogram


def bollinger_bands(
    closes: Sequence[Number],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[OptFloat], list[OptFloat], list[OptFloat]]:
    """Bollinger Bands: (upper, middle, lower) using population std dev."""
    n = len(closes)
    middle = sma(closes, period)
    upper: list[OptFloat] = [None] * n
    lower: list[OptFloat] = [None] * n
    if period <= 0 or n < period:
        return upper, middle, lower
    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mean = middle[i]
        assert mean is not None
        variance = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return upper, middle, lower


def atr(
    highs: Sequence[Number],
    lows: Sequence[Number],
    closes: Sequence[Number],
    period: int = 14,
) -> list[OptFloat]:
    """Average True Range (Wilder). Requires equal-length high/low/close series."""
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("highs, lows, closes must be the same length")
    out: list[OptFloat] = [None] * n
    if n == 0:
        return out

    true_range = [0.0] * n
    true_range[0] = highs[0] - lows[0]
    for i in range(1, n):
        prev_close = closes[i - 1]
        true_range[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
    return wilder_rma(true_range, period)


def latest(series: Sequence[OptFloat]) -> OptFloat:
    """Return the last non-None value in a series, or None."""
    for value in reversed(series):
        if value is not None:
            return value
    return None
