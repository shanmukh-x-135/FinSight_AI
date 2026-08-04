"""Unit tests for feature engineering and the normalizer (drift-prevention)."""

from __future__ import annotations

import pytest

from app.history.feature_engineering import (
    FEATURE_NAMES,
    MacroDay,
    Normalizer,
    StockDay,
    compute_session_feature,
    vector_from_features,
)

MACRO = MacroDay(
    usd_inr_return=0.01,
    crude_oil_return=-0.02,
    gold_return=0.005,
    us_10y_yield_return=0.003,
)


def test_compute_session_feature_reference() -> None:
    stock_days = [
        StockDay(close=110, prev_close=100, rsi=60, ema20=100, ema50=90,
                 bb_upper=120, bb_lower=100, atr=11, macd_hist=2.2),
        StockDay(close=99, prev_close=100, rsi=40, ema20=100, ema50=100,
                 bb_upper=110, bb_lower=90, atr=9.9, macd_hist=-0.99),
        StockDay(close=105, prev_close=100, rsi=50, ema20=100, ema50=100,
                 bb_upper=110, bb_lower=100, atr=10.5, macd_hist=1.05),
    ]
    f = compute_session_feature(stock_days, macro=MACRO)
    assert f is not None
    assert f["avg_return"] == pytest.approx((0.10 - 0.01 + 0.05) / 3)
    assert f["median_return"] == pytest.approx(0.05)
    assert f["pct_advancers"] == pytest.approx(2 / 3)
    assert f["advance_decline_ratio"] == pytest.approx(2.0)
    assert f["avg_rsi"] == pytest.approx(50.0)
    assert f["avg_ema20_distance"] == pytest.approx((0.10 - 0.01 + 0.05) / 3)
    assert f["avg_bollinger_position"] == pytest.approx((0.5 + 0.45 + 0.5) / 3)
    assert f["avg_atr_pct"] == pytest.approx(0.1)
    assert f["avg_sentiment"] == 0.0
    assert f["usd_inr_return"] == 0.01
    assert f["crude_oil_return"] == -0.02


def test_sentiment_is_averaged_into_feature() -> None:
    # Phase 5 loop closure: per-stock sentiment averages into avg_sentiment
    # (None values excluded).
    days = [
        StockDay(110, 100, 60, 100, 90, 120, 100, 11, 2.2, sentiment=0.5),
        StockDay(99, 100, 40, 100, 100, 110, 90, 9.9, -0.99, sentiment=-0.1),
        StockDay(105, 100, 50, 100, 100, 110, 100, 10.5, 1.05, sentiment=None),
    ]
    f = compute_session_feature(days, macro=MACRO)
    assert f is not None
    assert f["avg_sentiment"] == pytest.approx((0.5 - 0.1) / 2)


def test_no_sentiment_defaults_neutral() -> None:
    days = [
        StockDay(110, 100, 60, 100, 90, 120, 100, 11, 2.2),
        StockDay(99, 100, 40, 100, 100, 110, 90, 9.9, -0.99),
        StockDay(105, 100, 50, 100, 100, 110, 100, 10.5, 1.05),
    ]
    f = compute_session_feature(days, macro=MACRO)
    assert f is not None
    assert f["avg_sentiment"] == 0.0


def test_insufficient_stocks_returns_none() -> None:
    # Only 2 stocks with returns (< MIN_STOCKS_FOR_SESSION).
    days = [
        StockDay(100, 99, 50, 100, 100, 110, 90, 1, 0.1),
        StockDay(100, 99, 50, 100, 100, 110, 90, 1, 0.1),
    ]
    assert compute_session_feature(days, macro=MACRO) is None


def test_missing_indicator_returns_none() -> None:
    # 3 stocks with returns but none have RSI → incomplete vector → None.
    days = [
        StockDay(110, 100, None, 100, 100, 110, 90, 1, 0.1),
        StockDay(99, 100, None, 100, 100, 110, 90, 1, 0.1),
        StockDay(105, 100, None, 100, 100, 110, 90, 1, 0.1),
    ]
    assert compute_session_feature(days, macro=MACRO) is None


def test_missing_macro_returns_none() -> None:
    days = [
        StockDay(110, 100, 60, 100, 90, 120, 100, 11, 2.2),
        StockDay(99, 100, 40, 100, 100, 110, 90, 9.9, -0.99),
        StockDay(105, 100, 50, 100, 100, 110, 100, 10.5, 1.05),
    ]
    assert compute_session_feature(days, macro=None) is None


def test_vector_matches_feature_order() -> None:
    features = {name: float(i) for i, name in enumerate(FEATURE_NAMES)}
    assert vector_from_features(features) == [float(i) for i in range(len(FEATURE_NAMES))]


# ----- Normalizer ----------------------------------------------------------
def test_normalizer_zero_variance_dim_is_zeroed() -> None:
    # Second dimension is constant → must normalize to 0 (no div-by-zero).
    norm = Normalizer.fit([[0.0, 10.0], [2.0, 10.0], [4.0, 10.0]])
    out = norm.transform([2.0, 10.0])
    assert out[0] == pytest.approx(0.0)  # (2-2)/std
    assert out[1] == pytest.approx(0.0)  # constant dim
    out2 = norm.transform([4.0, 10.0])
    assert out2[1] == pytest.approx(0.0)


def test_normalizer_is_reproducible() -> None:
    norm = Normalizer.fit([[1.0, 2.0], [3.0, 6.0], [5.0, 10.0]])
    a = norm.transform([3.0, 6.0])
    b = norm.transform([3.0, 6.0])
    assert list(a) == list(b)


def test_normalizer_save_load_round_trip(tmp_path) -> None:
    norm = Normalizer.fit([[1.0, 2.0], [3.0, 6.0], [5.0, 10.0]])
    path = str(tmp_path / "normalizer.json")
    norm.save(path)
    loaded = Normalizer.load(path)
    before = norm.transform([3.0, 6.0])
    after = loaded.transform([3.0, 6.0])
    assert list(before) == list(after)
