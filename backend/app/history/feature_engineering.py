"""Deterministic market-regime features and shared robust normalization.

The vector is deliberately ticker-order-independent. Historical reconstruction
and the latest-session query both call the same computation and normalization
code; outcomes never enter the feature vector.
"""

from __future__ import annotations

import json
import math
import os
import statistics
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

FEATURE_VERSION = "market_regime_v1"
NORMALIZATION_METHOD = "median_iqr_clip8_v1"

# Ordered low-dimensional regime contract. Changing names/order requires a new
# feature version and complete PostgreSQL/FAISS rebuild.
FEATURE_NAMES: tuple[str, ...] = (
    "equal_weight_return",
    "median_return",
    "advancing_share",
    "declining_share",
    "unchanged_share",
    "advance_decline_ratio",
    "above_ema20_share",
    "above_ema50_share",
    "median_rsi",
    "rsi_dispersion",
    "overbought_share",
    "oversold_share",
    "median_momentum_20",
    "momentum_dispersion",
    "median_atr_pct",
    "return_dispersion",
    "median_realized_volatility_20",
    "median_relative_volume_20",
    "elevated_volume_share",
    "sector_return_dispersion",
    "sector_leadership_spread",
    "usd_inr_return",
    "crude_oil_return",
    "gold_return",
    "us_10y_yield_return",
)

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "direction": ("equal_weight_return", "median_return"),
    "breadth": (
        "advancing_share",
        "declining_share",
        "unchanged_share",
        "advance_decline_ratio",
        "above_ema20_share",
        "above_ema50_share",
    ),
    "momentum": (
        "median_rsi",
        "rsi_dispersion",
        "overbought_share",
        "oversold_share",
        "median_momentum_20",
        "momentum_dispersion",
    ),
    "volatility": (
        "median_atr_pct",
        "return_dispersion",
        "median_realized_volatility_20",
    ),
    "volume": ("median_relative_volume_20", "elevated_volume_share"),
    "sector": ("sector_return_dispersion", "sector_leadership_spread"),
    "macro": (
        "usd_inr_return",
        "crude_oil_return",
        "gold_return",
        "us_10y_yield_return",
    ),
}

MIN_USABLE_CONSTITUENTS = 3
MIN_CONSTITUENT_COVERAGE = 0.80
MIN_SECTOR_COVERAGE = 0.60
RETURN_CAP = 0.20
MOMENTUM_CAP = 0.50
ATR_CAP = 0.20
REALIZED_VOLATILITY_CAP = 0.20
RELATIVE_VOLUME_CAP = 10.0
MACRO_RETURN_CAP = 0.20
ELEVATED_VOLUME_THRESHOLD = 1.5
NORMALIZED_VALUE_CAP = 8.0


class MembershipMode(StrEnum):
    EFFECTIVE = "effective_membership"
    AVAILABLE_DATA_PROXY = "available_data_proxy"


class SessionRejectionReason(StrEnum):
    NO_EXPECTED_CONSTITUENTS = "no_expected_constituents"
    INSUFFICIENT_CONSTITUENTS = "insufficient_constituents"
    INSUFFICIENT_COVERAGE = "insufficient_coverage"
    INSUFFICIENT_SECTOR_COVERAGE = "insufficient_sector_coverage"
    MISSING_MACRO_CONTEXT = "missing_macro_context"
    NON_FINITE_FEATURE = "non_finite_feature"


@dataclass(frozen=True)
class StockDay:
    """Precomputed, past-only values for one expected constituent and date."""

    stock_id: int
    sector: str | None
    return_1d: float | None
    rsi: float | None
    above_ema20: bool | None
    above_ema50: bool | None
    momentum_20: float | None
    atr_pct: float | None
    realized_volatility_20: float | None
    relative_volume_20: float | None

    @property
    def usable(self) -> bool:
        numeric = (
            self.return_1d,
            self.rsi,
            self.momentum_20,
            self.atr_pct,
            self.realized_volatility_20,
            self.relative_volume_20,
        )
        return (
            self.above_ema20 is not None
            and self.above_ema50 is not None
            and all(value is not None and math.isfinite(value) for value in numeric)
        )


@dataclass(frozen=True)
class MacroDay:
    usd_inr_return: float
    crude_oil_return: float
    gold_return: float
    us_10y_yield_return: float


@dataclass(frozen=True)
class SessionFeatureResult:
    features: dict[str, float] | None
    rejection_reason: SessionRejectionReason | None
    expected_constituent_count: int
    usable_constituent_count: int
    coverage_ratio: float
    sector_coverage_ratio: float
    membership_mode: MembershipMode
    quality_flags: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.features is not None


