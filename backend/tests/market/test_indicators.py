"""Unit tests for technical indicators against hand-verified reference values.

Indicator bugs are silent, so each golden below is computed by hand in the
comment and asserted exactly (or within a tight tolerance for floats).
"""

from __future__ import annotations

import math

import pytest

from app.market import indicators as ind


# ----- SMA -----------------------------------------------------------------
def test_sma_reference() -> None:
    # trailing means of window 3
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_too_short() -> None:
    assert ind.sma([1, 2], 3) == [None, None]


# ----- EMA -----------------------------------------------------------------
def test_ema_reference() -> None:
    # period 3, k=0.5, seed=SMA(1,2,3)=2 → 2, then 4*.5+2*.5=3, 5*.5+3*.5=4
    result = ind.ema([1, 2, 3, 4, 5], 3)
    assert result[0] is None and result[1] is None
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(3.0)
    assert result[4] == pytest.approx(4.0)


# ----- RSI -----------------------------------------------------------------
def test_rsi_reference_wilder() -> None:
    # prices [10,11,10,11,10,11], period 2 → last RSI = 68.75 (hand-derived).
    result = ind.rsi([10, 11, 10, 11, 10, 11], period=2)
    assert result[0] is None and result[1] is None
    assert result[-1] == pytest.approx(68.75)


def test_rsi_bounds_and_extremes() -> None:
    rising = ind.rsi(list(range(1, 30)), period=14)
    falling = ind.rsi(list(range(30, 1, -1)), period=14)
    # A monotonically rising series has no losses → RSI pinned at 100.
    assert rising[-1] == pytest.approx(100.0)
    # A monotonically falling series has no gains → RSI at 0.
    assert falling[-1] == pytest.approx(0.0)
    for v in rising + falling:
        assert v is None or 0.0 <= v <= 100.0


def test_rsi_too_short_all_none() -> None:
    assert ind.rsi([1, 2, 3], period=14) == [None, None, None]


def test_rsi_flat_series_is_neutral() -> None:
    result = ind.rsi([100.0] * 20, period=14)
    assert result[-1] == pytest.approx(50.0)


# ----- MACD ----------------------------------------------------------------
def test_macd_reference() -> None:
    # closes [1..5], fast=2, slow=3, signal=2 → constant MACD 0.5, signal 0.5, hist 0.
    macd_line, signal_line, hist = ind.macd([1, 2, 3, 4, 5], fast=2, slow=3, signal=2)
    assert macd_line[-1] == pytest.approx(0.5)
    assert signal_line[-1] == pytest.approx(0.5)
    assert hist[-1] == pytest.approx(0.0)


def test_macd_equals_ema_difference() -> None:
    closes = [5, 7, 6, 8, 10, 9, 11, 13, 12, 14, 16, 15, 17]
    macd_line, _, _ = ind.macd(closes, fast=3, slow=6, signal=3)
    ef = ind.ema(closes, 3)
    es = ind.ema(closes, 6)
    for i in range(len(closes)):
        if ef[i] is not None and es[i] is not None:
            assert macd_line[i] == pytest.approx(ef[i] - es[i])


def test_constant_price_has_zero_macd_and_zero_width_bands() -> None:
    closes = [100.0] * 60
    macd_line, signal_line, histogram = ind.macd(closes)
    upper, middle, lower = ind.bollinger_bands(closes)

    assert macd_line[-1] == pytest.approx(0.0)
    assert signal_line[-1] == pytest.approx(0.0)
    assert histogram[-1] == pytest.approx(0.0)
    assert upper[-1] == middle[-1] == lower[-1] == pytest.approx(100.0)
    assert ind.ema(closes, 20)[-1] == pytest.approx(100.0)
    assert ind.ema(closes, 50)[-1] == pytest.approx(100.0)


# ----- Bollinger Bands -----------------------------------------------------
def test_bollinger_reference() -> None:
    # closes [2,4,6], period 3 → mean 4, pop std sqrt(8/3)
    upper, middle, lower = ind.bollinger_bands([2, 4, 6], period=3, num_std=2.0)
    std = math.sqrt(8 / 3)
    assert middle[-1] == pytest.approx(4.0)
    assert upper[-1] == pytest.approx(4 + 2 * std)
    assert lower[-1] == pytest.approx(4 - 2 * std)


def test_bollinger_bands_ordering() -> None:
    upper, middle, lower = ind.bollinger_bands([1, 3, 2, 5, 4, 6, 5, 7], period=3)
    for u, m, low in zip(upper, middle, lower, strict=True):
        if m is not None:
            assert low <= m <= u


# ----- ATR -----------------------------------------------------------------
def test_atr_reference_wilder() -> None:
    # highs [10,12,11], lows [8,9,9], closes [9,11,10], period 2.
    # TR = [2, 3, 2]; Wilder p2: seed=(2+3)/2=2.5; next=(2.5+2)/2=2.25 → last 2.25.
    result = ind.atr([10, 12, 11], [8, 9, 9], [9, 11, 10], period=2)
    assert result[-1] == pytest.approx(2.25)


def test_atr_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        ind.atr([1, 2], [1], [1, 2], period=2)


def test_true_range_includes_overnight_gap() -> None:
    # Day two range is 12-11=1, but the gap from prior close 9 makes TR=3.
    result = ind.atr([10, 12], [8, 11], [9, 11.5], period=1)
    assert result == pytest.approx([2.0, 3.0])


# ----- latest --------------------------------------------------------------
def test_latest_returns_last_defined() -> None:
    assert ind.latest([None, 1.0, 2.0, None]) == 2.0
    assert ind.latest([None, None]) is None
    assert ind.latest([]) is None
