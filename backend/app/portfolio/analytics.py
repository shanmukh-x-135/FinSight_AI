"""Portfolio analytics — pure functions, no DB/ORM.

Given each holding's quantity, average buy price, and live prices (assembled by
the service from Phase 2 data), compute valuation, P&L, allocation,
diversification, concentration, volatility, a health score, and a risk level.

Kept pure so it is unit-testable against hand-built portfolios with known
expected outputs. Formulas are documented in docs/portfolio.md.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from app.portfolio import constants as C
from app.portfolio.schemas import (
    HoldingAnalyticsOut,
    PortfolioAnalyticsOut,
    SectorAllocationOut,
)

UNKNOWN_SECTOR = "Unknown"


@dataclass(frozen=True)
class HoldingInput:
    """One holding plus the live data needed to value it."""

    id: int
    symbol: str
    name: str | None
    sector: str | None
    quantity: float
    avg_buy_price: float
    current_price: float | None
    previous_close: float | None = None
    atr: float | None = None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _risk_level(top_weight_pct: float) -> str:
    if top_weight_pct >= C.CONCENTRATION_HIGH_PCT:
        return "high"
    if top_weight_pct >= C.CONCENTRATION_MEDIUM_PCT:
        return "medium"
    return "low"


def _empty(portfolio_id: int, name: str) -> PortfolioAnalyticsOut:
    return PortfolioAnalyticsOut(
        portfolio_id=portfolio_id,
        name=name,
        total_value=0.0,
        total_cost=0.0,
        total_unrealized_pnl=0.0,
        total_return_percent=None,
        daily_pnl=0.0,
        daily_pnl_percent=None,
        number_of_holdings=0,
        number_of_sectors=0,
        top_holding_weight_percent=0.0,
        concentration_hhi=0.0,
        diversification_score=0.0,
        volatility_percent=None,
        health_score=0.0,
        risk_level="low",
        sector_allocation=[],
        holdings=[],
    )


def compute_portfolio_analytics(
    portfolio_id: int, name: str, holdings: list[HoldingInput]
) -> PortfolioAnalyticsOut:
    if not holdings:
        return _empty(portfolio_id, name)

    # --- Per-holding valuation (a missing price values that holding at 0) -----
    priced: list[dict] = []
    for h in holdings:
        price = h.current_price
        market_value = h.quantity * price if price is not None else 0.0
        cost_basis = h.quantity * h.avg_buy_price
        unrealized = market_value - cost_basis
        ret_pct = (unrealized / cost_basis * 100.0) if cost_basis > 0 else None
        daily = (
            h.quantity * (price - h.previous_close)
            if price is not None and h.previous_close is not None
            else 0.0
        )
        priced.append(
            {
                "h": h,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized": unrealized,
                "ret_pct": ret_pct,
                "daily": daily,
                "price": price,
            }
        )

    total_value = sum(p["market_value"] for p in priced)
    total_cost = sum(p["cost_basis"] for p in priced)
    total_unrealized = total_value - total_cost
    total_daily = sum(p["daily"] for p in priced)

    def weight(mv: float) -> float:
        return (mv / total_value * 100.0) if total_value > 0 else 0.0

    # --- Concentration / diversification -------------------------------------
    hhi = (
        sum((p["market_value"] / total_value) ** 2 for p in priced)
        if total_value > 0
        else 0.0
    )
    top_weight = max((weight(p["market_value"]) for p in priced), default=0.0)
    diversification_score = round((1.0 - hhi) * 100.0, 2)

    # --- Sector allocation (ordered by value desc) ---------------------------
    sector_values: "OrderedDict[str, float]" = OrderedDict()
    for p in priced:
        sector = p["h"].sector or UNKNOWN_SECTOR
        sector_values[sector] = sector_values.get(sector, 0.0) + p["market_value"]
    sector_allocation = [
        SectorAllocationOut(
            sector=sector, value=value, weight_percent=weight(value)
        )
        for sector, value in sorted(
            sector_values.items(), key=lambda kv: kv[1], reverse=True
        )
    ]

    # --- Volatility (market-value-weighted ATR%) -----------------------------
    vol_num = vol_den = 0.0
    for p in priced:
        h = p["h"]
        if h.atr is not None and p["price"]:
            vol_num += (h.atr / p["price"] * 100.0) * p["market_value"]
            vol_den += p["market_value"]
    volatility_pct = round(vol_num / vol_den, 4) if vol_den > 0 else None

    # --- Aggregate returns ---------------------------------------------------
    total_return_pct = (
        round(total_unrealized / total_cost * 100.0, 4) if total_cost > 0 else None
    )
    yesterday_value = total_value - total_daily
    daily_pnl_pct = (
        round(total_daily / yesterday_value * 100.0, 4) if yesterday_value > 0 else None
    )

    # --- Health score --------------------------------------------------------
    diversification_component = diversification_score
    concentration_component = 100.0 - top_weight
    performance_component = _clamp(50.0 + (total_return_pct or 0.0), 0.0, 100.0)
    health_score = round(
        C.HEALTH_DIVERSIFICATION_WEIGHT * diversification_component
        + C.HEALTH_CONCENTRATION_WEIGHT * concentration_component
        + C.HEALTH_PERFORMANCE_WEIGHT * performance_component,
        2,
    )

    holdings_out = [
        HoldingAnalyticsOut(
            id=p["h"].id,
            symbol=p["h"].symbol,
            name=p["h"].name,
            sector=p["h"].sector,
            quantity=p["h"].quantity,
            avg_buy_price=p["h"].avg_buy_price,
            current_price=p["price"],
            previous_close=p["h"].previous_close,
            market_value=round(p["market_value"], 4),
            cost_basis=round(p["cost_basis"], 4),
            unrealized_pnl=round(p["unrealized"], 4),
            return_percent=round(p["ret_pct"], 4) if p["ret_pct"] is not None else None,
            daily_pnl=round(p["daily"], 4),
            weight_percent=round(weight(p["market_value"]), 4),
        )
        for p in priced
    ]

    return PortfolioAnalyticsOut(
        portfolio_id=portfolio_id,
        name=name,
        total_value=round(total_value, 4),
        total_cost=round(total_cost, 4),
        total_unrealized_pnl=round(total_unrealized, 4),
        total_return_percent=total_return_pct,
        daily_pnl=round(total_daily, 4),
        daily_pnl_percent=daily_pnl_pct,
        number_of_holdings=len(holdings),
        number_of_sectors=len(sector_values),
        top_holding_weight_percent=round(top_weight, 4),
        concentration_hhi=round(hhi, 6),
        diversification_score=diversification_score,
        volatility_percent=volatility_pct,
        health_score=health_score,
        risk_level=_risk_level(top_weight),
        sector_allocation=sector_allocation,
        holdings=holdings_out,
    )