def _clip(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _iqr(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    q25, q75 = np.percentile(np.asarray(values, dtype="float64"), [25, 75])
    return float(q75 - q25)


def _rejected(
    reason: SessionRejectionReason,
    *,
    expected: int,
    usable: int,
    coverage: float,
    sector_coverage: float,
    membership_mode: MembershipMode,
) -> SessionFeatureResult:
    return SessionFeatureResult(
        features=None,
        rejection_reason=reason,
        expected_constituent_count=expected,
        usable_constituent_count=usable,
        coverage_ratio=coverage,
        sector_coverage_ratio=sector_coverage,
        membership_mode=membership_mode,
        quality_flags=(),
    )


def compute_session_feature(
    stock_days: list[StockDay],
    *,
    macro: MacroDay | None,
    expected_constituent_count: int,
    membership_mode: MembershipMode,
    minimum_coverage: float = MIN_CONSTITUENT_COVERAGE,
) -> SessionFeatureResult:
    """Build one complete robust regime vector or return an explicit rejection."""
    expected = expected_constituent_count
    if expected <= 0:
        return _rejected(
            SessionRejectionReason.NO_EXPECTED_CONSTITUENTS,
            expected=expected,
            usable=0,
            coverage=0.0,
            sector_coverage=0.0,
            membership_mode=membership_mode,
        )
    usable_days = [item for item in stock_days if item.usable]
    usable = len(usable_days)
    coverage = usable / expected
    with_sector = [item for item in usable_days if item.sector]
    sector_coverage = len(with_sector) / usable if usable else 0.0
    if usable < MIN_USABLE_CONSTITUENTS:
        return _rejected(
            SessionRejectionReason.INSUFFICIENT_CONSTITUENTS,
            expected=expected,
            usable=usable,
            coverage=coverage,
            sector_coverage=sector_coverage,
            membership_mode=membership_mode,
        )
    if coverage < minimum_coverage:
        return _rejected(
            SessionRejectionReason.INSUFFICIENT_COVERAGE,
            expected=expected,
            usable=usable,
            coverage=coverage,
            sector_coverage=sector_coverage,
            membership_mode=membership_mode,
        )
    if sector_coverage < MIN_SECTOR_COVERAGE:
        return _rejected(
            SessionRejectionReason.INSUFFICIENT_SECTOR_COVERAGE,
            expected=expected,
            usable=usable,
            coverage=coverage,
            sector_coverage=sector_coverage,
            membership_mode=membership_mode,
        )
    if macro is None:
        return _rejected(
            SessionRejectionReason.MISSING_MACRO_CONTEXT,
            expected=expected,
            usable=usable,
            coverage=coverage,
            sector_coverage=sector_coverage,
            membership_mode=membership_mode,
        )

    raw_returns = [float(item.return_1d) for item in usable_days]
    returns = [_clip(value, RETURN_CAP) for value in raw_returns]
    rsi = [float(item.rsi) for item in usable_days]
    momentum = [_clip(float(item.momentum_20), MOMENTUM_CAP) for item in usable_days]
    atr = [_clip(float(item.atr_pct), ATR_CAP) for item in usable_days]
    realized_volatility = [
        min(float(item.realized_volatility_20), REALIZED_VOLATILITY_CAP)
        for item in usable_days
    ]
    relative_volume = [
        min(float(item.relative_volume_20), RELATIVE_VOLUME_CAP) for item in usable_days
    ]
    advancers = sum(value > 0 for value in raw_returns)
    decliners = sum(value < 0 for value in raw_returns)
    unchanged = usable - advancers - decliners

    sector_returns: dict[str, list[float]] = {}
    for item in with_sector:
        assert item.sector is not None and item.return_1d is not None
        sector_returns.setdefault(item.sector, []).append(
            _clip(item.return_1d, RETURN_CAP)
        )
    sector_means = [statistics.fmean(values) for values in sector_returns.values()]

    features = {
        "equal_weight_return": statistics.fmean(returns),
        "median_return": statistics.median(returns),
        "advancing_share": advancers / usable,
        "declining_share": decliners / usable,
        "unchanged_share": unchanged / usable,
        "advance_decline_ratio": min(advancers / max(decliners, 1), 10.0),
        "above_ema20_share": sum(bool(item.above_ema20) for item in usable_days) / usable,
        "above_ema50_share": sum(bool(item.above_ema50) for item in usable_days) / usable,
        "median_rsi": statistics.median(rsi),
        "rsi_dispersion": _iqr(rsi),
        "overbought_share": sum(value >= 70.0 for value in rsi) / usable,
        "oversold_share": sum(value <= 30.0 for value in rsi) / usable,
        "median_momentum_20": statistics.median(momentum),
        "momentum_dispersion": _iqr(momentum),
        "median_atr_pct": statistics.median(atr),
        "return_dispersion": _iqr(returns),
        "median_realized_volatility_20": statistics.median(realized_volatility),
        "median_relative_volume_20": statistics.median(relative_volume),
        "elevated_volume_share": sum(
            value >= ELEVATED_VOLUME_THRESHOLD for value in relative_volume
        )
        / usable,
        "sector_return_dispersion": (
            statistics.pstdev(sector_means) if len(sector_means) >= 2 else 0.0
        ),
        "sector_leadership_spread": max(sector_means) - min(sector_means),
        "usd_inr_return": _clip(macro.usd_inr_return, MACRO_RETURN_CAP),
        "crude_oil_return": _clip(macro.crude_oil_return, MACRO_RETURN_CAP),
        "gold_return": _clip(macro.gold_return, MACRO_RETURN_CAP),
        "us_10y_yield_return": _clip(macro.us_10y_yield_return, MACRO_RETURN_CAP),
    }
    if set(features) != set(FEATURE_NAMES) or not all(
        math.isfinite(value) for value in features.values()
    ):
        return _rejected(
            SessionRejectionReason.NON_FINITE_FEATURE,
            expected=expected,
            usable=usable,
            coverage=coverage,
            sector_coverage=sector_coverage,
            membership_mode=membership_mode,
        )

    flags: list[str] = []
    if membership_mode == MembershipMode.AVAILABLE_DATA_PROXY:
        flags.append("historical_membership_unknown")
    if coverage < 1.0:
        flags.append("partial_constituent_coverage")
    if sector_coverage < 1.0:
        flags.append("partial_sector_coverage")
    return SessionFeatureResult(
        features=features,
        rejection_reason=None,
        expected_constituent_count=expected,
        usable_constituent_count=usable,
        coverage_ratio=coverage,
        sector_coverage_ratio=sector_coverage,
        membership_mode=membership_mode,
        quality_flags=tuple(flags),
    )


def vector_from_features(features: dict[str, float]) -> list[float]:
    return [float(features[name]) for name in FEATURE_NAMES]


class Normalizer:
    """Median/IQR scaler fitted on raw PostgreSQL vectors and persisted per corpus."""

    def __init__(self, center: np.ndarray, scale: np.ndarray) -> None:
        if center.ndim != 1 or center.shape != scale.shape or center.size == 0:
            raise ValueError("Normalizer parameters have incompatible dimensions.")
        if not (np.isfinite(center).all() and np.isfinite(scale).all()):
            raise ValueError("Normalizer contains non-finite values.")
        if (scale < 0).any():
            raise ValueError("Normalizer scale cannot be negative.")
        self.center = center
        self.scale = scale

    # Compatibility accessors used by existing integrity checks.
    @property
    def mean(self) -> np.ndarray:
        return self.center

    @property
    def std(self) -> np.ndarray:
        return self.scale

    @classmethod
    def fit(cls, vectors: list[list[float]]) -> "Normalizer":
        arr = np.asarray(vectors, dtype="float64")
        if arr.ndim != 2 or arr.shape[0] == 0 or arr.shape[1] == 0:
            raise ValueError("Cannot fit normalizer on an empty or malformed corpus.")
        center = np.median(arr, axis=0)
        q25 = np.percentile(arr, 25, axis=0)
        q75 = np.percentile(arr, 75, axis=0)
        return cls(center=center, scale=q75 - q25)

    def transform(self, vector: list[float]) -> np.ndarray:
        values = np.asarray(vector, dtype="float64")
        if values.shape != self.center.shape:
            raise ValueError("Vector dimension does not match normalizer.")
        safe_scale = np.where(self.scale == 0, 1.0, self.scale)
        transformed = (values - self.center) / safe_scale
        transformed = np.where(self.scale == 0, 0.0, transformed)
        transformed = np.clip(transformed, -NORMALIZED_VALUE_CAP, NORMALIZED_VALUE_CAP)
        return transformed.astype("float32")

    def transform_many(self, vectors: list[list[float]]) -> np.ndarray:
        if not vectors:
            return np.empty((0, self.center.size), dtype="float32")
        return np.vstack([self.transform(vector) for vector in vectors]).astype("float32")

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            json.dump(
                {
                    "feature_version": FEATURE_VERSION,
                    "feature_names": list(FEATURE_NAMES),
                    "normalization_method": NORMALIZATION_METHOD,
                    "center": self.center.tolist(),
                    "scale": self.scale.tolist(),
                },
                handle,
            )

    @classmethod
    def load(cls, path: str) -> "Normalizer":
        with open(path) as handle:
            data = json.load(handle)
        if (
            data.get("feature_version") != FEATURE_VERSION
            or tuple(data.get("feature_names", ())) != FEATURE_NAMES
            or data.get("normalization_method") != NORMALIZATION_METHOD
        ):
            raise ValueError("Persisted normalizer feature contract is incompatible.")
        return cls(
            center=np.asarray(data["center"], dtype="float64"),
            scale=np.asarray(data["scale"], dtype="float64"),
        )
