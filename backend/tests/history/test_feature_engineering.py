"""Reference tests for the versioned robust market-regime feature contract."""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.history.feature_engineering import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    NORMALIZATION_METHOD,
    MacroDay,
    MembershipMode,
    Normalizer,
    SessionRejectionReason,
    StockDay,
    compute_session_feature,
    vector_from_features,
)

MACRO = MacroDay(0.001, -0.002, 0.003, 0.0005)


def _stock(
    stock_id: int,
    daily_return: float,
    *,
    sector: str | None = "Technology",
    rsi: float = 55.0,
    above_ema20: bool = True,
    above_ema50: bool = True,
    momentum: float = 0.05,
    atr_pct: float = 0.02,
    realized: float = 0.015,
    relative_volume: float = 1.2,
) -> StockDay:
    return StockDay(
        stock_id=stock_id,
        sector=sector,
        return_1d=daily_return,
        rsi=rsi,
        above_ema20=above_ema20,
        above_ema50=above_ema50,
        momentum_20=momentum,
        atr_pct=atr_pct,
        realized_volatility_20=realized,
        relative_volume_20=relative_volume,
    )


def test_regime_feature_reference_covers_all_categories() -> None:
    days = [
        _stock(1, 0.02, sector="Technology", rsi=70, relative_volume=2.0),
        _stock(
            2,
            -0.01,
            sector="Financial Services",
            rsi=30,
            above_ema20=False,
            above_ema50=False,
            momentum=-0.02,
            relative_volume=0.8,
        ),
        _stock(3, 0.0, sector="Technology", rsi=50, relative_volume=1.0),
    ]

    result = compute_session_feature(
        days,
        macro=MACRO,
        expected_constituent_count=3,
        membership_mode=MembershipMode.EFFECTIVE,
    )

    assert result.accepted
    assert result.features is not None
    assert tuple(result.features) == FEATURE_NAMES
    assert len(FEATURE_NAMES) == 25
    assert result.features["equal_weight_return"] == pytest.approx(0.01 / 3)
    assert result.features["median_return"] == 0.0
    assert result.features["advancing_share"] == pytest.approx(1 / 3)
    assert result.features["declining_share"] == pytest.approx(1 / 3)
    assert result.features["unchanged_share"] == pytest.approx(1 / 3)
    assert result.features["above_ema20_share"] == pytest.approx(2 / 3)
    assert result.features["median_rsi"] == 50
    assert result.features["overbought_share"] == pytest.approx(1 / 3)
    assert result.features["oversold_share"] == pytest.approx(1 / 3)
    assert result.features["elevated_volume_share"] == pytest.approx(1 / 3)
    assert result.features["sector_leadership_spread"] > 0
    assert result.features["crude_oil_return"] == -0.002
    assert result.coverage_ratio == 1.0
    assert result.sector_coverage_ratio == 1.0
    assert result.quality_flags == ()


def test_outlier_return_is_capped_before_equal_weight_aggregation() -> None:
    result = compute_session_feature(
        [_stock(1, 0.01), _stock(2, 0.02), _stock(3, 5.0)],
        macro=MACRO,
        expected_constituent_count=3,
        membership_mode=MembershipMode.AVAILABLE_DATA_PROXY,
    )
    assert result.features is not None
    assert result.features["equal_weight_return"] == pytest.approx(
        (0.01 + 0.02 + 0.2) / 3
    )
    assert result.features["median_return"] == 0.02
    assert "historical_membership_unknown" in result.quality_flags


def test_feature_computation_is_ticker_order_independent() -> None:
    days = [_stock(1, 0.01), _stock(2, -0.02), _stock(3, 0.03)]
    forward = compute_session_feature(
        days,
        macro=MACRO,
        expected_constituent_count=3,
        membership_mode=MembershipMode.EFFECTIVE,
    )
    reverse = compute_session_feature(
        list(reversed(days)),
        macro=MACRO,
        expected_constituent_count=3,
        membership_mode=MembershipMode.EFFECTIVE,
    )
    assert forward.features == reverse.features


