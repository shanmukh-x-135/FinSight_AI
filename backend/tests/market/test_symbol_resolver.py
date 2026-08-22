"""NSE-to-Yahoo symbol mapping and historical replacement behavior."""

from __future__ import annotations

import pytest

from app.market.symbol_resolver import (
    SymbolOverride,
    SymbolResolutionError,
    YahooNseSymbolResolver,
)


def test_default_nse_to_yahoo_mapping() -> None:
    resolved = YahooNseSymbolResolver().resolve(" reliance ")
    assert resolved.exchange_symbol == "RELIANCE"
    assert resolved.provider_symbol == "RELIANCE.NS"
    assert resolved.alias_exchange_symbol is None


def test_explicit_provider_override() -> None:
    resolver = YahooNseSymbolResolver(
        {"SPECIAL": SymbolOverride(provider_symbol="SPECIAL-Y.NS")}
    )
    resolved = resolver.resolve("SPECIAL")
    assert resolved.exchange_symbol == "SPECIAL"
    assert resolved.provider_symbol == "SPECIAL-Y.NS"


def test_tata_motors_replacement_is_explicit_and_historical() -> None:
    resolved = YahooNseSymbolResolver().resolve("TATAMOTORS")
    assert resolved.exchange_symbol == "TMPV"
    assert resolved.provider_symbol == "TMPV.NS"
    assert resolved.alias_exchange_symbol == "TATAMOTORS"
    assert resolved.alias_provider_symbol == "TATAMOTORS.NS"
    assert resolved.alias_type == "replacement"


def test_invalid_candidate_symbol_is_rejected() -> None:
    with pytest.raises(SymbolResolutionError):
        YahooNseSymbolResolver().resolve("BAD SYMBOL")
