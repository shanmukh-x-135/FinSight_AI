"""Resolve canonical NSE symbols to market-data-provider tickers."""

from __future__ import annotations

import re
from dataclasses import dataclass

_NSE_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9&.\-]*$")


class SymbolResolutionError(ValueError):
    """A candidate symbol cannot be normalized safely."""


@dataclass(frozen=True)
class SymbolOverride:
    provider_symbol: str
    canonical_exchange_symbol: str | None = None
    alias_type: str | None = None


@dataclass(frozen=True)
class ResolvedSymbol:
    exchange_symbol: str
    provider_symbol: str
    alias_exchange_symbol: str | None = None
    alias_provider_symbol: str | None = None
    alias_type: str | None = None


# The listed Tata Motors entity was renamed to TMPV in 2025. This is recorded as
# a replacement relationship; it never rewrites historical TATAMOTORS price rows.
DEFAULT_NSE_OVERRIDES: dict[str, SymbolOverride] = {
    "TATAMOTORS": SymbolOverride(
        provider_symbol="TMPV.NS",
        canonical_exchange_symbol="TMPV",
        alias_type="replacement",
    )
}


class YahooNseSymbolResolver:
    def __init__(self, overrides: dict[str, SymbolOverride] | None = None) -> None:
        self.overrides = {**DEFAULT_NSE_OVERRIDES, **(overrides or {})}

    def resolve(self, exchange_symbol: str) -> ResolvedSymbol:
        normalized = exchange_symbol.strip().upper()
        if not normalized or not _NSE_SYMBOL_PATTERN.fullmatch(normalized):
            raise SymbolResolutionError(
                f"Invalid NSE exchange symbol: {exchange_symbol!r}"
            )
        override = self.overrides.get(normalized)
        if override is None:
            return ResolvedSymbol(
                exchange_symbol=normalized,
                provider_symbol=f"{normalized}.NS",
            )
        canonical = (override.canonical_exchange_symbol or normalized).strip().upper()
        provider_symbol = override.provider_symbol.strip().upper()
        if not _NSE_SYMBOL_PATTERN.fullmatch(canonical) or not provider_symbol:
            raise SymbolResolutionError(f"Invalid explicit mapping for {normalized}")
        return ResolvedSymbol(
            exchange_symbol=canonical,
            provider_symbol=provider_symbol,
            alias_exchange_symbol=normalized if canonical != normalized else None,
            alias_provider_symbol=(
                f"{normalized}.NS" if canonical != normalized else None
            ),
            alias_type=override.alias_type,
        )