@pytest.mark.parametrize(
    ("days", "expected", "macro", "reason"),
    [
        (
            [_stock(1, 0.01), _stock(2, 0.02)],
            2,
            MACRO,
            SessionRejectionReason.INSUFFICIENT_CONSTITUENTS,
        ),
        (
            [_stock(1, 0.01), _stock(2, 0.02), _stock(3, 0.03)],
            4,
            MACRO,
            SessionRejectionReason.INSUFFICIENT_COVERAGE,
        ),
        (
            [_stock(1, 0.01, sector=None), _stock(2, 0.02, sector=None), _stock(3, 0.03)],
            3,
            MACRO,
            SessionRejectionReason.INSUFFICIENT_SECTOR_COVERAGE,
        ),
        (
            [_stock(1, 0.01), _stock(2, 0.02), _stock(3, 0.03)],
            3,
            None,
            SessionRejectionReason.MISSING_MACRO_CONTEXT,
        ),
    ],
)
def test_session_quality_rejections_are_explicit(
    days: list[StockDay],
    expected: int,
    macro: MacroDay | None,
    reason: SessionRejectionReason,
) -> None:
    result = compute_session_feature(
        days,
        macro=macro,
        expected_constituent_count=expected,
        membership_mode=MembershipMode.EFFECTIVE,
    )
    assert result.features is None
    assert result.rejection_reason == reason


def test_missing_core_value_is_not_imputed_as_zero() -> None:
    incomplete = _stock(1, 0.01)
    incomplete = StockDay(**{**incomplete.__dict__, "rsi": None})
    result = compute_session_feature(
        [incomplete, _stock(2, 0.02), _stock(3, 0.03)],
        macro=MACRO,
        expected_constituent_count=3,
        membership_mode=MembershipMode.EFFECTIVE,
    )
    assert result.rejection_reason == SessionRejectionReason.INSUFFICIENT_CONSTITUENTS


def test_historical_sentiment_is_not_synthetically_present() -> None:
    assert not any("sentiment" in name for name in FEATURE_NAMES)


def test_vector_projection_uses_versioned_order() -> None:
    features = {name: float(index) for index, name in enumerate(FEATURE_NAMES)}
    assert vector_from_features(features) == [float(i) for i in range(25)]


def test_robust_normalizer_uses_median_iqr_and_zeroes_constant_dimension() -> None:
    normalizer = Normalizer.fit([[0.0, 10.0], [2.0, 10.0], [100.0, 10.0]])
    assert normalizer.center.tolist() == [2.0, 10.0]
    transformed = normalizer.transform([2.0, 10.0])
    assert transformed.tolist() == [0.0, 0.0]


def test_normalizer_is_reproducible_for_historical_and_current_vectors() -> None:
    vectors = [[float(i + offset) for i in range(25)] for offset in range(5)]
    normalizer = Normalizer.fit(vectors)
    current = vectors[-1]
    assert np.array_equal(normalizer.transform(current), normalizer.transform(current))


def test_normalizer_save_load_round_trip_is_contract_versioned(tmp_path) -> None:
    vectors = [[float(i + offset) for i in range(25)] for offset in range(5)]
    normalizer = Normalizer.fit(vectors)
    path = str(tmp_path / "normalizer.json")
    normalizer.save(path)
    payload = json.loads((tmp_path / "normalizer.json").read_text())
    assert payload["feature_version"] == FEATURE_VERSION
    assert payload["normalization_method"] == NORMALIZATION_METHOD
    loaded = Normalizer.load(path)
    assert np.array_equal(normalizer.transform(vectors[2]), loaded.transform(vectors[2]))


def test_normalizer_rejects_legacy_contract(tmp_path) -> None:
    path = tmp_path / "normalizer.json"
    path.write_text(json.dumps({"feature_names": ["old"], "mean": [0], "std": [1]}))
    with pytest.raises(ValueError, match="feature contract"):
        Normalizer.load(str(path))
