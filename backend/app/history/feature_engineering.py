"""Feature engineering + normalization for historical sessions.

Turns one trading day's per-stock prices/indicators into a fixed-length market
feature vector, and standardizes vectors with a fitted ``Normalizer``.

CRITICAL (design doc / roadmap): the *same* normalization must be applied when
building the index and when querying it — any drift silently breaks similarity.
So there is exactly one ``Normalizer`` class, fitted once on the corpus and
persisted; both paths load and use it. Do not normalize anywhere else.
"""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass

import numpy as np

# Fixed, ordered feature set. Order is part of the contract — never reorder
# without rebuilding the index.
FEATURE_NAMES: tuple[str, ...] = (
    "avg_return",
    "median_return",
    "pct_advancers",
    "advance_decline_ratio",
    "avg_rsi",
    "avg_ema20_distance",
    "avg_ema50_distance",
    "avg_bollinger_position",
    "avg_atr_pct",
    "avg_macd_hist_pct",
    "avg_sentiment",   # real news sentiment (Phase 5); neutral 0.0 when no news
    "usd_inr_return",
    "crude_oil_return",
    "gold_return",
    "us_10y_yield_return",
)

# Neutral value used when a date has no news sentiment. Dates before news existed
# get a constant 0.0 (zero variance → no effect on distance); dates with news get
# real, varying values that then contribute to similarity automatically.
SENTIMENT_NEUTRAL = 0.0

MIN_STOCKS_FOR_SESSION = 3


@dataclass(frozen=True)
class StockDay:
    """One stock's data for one date (raw close + indicator + sentiment values)."""

    close: float
    prev_close: float | None
    rsi: float | None
    ema20: float | None
    ema50: float | None
    bb_upper: float | None
    bb_lower: float | None
    atr: float | None
    macd_hist: float | None
    sentiment: float | None = None


@dataclass(frozen=True)
class MacroDay:
    """Daily returns for the persisted cross-asset macro proxies."""

    usd_inr_return: float
    crude_oil_return: float
    gold_return: float
    us_10y_yield_return: float


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def compute_session_feature(
    stock_days: list[StockDay], *, macro: MacroDay | None
) -> dict[str, float] | None:
    """Aggregate per-stock data into a market feature dict.

    Returns ``None`` if the day lacks enough data to form a *complete* vector
    (so every stored session has all features — no imputation, no NaNs).
    """
    returns = [
        sd.close / sd.prev_close - 1.0
        for sd in stock_days
        if sd.prev_close and sd.prev_close > 0 and sd.close > 0
    ]
    if len(returns) < MIN_STOCKS_FOR_SESSION or macro is None:
        return None

    advancers = sum(1 for r in returns if r > 0)
    decliners = sum(1 for r in returns if r < 0)

    avg_rsi = _mean([sd.rsi for sd in stock_days if sd.rsi is not None])
    ema20 = _mean(
        [(sd.close - sd.ema20) / sd.ema20 for sd in stock_days if sd.ema20]
    )
    ema50 = _mean(
        [(sd.close - sd.ema50) / sd.ema50 for sd in stock_days if sd.ema50]
    )
    bb = _mean(
        [
            (sd.close - sd.bb_lower) / (sd.bb_upper - sd.bb_lower)
            for sd in stock_days
            if sd.bb_upper is not None
            and sd.bb_lower is not None
            and sd.bb_upper > sd.bb_lower
        ]
    )
    atr = _mean([sd.atr / sd.close for sd in stock_days if sd.atr is not None and sd.close])
    macd = _mean(
        [sd.macd_hist / sd.close for sd in stock_days if sd.macd_hist is not None and sd.close]
    )

    # Require every technical aggregate — a complete vector or nothing.
    if None in (avg_rsi, ema20, ema50, bb, atr, macd):
        return None

    # Real news sentiment (Phase 5); neutral 0.0 when no article covered the day.
    sentiments = [sd.sentiment for sd in stock_days if sd.sentiment is not None]
    avg_sentiment = _mean(sentiments) if sentiments else SENTIMENT_NEUTRAL

    return {
        "avg_return": _mean(returns),
        "median_return": statistics.median(returns),
        "pct_advancers": advancers / len(returns),
        "advance_decline_ratio": advancers / max(decliners, 1),
        "avg_rsi": avg_rsi,
        "avg_ema20_distance": ema20,
        "avg_ema50_distance": ema50,
        "avg_bollinger_position": bb,
        "avg_atr_pct": atr,
        "avg_macd_hist_pct": macd,
        "avg_sentiment": avg_sentiment,
        "usd_inr_return": macro.usd_inr_return,
        "crude_oil_return": macro.crude_oil_return,
        "gold_return": macro.gold_return,
        "us_10y_yield_return": macro.us_10y_yield_return,
    }


def vector_from_features(features: dict[str, float]) -> list[float]:
    """Project a feature dict onto the fixed-order vector."""
    return [float(features[name]) for name in FEATURE_NAMES]


class Normalizer:
    """Z-score standardizer fitted on the corpus and reused for queries.

    Zero-variance features map to 0 to avoid division by zero, so they simply
    don't affect distance.
    """

    def __init__(self, mean: np.ndarray, std: np.ndarray) -> None:
        self.mean = mean
        self.std = std

    @classmethod
    def fit(cls, vectors: list[list[float]]) -> "Normalizer":
        arr = np.asarray(vectors, dtype="float64")
        mean = arr.mean(axis=0)
        std = arr.std(axis=0)
        return cls(mean=mean, std=std)

    def transform(self, vector: list[float]) -> np.ndarray:
        v = np.asarray(vector, dtype="float64")
        safe_std = np.where(self.std == 0, 1.0, self.std)
        out = (v - self.mean) / safe_std
        out = np.where(self.std == 0, 0.0, out)  # constant features → 0
        return out.astype("float32")

    def transform_many(self, vectors: list[list[float]]) -> np.ndarray:
        return np.vstack([self.transform(v) for v in vectors]).astype("float32")

    # ----- persistence (same params for build + query) --------------------
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {
                    "feature_names": list(FEATURE_NAMES),
                    "mean": self.mean.tolist(),
                    "std": self.std.tolist(),
                },
                f,
            )

    @classmethod
    def load(cls, path: str) -> "Normalizer":
        with open(path) as f:
            data = json.load(f)
        if tuple(data["feature_names"]) != FEATURE_NAMES:
            raise ValueError("Persisted normalizer feature set does not match code.")
        return cls(
            mean=np.asarray(data["mean"], dtype="float64"),
            std=np.asarray(data["std"], dtype="float64"),
        )
